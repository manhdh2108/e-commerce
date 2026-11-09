"""Bộ kiểm thử tổng hợp T1–T7 (PLAN mục 8) — chạy MỘT lệnh, in bảng PASS/FAIL, thoát mã ≠ 0 nếu có FAIL.

    cd <repo> && .venv/bin/python -m dw.tests.run_tests            # đầy đủ (~5 phút, gồm nạp lại batch T3, dashboard)
    cd <repo> && .venv/bin/python -m dw.tests.run_tests --quick    # bỏ T3 (nạp lại batch) và kiểm thử dashboard (~20 s)
    cd <repo> && .venv/bin/python -m dw.tests.run_tests --only T4,T6

Tổng hợp lại các bộ kiểm thử đã có (test_scd_load.py, test_mart.sql, measure_*.sql, dashboard/test_app.py)
và bổ sung các kiểm thử còn thiếu theo bảng T1–T7 của PLAN. Chỉ T3 ghi vào kho (nạp lại batch SUCCESS mới nhất —
idempotent, đúng điều T3 cần chứng minh); mọi kiểm thử khác chỉ đọc.
"""
import argparse
import contextlib
import io
import pathlib
import re
import subprocess
import sys
import time

import psycopg

from dw.etl import config

ROOT = config.ROOT
ANALYST_URL = "postgresql://dw_analyst:dw_analyst_local@127.0.0.1:55432/dwh"
FACTS = ("fact_order_item", "fact_inventory_snapshot", "fact_ad_spend")
RESULTS = []          # (mã, nhóm, mô tả, trạng thái, chi tiết)
GROUP = ""


def rec(tid, desc, ok, detail="", status=None):
    status = status or ("PASS" if ok else "FAIL")
    RESULTS.append((tid, GROUP, desc, status, detail))
    print(f"{status:4} {tid:6} {desc}" + (f"\n            → {detail}" if detail else ""), flush=True)


def one(con, sql, params=None):
    return con.execute(sql, params).fetchone()


def rows(con, sql, params=None):
    return con.execute(sql, params).fetchall()


# ================================================================================================
# T1 — Mô hình
# ================================================================================================
def t1(c):
    for f in FACTS:
        pk = one(c, "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = %s::regclass AND contype = 'p'", (f"dw.{f}",))
        rec("T1.1", f"{f} có khóa chính", pk is not None, pk[0] if pk else "")
    for f in FACTS:
        keys = {r[0] for r in rows(c, """SELECT column_name FROM information_schema.columns
                 WHERE table_schema = 'dw' AND table_name = %s AND right(column_name, 4) = '_key'""", (f,))}
        fks = {r[0]: r[1] for r in rows(c, """SELECT a.attname, t.relname FROM pg_constraint k
                 JOIN pg_attribute a ON a.attrelid = k.conrelid AND a.attnum = ANY (k.conkey)
                 JOIN pg_class t ON t.oid = k.confrelid
                 WHERE k.conrelid = %s::regclass AND k.contype = 'f'""", (f"dw.{f}",))}
        missing = sorted(keys - set(fks))
        not_dim = sorted(k for k, t in fks.items() if not t.startswith("dim_"))
        rec("T1.2", f"{f}: mọi cột *_key ({len(keys)}) có FK tới dimension", not missing and not not_dim,
            f"thiếu FK: {missing}; FK không tới dim_*: {not_dim}" if (missing or not_dim) else ", ".join(sorted(f'{k}→{t}' for k, t in fks.items())))
    n, d = one(c, "SELECT count(*), count(DISTINCT (source_system, order_id, line_number)) FROM dw.fact_order_item")
    rec("T1.3", "Grain fact_order_item: count(*) = count(distinct khóa nghiệp vụ (source_system, order_id, line_number))", n == d, f"{n} = {d}")
    n, d = one(c, """SELECT count(*), count(DISTINCT (f.date_key, p.product_id, f.warehouse_key))
                     FROM dw.fact_inventory_snapshot f JOIN dw.dim_product p USING (product_key)""")
    rec("T1.3", "Grain fact_inventory_snapshot: 1 dòng / (ngày, sản phẩm nghiệp vụ, kho)", n == d, f"{n} = {d}")
    n, d = one(c, "SELECT count(*), count(DISTINCT (month_key, campaign_key, channel_key)) FROM dw.fact_ad_spend")
    rec("T1.3", "Grain fact_ad_spend: 1 dòng / (tháng, chiến dịch, kênh)", n == d, f"{n} = {d}")
    total, covered = one(c, """SELECT count(*), count(*) FILTER (WHERE nullif(btrim(description), '') IS NOT NULL)
                               FROM audit.data_dictionary WHERE schema_name = 'dw'""")
    in_db = one(c, """SELECT count(*) FROM information_schema.columns c JOIN pg_class r
                      ON r.relname = c.table_name AND r.relnamespace = 'dw'::regnamespace
                      WHERE c.table_schema = 'dw' AND NOT r.relispartition""")[0]
    rec("T1.4", "Từ điển dữ liệu phủ 100% cột của schema dw (không tính partition con)", total == in_db and covered == total,
        f"{covered}/{in_db} cột có mô tả")
    bad = [r[0] for r in rows(c, """SELECT r.relname FROM pg_class r WHERE r.relnamespace = 'dw'::regnamespace
              AND r.relkind IN ('r', 'p') AND NOT r.relispartition AND (r.relname LIKE 'dim\\_%' OR r.relname LIKE 'bridge\\_%')
              AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conrelid = r.oid AND k.contype = 'p')""")]
    rec("T1.5", "Mọi dimension và bridge có khóa chính", not bad, f"thiếu PK: {bad}" if bad else "")
    nv = one(c, "SELECT count(*) FROM pg_constraint WHERE connamespace = 'dw'::regnamespace AND contype = 'f' AND NOT convalidated")[0]
    rec("T1.6", "Mọi FK trong dw đã được validate", nv == 0, f"{nv} FK chưa validate")
    # bridge
    bad = one(c, """SELECT count(*) FROM (SELECT promotion_group_key FROM dw.bridge_promotion_group GROUP BY 1
                    HAVING abs(sum(weighting_factor) - 1) > 0.000001) x""")[0]
    rec("T1.7", "Bridge khuyến mãi: Σ weighting_factor = 1 trên từng promotion_group", bad == 0, f"{bad} nhóm sai")
    alloc, disc = one(c, """SELECT (SELECT coalesce(sum(f.discount_amount * b.weighting_factor), 0) FROM dw.fact_order_item f
                                    JOIN dw.bridge_promotion_group b USING (promotion_group_key)),
                                   (SELECT coalesce(sum(discount_amount), 0) FROM dw.fact_order_item WHERE promotion_group_key > 0)""")
    rec("T1.7", "Bridge khuyến mãi: Σ giảm giá phân bổ = Σ discount_amount của dòng có voucher", abs(alloc - disc) <= 0.01,
        f"{alloc} vs {disc}")


# ================================================================================================
# T2 — Dữ liệu (đối soát, cách ly, khóa mồ côi, khóa 0)
# ================================================================================================
def t2(c):
    need = {"RC-01", "RC-02", "RC-03a", "RC-03b", "RC-04", "RC-05", "RC-06", "RC-07"}
    for b, st in rows(c, "SELECT batch_id, status FROM audit.batch_log WHERE status = 'SUCCESS' ORDER BY batch_id"):
        got = {r[0]: r[1] for r in rows(c, "SELECT check_code, passed FROM audit.reconciliation WHERE batch_id = %s", (b,))}
        miss = sorted(need - set(got))
        fail = sorted(k for k, v in got.items() if not v)
        rec("T2.1", f"Batch {b}: RC-01..07 (+SCD-01/02) đều có và đạt", not miss and not fail,
            f"{len(got)} kiểm tra" + (f"; thiếu {miss}" if miss else "") + (f"; không đạt {fail}" if fail else ""))
    tot, bad = one(c, """SELECT count(*), count(*) FILTER (WHERE nullif(btrim(reason), '') IS NULL OR rule_code IS NULL
                                                          OR source_table IS NULL OR payload IS NULL) FROM audit.quarantine""")
    rec("T2.2", "Mọi dòng cách ly có reason, rule_code, source_table và payload", bad == 0, f"{tot} dòng cách ly, {bad} thiếu thông tin")
    orphan = one(c, """SELECT
        (SELECT count(*) FROM dw.fact_order_item f WHERE NOT EXISTS (SELECT 1 FROM dw.dim_product d WHERE d.product_key = f.product_key)
            OR NOT EXISTS (SELECT 1 FROM dw.dim_customer d WHERE d.customer_key = f.customer_key)
            OR NOT EXISTS (SELECT 1 FROM dw.dim_seller d WHERE d.seller_key = f.seller_key)
            OR NOT EXISTS (SELECT 1 FROM dw.dim_category d WHERE d.category_key = f.category_key)
            OR NOT EXISTS (SELECT 1 FROM dw.dim_channel d WHERE d.channel_key = f.channel_key)
            OR NOT EXISTS (SELECT 1 FROM dw.dim_payment_method d WHERE d.payment_method_key = f.payment_method_key)
            OR NOT EXISTS (SELECT 1 FROM dw.dim_campaign d WHERE d.campaign_key = f.campaign_key)
            OR NOT EXISTS (SELECT 1 FROM dw.dim_promotion_group d WHERE d.promotion_group_key = f.promotion_group_key)
            OR NOT EXISTS (SELECT 1 FROM dw.dim_customer_profile d WHERE d.customer_profile_key = f.customer_profile_key))
      + (SELECT count(*) FROM dw.fact_inventory_snapshot f WHERE NOT EXISTS (SELECT 1 FROM dw.dim_product d WHERE d.product_key = f.product_key)
            OR NOT EXISTS (SELECT 1 FROM dw.dim_warehouse d WHERE d.warehouse_key = f.warehouse_key))
      + (SELECT count(*) FROM dw.fact_ad_spend f WHERE NOT EXISTS (SELECT 1 FROM dw.dim_campaign d WHERE d.campaign_key = f.campaign_key))""")[0]
    rec("T2.3", "0 dòng fact có khóa ngoại mồ côi (truy vấn độc lập với RC-06)", orphan == 0, f"{orphan} dòng")
    ind = one(c, """SELECT count(*) FILTER (WHERE product_key = 0) + count(*) FILTER (WHERE customer_key = 0) + count(*) FILTER (WHERE seller_key = 0)
                      + count(*) FILTER (WHERE category_key = 0) + count(*) FILTER (WHERE channel_key = 0)
                      + count(*) FILTER (WHERE payment_method_key = 0) + count(*) FILTER (WHERE campaign_key = 0)
                      + count(*) FILTER (WHERE promotion_group_key = 0) + count(*) FILTER (WHERE customer_profile_key = 0)
                    FROM dw.fact_order_item""")[0]
    with psycopg.connect(ANALYST_URL, autocommit=True) as a:
        shown = one(a, "SELECT coalesce(sum(unknown_0), 0) FROM mart.v_unknown_keys WHERE fact = 'fact_order_item'")[0]
    src = (ROOT / "dashboard/app.py").read_text(encoding="utf-8")
    rec("T2.4", "Khóa 0 (chưa xác định) được đếm đúng và hiển thị trên màn hình Chất lượng dữ liệu",
        ind == shown and "mart.v_unknown_keys" in src, f"đếm độc lập {ind} = mart.v_unknown_keys {shown}; dashboard truy vấn view: {'mart.v_unknown_keys' in src}")
    worst = rows(c, """SELECT b.batch_id, t.table_name, t.rows_quarantined::float / nullif(t.rows_read, 0)
                       FROM audit.batch_table_log t JOIN audit.batch_log b USING (batch_id)
                       WHERE t.stage = 'TRANSFORM' AND b.status = 'SUCCESS' AND t.rows_read > 0
                       ORDER BY 3 DESC NULLS LAST LIMIT 1""")[0]
    rec("T2.5", "Tỷ lệ cách ly của mọi bảng ở các batch SUCCESS ≤ 5% (ngưỡng cấu hình)", (worst[2] or 0) <= 0.05,
        f"cao nhất: batch {worst[0]} bảng {worst[1]} = {(worst[2] or 0) * 100:.2f}%")
    b1, b3 = (one(c, "SELECT count(*) FROM audit.quarantine WHERE batch_id = %s", (b,))[0] for b in (1, 3))
    rec("T2.6", "Batch 3 (cùng dữ liệu batch 1 + lỗi chèn có chủ đích) bị cách ly nhiều hơn batch 1 — lỗi nguồn được bắt",
        b3 > b1, f"batch 1: {b1} dòng; batch 3: {b3} dòng")
    bad = one(c, """SELECT count(*) FROM audit.batch_table_log t WHERE t.stage = 'TRANSFORM' AND t.rows_read IS NOT NULL
                      AND t.rows_read <> t.rows_valid + t.rows_warn + t.rows_quarantined + t.rows_deduplicated""")[0]
    rec("T2.7", "RC-07 theo bảng: đọc = hợp lệ + cảnh báo + cách ly + trùng bị loại (mọi batch, mọi bảng)", bad == 0, f"{bad} dòng log lệch")


# ================================================================================================
# T3 — Cập nhật (idempotent, rollback khi lỗi giữa batch)
# ================================================================================================
def fingerprint(c, a):
    f = {}
    f["foi"] = one(c, """SELECT count(*), sum(net_revenue), sum(discount_amount), sum(quantity), sum(commission_amount), sum(cost_amount_est),
        md5(string_agg(concat_ws('|', date_key, source_system, order_id, line_number, product_key, seller_key, customer_key,
            customer_profile_key, category_key, channel_key, payment_method_key, campaign_key, promotion_group_key, quantity,
            net_revenue, discount_amount, is_returned), ',' ORDER BY date_key, source_system, order_id, line_number))
        FROM dw.fact_order_item""")
    f["inv"] = one(c, "SELECT count(*), sum(quantity_on_hand), sum(qty_sold), sum(qty_imported), sum(inventory_value_est) FROM dw.fact_inventory_snapshot")
    f["ads"] = one(c, "SELECT count(*), sum(cost_amount), sum(clicks), sum(impressions) FROM dw.fact_ad_spend")
    for d in ("dim_product", "dim_seller", "dim_customer", "dim_category", "dim_promotion_group", "bridge_promotion_group", "dim_seller_tier_t3"):
        f[d] = one(c, f"SELECT count(*) FROM dw.{d}")
    f["dim_keys"] = one(c, "SELECT (SELECT max(product_key) FROM dw.dim_product), (SELECT max(seller_key) FROM dw.dim_seller), (SELECT max(customer_key) FROM dw.dim_customer)")
    f["mart"] = one(a, """SELECT (SELECT sum(net_revenue) FROM mart.mv_sales_day_product), (SELECT sum(net_revenue) FROM mart.mv_sales_month_category),
                                 (SELECT sum(end_on_hand) FROM mart.mv_inventory_month_product), (SELECT sum(cost_amount) FROM mart.mv_ads_month_channel)""")
    return f


def mart_state(a):
    return one(a, "SELECT mart_batch, mart_refreshed_at, mart_stale FROM mart.v_data_freshness")


def t3(c, a):
    last = one(c, "SELECT batch_id FROM audit.batch_log WHERE status = 'SUCCESS' ORDER BY watermark_to DESC, batch_id DESC LIMIT 1")[0]
    fp0 = fingerprint(c, a)
    runs = []
    for i in (1, 2):
        t0 = time.time()
        p = subprocess.run([sys.executable, "-m", "dw.etl.load", "--reload"], cwd=ROOT, capture_output=True, text=True)
        runs.append((p.returncode, round(time.time() - t0, 1)))
        fp = fingerprint(c, a)
        diff = [k for k in fp0 if fp[k] != fp0[k]]
        rec("T3.1", f"Nạp lại batch {last} (--reload) lần {i}: số dòng, Σ tiền và băm nội dung không đổi",
            p.returncode == 0 and not diff, f"mã thoát {p.returncode}, {runs[-1][1]} s" + (f"; khác: {diff}\n{p.stderr[-400:]}" if diff or p.returncode else
            f"; fact_order_item {fp['foi'][0]} dòng, Σ net {fp['foi'][1]}, md5 {fp['foi'][6][:12]}…"))
    st = one(c, "SELECT status FROM audit.batch_log WHERE batch_id = %s", (last,))[0]
    ok = one(c, "SELECT count(*) = count(*) FILTER (WHERE passed) FROM audit.reconciliation WHERE batch_id = %s", (last,))[0]
    rec("T3.2", f"Sau 2 lần nạp lại: batch {last} vẫn SUCCESS và mọi đối soát đạt", st == "SUCCESS" and ok, f"status={st}, đối soát đạt={ok}")

    # giả lập lỗi giữa batch: dimension + fact đã nạp xong, lỗi ở fact cuối → rollback toàn bộ, mart không refresh
    from dw.etl import load as L
    before, mstate = fingerprint(c, a), mart_state(a)
    orig = L.load_ad_spend

    def boom(cur, b):
        raise RuntimeError("giả lập lỗi giữa batch (T3)")
    L.load_ad_spend = boom
    raised = None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            L.main(["--reload"])
    except Exception as exc:  # noqa: BLE001
        raised = str(exc)
    finally:
        L.load_ad_spend = orig
    after, mstate2 = fingerprint(c, a), mart_state(a)
    st = one(c, "SELECT status FROM audit.batch_log WHERE batch_id = %s", (last,))[0]
    rec("T3.3", "Giả lập lỗi giữa batch (sau khi nạp dimension + fact): ROLLBACK, dw không đổi",
        raised is not None and before == after, f"lỗi bắt được: {raised!r}; khác biệt: {[k for k in before if before[k] != after[k]]}")
    rec("T3.4", "Giả lập lỗi giữa batch: mart không được refresh và không đổi, batch SUCCESS giữ nguyên",
        mstate == mstate2 and st == "SUCCESS", f"mart_batch/refreshed_at trước={mstate[:2]} sau={mstate2[:2]}; status={st}")


# ================================================================================================
# T4 — Lịch sử (SCD)
# ================================================================================================
def t4(c, quick):
    for dim, bk in (("dim_product", "product_id"), ("dim_seller", "seller_id"), ("dim_customer", "customer_id")):
        ov = one(c, f"""SELECT count(*) FROM dw.{dim} a JOIN dw.{dim} b ON b.{bk} = a.{bk} AND b.ctid <> a.ctid
                        AND a.valid_from < b.valid_to AND b.valid_from < a.valid_to""")[0]
        cur = one(c, f"SELECT count(*) FROM (SELECT {bk} FROM dw.{dim} GROUP BY 1 HAVING count(*) FILTER (WHERE is_current) <> 1) x")[0]
        gap = one(c, f"""SELECT count(*) FROM (SELECT {bk}, valid_from, lag(valid_to) OVER (PARTITION BY {bk} ORDER BY valid_from) prev_to
                         FROM dw.{dim}) x WHERE prev_to IS NOT NULL AND prev_to <> valid_from""")[0]
        n, multi = one(c, f"SELECT count(*), count(*) - count(DISTINCT {bk}) FROM dw.{dim}")
        rec("T4.1", f"{dim}: không chồng lấn [valid_from, valid_to), không hở, đúng 1 current/khóa", ov == 0 and cur == 0 and gap == 0,
            f"chồng lấn {ov}, khóa sai current {cur}, hở {gap}; {n} phiên bản, {multi} phiên bản thêm do thay đổi SCD2")
    # fact gắn đúng phiên bản theo ngày hoàn tất
    day = "to_date(f.date_key::text, 'YYYYMMDD')"
    for dim, key, extra in (("dim_seller", "seller_key", ""), ("dim_product", "product_key", ""), ("dim_customer", "customer_key", "AND f.customer_key > 0")):
        bad = one(c, f"""SELECT count(*) FROM dw.fact_order_item f JOIN dw.{dim} d USING ({key})
                         WHERE NOT ({day} >= d.valid_from AND {day} < d.valid_to) {extra}""")[0]
        rec("T4.2", f"Mọi dòng fact_order_item gắn {key} của phiên bản có hiệu lực tại ngày hoàn tất", bad == 0, f"{bad} dòng sai phiên bản")
    bad = one(c, """SELECT count(*) FROM dw.fact_inventory_snapshot f JOIN dw.dim_product d USING (product_key)
                    WHERE NOT (to_date(f.date_key::text, 'YYYYMMDD') >= d.valid_from AND to_date(f.date_key::text, 'YYYYMMDD') < d.valid_to)""")[0]
    rec("T4.2", "Mọi dòng fact_inventory_snapshot gắn product_key đúng phiên bản tại ngày snapshot", bad == 0, f"{bad} dòng sai phiên bản")
    # ca cụ thể: seller đã đổi hạng (MGR-01) và có fact ở cả hai phiên bản
    cases = rows(c, """WITH x AS (SELECT s.seller_id, s.seller_key, s.tier, s.valid_from, s.valid_to, min(f.date_key) dmin, max(f.date_key) dmax, count(*) n
                          FROM dw.fact_order_item f JOIN dw.dim_seller s USING (seller_key)
                          WHERE s.seller_id IN (SELECT seller_id FROM dw.dim_seller GROUP BY 1 HAVING count(DISTINCT tier) > 1)
                          GROUP BY 1, 2, 3, 4, 5)
                       SELECT a.seller_id, a.tier, a.valid_to, a.n, a.dmax, b.tier, b.n, b.dmin
                       FROM x a JOIN x b ON b.seller_id = a.seller_id AND b.valid_from = a.valid_to AND b.tier <> a.tier ORDER BY 1""")
    ok = bool(cases) and all(r[4] < int(r[2].strftime("%Y%m%d")) <= r[7] for r in cases)
    rec("T4.3", "Ca cụ thể: seller đã đổi hạng — fact trước ngày đổi gắn phiên bản cũ, từ ngày đổi gắn phiên bản mới", ok,
        "; ".join(f"seller {r[0]}: {r[1]} ({r[3]} dòng, đến {r[4]}) → {r[5]} từ {r[2]} ({r[6]} dòng, từ {r[7]})" for r in cases) or "không có seller nào thỏa")
    bad = one(c, """SELECT count(*) FROM dw.dim_seller_tier_t3 t JOIN dw.dim_seller cur ON cur.seller_id = t.seller_id AND cur.is_current
                    WHERE t.current_tier <> cur.tier""")[0]
    bad2 = one(c, """SELECT count(*) FROM dw.dim_seller_tier_t3 t WHERE t.previous_tier IS NOT NULL AND NOT EXISTS (
                       SELECT 1 FROM dw.dim_seller v WHERE v.seller_id = t.seller_id AND v.tier = t.previous_tier AND v.valid_to = t.tier_changed_on)""")[0]
    rec("T4.4", "SCD3 dim_seller_tier_t3 khớp lịch sử SCD2 (current_tier = phiên bản hiện hành; previous_tier = hạng của phiên bản ngay trước ngày đổi)",
        bad == 0 and bad2 == 0, f"current sai {bad}, previous sai {bad2}")
    if quick:
        rec("T4.5", "Kịch bản có kiểm soát SCD1/SCD2/SCD3 + đến muộn (test_scd_load, rollback)", None, "bỏ qua (--quick)", status="SKIP")
    else:
        p = subprocess.run([sys.executable, "-m", "dw.tests.test_scd_load"], cwd=ROOT, capture_output=True, text=True)
        m = re.search(r"(\d+)/(\d+) PASS", p.stdout)
        rec("T4.5", "Kịch bản có kiểm soát: SCD1 không tăng phiên bản, SCD2 đóng/mở, SCD3, cùng ngày sửa tại chỗ, đến muộn → DQ-23 (rollback)",
            p.returncode == 0 and m is not None and m.group(1) == m.group(2), f"{m.group(0) if m else p.stdout[-300:]}; kho không đổi")


# ================================================================================================
# T5 — Báo cáo (mart, dashboard, CSV, drill-across) và kiểm thử đặc thù
# ================================================================================================
def t5(c, a, quick):
    sql = "\n".join(l for l in (ROOT / "dw/tests/test_mart.sql").read_text(encoding="utf-8").splitlines() if not l.startswith("\\"))
    res = rows(a, sql)
    bad = [r[0] for r in res if r[3] == "FAIL"]
    info = [f"{r[0]} = {r[1]}" for r in res if r[3] == "INFO"]
    rec("T5.1", "Mart = truy vấn độc lập trên fact atomic (test_mart.sql)", not bad and len(res) > 0,
        f"{sum(r[3] == 'PASS' for r in res)}/{len(res) - len(info)} PASS" + (f"; sai: {bad}" if bad else "") + (f"; thông tin: {info}" if info else ""))
    sales_only, ads_only, groups = one(a, """SELECT count(*) FILTER (WHERE missing_ads), count(*) FILTER (WHERE missing_sales), count(*) FROM mart.v_drill_sales_ads""")
    net_m, cost_m = one(a, "SELECT sum(net_revenue), sum(cost_amount) FROM mart.v_drill_sales_ads")
    net_f = one(c, "SELECT sum(net_revenue) FROM dw.fact_order_item")[0]
    cost_f = one(c, "SELECT sum(cost_amount) FROM dw.fact_ad_spend")[0]
    rec("T5.2", "Drill-across bán hàng – quảng cáo giữ nhóm chỉ có một phía và không nhân đôi doanh thu/chi phí",
        sales_only + ads_only > 0 and net_m == net_f and cost_m == cost_f,
        f"{groups} nhóm (tháng,kênh): {sales_only} chỉ có bán, {ads_only} chỉ có QC; Σ doanh thu {net_m} = fact {net_f}; Σ chi phí {cost_m} = fact {cost_f}")
    # semi-additive: tồn kho cuối kỳ = ngày cuối kỳ, khác SUM qua ngày
    end_mart = one(a, "SELECT sum(end_on_hand) FROM mart.mv_inventory_month_product")[0]
    last_day, end_idx, sum_days = one(c, """SELECT max(date_key), (SELECT sum(quantity_on_hand) FROM dw.fact_inventory_snapshot WHERE date_key = (SELECT max(date_key) FROM dw.fact_inventory_snapshot)),
                                            (SELECT sum(quantity_on_hand) FROM dw.fact_inventory_snapshot) FROM dw.fact_inventory_snapshot""")
    rec("T5.3", "Semi-additive: tồn kho cuối kỳ = tồn ngày cuối kỳ (mart = độc lập), KHÔNG bằng tổng qua các ngày",
        end_mart == end_idx and end_idx != sum_days, f"cuối kỳ (ngày {last_day}): {end_idx}; mart: {end_mart}; SUM qua ngày (sai): {sum_days}")
    # non-additive
    aov_p, aov_atomic, aov_avg = one(c, """WITH d AS (SELECT date_key, sum(net_revenue) net, count(DISTINCT order_id) n FROM dw.fact_order_item GROUP BY 1)
        SELECT round((SELECT sum(net) / sum(n) FROM d), 2), round((SELECT sum(net_revenue) / count(DISTINCT order_id) FROM dw.fact_order_item), 2),
               round((SELECT avg(net / n) FROM d), 2)""")
    rec("T5.4", "Non-additive: AOV tính lại từ tử/mẫu = AOV atomic; trung bình các AOV ngày (sai) cho giá trị khác", aov_p == aov_atomic and aov_avg != aov_atomic,
        f"từ tổng {aov_p} = atomic {aov_atomic}; trung bình ngày (sai) {aov_avg}")
    # cây danh mục
    cyc = one(c, "SELECT count(*) FROM dw.dim_category WHERE parent_category_key = category_key")[0]
    loops = one(c, """WITH RECURSIVE w AS (SELECT category_key AS start, parent_category_key AS cur, 1 AS d FROM dw.dim_category WHERE parent_category_key IS NOT NULL
                         UNION ALL SELECT w.start, p.parent_category_key, w.d + 1 FROM w JOIN dw.dim_category p ON p.category_key = w.cur
                         WHERE p.parent_category_key IS NOT NULL AND w.d < 20)
                      SELECT count(*) FROM w WHERE cur = start""")[0]
    rec("T5.5", "Cây danh mục: không chu trình, không tự làm cha", cyc == 0 and loops == 0, f"tự làm cha {cyc}, chu trình {loops}")
    mism, nodes = one(c, """WITH direct AS (SELECT dc.category_key, coalesce(sum(f.net_revenue), 0) rev FROM dw.dim_category dc
                                LEFT JOIN dw.fact_order_item f ON f.category_key = dc.category_key GROUP BY 1),
          via_bridge AS (SELECT b.ancestor_key AS category_key, sum(d.rev) rev FROM dw.bridge_category_hierarchy b JOIN direct d ON d.category_key = b.descendant_key GROUP BY 1),
          via_path AS (SELECT a.category_key, coalesce(sum(f.net_revenue), 0) rev FROM dw.dim_category a
                       JOIN dw.dim_category l ON l.path_ids = a.path_ids OR l.path_ids LIKE a.path_ids || '/%'
                       LEFT JOIN dw.fact_order_item f ON f.category_key = l.category_key WHERE a.category_key > 0 GROUP BY 1)
          SELECT count(*) FILTER (WHERE vb.rev <> vp.rev), count(*) FROM via_bridge vb JOIN via_path vp USING (category_key)""")
    roots = one(c, """SELECT coalesce(sum(vb.rev), 0) FROM (SELECT b.ancestor_key, sum(f.net_revenue) rev FROM dw.bridge_category_hierarchy b
                      JOIN dw.dim_category a ON a.category_key = b.ancestor_key AND a.level = 1
                      JOIN dw.fact_order_item f ON f.category_key = b.descendant_key GROUP BY 1) vb""")[0]
    total = one(c, "SELECT sum(net_revenue) FROM dw.fact_order_item WHERE category_key > 0")[0]
    rec("T5.6", "Cây danh mục: doanh thu cây con qua bridge = tính độc lập theo path_ids; Σ các nút gốc = tổng (không cộng lặp)",
        mism == 0 and roots == total, f"{nodes} nút so sánh, {mism} lệch; Σ nút gốc {roots} = tổng fact {total}")
    # mini-dimension: tính lại độc lập bằng window function
    n, bad = one(c, """WITH l AS (SELECT f.date_key, f.order_id, f.line_number, dc.customer_id, f.customer_profile_key FROM dw.fact_order_item f
                                       JOIN dw.dim_customer dc USING (customer_key) WHERE f.customer_key > 0),
        h AS (SELECT l.*, (SELECT coalesce(sum(x.net_revenue), 0) FROM dw.fact_order_item x JOIN dw.dim_customer xc USING (customer_key)
                           WHERE xc.customer_id = l.customer_id AND x.date_key < l.date_key
                             AND x.date_key >= to_char(to_date(l.date_key::text, 'YYYYMMDD') - 365, 'YYYYMMDD')::int) spend,
                          (SELECT count(DISTINCT x.order_id) FROM dw.fact_order_item x JOIN dw.dim_customer xc USING (customer_key)
                           WHERE xc.customer_id = l.customer_id AND x.date_key < l.date_key
                             AND x.date_key >= to_char(to_date(l.date_key::text, 'YYYYMMDD') - 365, 'YYYYMMDD')::int) freq FROM l)
        SELECT count(*), count(*) FILTER (WHERE cp.spend_band_12m IS DISTINCT FROM CASE WHEN h.freq = 0 THEN 'Chưa mua' WHEN h.spend < 1000000 THEN '< 1 triệu'
                  WHEN h.spend < 5000000 THEN '1–5 triệu' WHEN h.spend < 20000000 THEN '5–20 triệu' ELSE '> 20 triệu' END
               OR cp.frequency_band IS DISTINCT FROM CASE WHEN h.freq = 0 THEN '0 đơn' WHEN h.freq = 1 THEN '1 đơn' WHEN h.freq <= 3 THEN '2–3 đơn'
                  WHEN h.freq <= 9 THEN '4–9 đơn' ELSE '≥ 10 đơn' END)
        FROM h JOIN dw.dim_customer_profile cp USING (customer_profile_key)""")
    first = one(c, """SELECT count(*), count(*) FILTER (WHERE cp.spend_band_12m = 'Chưa mua' AND cp.frequency_band = '0 đơn') FROM dw.fact_order_item f
                      JOIN dw.dim_customer dc USING (customer_key) JOIN dw.dim_customer_profile cp USING (customer_profile_key)
                      WHERE f.customer_key > 0 AND f.date_key = (SELECT min(x.date_key) FROM dw.fact_order_item x JOIN dw.dim_customer xc USING (customer_key)
                                                                 WHERE xc.customer_id = dc.customer_id)""")
    rec("T5.7", "Mini-dimension: hồ sơ khách tính theo trạng thái TRƯỚC giao dịch (tính lại độc lập; dòng ngày mua đầu tiên → 'Chưa mua / 0 đơn')",
        bad == 0 and first[0] == first[1], f"{n} dòng, {bad} lệch; ngày mua đầu tiên: {first[1]}/{first[0]} dòng ở bucket 'Chưa mua'")
    if quick:
        rec("T5.8", "Dashboard: 9 màn hình chạy không lỗi, KPI = SQL độc lập (test_app.py)", None, "bỏ qua (--quick)", status="SKIP")
        rec("T5.9", "File CSV xuất ra = bảng hiển thị trên từng màn hình", None, "bỏ qua (--quick)", status="SKIP")
        return
    p = subprocess.run([sys.executable, "dashboard/test_app.py"], cwd=ROOT, capture_output=True, text=True)
    n_pass = p.stdout.count("PASS")
    rec("T5.8", "Dashboard: 9 màn hình chạy không lỗi, KPI hiển thị và bộ lọc = SQL độc lập (test_app.py)", p.returncode == 0 and "FAIL" not in p.stdout,
        f"{n_pass} kiểm tra PASS" + ("" if p.returncode == 0 else "\n" + p.stdout[-600:]))
    csv_vs_table()


def csv_vs_table():
    """T5.9 — chặn st.dataframe / st.download_button, so từng cặp (bảng hiển thị, file CSV)."""
    import logging

    import pandas as pd
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    sys.path.insert(0, str(ROOT / "dashboard"))   # AppTest không tự thêm thư mục của app.py như `streamlit run`
    logging.disable(logging.WARNING)   # tắt cảnh báo "missing ScriptRunContext" của chế độ bare (khôi phục ở finally)
    shown, pairs, orig_df, orig_dl = [], [], st.dataframe, st.download_button

    def df_spy(data=None, *a, **k):
        shown.append(data)
        return orig_df(data, *a, **k)

    def dl_spy(label, data=None, *a, **k):
        pairs.append((label, shown[-1] if shown else None, data))
        return orig_dl(label, data, *a, **k)
    st.dataframe, st.download_button = df_spy, dl_spy
    try:
        tech = "Kỹ thuật kho dữ liệu"
        for mode, page in [("Thống kê", "Bán hàng chi tiết"), (tech, "3 bảng Fact và kỹ thuật (SCD, bridge)"), (tech, "Lịch sử thuộc tính (SCD)"),
                           (tech, "Đối soát vận hành (drill-across)"), (tech, "Chất lượng dữ liệu"), (tech, "Hiệu năng")]:
            at = AppTest.from_file(str(ROOT / "dashboard/app.py"), default_timeout=120)
            at.session_state["mode"] = mode
            at.session_state[f"page_{mode}"] = page
            at.run()
            if at.exception:
                rec("T5.9", f"CSV = bảng hiển thị — màn hình {page}", False, f"exception: {at.exception[0].value[:200]}")
    finally:
        st.dataframe, st.download_button = orig_df, orig_dl
        logging.disable(logging.NOTSET)
    bad = []
    for label, df, data in pairs:
        raw = data if isinstance(data, bytes) else str(data).encode("utf-8")
        back = pd.read_csv(io.BytesIO(raw))
        if df is None or back.shape != df.shape or list(back.columns) != [str(x) for x in df.columns]:
            bad.append(label)
    rec("T5.9", "File CSV xuất ra có đúng cột, đúng số dòng của bảng hiển thị (mọi nút xuất CSV trên các màn hình có nút này)", bool(pairs) and not bad,
        f"{len(pairs) - len(bad)}/{len(pairs)} nút CSV khớp bảng" + (f"; lệch: {bad}" if bad else ""))


# ================================================================================================
# T6 — Hiệu năng
# ================================================================================================
def t6(a):
    res = rows(a, """SELECT experiment, query_id, variant, is_baseline, p95_ms, hash_match, speedup FROM bench.bm_result
                     WHERE run_id = (SELECT max(run_id) FROM bench.bm_result)""")
    rec("T6.1", "Đủ BM01, BM02, BM03 trong lần đo mới nhất", {r[0] for r in res} == {"BM01", "BM02", "BM03"}, f"{len(res)} cấu hình đo, lần đo {one(a, 'SELECT max(run_id) FROM bench.bm_result')[0]}")
    bad = [f"{r[1]}/{r[2]}" for r in res if not r[5]]
    rec("T6.2", "Kết quả mọi biến thể trùng hash với baseline (kết quả tương đương trước khi đo)", not bad, f"{len(res) - len(bad)}/{len(res)} trùng" + (f"; lệch {bad}" if bad else ""))
    plans = list((ROOT / "bench/results/plans").glob("*.json"))
    raws = list((ROOT / "bench/results").glob("raw_*.csv"))
    lines = sum(1 for _ in open(raws[-1], encoding="utf-8")) - 1 if raws else 0
    nobj = one(a, "SELECT count(*) FROM bench.bm_object")[0]
    rec("T6.3", "Có plan EXPLAIN JSON, lượt đo thô CSV và kích thước đối tượng", len(plans) >= len(res) and lines >= 15 * len(res) and nobj > 0,
        f"{len(plans)} plan JSON, {lines} lượt đo thô, {nobj} đối tượng có kích thước")
    best = {}
    for _, q, _, _, p95, _, _ in res:
        best[q] = min(best.get(q, 1e18), float(p95))
    base = {r[1]: float(r[4]) for r in res if r[3]}
    over = {q: v for q, v in best.items() if v > 3000}
    rec("T6.4", "p95 ≤ 3 s trên ~2 triệu dòng ở phương án tối ưu của MỌI truy vấn (baseline vượt 3 s được MV/index/partition xử lý)", not over,
        f"p95 tốt nhất theo truy vấn (ms): {dict(sorted((q, round(v, 1)) for q, v in best.items()))}; baseline vượt 3 s: {[q for q, v in base.items() if v > 3000]}")
    n_foi = one(a, "SELECT count(*) FROM bench.foi_noidx")[0]
    rec("T6.5", "Quy mô dữ liệu đo ≥ 2 triệu dòng (bảng nhân bản có seed, ghi rõ không phục vụ báo cáo)", n_foi >= 2_000_000, f"bench.foi_noidx = {n_foi} dòng")


# ================================================================================================
# T7 — Tái lập
# ================================================================================================
def t7(c):
    rd = ROOT / "README.md"
    txt = rd.read_text(encoding="utf-8") if rd.exists() else ""
    need = ["seed 42", "dw-scd-2026", "medium-ecommerce", "start_all.sh", "run.sh extract", "run.sh transform", "run.sh load",
            "run_tests", "batch_log", "etl.log", "docker"]
    miss = [k for k in need if k.lower() not in txt.lower()]
    rec("T7.1", "README.md nêu seed, phiên bản cấu hình mock, settings, lệnh chạy mock, lệnh ETL, kiểm thử, log batch", bool(txt) and not miss, f"thiếu: {miss}" if miss else f"đủ {len(need)} mục")
    paths = sorted({p for p in re.findall(r"`([\w./-]+\.(?:py|sh|sql|md|json))`", txt)})
    # tên tệp trần (không có thư mục, ví dụ trong bảng cấu trúc) được tìm theo tên trong các thư mục mã nguồn và tài liệu
    code_dirs = [ROOT / d for d in ("dw", "scripts", "dashboard", "bench", "docs")]
    gone = [p for p in paths if not (ROOT / p).exists() and not ("/" not in p and any(next(d.rglob(p), None) for d in code_dirs if d.exists()))]
    rec("T7.2", "Mọi đường dẫn tệp nêu trong README đều tồn tại", bool(paths) and not gone, f"{len(paths)} đường dẫn" + (f"; không thấy: {gone}" if gone else ""))
    snap = rows(c, "SELECT batch_id, source_snapshot FROM audit.batch_log WHERE status = 'SUCCESS' ORDER BY batch_id")
    rec("T7.3", "Mỗi batch SUCCESS ghi mốc nguồn (source_snapshot) và thời gian từng bước vào batch_log", all(s for _, s in snap), "; ".join(f"#{b}: {s}" for b, s in snap))
    diff = one(c, """SELECT count(*) FROM audit.batch_table_log a JOIN audit.batch_table_log b ON b.table_name = a.table_name AND b.stage = 'EXTRACT' AND b.batch_id = 2
                     WHERE a.batch_id = 1 AND a.stage = 'EXTRACT' AND a.checksum IS DISTINCT FROM b.checksum""")[0]
    tot = one(c, "SELECT count(*) FROM audit.batch_table_log WHERE batch_id = 1 AND stage = 'EXTRACT'")[0]
    rec("T7.4", "Tái lập Extract: nạp lại cùng mốc (batch 1 và batch 2) cho checksum trùng ở mọi bảng", diff == 0 and tot > 0, f"{tot - diff}/{tot} bảng trùng checksum")
    ev = list((ROOT / "docs/implementation").glob("*.md"))
    rec("T7.5", "Mỗi bước có ghi chép triển khai trong docs/implementation (đủ 8 mục) và bằng chứng chạy thật", len(ev) >= 14 and (ROOT / "docs/implementation/evidence").is_dir(),
        f"{len(ev)} tệp ghi chép, {len(list((ROOT / 'docs/implementation/evidence').glob('*.txt')))} tệp bằng chứng")


# ================================================================================================
def main():
    global GROUP
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="bỏ T3 (nạp lại batch) và các kiểm thử chạy lâu (dashboard, test_scd_load)")
    ap.add_argument("--only", help="chỉ chạy các nhóm, ví dụ T1,T4")
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else {f"T{i}" for i in range(1, 8)}
    t0 = time.time()
    with psycopg.connect(config.TARGET_URL, autocommit=True) as c, psycopg.connect(ANALYST_URL, autocommit=True) as a:
        b, wm = one(c, "SELECT batch_id, watermark_to FROM audit.batch_log WHERE status = %s ORDER BY batch_id DESC LIMIT 1", ("SUCCESS",))
        print(f"Kho dwh — batch SUCCESS mới nhất: #{b} (dữ liệu đến hết {wm})\n")
        for name, fn in (("T1", lambda: t1(c)), ("T2", lambda: t2(c)), ("T3", lambda: t3(c, a)), ("T4", lambda: t4(c, args.quick)),
                         ("T5", lambda: t5(c, a, args.quick)), ("T6", lambda: t6(a)), ("T7", lambda: t7(c))):
            if name not in only:
                continue
            GROUP = name
            print(f"\n=== {name} ===")
            if name == "T3" and args.quick:
                rec("T3", "Nạp lại batch (idempotent) và giả lập lỗi giữa batch", None, "bỏ qua (--quick)", status="SKIP")
                continue
            fn()
    print("\n=== TỔNG KẾT ===")
    for g in sorted({r[1] for r in RESULTS}):
        sub = [r for r in RESULTS if r[1] == g]
        print(f"{g}: {sum(r[3] == 'PASS' for r in sub)} PASS, {sum(r[3] == 'FAIL' for r in sub)} FAIL, {sum(r[3] == 'SKIP' for r in sub)} SKIP  / {len(sub)}")
    n_fail = sum(r[3] == "FAIL" for r in RESULTS)
    print(f"\nTổng: {sum(r[3] == 'PASS' for r in RESULTS)} PASS, {n_fail} FAIL, {sum(r[3] == 'SKIP' for r in RESULTS)} SKIP — {round(time.time() - t0)} s")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
