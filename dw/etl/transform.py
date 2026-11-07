"""PLAN 5.3 — Transform (B2): raw.* của một batch → stg.*, kiểm tra DQ, cách ly lỗi.

    cd <repo> && .venv/bin/python -m dw.etl.transform [--batch N] [--max-quarantine-ratio 0.05]

Mỗi thực thể chạy qua cùng một bộ máy (T1–T10 trong PLAN 5.3.1):
  T2–T5  câu SELECT chuẩn hóa (ép kiểu, ánh xạ map_*, tích hợp khóa, cột dẫn xuất) → bảng tạm
  T6     các quy tắc DQ (biểu thức boolean trên bảng tạm), đếm vào audit.dq_result
  T7     dòng vi phạm ERROR → audit.quarantine (kèm rule_code, reason, payload) và bị loại;
         WARN → vẫn vào stg với dq_status = 'WARN' (cũng ghi quarantine severity WARN để theo dõi)
  T8     khử trùng lặp theo khóa nghiệp vụ (giữ bản mới nhất) — bản bị loại ghi WARN DQ-07
  T10    kiểm đếm: đọc = VALID + WARN + cách ly + trùng; ghi audit.batch_table_log (TRANSFORM)
Kiểm tra mức bảng: DQ-13/14 (cây danh mục), DQ-18 (tồn kho liên tục với sổ cái).
Toàn bộ chạy trong MỘT transaction: lỗi → rollback, batch FAILED. Chạy lại cùng batch: xóa stg/audit
TRANSFORM của batch rồi làm lại (stg không bất biến; raw thì bất biến).
"""
import argparse
import csv
import datetime as dt
import json
import time

import psycopg

from . import config
from .extract import log

MAPPINGS = config.ROOT / "dw/etl/mappings"


# ------------------------------------------------------------------------------------------------
# Đặc tả từng thực thể. {b} = batch_id; {T} = mốc cuối cửa sổ (không gồm) dạng timestamp.
# rules: (mã, mức, biểu thức đúng khi VI PHẠM, lý do)
# ------------------------------------------------------------------------------------------------
ENTITIES = []


def entity(name, source_table, key, order, select, rules, pk_expr=None):
    ENTITIES.append(dict(name=name, source_table=source_table, key=key, order=order, select=select,
                         rules=rules, pk_expr=pk_expr or key))


# ---------- Danh mục (IR-04): path Tiki bỏ '1/2', cắt tại danh mục OLTP ----------
entity("category", "tiki_product_category + categories", "category_id", "category_id", """
WITH prod AS (
  SELECT p.id, p.category_id AS cat, string_to_array(t.primary_category_path, '/')::bigint[] AS a, t.product_category_name AS pname
  FROM raw.products p JOIN raw.tiki_product_category t ON t.product_id = p.id AND t.batch_id = p.batch_id
  WHERE p.batch_id = {b}),
cut AS (SELECT id, cat, pname, array_position(a, cat) = array_length(a, 1) AS cat_is_last,
                   a[3:array_position(a, cat)] AS a FROM prod WHERE array_position(a, cat) >= 3),
edge AS (SELECT n.node, n.pos, CASE WHEN n.pos > 1 THEN cut.a[n.pos - 1] END AS parent, cut.cat, cut.pname, cut.cat_is_last
         FROM cut, unnest(cut.a) WITH ORDINALITY AS n(node, pos)),
-- danh mục OLTP không xuất hiện trong path (dự phòng): cạnh gốc → lá từ bảng categories
fallback AS (SELECT c.id AS node, 2 AS pos, c.parent_id AS parent FROM raw.categories c
             WHERE c.batch_id = {b} AND c.parent_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM edge e WHERE e.node = c.id)
             UNION ALL SELECT c.id, 1, NULL FROM raw.categories c
             WHERE c.batch_id = {b} AND c.parent_id IS NULL AND NOT EXISTS (SELECT 1 FROM edge e WHERE e.node = c.id)),
allx AS (SELECT node, pos, parent FROM edge UNION ALL SELECT node, pos, parent FROM fallback),
nodes AS (SELECT node AS category_id, min(pos) AS level, min(parent) AS parent_id, count(DISTINCT parent) AS parent_count
          FROM allx GROUP BY node),
-- tên trong crawler là tên NÚT CUỐI của path: chỉ dùng khi nút cuối chính là danh mục OLTP
leafname AS (SELECT DISTINCT ON (cat) cat, pname FROM edge WHERE node = cat AND cat_is_last AND pname IS NOT NULL ORDER BY cat, pname)
SELECT n.category_id, n.parent_id, n.level::smallint AS level,
       coalesce(c.category_name, ln.pname, 'Danh mục ' || n.category_id) AS category_name,
       (c.category_name IS NOT NULL OR ln.pname IS NOT NULL) AS is_named, n.parent_count::int AS parent_count,
       NULL::boolean AS is_leaf, NULL::bigint AS root_id, NULL::text AS path_ids, NULL::text AS path_names
FROM nodes n
LEFT JOIN raw.categories c ON c.id = n.category_id AND c.batch_id = {b}
LEFT JOIN leafname ln ON ln.cat = n.category_id""", [
    ("DQ-01", "ERROR", "category_id IS NULL", "Thiếu mã danh mục"),
    ("DQ-13", "ERROR", "parent_count > 1", "Một nút có nhiều cha trong cây danh mục"),
    ("DQ-12", "WARN", "NOT is_named", "Nút danh mục trung gian chưa có tên — dùng tên tạm"),
])

# ---------- Sản phẩm ----------
entity("product", "products", "product_id", "updated_at DESC NULLS LAST", """
SELECT p.id AS product_id, trim(p.sku) AS sku, regexp_replace(trim(p.name), '\\s+', ' ', 'g') AS product_name,
       coalesce(nullif(trim(p.brand_name), ''), 'Không rõ thương hiệu') AS brand_name,
       (p.brand_name IS NULL OR trim(p.brand_name) = '') AS brand_missing,
       p.category_id AS leaf_category_id, sc.root_id AS root_category_id, p.seller_id,
       p.price::numeric(18,2) AS list_price, coalesce(p.original_price, p.price)::numeric(18,2) AS original_price,
       (coalesce(p.discount_rate, 0) / 100)::numeric(6,4) AS discount_rate,
       coalesce(cr.cost_ratio, cr0.cost_ratio) AS cost_ratio,
       (round(p.price * coalesce(cr.cost_ratio, cr0.cost_ratio) / 1000) * 1000)::numeric(18,2) AS unit_cost_est,
       coalesce(p.is_active, false) AS is_active, coalesce(p.updated_at, p.created_at) AS updated_at,
       coalesce(p.updated_at, p.created_at)::date AS effective_date,
       md5(concat_ws('|', regexp_replace(trim(p.name), '\\s+', ' ', 'g'), coalesce(nullif(trim(p.brand_name), ''), 'Không rõ thương hiệu'),
                     coalesce(p.original_price, p.price)::numeric(18,2), (coalesce(p.discount_rate, 0) / 100)::numeric(6,4))) AS scd1_hash,
       md5(concat_ws('|', p.price::numeric(18,2), p.category_id, coalesce(p.is_active, false))) AS scd2_hash
FROM raw.products p
LEFT JOIN stg.category sc ON sc.batch_id = {b} AND sc.category_id = p.category_id
LEFT JOIN stg.map_cost_ratio cr ON cr.root_category_id = sc.root_id
CROSS JOIN (SELECT cost_ratio FROM stg.map_cost_ratio WHERE root_category_id = 0) cr0
WHERE p.batch_id = {b}""", [
    ("DQ-01", "ERROR", "product_id IS NULL OR sku IS NULL OR sku = '' OR seller_id IS NULL", "Thiếu khóa sản phẩm / SKU / seller"),
    ("DQ-09", "ERROR", "list_price IS NULL OR list_price <= 0", "Giá niêm yết không dương"),
    ("DQ-04", "ERROR", "root_category_id IS NULL", "Danh mục sản phẩm không có trong cây danh mục"),
    ("DQ-10", "WARN", "unit_cost_est > list_price * 0.98", "Giá vốn ước tính vượt 98% giá bán (R-PRD-05)"),
    ("DQ-21", "WARN", "brand_missing", "Thiếu thương hiệu — dùng giá trị mặc định"),
])

# ---------- Người bán ----------
entity("seller", "sellers", "seller_id", "updated_at DESC NULLS LAST", """
SELECT s.id AS seller_id, trim(s.shop_name) AS shop_name, trim(s.seller_name) AS seller_name,
       nullif(split_part(s.email, '@', 2), '') AS email_domain,
       CASE WHEN s.phone IS NOT NULL THEN left(s.phone, 3) || '****' || right(s.phone, 3) END AS phone_masked,
       s.phone AS phone_raw, s.email AS email_raw,
       mp.province_code, mp.province_name, mp.region, s.province AS province_raw, s.tier, s.status,
       coalesce(s.updated_at, s.created_at) AS updated_at, coalesce(s.updated_at, s.created_at)::date AS effective_date,
       md5(concat_ws('|', trim(s.shop_name), trim(s.seller_name), s.email, s.phone)) AS scd1_hash,
       md5(concat_ws('|', s.tier, mp.province_code, s.status)) AS scd2_hash
FROM raw.sellers s LEFT JOIN stg.map_province mp ON mp.source_name = trim(s.province)
WHERE s.batch_id = {b}""", [
    ("DQ-01", "ERROR", "seller_id IS NULL OR shop_name IS NULL", "Thiếu khóa / tên shop"),
    ("DQ-04", "ERROR", "province_code IS NULL OR tier NOT IN ('Mall','Preferred','Normal') OR status IS NULL",
     "Tỉnh không ánh xạ được (map_province) hoặc hạng/trạng thái ngoài danh mục"),
    ("DQ-08", "WARN", "phone_raw !~ '^0[0-9]{{9}}$' OR email_raw !~ '^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$'", "SĐT/email sai định dạng"),
])

# ---------- Khách hàng ----------
entity("customer", "customers", "customer_id", "updated_at DESC NULLS LAST", """
SELECT c.id AS customer_id, regexp_replace(trim(c.full_name), '\\s+', ' ', 'g') AS full_name,
       CASE WHEN c.phone_number IS NOT NULL THEN left(c.phone_number, 3) || '****' || right(c.phone_number, 3) END AS phone_masked,
       nullif(split_part(c.email, '@', 2), '') AS email_domain, c.phone_number AS phone_raw, c.email AS email_raw,
       coalesce(mg.gender, 'U') AS gender, extract(year FROM c.date_of_birth)::smallint AS birth_year,
       CASE WHEN c.date_of_birth IS NULL THEN 'Không rõ'
            WHEN date_part('year', age(DATE '2026-01-01', c.date_of_birth)) < 18 THEN 'Dưới 18'
            WHEN date_part('year', age(DATE '2026-01-01', c.date_of_birth)) < 25 THEN '18–24'
            WHEN date_part('year', age(DATE '2026-01-01', c.date_of_birth)) < 35 THEN '25–34'
            WHEN date_part('year', age(DATE '2026-01-01', c.date_of_birth)) < 45 THEN '35–44' ELSE '45+' END AS age_band,
       mp.province_code, mp.province_name, mp.region, c.membership_tier,
       c.registration_date::date AS registration_date, coalesce(c.updated_at, c.registration_date) AS updated_at,
       coalesce(c.updated_at, c.registration_date)::date AS effective_date,
       md5(concat_ws('|', trim(c.full_name), c.phone_number, c.email)) AS scd1_hash,
       md5(concat_ws('|', mp.province_code)) AS scd2_hash
FROM raw.customers c
LEFT JOIN stg.map_province mp ON mp.source_name = trim(c.province)
LEFT JOIN stg.map_gender mg ON mg.source_value = c.gender
WHERE c.batch_id = {b}""", [
    ("DQ-01", "ERROR", "customer_id IS NULL OR full_name IS NULL OR effective_date IS NULL", "Thiếu khóa / tên / ngày"),
    ("DQ-04", "ERROR", "province_code IS NULL OR membership_tier NOT IN ('Member','Silver','Gold','Platinum')",
     "Tỉnh không ánh xạ được hoặc hạng thành viên ngoài danh mục"),
    ("DQ-08", "WARN", "phone_raw !~ '^0[0-9]{{9}}$' OR email_raw !~ '^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$'", "SĐT/email sai định dạng"),
])

# ---------- Dimension nhỏ ----------
entity("channel", "channels", "channel_id", "channel_id", """
SELECT c.id AS channel_id, c.channel_name, c.channel_type,
       (SELECT min(m.source_code) FROM stg.map_channel m WHERE m.channel_id = c.id AND m.note LIKE 'mã engine%') AS marketing_code
FROM raw.channels c WHERE c.batch_id = {b}""", [
    ("DQ-04", "ERROR", "marketing_code IS NULL", "Kênh không có mã marketing trong map_channel"),
])
entity("payment_method", "payment_methods", "payment_method_id", "payment_method_id", """
SELECT id AS payment_method_id, method_name, method_group FROM raw.payment_methods WHERE batch_id = {b}""", [
    ("DQ-04", "ERROR", "method_group NOT IN ('COD','E-Wallet','Card','Bank Transfer')", "Nhóm phương thức ngoài danh mục"),
])
entity("warehouse", "warehouses", "warehouse_id", "warehouse_id", """
SELECT w.id AS warehouse_id, w.warehouse_code, w.warehouse_name, mp.province_code, mp.province_name, mp.region
FROM raw.warehouses w LEFT JOIN stg.map_province mp ON mp.source_name = trim(w.province) WHERE w.batch_id = {b}""", [
    ("DQ-04", "ERROR", "province_code IS NULL", "Tỉnh của kho không ánh xạ được"),
])
entity("promotion", "promotions", "promotion_id", "promotion_id", """
SELECT id AS promotion_id, promo_code, promo_name, promo_type,
       CASE WHEN seller_id IS NOT NULL THEN 'Seller' ELSE 'Platform' END AS funded_by, apply_level,
       discount_type, discount_value::numeric(18,2) AS discount_value, min_order_value::numeric(18,2) AS min_order_value,
       seller_id, start_date AS start_ts, end_date AS end_ts
FROM raw.promotions WHERE batch_id = {b}""", [
    ("DQ-01", "ERROR", "promotion_id IS NULL OR promo_code IS NULL", "Thiếu khóa voucher"),
])
entity("campaign", "marketing_campaigns", "campaign_id", "campaign_id", """
SELECT c.id AS campaign_id, c.campaign_code, c.campaign_name, c.campaign_type, c.target_channel_code,
       m.channel_id AS target_channel_id, c.budget_amount::numeric(18,2) AS budget_amount, c.start_date, c.end_date
FROM raw.marketing_campaigns c LEFT JOIN stg.map_channel m ON m.source_code = c.target_channel_code
WHERE c.batch_id = {b}""", [
    ("DQ-04", "ERROR", "target_channel_id IS NULL", "Mã kênh chiến dịch không có trong map_channel (IR-03)"),
])

# ---------- Bridge khuyến mãi (trước order_item_sales để DQ-16 dùng chung) ----------
entity("order_item_promotion", "order_item_promotions", "order_item_id, promotion_id", "order_item_id",
       """
WITH x AS (
  SELECT oip.order_item_id, oip.promotion_id, oip.applied_discount_amount::numeric(18,2) AS applied_discount_amount,
         oip.funded_by, oi.discount_amount::numeric(18,2) AS line_discount
  FROM raw.order_item_promotions oip
  JOIN raw.order_items oi ON oi.id = oip.order_item_id AND oi.batch_id = oip.batch_id
  WHERE oip.batch_id = {b}),
s AS (SELECT order_item_id, sum(applied_discount_amount) AS total_applied FROM x GROUP BY 1),
w AS (SELECT x.*, s.total_applied,
             CASE WHEN s.total_applied > 0 THEN round(x.applied_discount_amount / s.total_applied, 6) END AS weighting_factor
      FROM x JOIN s USING (order_item_id)),
sig AS (SELECT order_item_id, string_agg(promotion_id || ':' || weighting_factor, ',' ORDER BY promotion_id) AS group_signature
        FROM w GROUP BY 1)
SELECT w.order_item_id, w.promotion_id, w.applied_discount_amount, w.funded_by, w.weighting_factor, sig.group_signature,
       w.total_applied, w.line_discount
FROM w JOIN sig USING (order_item_id)""", [
    ("DQ-01", "ERROR", "order_item_id IS NULL OR promotion_id IS NULL", "Thiếu khóa"),
    ("DQ-16", "ERROR", "abs(total_applied - line_discount) > 0.01 OR weighting_factor IS NULL",
     "Tổng giảm giá voucher ≠ discount_amount của dòng hàng"),
], pk_expr="order_item_id || '/' || promotion_id")

# ---------- Dòng hàng bán (nguồn Fact_Order_Item) ----------
entity("order_item_sales", "order_items + orders + payments", "order_id, line_number", "order_id", """
WITH pay AS (
  SELECT DISTINCT ON (order_id) order_id, payment_method_id
  FROM raw.payments WHERE batch_id = {b}
  ORDER BY order_id, (payment_status = 'Success') DESC, transaction_time DESC, id DESC),
promo AS (SELECT order_item_id, sum(applied_discount_amount) AS total_applied
          FROM raw.order_item_promotions WHERE batch_id = {b} GROUP BY 1)
SELECT '{src}'::text AS source_system, o.id AS order_id, oi.line_number, oi.id AS order_item_id, o.order_code,
       o.completed_at, to_char(o.completed_at, 'YYYYMMDD')::int AS date_key,
       o.created_at AS ordered_at, to_char(o.created_at, 'YYYYMMDD')::int AS order_date_key,
       oi.product_id, o.seller_id, o.customer_id, o.channel_id, o.campaign_id, pay.payment_method_id,
       oi.quantity, oi.list_price::numeric(18,2) AS list_price, oi.unit_price::numeric(18,2) AS unit_price,
       (oi.quantity * oi.list_price)::numeric(18,2) AS list_amount,
       (oi.quantity * oi.unit_price)::numeric(18,2) AS gross_amount,
       (oi.quantity * (oi.list_price - oi.unit_price))::numeric(18,2) AS list_discount_amount,
       oi.discount_amount::numeric(18,2) AS discount_amount, oi.net_amount::numeric(18,2) AS net_revenue,
       oi.commission_rate::numeric(6,4) AS commission_rate,
       round(oi.net_amount * oi.commission_rate, 2)::numeric(18,2) AS commission_amount,
       oi.item_status, (oi.item_status = 'Returned') AS is_returned, promo.total_applied
FROM raw.order_items oi
JOIN raw.orders o ON o.id = oi.order_id AND o.batch_id = oi.batch_id
LEFT JOIN pay ON pay.order_id = o.id
LEFT JOIN promo ON promo.order_item_id = oi.id
WHERE oi.batch_id = {b} AND o.order_status = 'Completed' AND oi.item_status IN ('Fulfilled', 'Returned')
  AND (o.completed_at IS NULL OR o.completed_at < {T})   -- hoàn tất trong ngày chưa chốt: để batch sau""", [
    ("DQ-05", "ERROR", "completed_at IS NULL", "Đơn Completed thiếu completed_at"),
    ("DQ-01", "ERROR", "product_id IS NULL OR seller_id IS NULL OR channel_id IS NULL", "Thiếu khóa sản phẩm/seller/kênh"),
    ("DQ-02", "ERROR", "quantity <= 0 OR unit_price < 0 OR discount_amount < 0 OR net_revenue < 0", "Số lượng/tiền âm hoặc bằng 0"),
    ("DQ-03", "ERROR", "abs(net_revenue - (gross_amount - discount_amount)) > 0.01", "net ≠ quantity × unit_price − discount"),
    ("DQ-04", "ERROR", "NOT EXISTS (SELECT 1 FROM stg.product p WHERE p.batch_id = {b} AND p.product_id = t.product_id) "
                       "OR NOT EXISTS (SELECT 1 FROM stg.channel c WHERE c.batch_id = {b} AND c.channel_id = t.channel_id)",
     "Sản phẩm hoặc kênh không có trong stg (không ánh xạ được)"),
    ("DQ-16", "ERROR", "abs(coalesce(total_applied, 0) - discount_amount) > 0.01", "Giảm giá dòng ≠ tổng voucher phân bổ"),
    ("DQ-11", "WARN", "list_price < unit_price", "Giá niêm yết thấp hơn giá bán"),
    ("DQ-15", "WARN", "payment_method_id IS NULL", "Không xác định được phương thức thanh toán → key 0"),
])

# ---------- Tồn kho cuối ngày (nguồn Fact_Inventory_Snapshot) ----------
entity("inventory_daily", "inventory_daily_balance + inventory_movements", "balance_date, warehouse_id, sku", "balance_date", """
WITH mv AS (
  SELECT movement_date::date AS d, warehouse_id, sku,
         sum(quantity_change) FILTER (WHERE movement_type = 'Import')     AS imp,
         -sum(quantity_change) FILTER (WHERE movement_type = 'Sale')      AS sold,
         sum(quantity_change) FILTER (WHERE movement_type = 'Return')     AS ret,
         sum(quantity_change) FILTER (WHERE movement_type = 'Adjustment') AS adj,
         count(*) FILTER (WHERE movement_type NOT IN ('Import','Sale','Return','Adjustment')) AS unknown_type
  FROM raw.inventory_movements WHERE batch_id = {b} GROUP BY 1, 2, 3)
SELECT b.balance_date, to_char(b.balance_date, 'YYYYMMDD')::int AS date_key, b.warehouse_id, b.sku, p.id AS product_id,
       b.quantity_on_hand, b.quantity_reserved, b.quantity_on_hand - b.quantity_reserved AS quantity_available,
       coalesce(mv.imp, 0)::int AS qty_imported, coalesce(mv.sold, 0)::int AS qty_sold,
       coalesce(mv.ret, 0)::int AS qty_returned, coalesce(mv.adj, 0)::int AS qty_adjusted,
       (b.quantity_on_hand - b.quantity_reserved = 0)::int::smallint AS stockout_flag, coalesce(mv.unknown_type, 0) AS unknown_type
FROM raw.inventory_daily_balance b
LEFT JOIN raw.products p ON p.sku = b.sku AND p.batch_id = b.batch_id
LEFT JOIN mv ON mv.d = b.balance_date AND mv.warehouse_id = b.warehouse_id AND mv.sku = b.sku
WHERE b.batch_id = {b}""", [
    ("DQ-01", "ERROR", "balance_date IS NULL OR warehouse_id IS NULL OR sku IS NULL", "Thiếu khóa tồn kho"),
    ("DQ-04", "ERROR", "product_id IS NULL", "SKU không ánh xạ được sang sản phẩm (IR-01)"),
    ("DQ-17", "ERROR", "quantity_on_hand < 0 OR quantity_reserved < 0 OR quantity_reserved > quantity_on_hand",
     "Tồn âm hoặc giữ hàng vượt tồn"),
    ("DQ-22", "WARN", "unknown_type > 0", "Loại biến động kho ngoài danh mục Import/Sale/Return/Adjustment"),
], pk_expr="balance_date || '/' || warehouse_id || '/' || sku")

# ---------- Chi phí quảng cáo mức ngày ----------
entity("ad_spend_daily", "ad_spend_logs", "ad_spend_log_id", "ad_spend_log_id", """
SELECT a.id AS ad_spend_log_id, a.campaign_id, a.channel_code, m.channel_id, a.log_date,
       to_char(a.log_date, 'YYYYMM')::int AS month_key, a.cost_amount::numeric(18,2) AS cost_amount,
       a.impressions, a.clicks, c.start_date AS campaign_start, c.end_date AS campaign_end
FROM raw.ad_spend_logs a
LEFT JOIN stg.map_channel m ON m.source_code = a.channel_code
LEFT JOIN raw.marketing_campaigns c ON c.id = a.campaign_id AND c.batch_id = a.batch_id
WHERE a.batch_id = {b}""", [
    ("DQ-01", "ERROR", "campaign_id IS NULL OR log_date IS NULL", "Thiếu khóa"),
    ("DQ-04", "ERROR", "channel_id IS NULL", "Mã kênh quảng cáo không có trong map_channel (IR-03)"),
    ("DQ-19", "ERROR", "cost_amount < 0 OR clicks < 0 OR impressions < clicks", "Chi phí/lượt âm hoặc impressions < clicks"),
    ("DQ-20", "WARN", "log_date < campaign_start OR log_date > campaign_end", "Chi phí ngoài thời gian chạy chiến dịch"),
])


# ------------------------------------------------------------------------------------------------
def load_mappings(cur):
    files = {"map_channel": ["source_code", "channel_id", "note"],
             "map_province": ["source_name", "province_code", "province_name", "region"],
             "map_gender": ["source_value", "gender"],
             "map_cost_ratio": ["root_category_id", "cost_group", "cost_ratio_min", "cost_ratio_max", "cost_ratio", "note"]}
    counts = {}
    for table, cols in files.items():
        cur.execute(f"DELETE FROM stg.{table}")
        with open(MAPPINGS / f"{table}.csv", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        with cur.copy(f"COPY stg.{table} ({', '.join(cols)}) FROM STDIN") as cp:
            for r in rows:
                cp.write_row([r[c] if r[c] != "" else None for c in cols])
        counts[table] = len(rows)
    return counts


def target_columns(cur, table):
    return [r[0] for r in cur.execute("""SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'stg' AND table_name = %s AND column_name NOT IN ('batch_id','dq_status')
        ORDER BY ordinal_position""", (table,)).fetchall()]


def run_entity(cur, b, e, fmt):
    t0 = time.time()
    name = e["name"]
    sel = e["select"].format(**fmt)
    cur.execute(f"DROP TABLE IF EXISTS tmp_{name}")
    cur.execute(f"""CREATE TEMP TABLE tmp_{name} AS
        SELECT s.*, row_number() OVER (PARTITION BY {e['key']} ORDER BY {e['order']}) AS rn FROM ({sel}
) s""")
    cur.execute(f"ANALYZE tmp_{name}")  # bảng tạm không được autovacuum phân tích → planner cần thống kê
    rules = [(c, sev, expr.format(**fmt), reason) for c, sev, expr, reason in e["rules"]]
    err = " OR ".join(f"coalesce(({x}), false)" for c, sev, x, r in rules if sev == "ERROR") or "false"
    warn = " OR ".join(f"coalesce(({x}), false)" for c, sev, x, r in rules if sev == "WARN") or "false"
    total = cur.execute(f"SELECT count(*) FROM tmp_{name}").fetchone()[0]
    # T6 + T7: kết quả từng quy tắc, cách ly
    for code, sev, expr, reason in rules:
        failed = cur.execute(f"SELECT count(*) FROM tmp_{name} t WHERE coalesce(({expr}), false)").fetchone()[0]
        cur.execute("""INSERT INTO audit.dq_result (batch_id, rule_code, table_name, severity, rows_checked, rows_failed)
                       VALUES (%s, %s, %s, %s, %s, %s)""", (b, code, name, sev, total, failed))
        if failed:
            cur.execute(f"""INSERT INTO audit.quarantine (batch_id, source_table, source_pk, rule_code, severity, reason, payload)
                SELECT %s, %s, ({e['pk_expr']})::text, %s, %s, %s, to_jsonb(t) - 'rn'
                FROM tmp_{name} t WHERE coalesce(({expr}), false)""", (b, e["source_table"], code, sev, reason))
    quarantined = cur.execute(f"SELECT count(*) FROM tmp_{name} t WHERE {err}").fetchone()[0]
    # T8: trùng khóa trong batch (chỉ tính trên dòng không lỗi)
    dup = cur.execute(f"SELECT count(*) FROM tmp_{name} t WHERE NOT ({err}) AND rn > 1").fetchone()[0]
    cur.execute("""INSERT INTO audit.dq_result (batch_id, rule_code, table_name, severity, rows_checked, rows_failed)
                   VALUES (%s, 'DQ-07', %s, 'WARN', %s, %s)""", (b, name, total, dup))
    if dup:
        cur.execute(f"""INSERT INTO audit.quarantine (batch_id, source_table, source_pk, rule_code, severity, reason, payload)
            SELECT %s, %s, ({e['pk_expr']})::text, 'DQ-07', 'WARN', 'Trùng khóa nghiệp vụ trong batch — giữ bản mới nhất',
                   to_jsonb(t) - 'rn' FROM tmp_{name} t WHERE NOT ({err}) AND rn > 1""", (b, e["source_table"]))
    # Ghi stg
    cols = target_columns(cur, name)
    collist = ", ".join(cols)
    cur.execute(f"""INSERT INTO stg.{name} (batch_id, dq_status, {collist})
        SELECT %s, CASE WHEN {warn} THEN 'WARN' ELSE 'VALID' END, {collist}
        FROM tmp_{name} t WHERE NOT ({err}) AND rn = 1""", (b,))
    written = cur.rowcount
    cur.execute(f"ANALYZE stg.{name}")  # thống kê cho các kiểm tra mức bảng và bước Load
    n_warn = cur.execute(f"SELECT count(*) FROM stg.{name} WHERE batch_id = %s AND dq_status = 'WARN'", (b,)).fetchone()[0]
    # T10: kiểm đếm
    ok = total == written + quarantined + dup
    cur.execute("""INSERT INTO audit.batch_table_log (batch_id, stage, table_name, rows_read, rows_valid, rows_warn,
                     rows_quarantined, rows_deduplicated, rows_written)
                   VALUES (%s, 'TRANSFORM', %s, %s, %s, %s, %s, %s, %s)""",
                (b, name, total, written - n_warn, n_warn, quarantined, dup, written))
    log(event="transformed", entity=name, read=total, valid=written - n_warn, warn=n_warn, quarantined=quarantined,
        dedup=dup, written=written, balanced=ok, sec=round(time.time() - t0, 2))
    if not ok:
        raise RuntimeError(f"Kiểm đếm lệch ở {name}: đọc {total} ≠ ghi {written} + cách ly {quarantined} + trùng {dup}")
    return total, written, quarantined, dup


def post_category(cur, b):
    """Điền root/path/is_leaf; DQ-14: phát hiện chu trình (độ sâu > 10)."""
    cur.execute(f"""
WITH RECURSIVE up AS (
  SELECT category_id AS start, category_id AS node, parent_id, 1 AS depth,
         category_id::text AS ids, category_name AS names
  FROM stg.category WHERE batch_id = {b}
  UNION ALL
  SELECT up.start, c.category_id, c.parent_id, up.depth + 1, c.category_id || '/' || up.ids, c.category_name || ' > ' || up.names
  FROM up JOIN stg.category c ON c.batch_id = {b} AND c.category_id = up.parent_id
  WHERE up.depth <= 11),
top AS (SELECT DISTINCT ON (start) start, node AS root, ids, names, depth FROM up ORDER BY start, depth DESC)
UPDATE stg.category s SET root_id = top.root, path_ids = top.ids, path_names = top.names,
       is_leaf = NOT EXISTS (SELECT 1 FROM stg.category ch WHERE ch.batch_id = {b} AND ch.parent_id = s.category_id)
FROM top WHERE s.batch_id = {b} AND s.category_id = top.start""")
    deep = cur.execute(f"""SELECT count(*) FROM stg.category WHERE batch_id = {b}
                           AND (array_length(string_to_array(path_ids, '/'), 1) > 10 OR root_id IS NULL)""").fetchone()[0]
    n = cur.execute(f"SELECT count(*) FROM stg.category WHERE batch_id = {b}").fetchone()[0]
    cur.execute("""INSERT INTO audit.dq_result VALUES (%s, 'DQ-14', 'category', 'ERROR', %s, %s)""", (b, n, deep))
    if deep:
        raise RuntimeError(f"DQ-14: cây danh mục có chu trình hoặc nút không về gốc ({deep} nút)")


def post_inventory(cur, b):
    """DQ-18 (WARN): tồn ngày d = tồn ngày d-1 + Σ biến động ngày d (trong phạm vi batch)."""
    cur.execute(f"""
INSERT INTO audit.quarantine (batch_id, source_table, source_pk, rule_code, severity, reason, payload)
SELECT {b}, 'inventory_daily_balance', cur.balance_date || '/' || cur.warehouse_id || '/' || cur.sku, 'DQ-18', 'WARN',
       'Tồn cuối ngày không khớp tồn hôm trước + biến động trong ngày',
       jsonb_build_object('prev', prev.quantity_on_hand, 'cur', cur.quantity_on_hand,
                          'delta', cur.qty_imported - cur.qty_sold + cur.qty_returned + cur.qty_adjusted)
FROM stg.inventory_daily cur
JOIN stg.inventory_daily prev ON prev.batch_id = cur.batch_id AND prev.warehouse_id = cur.warehouse_id AND prev.sku = cur.sku
 AND prev.balance_date = cur.balance_date - 1
WHERE cur.batch_id = {b}
  AND cur.quantity_on_hand <> prev.quantity_on_hand + cur.qty_imported - cur.qty_sold + cur.qty_returned + cur.qty_adjusted""")
    failed = cur.rowcount
    checked = cur.execute(f"""SELECT count(*) FROM stg.inventory_daily c JOIN stg.inventory_daily p
        ON p.batch_id = c.batch_id AND p.warehouse_id = c.warehouse_id AND p.sku = c.sku AND p.balance_date = c.balance_date - 1
        WHERE c.batch_id = {b}""").fetchone()[0]
    cur.execute("INSERT INTO audit.dq_result VALUES (%s, 'DQ-18', 'inventory_daily', 'WARN', %s, %s)", (b, checked, failed))
    log(event="dq_table_check", rule="DQ-18", checked=checked, failed=failed)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch", type=int, help="batch cần transform (mặc định: batch EXTRACTED mới nhất)")
    ap.add_argument("--max-quarantine-ratio", type=float, default=0.05)
    a = ap.parse_args(argv)
    with psycopg.connect(config.TARGET_URL) as con:
        cur = con.cursor()
        if a.batch:
            row = cur.execute("SELECT batch_id, status, watermark_to FROM audit.batch_log WHERE batch_id = %s", (a.batch,)).fetchone()
        else:
            row = cur.execute("""SELECT batch_id, status, watermark_to FROM audit.batch_log
                                 WHERE status = 'EXTRACTED' ORDER BY batch_id DESC LIMIT 1""").fetchone()
        if not row:
            raise SystemExit("Không có batch EXTRACTED để transform")
        b, status, wto = row
        # FAILED chỉ được chạy lại khi chỉ định rõ --batch (raw của batch vẫn nguyên vẹn, bất biến)
        if status not in ("EXTRACTED", "TRANSFORMED") and not (status == "FAILED" and a.batch):
            raise SystemExit(f"Batch {b} đang ở trạng thái {status}, không transform được")
        con.commit()
    fmt = {"b": int(b), "T": f"'{wto + dt.timedelta(days=1)} 00:00:00'::timestamp", "src": config.SOURCE_SYSTEM}
    log(event="transform_start", batch_id=b, watermark_to=wto)
    t0 = time.time()
    try:
        with psycopg.connect(config.TARGET_URL) as con:
            cur = con.cursor()
            # Chạy lại cùng batch: xóa kết quả TRANSFORM cũ của batch (stg + audit giai đoạn TRANSFORM)
            for e in ENTITIES:
                cur.execute(f"DELETE FROM stg.{e['name']} WHERE batch_id = %s", (b,))
            cur.execute("DELETE FROM audit.quarantine WHERE batch_id = %s", (b,))
            cur.execute("DELETE FROM audit.dq_result WHERE batch_id = %s", (b,))
            cur.execute("DELETE FROM audit.batch_table_log WHERE batch_id = %s AND stage = 'TRANSFORM'", (b,))
            cur.execute("DELETE FROM audit.reconciliation WHERE batch_id = %s AND check_code = 'RC-07'", (b,))
            # Thống kê mới cho raw trước khi join (tránh kế hoạch nested loop khi raw vừa tăng mạnh)
            for t in ("products", "categories", "orders", "order_items", "payments", "order_item_promotions",
                      "inventory_daily_balance", "inventory_movements", "tiki_product_category", "customers", "sellers"):
                cur.execute(f"ANALYZE raw.{t}")
            maps = load_mappings(cur)
            log(event="mappings_loaded", **maps)
            totals = [0, 0, 0, 0]
            for e in ENTITIES:
                res = run_entity(cur, b, e, fmt)
                totals = [x + y for x, y in zip(totals, res)]
                if e["name"] == "category":
                    post_category(cur, b)
                if e["name"] == "inventory_daily":
                    post_inventory(cur, b)
                ratio = res[2] / res[0] if res[0] else 0
                if ratio > a.max_quarantine_ratio:
                    raise RuntimeError(f"Tỷ lệ cách ly {e['name']} = {ratio:.1%} vượt ngưỡng {a.max_quarantine_ratio:.0%}")
            read, written, quarantined, dup = totals
            cur.execute("""INSERT INTO audit.reconciliation (batch_id, check_code, description, source_value, target_value, passed)
                           VALUES (%s, 'RC-07', 'Số dòng đọc = ghi stg + cách ly + trùng (mọi thực thể)', %s, %s, %s)""",
                        (b, read, written + quarantined + dup, read == written + quarantined + dup))
            # giữ phần thông báo của Extract, bỏ thông báo lỗi của lần transform trước (nếu có)
            cur.execute("""UPDATE audit.batch_log SET status = 'TRANSFORMED', finished_at = NULL,
                           message = coalesce(substring(message from 'extract [0-9.]+ s'), '') || %s WHERE batch_id = %s""",
                        (f"; transform {round(time.time() - t0, 1)} s", b))
            con.commit()
    except Exception as exc:
        with psycopg.connect(config.TARGET_URL) as con:
            con.execute("UPDATE audit.batch_log SET status = 'FAILED', finished_at = now(), message = %s WHERE batch_id = %s",
                        (f"TRANSFORM: {exc}"[:2000], b))
        log(event="transform_failed", batch_id=b, error=str(exc))
        raise
    log(event="batch_transformed", batch_id=b, read=read, written=written, quarantined=quarantined, dedup=dup,
        sec=round(time.time() - t0, 1))
    return b


if __name__ == "__main__":
    main()
