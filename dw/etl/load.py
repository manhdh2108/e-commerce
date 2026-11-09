"""PLAN 5.4–5.6 — Load (B3 dimension + SCD, B4 fact + bridge, B5 đối soát, B6 refresh mart): stg.* của một batch → dw.*

    cd <repo> && .venv/bin/python -m dw.etl.load [--batch N] [--reload]

- B3, B4, B5 chạy trong MỘT transaction. Một kiểm tra đối soát (RC-01..06, SCD-01/02) không đạt → rollback toàn bộ,
  kết quả đối soát vẫn được ghi (transaction riêng) và batch → FAILED. Đạt hết → batch SUCCESS (mốc watermark mới).
- Thứ tự batch: chỉ nạp batch có watermark_from = watermark_to của batch SUCCESS gần nhất (lần đầu: INITIAL_WATERMARK),
  để không nạp lẫn batch cũ (ví dụ batch 1–3 trích từ bộ OLTP trước khi sinh lại).
- --reload: nạp lại chính batch SUCCESS mới nhất → chứng minh idempotent (T3): SCD không sinh phiên bản mới, fact không nhân đôi.

Quy tắc dimension (PLAN 5.4):
  khóa mới            → phiên bản đầu valid_from = 1900-01-01
  đổi cột SCD1        → UPDATE tại chỗ MỌI phiên bản của khóa (không thêm phiên bản)
  đổi cột SCD2        → đóng phiên bản current (valid_to = effective_date), mở phiên bản mới (valid_from = effective_date)
                        effective_date = ngày updated_at nguồn; = valid_from của current → sửa tại chỗ (cùng ngày);
                        < valid_from của current → đến muộn: cách ly DQ-23, không sửa hồi tố
  SCD3 dim_seller_tier_t3: previous_tier ← current_tier, current_tier ← tier mới, tier_changed_on
"""
import argparse
import time

import psycopg

from . import config
from .extract import log

FAR = "DATE '9999-12-31'"
FIRST = "DATE '1900-01-01'"


# ------------------------------------------------------------------------------------------------
# B3 — Dimension
# ------------------------------------------------------------------------------------------------
SCD_DIMS = [
    # (dimension, surrogate key, business key, cột SCD1, cột SCD2, SELECT nguồn từ stg (đặt tên cột như dimension))
    ("dim_product", "product_key", "product_id",
     ["sku", "product_name", "brand_name", "seller_id", "original_price", "discount_rate"],
     ["list_price", "category_key", "is_active", "unit_cost_est"],
     """SELECT s.product_id, s.sku, s.product_name, s.brand_name, s.seller_id, s.original_price, s.discount_rate,
               s.list_price, coalesce(c.category_key, 0) AS category_key, s.is_active, s.unit_cost_est,
               s.scd1_hash, s.scd2_hash, s.effective_date
        FROM stg.product s LEFT JOIN dw.dim_category c ON c.category_id = s.leaf_category_id
        WHERE s.batch_id = {b}"""),
    ("dim_seller", "seller_key", "seller_id",
     ["shop_name", "seller_name", "email_domain", "phone_masked"],
     ["province_code", "province_name", "region", "tier", "status"],
     """SELECT seller_id, shop_name, seller_name, email_domain, phone_masked, province_code, province_name, region,
               tier, status, scd1_hash, scd2_hash, effective_date
        FROM stg.seller WHERE batch_id = {b}"""),
    ("dim_customer", "customer_key", "customer_id",
     ["full_name", "phone_masked", "email_domain", "gender", "birth_year", "age_band", "registration_date"],
     ["province_code", "province_name", "region"],
     """SELECT customer_id, full_name, phone_masked, email_domain, gender, birth_year, age_band, registration_date,
               province_code, province_name, region, scd1_hash, scd2_hash, effective_date
        FROM stg.customer WHERE batch_id = {b}"""),
]


def load_category(cur, b):
    """Cây danh mục (SCD1, phân cấp) + bảng đóng (closure) dựng lại từ dim_category."""
    cur.execute(f"""
INSERT INTO dw.dim_category (category_key, category_id, category_name, is_named, parent_category_key, level, is_leaf,
                             root_category_key, path_ids, path_names, batch_id)
SELECT category_id, category_id, category_name, is_named, NULL, level, coalesce(is_leaf, true), NULL, path_ids, path_names, {b}
FROM stg.category WHERE batch_id = {b}
ON CONFLICT (category_key) DO UPDATE SET category_name = EXCLUDED.category_name, is_named = EXCLUDED.is_named,
  level = EXCLUDED.level, is_leaf = EXCLUDED.is_leaf, path_ids = EXCLUDED.path_ids, path_names = EXCLUDED.path_names,
  batch_id = EXCLUDED.batch_id
WHERE (dw.dim_category.category_name, dw.dim_category.is_named, dw.dim_category.level, dw.dim_category.is_leaf,
       dw.dim_category.path_ids, dw.dim_category.path_names)
  IS DISTINCT FROM (EXCLUDED.category_name, EXCLUDED.is_named, EXCLUDED.level, EXCLUDED.is_leaf,
                    EXCLUDED.path_ids, EXCLUDED.path_names)""")
    changed = cur.rowcount
    # cha / gốc sau khi mọi nút đã có (khóa ngoại tự tham chiếu)
    cur.execute(f"""
UPDATE dw.dim_category d SET parent_category_key = s.parent_id, root_category_key = s.root_id
FROM stg.category s WHERE s.batch_id = {b} AND d.category_key = s.category_id
  AND (d.parent_category_key, d.root_category_key) IS DISTINCT FROM (s.parent_id, s.root_id)""")
    changed += cur.rowcount
    cur.execute("DELETE FROM dw.bridge_category_hierarchy")
    cur.execute("""
INSERT INTO dw.bridge_category_hierarchy (ancestor_key, descendant_key, depth)
WITH RECURSIVE up AS (
  SELECT category_key AS descendant_key, category_key AS ancestor_key, parent_category_key AS next, 0 AS depth
  FROM dw.dim_category
  UNION ALL
  SELECT up.descendant_key, d.category_key, d.parent_category_key, up.depth + 1
  FROM up JOIN dw.dim_category d ON d.category_key = up.next WHERE up.depth < 10)
SELECT ancestor_key, descendant_key, depth FROM up""")
    closure = cur.rowcount
    n = cur.execute(f"SELECT count(*) FROM stg.category WHERE batch_id = {b}").fetchone()[0]
    return dict(read=n, written=changed, closure_rows=closure)


def load_scd(cur, b, dim, sk, bk, scd1, scd2, select):
    t0 = time.time()
    cur.execute("DROP TABLE IF EXISTS tmp_src")
    cur.execute(f"CREATE TEMP TABLE tmp_src AS {select.format(b=b)}")
    cur.execute("ANALYZE tmp_src")
    read = cur.execute("SELECT count(*) FROM tmp_src").fetchone()[0]
    attrs = scd1 + scd2
    cols = ", ".join(attrs)
    # 1) khóa mới → phiên bản đầu
    cur.execute(f"""INSERT INTO dw.{dim} ({bk}, {cols}, scd1_hash, scd2_hash, valid_from, batch_id)
        SELECT {bk}, {cols}, scd1_hash, scd2_hash, {FIRST}, {b} FROM tmp_src s
        WHERE NOT EXISTS (SELECT 1 FROM dw.{dim} d WHERE d.{bk} = s.{bk})""")
    new = cur.rowcount
    # 2) SCD1: ghi đè mọi phiên bản của khóa
    keys1 = cur.execute(f"""SELECT count(*) FROM tmp_src s JOIN dw.{dim} d ON d.{bk} = s.{bk} AND d.is_current
                            WHERE d.scd1_hash <> s.scd1_hash""").fetchone()[0]
    sets1 = ", ".join(f"{c} = s.{c}" for c in scd1)
    cur.execute(f"""UPDATE dw.{dim} d SET {sets1}, scd1_hash = s.scd1_hash FROM tmp_src s
                    WHERE d.{bk} = s.{bk} AND d.scd1_hash <> s.scd1_hash""")
    rows1 = cur.rowcount
    # 3) SCD2: phân loại thay đổi so với phiên bản current
    cur.execute("DROP TABLE IF EXISTS tmp_chg")
    cur.execute(f"""CREATE TEMP TABLE tmp_chg AS
        SELECT s.*, d.{sk} AS cur_key, d.valid_from AS cur_from FROM tmp_src s
        JOIN dw.{dim} d ON d.{bk} = s.{bk} AND d.is_current WHERE d.scd2_hash <> s.scd2_hash""")
    cur.execute(f"""INSERT INTO audit.quarantine (batch_id, source_table, source_pk, rule_code, severity, reason, payload)
        SELECT {b}, 'stg.{dim[4:]}', {bk}::text, 'DQ-23', 'ERROR',
               'Thay đổi SCD2 đến muộn (effective_date trước valid_from của phiên bản hiện hành) — không sửa hồi tố',
               to_jsonb(c) FROM tmp_chg c WHERE effective_date < cur_from""")
    late = cur.rowcount
    sets2 = ", ".join(f"{c} = c.{c}" for c in scd2)
    cur.execute(f"""UPDATE dw.{dim} d SET {sets2}, scd2_hash = c.scd2_hash, batch_id = {b}
                    FROM tmp_chg c WHERE d.{sk} = c.cur_key AND c.effective_date = c.cur_from""")
    same_day = cur.rowcount
    cur.execute(f"""UPDATE dw.{dim} d SET valid_to = c.effective_date, is_current = false
                    FROM tmp_chg c WHERE d.{sk} = c.cur_key AND c.effective_date > c.cur_from""")
    closed = cur.rowcount
    cur.execute(f"""INSERT INTO dw.{dim} ({bk}, {cols}, scd1_hash, scd2_hash, valid_from, batch_id)
        SELECT {bk}, {cols}, scd1_hash, scd2_hash, effective_date, {b} FROM tmp_chg WHERE effective_date > cur_from""")
    opened = cur.rowcount
    cur.execute(f"ANALYZE dw.{dim}")
    stats = dict(read=read, new=new, scd1_keys=keys1, scd1_rows=rows1, scd2_new_version=opened, scd2_closed=closed,
                 scd2_same_day=same_day, late_quarantined=late, sec=round(time.time() - t0, 2))
    if closed != opened:
        raise RuntimeError(f"{dim}: đóng {closed} phiên bản nhưng mở {opened}")
    return stats


def load_seller_t3(cur, b):
    """SCD3 minh họa: một dòng/seller, giữ hạng hiện tại và hạng liền trước."""
    cur.execute(f"""INSERT INTO dw.dim_seller_tier_t3 (seller_id, current_tier, previous_tier, tier_changed_on, batch_id)
        SELECT seller_id, tier, NULL, NULL, {b} FROM stg.seller WHERE batch_id = {b}
        ON CONFLICT (seller_id) DO NOTHING""")
    new = cur.rowcount
    cur.execute(f"""UPDATE dw.dim_seller_tier_t3 t SET previous_tier = t.current_tier, current_tier = s.tier,
                           tier_changed_on = s.effective_date, batch_id = {b}
                    FROM stg.seller s WHERE s.batch_id = {b} AND s.seller_id = t.seller_id AND s.tier <> t.current_tier""")
    return dict(new=new, tier_changed=cur.rowcount)


SMALL_DIMS = [
    ("dim_channel", "channel_key", """SELECT channel_id, channel_id, channel_name, channel_type, marketing_code
        FROM stg.channel WHERE batch_id = {b}""",
     ["channel_id", "channel_name", "channel_type", "marketing_code"]),
    ("dim_payment_method", "payment_method_key", """SELECT payment_method_id, payment_method_id, method_name, method_group
        FROM stg.payment_method WHERE batch_id = {b}""", ["payment_method_id", "method_name", "method_group"]),
    ("dim_warehouse", "warehouse_key", """SELECT warehouse_id, warehouse_id, warehouse_code, warehouse_name, province_code,
               province_name, region FROM stg.warehouse WHERE batch_id = {b}""",
     ["warehouse_id", "warehouse_code", "warehouse_name", "province_code", "province_name", "region"]),
    ("dim_promotion", "promotion_key", """SELECT promotion_id, promotion_id, promo_code, promo_name, promo_type, funded_by,
               apply_level, discount_type, discount_value, min_order_value, seller_id, start_ts, end_ts
        FROM stg.promotion WHERE batch_id = {b}""",
     ["promotion_id", "promo_code", "promo_name", "promo_type", "funded_by", "apply_level", "discount_type",
      "discount_value", "min_order_value", "seller_id", "start_ts", "end_ts"]),
    ("dim_campaign", "campaign_key", """SELECT s.campaign_id, s.campaign_id, s.campaign_code, s.campaign_name, s.campaign_type,
               coalesce(ch.channel_key, 0), s.budget_amount, s.start_date, s.end_date
        FROM stg.campaign s LEFT JOIN dw.dim_channel ch ON ch.channel_id = s.target_channel_id WHERE s.batch_id = {b}""",
     ["campaign_id", "campaign_code", "campaign_name", "campaign_type", "target_channel_key", "budget_amount",
      "start_date", "end_date"]),
]


def load_small(cur, b, dim, sk, select, cols):
    """Dimension nhỏ: SCD1 (upsert theo khóa; chỉ ghi khi có thay đổi)."""
    collist = ", ".join(cols)
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
    cur.execute(f"""INSERT INTO dw.{dim} ({sk}, {collist}) {select.format(b=b)}
        ON CONFLICT ({sk}) DO UPDATE SET {sets}
        WHERE ({', '.join('dw.' + dim + '.' + c for c in cols)}) IS DISTINCT FROM ({', '.join('EXCLUDED.' + c for c in cols)})""")
    written = cur.rowcount
    read = cur.execute(f"SELECT count(*) FROM ({select.format(b=b)}) x").fetchone()[0]
    return dict(read=read, written=written)


# ------------------------------------------------------------------------------------------------
# B4 — Fact + bridge
# ------------------------------------------------------------------------------------------------
PROFILE_SQL = """
WITH l AS (
  SELECT f.date_key, f.source_system, f.order_id, f.line_number, dc.customer_id
  FROM dw.fact_order_item f
  JOIN tmp_foi t USING (date_key, source_system, order_id, line_number)
  JOIN dw.dim_customer dc ON dc.customer_key = f.customer_key
  WHERE f.customer_key > 0),
p AS (  -- lịch sử mua TRƯỚC ngày giao dịch, trong 365 ngày (trạng thái trước giao dịch, PLAN 4.3)
  SELECT l.date_key, l.source_system, l.order_id, l.line_number, l.customer_id,
         coalesce(sum(h.net_revenue), 0) AS spend, count(DISTINCT h.order_id) AS freq
  FROM l
  LEFT JOIN (dw.fact_order_item h JOIN dw.dim_customer hc ON hc.customer_key = h.customer_key)
         ON hc.customer_id = l.customer_id AND h.date_key < l.date_key
        AND h.date_key >= to_char(to_date(l.date_key::text, 'YYYYMMDD') - 365, 'YYYYMMDD')::int
  GROUP BY 1, 2, 3, 4, 5),
bands AS (
  SELECT p.*, coalesce(sc.membership_tier, 'Không rõ') AS tier,
         CASE WHEN p.freq = 0 THEN 'Chưa mua' WHEN p.spend < 1000000 THEN '< 1 triệu'
              WHEN p.spend < 5000000 THEN '1–5 triệu' WHEN p.spend < 20000000 THEN '5–20 triệu' ELSE '> 20 triệu' END AS sb,
         CASE WHEN p.freq = 0 THEN '0 đơn' WHEN p.freq = 1 THEN '1 đơn' WHEN p.freq <= 3 THEN '2–3 đơn'
              WHEN p.freq <= 9 THEN '4–9 đơn' ELSE '≥ 10 đơn' END AS fb
  FROM p LEFT JOIN stg.customer sc ON sc.batch_id = {b} AND sc.customer_id = p.customer_id)
UPDATE dw.fact_order_item f SET customer_profile_key = coalesce(cp.customer_profile_key, 0)
FROM bands LEFT JOIN dw.dim_customer_profile cp
       ON cp.membership_tier = bands.tier AND cp.spend_band_12m = bands.sb AND cp.frequency_band = bands.fb
WHERE f.date_key = bands.date_key AND f.source_system = bands.source_system
  AND f.order_id = bands.order_id AND f.line_number = bands.line_number"""

FOI_COLS = ["source_system", "order_id", "line_number", "order_code", "date_key", "order_date_key", "product_key",
            "category_key", "seller_key", "customer_key", "customer_profile_key", "channel_key", "payment_method_key",
            "campaign_key", "promotion_group_key", "quantity", "list_price", "unit_price", "list_amount", "gross_amount",
            "list_discount_amount", "discount_amount", "net_revenue", "commission_rate", "commission_amount",
            "seller_net_amount", "cost_amount_est", "gross_margin_est", "is_returned", "line_count", "batch_id"]


def upsert(cur, table, cols, conflict, update_cols, extra_set=""):
    """Upsert theo khóa; trả về (số dòng mới, số dòng cập nhật). Bảng partition không cho RETURNING xmax,
    nên đếm trước số khóa đã có."""
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols) + extra_set
    keys = [k.strip() for k in conflict.split(",")]
    existing = cur.execute(f"""SELECT count(*) FROM tmp_{table} t WHERE EXISTS (SELECT 1 FROM dw.{table} f
        WHERE {' AND '.join(f'f.{k} = t.{k}' for k in keys)})""").fetchone()[0]
    cur.execute(f"""INSERT INTO dw.{table} ({', '.join(cols)}) SELECT {', '.join(cols)} FROM tmp_{table}
        ON CONFLICT ({conflict}) DO UPDATE SET {sets}""")
    return cur.rowcount - existing, existing


def load_order_item(cur, b):
    t0 = time.time()
    # Nhóm voucher của mỗi dòng hàng (đề xuất Bảng 9) → dim_promotion_group + bridge (tái dùng nhóm đã có)
    cur.execute("DROP TABLE IF EXISTS tmp_sig")
    cur.execute(f"""CREATE TEMP TABLE tmp_sig AS
        SELECT order_item_id, min(group_signature) AS group_signature, count(*) AS n
        FROM stg.order_item_promotion
        WHERE batch_id = {b} AND order_item_id IN (SELECT order_item_id FROM stg.order_item_sales WHERE batch_id = {b})
        GROUP BY order_item_id""")
    cur.execute("""INSERT INTO dw.dim_promotion_group (promotion_group_key, group_signature, promotion_count)
        SELECT (SELECT max(promotion_group_key) FROM dw.dim_promotion_group) + row_number() OVER (ORDER BY group_signature),
               group_signature, n
        FROM (SELECT DISTINCT group_signature, n FROM tmp_sig) x
        WHERE NOT EXISTS (SELECT 1 FROM dw.dim_promotion_group g WHERE g.group_signature = x.group_signature)""")
    new_groups = cur.rowcount
    cur.execute(f"""INSERT INTO dw.bridge_promotion_group (promotion_group_key, promotion_key, weighting_factor)
        SELECT DISTINCT g.promotion_group_key, coalesce(dp.promotion_key, 0), oip.weighting_factor
        FROM stg.order_item_promotion oip
        JOIN tmp_sig ts ON ts.order_item_id = oip.order_item_id
        JOIN dw.dim_promotion_group g ON g.group_signature = ts.group_signature
        LEFT JOIN dw.dim_promotion dp ON dp.promotion_id = oip.promotion_id
        WHERE oip.batch_id = {b}
        ON CONFLICT DO NOTHING""")
    bridge_rows = cur.rowcount
    # Tra khóa dimension theo thời điểm hoàn tất (SCD2: valid_from ≤ ngày < valid_to)
    cur.execute("DROP TABLE IF EXISTS tmp_fact_order_item")
    cur.execute(f"""CREATE TEMP TABLE tmp_fact_order_item AS
SELECT s.source_system, s.order_id, s.line_number, s.order_code, s.date_key, s.order_date_key,
       coalesce(dp.product_key, 0) AS product_key, coalesce(dp.category_key, 0) AS category_key,
       coalesce(ds.seller_key, 0) AS seller_key,
       CASE WHEN s.customer_id IS NULL THEN -1 ELSE coalesce(dc.customer_key, 0) END AS customer_key,
       (CASE WHEN s.customer_id IS NULL THEN -1 ELSE 0 END)::smallint AS customer_profile_key,
       coalesce(ch.channel_key, 0) AS channel_key,
       CASE WHEN s.payment_method_id IS NULL THEN 0 ELSE coalesce(pm.payment_method_key, 0) END AS payment_method_key,
       CASE WHEN s.campaign_id IS NULL THEN -1 ELSE coalesce(cm.campaign_key, 0) END AS campaign_key,
       coalesce(g.promotion_group_key, -1) AS promotion_group_key,
       s.quantity, s.list_price, s.unit_price, s.list_amount, s.gross_amount, s.list_discount_amount,
       s.discount_amount, s.net_revenue, s.commission_rate, s.commission_amount,
       (s.net_revenue - s.commission_amount)::numeric(18,2) AS seller_net_amount,
       (s.quantity * dp.unit_cost_est)::numeric(18,2) AS cost_amount_est,
       (s.net_revenue - s.quantity * dp.unit_cost_est)::numeric(18,2) AS gross_margin_est,
       s.is_returned, 1::smallint AS line_count, {b}::bigint AS batch_id
FROM stg.order_item_sales s
LEFT JOIN dw.dim_product dp ON dp.product_id = s.product_id
      AND s.completed_at::date >= dp.valid_from AND s.completed_at::date < dp.valid_to
LEFT JOIN dw.dim_seller ds ON ds.seller_id = s.seller_id
      AND s.completed_at::date >= ds.valid_from AND s.completed_at::date < ds.valid_to
LEFT JOIN dw.dim_customer dc ON dc.customer_id = s.customer_id
      AND s.completed_at::date >= dc.valid_from AND s.completed_at::date < dc.valid_to
LEFT JOIN dw.dim_channel ch ON ch.channel_id = s.channel_id
LEFT JOIN dw.dim_payment_method pm ON pm.payment_method_id = s.payment_method_id
LEFT JOIN dw.dim_campaign cm ON cm.campaign_id = s.campaign_id
LEFT JOIN tmp_sig ts ON ts.order_item_id = s.order_item_id
LEFT JOIN dw.dim_promotion_group g ON g.group_signature = ts.group_signature
WHERE s.batch_id = {b}""")
    cur.execute("ANALYZE tmp_fact_order_item")
    cur.execute("DROP TABLE IF EXISTS tmp_foi")
    cur.execute("CREATE TEMP TABLE tmp_foi AS SELECT date_key, source_system, order_id, line_number FROM tmp_fact_order_item")
    read = cur.execute("SELECT count(*) FROM tmp_fact_order_item").fetchone()[0]
    # Upsert theo khóa nghiệp vụ: chạy lại không nhân đôi (T3); dòng đổi trạng thái (Returned) cập nhật ở batch sau
    keep = {"source_system", "order_id", "line_number", "date_key", "batch_id"}
    ins, upd = upsert(cur, "fact_order_item", FOI_COLS, "date_key, source_system, order_id, line_number",
                      [c for c in FOI_COLS if c not in keep], f", updated_batch_id = {b}")
    cur.execute(PROFILE_SQL.format(b=b))
    profiled = cur.rowcount
    cur.execute("ANALYZE dw.fact_order_item")
    return dict(read=read, inserted=ins, updated=upd, profile_set=profiled, new_promotion_groups=new_groups,
                bridge_rows=bridge_rows, sec=round(time.time() - t0, 2))


INV_COLS = ["date_key", "product_key", "warehouse_key", "category_key", "quantity_on_hand", "quantity_reserved",
            "quantity_available", "qty_imported", "qty_sold", "qty_returned", "qty_adjusted", "stockout_flag",
            "inventory_value_est", "batch_id"]


def load_inventory(cur, b):
    t0 = time.time()
    cur.execute("DROP TABLE IF EXISTS tmp_fact_inventory_snapshot")
    cur.execute(f"""CREATE TEMP TABLE tmp_fact_inventory_snapshot AS
SELECT s.date_key, coalesce(dp.product_key, 0) AS product_key, coalesce(w.warehouse_key, 0) AS warehouse_key,
       coalesce(dp.category_key, 0) AS category_key, s.quantity_on_hand, s.quantity_reserved, s.quantity_available,
       s.qty_imported, s.qty_sold, s.qty_returned, s.qty_adjusted, s.stockout_flag,
       (s.quantity_on_hand * dp.unit_cost_est)::numeric(18,2) AS inventory_value_est, {b}::bigint AS batch_id
FROM stg.inventory_daily s
LEFT JOIN dw.dim_product dp ON dp.product_id = s.product_id AND s.balance_date >= dp.valid_from AND s.balance_date < dp.valid_to
LEFT JOIN dw.dim_warehouse w ON w.warehouse_id = s.warehouse_id
WHERE s.batch_id = {b}""")
    read = cur.execute("SELECT count(*) FROM tmp_fact_inventory_snapshot").fetchone()[0]
    keep = {"date_key", "product_key", "warehouse_key"}
    ins, upd = upsert(cur, "fact_inventory_snapshot", INV_COLS, "date_key, product_key, warehouse_key",
                      [c for c in INV_COLS if c not in keep])
    cur.execute("ANALYZE dw.fact_inventory_snapshot")
    return dict(read=read, inserted=ins, updated=upd, sec=round(time.time() - t0, 2))


AD_SRC = """SELECT DISTINCT ON (ad_spend_log_id) * FROM stg.ad_spend_daily
    WHERE batch_id = {b} OR batch_id IN (SELECT batch_id FROM audit.batch_log WHERE status = 'SUCCESS' AND batch_id <> {b})
    ORDER BY ad_spend_log_id, batch_id DESC"""


def load_ad_spend(cur, b):
    """Gộp tháng từ mọi dòng ngày hợp lệ (batch này + các batch SUCCESS), tính lại trọn các tháng batch chạm tới."""
    t0 = time.time()
    cur.execute("DROP TABLE IF EXISTS tmp_ad")
    cur.execute(f"CREATE TEMP TABLE tmp_ad AS {AD_SRC.format(b=b)}")
    cur.execute(f"DROP TABLE IF EXISTS tmp_ad_months")
    cur.execute(f"CREATE TEMP TABLE tmp_ad_months AS SELECT DISTINCT month_key FROM stg.ad_spend_daily WHERE batch_id = {b}")
    cur.execute("DELETE FROM dw.fact_ad_spend WHERE month_key IN (SELECT month_key FROM tmp_ad_months)")
    removed = cur.rowcount
    cur.execute(f"""INSERT INTO dw.fact_ad_spend (month_key, campaign_key, channel_key, cost_amount, impressions, clicks,
                                                  active_days, batch_id)
        SELECT a.month_key, coalesce(cm.campaign_key, 0), coalesce(ch.channel_key, 0), sum(a.cost_amount),
               sum(a.impressions), sum(a.clicks), count(DISTINCT a.log_date), {b}
        FROM tmp_ad a
        LEFT JOIN dw.dim_campaign cm ON cm.campaign_id = a.campaign_id
        LEFT JOIN dw.dim_channel ch ON ch.channel_id = a.channel_id
        WHERE a.month_key IN (SELECT month_key FROM tmp_ad_months)
        GROUP BY 1, 2, 3""")
    written = cur.rowcount
    read = cur.execute("SELECT count(*) FROM tmp_ad WHERE month_key IN (SELECT month_key FROM tmp_ad_months)").fetchone()[0]
    return dict(read=read, months=cur.execute("SELECT count(*) FROM tmp_ad_months").fetchone()[0],
                replaced=removed, written=written, sec=round(time.time() - t0, 2))


# ------------------------------------------------------------------------------------------------
# B5 — Đối soát
# ------------------------------------------------------------------------------------------------
def reconcile(cur, b):
    """Trả về danh sách (mã, mô tả, nguồn, đích, đạt)."""
    q = lambda sql: cur.execute(sql.format(b=b)).fetchone()
    out = []
    foi = """FROM stg.order_item_sales s JOIN dw.fact_order_item f ON f.date_key = s.date_key
             AND f.source_system = s.source_system AND f.order_id = s.order_id AND f.line_number = s.line_number
             WHERE s.batch_id = {b}"""
    src, tgt = q("SELECT (SELECT coalesce(sum(net_revenue), 0) FROM stg.order_item_sales WHERE batch_id = {b}), "
                 "coalesce(sum(f.net_revenue), 0) " + foi)
    out.append(("RC-01", "Σ net_amount dòng hợp lệ (stg) = Σ net_revenue fact", src, tgt, src == tgt))
    src, tgt = q("SELECT (SELECT count(*) FROM stg.order_item_sales WHERE batch_id = {b}), count(*) " + foi)
    out.append(("RC-02", "Số dòng hợp lệ (stg) = số dòng fact mới/cập nhật", src, tgt, src == tgt))
    bad = q("""SELECT count(*) FROM (SELECT promotion_group_key FROM dw.bridge_promotion_group GROUP BY 1
               HAVING abs(sum(weighting_factor) - 1) > 0.000001) x""")[0]
    out.append(("RC-03a", "Số nhóm voucher có Σ weighting_factor ≠ 1", 0, bad, bad == 0))
    src, tgt = q("""SELECT (SELECT coalesce(sum(oip.applied_discount_amount), 0) FROM stg.order_item_promotion oip
                     WHERE oip.batch_id = {b} AND oip.order_item_id IN (SELECT order_item_id FROM stg.order_item_sales WHERE batch_id = {b})),
                    coalesce(sum(f.discount_amount * bw.weighting_factor), 0)
             FROM stg.order_item_sales s JOIN dw.fact_order_item f ON f.date_key = s.date_key
               AND f.source_system = s.source_system AND f.order_id = s.order_id AND f.line_number = s.line_number
             JOIN dw.bridge_promotion_group bw ON bw.promotion_group_key = f.promotion_group_key
             WHERE s.batch_id = {b}""")
    out.append(("RC-03b", "Σ applied_discount nguồn = Σ discount_amount × weight (qua bridge)", src, round(tgt, 2),
                abs(src - tgt) <= 0.01))
    src, tgt = q("""SELECT (SELECT count(*) FROM stg.inventory_daily WHERE batch_id = {b}), count(f.*)
             FROM stg.inventory_daily s
             JOIN dw.dim_product dp ON dp.product_id = s.product_id AND s.balance_date >= dp.valid_from AND s.balance_date < dp.valid_to
             JOIN dw.fact_inventory_snapshot f ON f.date_key = s.date_key AND f.product_key = dp.product_key
              AND f.warehouse_key = s.warehouse_id AND f.quantity_on_hand = s.quantity_on_hand
              AND f.quantity_reserved = s.quantity_reserved AND f.qty_sold = s.qty_sold AND f.qty_imported = s.qty_imported
             WHERE s.batch_id = {b}""")
    out.append(("RC-04", "Dòng tồn kho fact khớp từng (sku, kho, ngày) với stg", src, tgt, src == tgt))
    src, tgt = q(f"""SELECT (SELECT coalesce(sum(cost_amount), 0) FROM ({AD_SRC}) a
                              WHERE month_key IN (SELECT DISTINCT month_key FROM stg.ad_spend_daily WHERE batch_id = {{b}})),
                             (SELECT coalesce(sum(cost_amount), 0) FROM dw.fact_ad_spend
                              WHERE month_key IN (SELECT DISTINCT month_key FROM stg.ad_spend_daily WHERE batch_id = {{b}}))""")
    out.append(("RC-05", "Σ chi phí QC (stg ngày, các tháng của batch) = Σ fact_ad_spend", src, tgt, src == tgt))
    orphan = q("""SELECT
        (SELECT count(*) FROM dw.fact_order_item f WHERE NOT EXISTS (SELECT 1 FROM dw.dim_product d WHERE d.product_key = f.product_key)
            OR NOT EXISTS (SELECT 1 FROM dw.dim_customer d WHERE d.customer_key = f.customer_key)
            OR NOT EXISTS (SELECT 1 FROM dw.dim_seller d WHERE d.seller_key = f.seller_key)
            OR NOT EXISTS (SELECT 1 FROM dw.dim_promotion_group d WHERE d.promotion_group_key = f.promotion_group_key))
      + (SELECT count(*) FROM dw.fact_inventory_snapshot f WHERE NOT EXISTS (SELECT 1 FROM dw.dim_product d WHERE d.product_key = f.product_key))""")[0]
    out.append(("RC-06", "Số dòng fact có khóa ngoại mồ côi", 0, orphan, orphan == 0))
    unknown = q("""SELECT count(*) FROM dw.fact_order_item WHERE (batch_id = {b} OR updated_batch_id = {b}) AND
                   0 IN (product_key, seller_key, customer_key, channel_key, payment_method_key, campaign_key, category_key)""")[0]
    out.append(("RC-06i", "Thông tin: số dòng fact của batch dùng khóa 0 = chưa xác định (không chặn)", None, unknown, True))
    # Kiểm tra SCD sau nạp (T4)
    for dim, bk in (("dim_product", "product_id"), ("dim_seller", "seller_id"), ("dim_customer", "customer_id")):
        overlap = q(f"""SELECT count(*) FROM dw.{dim} a JOIN dw.{dim} c ON c.{bk} = a.{bk} AND c.ctid <> a.ctid
                        AND a.valid_from < c.valid_to AND c.valid_from < a.valid_to""")[0]
        cur_bad = q(f"""SELECT count(*) FROM (SELECT {bk} FROM dw.{dim} GROUP BY 1
                        HAVING count(*) FILTER (WHERE is_current) <> 1) x""")[0]
        out.append((f"SCD-01 {dim}", f"{dim}: số cặp phiên bản chồng lấn khoảng hiệu lực", 0, overlap, overlap == 0))
        out.append((f"SCD-02 {dim}", f"{dim}: số khóa nghiệp vụ không có đúng 1 phiên bản current", 0, cur_bad, cur_bad == 0))
    return out


# ------------------------------------------------------------------------------------------------
def run_load(cur, b):
    """B3 + B4 + B5 trên một cursor (gọi trong transaction). Trả về (stats, reconciliation)."""
    stats = {}
    t0 = time.time()
    stats["dim_category"] = load_category(cur, b)
    for dim, sk, select, cols in SMALL_DIMS:
        stats[dim] = load_small(cur, b, dim, sk, select, cols)
    for dim, sk, bk, scd1, scd2, select in SCD_DIMS:
        stats[dim] = load_scd(cur, b, dim, sk, bk, scd1, scd2, select)
    stats["dim_seller_tier_t3"] = load_seller_t3(cur, b)
    log(event="dimensions_loaded", batch_id=b, sec=round(time.time() - t0, 2),
        **{k: v for k, v in stats.items()})
    stats["fact_order_item"] = load_order_item(cur, b)
    log(event="fact_loaded", table="fact_order_item", **stats["fact_order_item"])
    stats["fact_inventory_snapshot"] = load_inventory(cur, b)
    log(event="fact_loaded", table="fact_inventory_snapshot", **stats["fact_inventory_snapshot"])
    stats["fact_ad_spend"] = load_ad_spend(cur, b)
    log(event="fact_loaded", table="fact_ad_spend", **stats["fact_ad_spend"])
    for table, s in stats.items():
        written = s.get("written", s.get("inserted", 0) + s.get("updated", 0) + s.get("new", 0)
                        + s.get("scd2_new_version", 0) + s.get("scd1_rows", 0) + s.get("tier_changed", 0))
        cur.execute("""INSERT INTO audit.batch_table_log (batch_id, stage, table_name, rows_read, rows_valid, rows_quarantined, rows_written)
                       VALUES (%s, 'LOAD', %s, %s, %s, %s, %s)""",
                    (b, table, s.get("read"), s.get("read"), s.get("late_quarantined", 0), written))
    return stats, reconcile(cur, b)


def write_reconciliation(cur, b, rc):
    cur.execute("DELETE FROM audit.reconciliation WHERE batch_id = %s AND check_code <> 'RC-07'", (b,))
    for code, desc, src, tgt, ok in rc:
        cur.execute("""INSERT INTO audit.reconciliation (batch_id, check_code, description, source_value, target_value, passed)
                       VALUES (%s, %s, %s, %s, %s, %s)""", (b, code, desc, src, tgt, ok))


def choose_batch(cur, batch, reload):
    last_ok = cur.execute("""SELECT batch_id, watermark_to FROM audit.batch_log WHERE status = 'SUCCESS'
                             ORDER BY watermark_to DESC, batch_id DESC LIMIT 1""").fetchone()
    if reload:
        if not last_ok:
            raise SystemExit("--reload: chưa có batch SUCCESS nào")
        if batch and batch != last_ok[0]:
            raise SystemExit(f"--reload chỉ áp dụng cho batch SUCCESS mới nhất ({last_ok[0]})")
        return last_ok[0]
    expected_from = last_ok[1] if last_ok else __import__("datetime").date.fromisoformat(config.INITIAL_WATERMARK)
    if batch:
        row = cur.execute("SELECT status, watermark_from FROM audit.batch_log WHERE batch_id = %s", (batch,)).fetchone()
        if not row:
            raise SystemExit(f"Không có batch {batch}")
        status, wfrom = row
        if status not in ("TRANSFORMED",) and not (status == "FAILED" and stage_done(cur, batch)):
            raise SystemExit(f"Batch {batch} đang ở trạng thái {status}; cần TRANSFORMED")
        if wfrom != expected_from:
            raise SystemExit(f"Batch {batch} có watermark_from {wfrom} ≠ mốc SUCCESS gần nhất {expected_from} "
                             "(batch cũ/không liên tục — không nạp)")
        return batch
    row = cur.execute("""SELECT batch_id FROM audit.batch_log WHERE status = 'TRANSFORMED' AND watermark_from = %s
                         ORDER BY batch_id DESC LIMIT 1""", (expected_from,)).fetchone()
    if not row:
        raise SystemExit(f"Không có batch TRANSFORMED nối tiếp mốc {expected_from}")
    return row[0]


def stage_done(cur, b):
    """Batch FAILED ở bước Load (Transform đã xong) thì được nạp lại khi chỉ định --batch."""
    return cur.execute("""SELECT EXISTS (SELECT 1 FROM audit.batch_table_log WHERE batch_id = %s AND stage = 'TRANSFORM')""",
                       (b,)).fetchone()[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch", type=int, help="batch TRANSFORMED cần nạp (mặc định: batch nối tiếp mốc SUCCESS)")
    ap.add_argument("--reload", action="store_true", help="nạp lại batch SUCCESS mới nhất (kiểm thử idempotent T3)")
    a = ap.parse_args(argv)
    with psycopg.connect(config.TARGET_URL) as con:
        b = choose_batch(con.cursor(), a.batch, a.reload)
    log(event="load_start", batch_id=b, reload=a.reload)
    t0 = time.time()
    rc = None
    try:
        with psycopg.connect(config.TARGET_URL) as con:
            cur = con.cursor()
            cur.execute("DELETE FROM audit.batch_table_log WHERE batch_id = %s AND stage = 'LOAD'", (b,))
            cur.execute("DELETE FROM audit.quarantine WHERE batch_id = %s AND rule_code = 'DQ-23'", (b,))
            stats, rc = run_load(cur, b)
            for code, desc, src, tgt, ok in rc:
                log(event="reconciliation", check=code, source=src, target=tgt, passed=ok)
            failed = [c for c, _, _, _, ok in rc if not ok]
            if failed:
                raise RuntimeError("Đối soát không đạt: " + ", ".join(failed))
            write_reconciliation(cur, b, rc)
            # giữ thời gian Extract/Transform, bỏ thông báo lỗi của lần Load trước (nếu có)
            msg = cur.execute("""SELECT concat_ws('; ', substring(message from 'extract [0-9.]+ s'),
                                                 substring(message from 'transform [0-9.]+ s'))
                                 FROM audit.batch_log WHERE batch_id = %s""", (b,)).fetchone()[0] or ""
            msg = (msg + "; " if msg else "") + f"load {round(time.time() - t0, 1)} s" + (" (reload)" if a.reload else "")
            cur.execute("UPDATE audit.batch_log SET status = 'SUCCESS', finished_at = now(), message = %s WHERE batch_id = %s",
                        (msg, b))
            con.commit()
    except Exception as exc:
        with psycopg.connect(config.TARGET_URL) as con:
            if rc:
                write_reconciliation(con.cursor(), b, rc)
            if not a.reload:  # nạp lại thất bại thì rollback, batch SUCCESS giữ nguyên
                con.execute("UPDATE audit.batch_log SET status = 'FAILED', finished_at = now(), message = %s WHERE batch_id = %s",
                            (f"LOAD: {exc}"[:2000], b))
        log(event="load_failed", batch_id=b, error=str(exc))
        raise
    log(event="batch_success", batch_id=b, sec=round(time.time() - t0, 1))
    refresh_mart(b)
    return b


def refresh_mart(b):
    """B6 (PLAN 5.1): refresh MV của mart CHỈ sau khi batch SUCCESS. Lỗi refresh không hủy batch:
    mart giữ bản cũ, mart.v_data_freshness.mart_stale = true → dashboard hiển thị "dữ liệu cũ"."""
    t0 = time.time()
    try:
        with psycopg.connect(config.TARGET_URL) as con:
            rows = con.execute("SELECT mv_name, row_count, seconds FROM mart.refresh_all(%s)", (b,)).fetchall()
        log(event="mart_refreshed", batch_id=b, sec=round(time.time() - t0, 1),
            mvs={name: int(n) for name, n, _ in rows})
    except Exception as exc:  # noqa: BLE001 — mart cũ vẫn dùng được
        log(event="mart_refresh_failed", batch_id=b, error=str(exc))


if __name__ == "__main__":
    main()
