"""PLAN 7 — Thí nghiệm hiệu năng BM01 (Materialized View), BM02 (Partition), BM03 (Index).

    bash bench/run.sh                    # tạm dừng mock → setup + run → chạy lại mock (khuyên dùng)
    .venv/bin/python -m bench.run_bench setup        # dựng dữ liệu nhân bản trong schema bench
    .venv/bin/python -m bench.run_bench run [--only BM02] [--rounds 15] [--warmup 3]

Dữ liệu thí nghiệm (PLAN 7.1) — CHỈ phục vụ thí nghiệm, không phục vụ báo cáo:
  bench.foi_*   : nhân bản dw.fact_order_item 1.680 lần (~2 triệu dòng): bản k dịch ngày (k mod 36)×10 ngày trong 2026,
                  order_id += k×10^7, seller_key hoán vị tất định ((seller_key×31 + k×17) mod 481) + 1 → mỗi seller ~4.000 dòng.
                  Ghi vật lý theo thứ tự date_key (giống fact nạp tăng dần theo ngày).
  bench.inv_*   : nhân bản dw.fact_inventory_snapshot (12 ngày thật) 30 lần, dịch 12×j ngày → 360 ngày (~6,6 triệu dòng).
Quy trình đo (PLAN 7.3): kiểm tra kết quả tương đương (md5) → 3 lượt warm-up + 15 lượt đo, mỗi lượt xáo thứ tự biến thể
(seed 42), concurrency 1, đo thời gian phía client (execute + fetch hết kết quả) → median, p95, speedup = median baseline /
median biến thể; EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) lưu bench/results/plans/; lượt đo thô bench/results/raw_<run>.csv.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import pathlib
import random
import statistics
import subprocess
import time

import psycopg

from dw.etl import config

OUT = pathlib.Path(__file__).resolve().parent / "results"
COPIES_FOI, COPIES_INV = 1680, 30

FOI_COLS = """source_system, order_id, line_number, order_code, date_key, order_date_key, product_key, category_key, seller_key,
  customer_key, customer_profile_key, channel_key, payment_method_key, campaign_key, promotion_group_key, quantity, list_price,
  unit_price, list_amount, gross_amount, list_discount_amount, discount_amount, net_revenue, commission_rate, commission_amount,
  seller_net_amount, cost_amount_est, gross_margin_est, is_returned, line_count, batch_id"""
FOI_SELECT = f"""SELECT f.source_system, f.order_id + k::bigint * 10000000 AS order_id, f.line_number, f.order_code || '-' || k AS order_code,
  to_char(to_date(f.date_key::text, 'YYYYMMDD') + (k % 36) * 10, 'YYYYMMDD')::int AS date_key,
  to_char(to_date(f.order_date_key::text, 'YYYYMMDD') + (k % 36) * 10, 'YYYYMMDD')::int AS order_date_key,
  f.product_key, f.category_key,
  CASE WHEN f.seller_key > 0 THEN ((f.seller_key * 31 + k * 17) % 481) + 1 ELSE f.seller_key END AS seller_key,
  f.customer_key, f.customer_profile_key, f.channel_key, f.payment_method_key, f.campaign_key, f.promotion_group_key, f.quantity,
  f.list_price, f.unit_price, f.list_amount, f.gross_amount, f.list_discount_amount, f.discount_amount, f.net_revenue,
  f.commission_rate, f.commission_amount, f.seller_net_amount, f.cost_amount_est, f.gross_margin_est, f.is_returned, f.line_count, f.batch_id
FROM dw.fact_order_item f CROSS JOIN generate_series(0, {COPIES_FOI - 1}) k"""
INV_COLS = """date_key, product_key, warehouse_key, category_key, quantity_on_hand, quantity_reserved, quantity_available,
  qty_imported, qty_sold, qty_returned, qty_adjusted, stockout_flag, inventory_value_est, batch_id"""
INV_SELECT = f"""SELECT to_char(to_date(f.date_key::text, 'YYYYMMDD') + j * 12, 'YYYYMMDD')::int AS date_key, f.product_key, f.warehouse_key,
  f.category_key, f.quantity_on_hand, f.quantity_reserved, f.quantity_available, f.qty_imported, f.qty_sold, f.qty_returned,
  f.qty_adjusted, f.stockout_flag, f.inventory_value_est, f.batch_id
FROM dw.fact_inventory_snapshot f CROSS JOIN generate_series(0, {COPIES_INV - 1}) j"""

MV_SALES = """SELECT d.month_key, f.category_key, sum(f.net_revenue) AS net_revenue, sum(f.quantity) AS quantity,
       count(DISTINCT f.order_id) AS order_count
FROM {t} f JOIN dw.dim_date d USING (date_key) GROUP BY 1, 2"""
MV_INV = """WITH daily AS (SELECT f.date_key, d.month_key, f.category_key, sum(f.quantity_on_hand) AS on_hand, sum(f.qty_sold) AS sold
                FROM {t} f JOIN dw.dim_date d USING (date_key) GROUP BY 1, 2, 3)
SELECT month_key, category_key, (array_agg(on_hand ORDER BY date_key DESC))[1] AS end_on_hand,
       round(avg(on_hand), 2) AS avg_on_hand, sum(sold) AS qty_sold
FROM daily GROUP BY 1, 2"""


def partitioned(name, cols_src, select, order, pk=None):
    stmts = [f"DROP TABLE IF EXISTS bench.{name} CASCADE",
             f"CREATE TABLE bench.{name} (LIKE bench.{cols_src} INCLUDING DEFAULTS) PARTITION BY RANGE (date_key)"]
    for m in range(1, 13):
        lo, hi = f"2026{m:02d}01", (f"2026{m + 1:02d}01" if m < 12 else "20270101")
        stmts.append(f"CREATE TABLE bench.{name}_{lo[:6]} PARTITION OF bench.{name} FOR VALUES FROM ({lo}) TO ({hi})")
    stmts.append(f"CREATE TABLE bench.{name}_default PARTITION OF bench.{name} DEFAULT")
    stmts.append(f"INSERT INTO bench.{name} SELECT * FROM bench.{cols_src} ORDER BY {order}")
    if pk:
        stmts.append(f"ALTER TABLE bench.{name} ADD PRIMARY KEY ({pk})")
    return stmts


SETUP = [
    # (đối tượng, loại, [câu lệnh]) — thời gian dựng mỗi đối tượng được ghi vào bench.bm_object
    ("foi_noidx", "table", ["DROP TABLE IF EXISTS bench.foi_noidx CASCADE",
                            f"CREATE TABLE bench.foi_noidx AS {FOI_SELECT} ORDER BY 5, 2, 3"]),
    ("foi_idx_seller", "table+index", ["DROP TABLE IF EXISTS bench.foi_idx_seller",
                                       "CREATE TABLE bench.foi_idx_seller AS SELECT * FROM bench.foi_noidx"]),
    ("ix_foi_seller", "index", ["CREATE INDEX ix_foi_seller ON bench.foi_idx_seller (seller_key)"]),
    ("foi_idx_seller_date", "table+index", ["DROP TABLE IF EXISTS bench.foi_idx_seller_date",
                                            "CREATE TABLE bench.foi_idx_seller_date AS SELECT * FROM bench.foi_noidx"]),
    ("ix_foi_seller_date", "index", ["CREATE INDEX ix_foi_seller_date ON bench.foi_idx_seller_date (seller_key, date_key)"]),
    ("foi_idx_date_seller", "table+index", ["DROP TABLE IF EXISTS bench.foi_idx_date_seller",
                                            "CREATE TABLE bench.foi_idx_date_seller AS SELECT * FROM bench.foi_noidx"]),
    ("ix_foi_date_seller", "index", ["CREATE INDEX ix_foi_date_seller ON bench.foi_idx_date_seller (date_key, seller_key)"]),
    ("foi_part", "partitioned", partitioned("foi_part", "foi_noidx", "", "date_key, order_id, line_number")),
    ("mv_sales_month_category_scaled", "matview", [
        "DROP MATERIALIZED VIEW IF EXISTS bench.mv_sales_month_category_scaled",
        "CREATE MATERIALIZED VIEW bench.mv_sales_month_category_scaled AS " + MV_SALES.format(t="bench.foi_noidx"),
        "CREATE UNIQUE INDEX ON bench.mv_sales_month_category_scaled (month_key, category_key)"]),
    ("inv_plain", "table", ["DROP TABLE IF EXISTS bench.inv_plain CASCADE",
                            f"CREATE TABLE bench.inv_plain AS {INV_SELECT} ORDER BY 1, 2, 3",
                            "ALTER TABLE bench.inv_plain ADD PRIMARY KEY (date_key, product_key, warehouse_key)",
                            "CREATE INDEX ix_inv_plain_product ON bench.inv_plain (product_key)"]),
    ("inv_part", "partitioned", partitioned("inv_part", "inv_plain", "", "date_key, product_key, warehouse_key",
                                            pk="date_key, product_key, warehouse_key")
     + ["CREATE INDEX ix_inv_part_product ON bench.inv_part (product_key)"]),
    ("mv_inventory_month_category_scaled", "matview", [
        "DROP MATERIALIZED VIEW IF EXISTS bench.mv_inventory_month_category_scaled",
        "CREATE MATERIALIZED VIEW bench.mv_inventory_month_category_scaled AS " + MV_INV.format(t="bench.inv_plain"),
        "CREATE UNIQUE INDEX ON bench.mv_inventory_month_category_scaled (month_key, category_key)"]),
]

META = """
CREATE TABLE IF NOT EXISTS bench.bm_run (run_id text PRIMARY KEY, started_at timestamp NOT NULL, finished_at timestamp,
  env jsonb NOT NULL, params jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS bench.bm_object (object_name text PRIMARY KEY, kind text NOT NULL, row_count bigint,
  size_mb numeric(12,2), build_seconds numeric(10,3), built_at timestamp NOT NULL DEFAULT now(), note text);
CREATE TABLE IF NOT EXISTS bench.bm_result (
  run_id text NOT NULL, experiment text NOT NULL, query_id text NOT NULL, query_desc text NOT NULL, variant text NOT NULL,
  is_baseline boolean NOT NULL, runs int NOT NULL, median_ms numeric(12,3) NOT NULL, p95_ms numeric(12,3) NOT NULL,
  min_ms numeric(12,3), max_ms numeric(12,3), mean_ms numeric(12,3), speedup numeric(10,2),
  result_rows bigint, result_hash text, hash_match boolean, plan_ms numeric(12,3), shared_hit bigint, shared_read bigint,
  scan_rows bigint, relations_scanned int, plan_root text, scan_nodes text, indexes_used text, object_size_mb numeric(12,2),
  note text, measured_at timestamp NOT NULL DEFAULT now(), PRIMARY KEY (run_id, experiment, query_id, variant));
"""

S = "{seller}"  # điền seller có số dòng trung vị lúc chạy
EXPERIMENTS = [
    # (thí nghiệm, mã query, mô tả, [(biến thể, SQL)], ghi chú) — biến thể đầu tiên là baseline
    ("BM01", "Q1a", "Doanh thu tháng × danh mục — fact nhân bản ~2 triệu dòng", [
        ("Tổng hợp trực tiếp fact", MV_SALES.format(t="bench.foi_noidx") + " ORDER BY 1, 2"),
        ("Đọc MV", "SELECT month_key, category_key, net_revenue, quantity, order_count FROM bench.mv_sales_month_category_scaled ORDER BY 1, 2")],
     "MV lưu sẵn kết quả GROUP BY; chi phí dời sang lúc refresh (xem bm_object)."),
    ("BM01", "Q1b", "Doanh thu tháng × danh mục — dữ liệu THẬT (1.195 dòng)", [
        ("Tổng hợp trực tiếp fact", """SELECT d.month_key, f.category_key, sum(f.net_revenue), sum(f.quantity)
            FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key) GROUP BY 1, 2 ORDER BY 1, 2"""),
        ("Đọc MV mart (gộp kênh)", """SELECT month_key, category_key, sum(net_revenue), sum(quantity)
            FROM mart.mv_sales_month_category GROUP BY 1, 2 ORDER BY 1, 2""")],
     "Fact thật còn nhỏ: chênh lệch tuyệt đối không đáng kể — ghi trung thực."),
    ("BM01", "Q1c", "Tồn cuối tháng & bình quân × danh mục — tồn kho nhân bản ~6,6 triệu dòng", [
        ("Tổng hợp trực tiếp fact", MV_INV.format(t="bench.inv_plain") + " ORDER BY 1, 2"),
        ("Đọc MV", "SELECT month_key, category_key, end_on_hand, avg_on_hand, qty_sold FROM bench.mv_inventory_month_category_scaled ORDER BY 1, 2")],
     "Semi-additive: tồn cuối = ngày snapshot cuối tháng, không SUM qua ngày."),
    ("BM02", "Q2a", "Tồn kho theo ngày trong 1 tháng (06/2026)", [
        ("Bảng thường", "SELECT date_key, sum(quantity_on_hand), sum(qty_sold) FROM bench.inv_plain WHERE date_key BETWEEN 20260601 AND 20260630 GROUP BY 1 ORDER BY 1"),
        ("Partition tháng", "SELECT date_key, sum(quantity_on_hand), sum(qty_sold) FROM bench.inv_part WHERE date_key BETWEEN 20260601 AND 20260630 GROUP BY 1 ORDER BY 1")],
     "Cùng dữ liệu, cùng PK (date_key, product_key, warehouse_key) + index product_key."),
    ("BM02", "Q2b", "Tồn kho 1 ngày theo kho (15/06/2026)", [
        ("Bảng thường", "SELECT warehouse_key, sum(quantity_on_hand), sum(quantity_available) FROM bench.inv_plain WHERE date_key = 20260615 GROUP BY 1 ORDER BY 1"),
        ("Partition tháng", "SELECT warehouse_key, sum(quantity_on_hand), sum(quantity_available) FROM bench.inv_part WHERE date_key = 20260615 GROUP BY 1 ORDER BY 1")],
     "Truy vấn rất chọn lọc: cả hai đều dùng index; partition chỉ bớt chiều cao cây index."),
    ("BM02", "Q2c", "Doanh thu 1 tháng theo danh mục — fact bán nhân bản, KHÔNG index", [
        ("Bảng thường", "SELECT category_key, sum(net_revenue), sum(quantity) FROM bench.foi_noidx WHERE date_key BETWEEN 20260601 AND 20260630 GROUP BY 1 ORDER BY 1"),
        ("Partition tháng", "SELECT category_key, sum(net_revenue), sum(quantity) FROM bench.foi_part WHERE date_key BETWEEN 20260601 AND 20260630 GROUP BY 1 ORDER BY 1")],
     "Không có index: bảng thường phải seq scan cả năm; partition pruning chỉ đọc 1/12."),
    ("BM02", "Q2d", "Quét cả năm (không lọc ngày) — ca partition KHÔNG có lợi", [
        ("Bảng thường", "SELECT sum(quantity_on_hand), sum(qty_sold), count(*) FROM bench.inv_plain"),
        ("Partition tháng", "SELECT sum(quantity_on_hand), sum(qty_sold), count(*) FROM bench.inv_part")],
     "Không có điều kiện để cắt tỉa: kỳ vọng tương đương hoặc chậm hơn chút (Append 13 partition)."),
    ("BM03", "Q3a", "Doanh thu 1 seller trong 1 tháng (06/2026)", [
        ("Không index", f"SELECT sum(net_revenue), sum(quantity), count(*) FROM bench.foi_noidx WHERE seller_key = {S} AND date_key BETWEEN 20260601 AND 20260630"),
        ("Index (seller_key)", f"SELECT sum(net_revenue), sum(quantity), count(*) FROM bench.foi_idx_seller WHERE seller_key = {S} AND date_key BETWEEN 20260601 AND 20260630"),
        ("Index (seller_key, date_key)", f"SELECT sum(net_revenue), sum(quantity), count(*) FROM bench.foi_idx_seller_date WHERE seller_key = {S} AND date_key BETWEEN 20260601 AND 20260630"),
        ("Index (date_key, seller_key)", f"SELECT sum(net_revenue), sum(quantity), count(*) FROM bench.foi_idx_date_seller WHERE seller_key = {S} AND date_key BETWEEN 20260601 AND 20260630")],
     "Cột so sánh bằng (=) đứng trước cột khoảng (BETWEEN) cho phạm vi quét hẹp nhất."),
    ("BM03", "Q3b", "Doanh thu 1 seller cả năm", [
        ("Không index", f"SELECT sum(net_revenue), sum(quantity), count(*) FROM bench.foi_noidx WHERE seller_key = {S}"),
        ("Index (seller_key)", f"SELECT sum(net_revenue), sum(quantity), count(*) FROM bench.foi_idx_seller WHERE seller_key = {S}"),
        ("Index (seller_key, date_key)", f"SELECT sum(net_revenue), sum(quantity), count(*) FROM bench.foi_idx_seller_date WHERE seller_key = {S}"),
        ("Index (date_key, seller_key)", f"SELECT sum(net_revenue), sum(quantity), count(*) FROM bench.foi_idx_date_seller WHERE seller_key = {S}")],
     "Độ chọn lọc ~0,2%: index có seller_key đứng đầu dùng được; (date_key, seller_key) không dùng được tiền tố."),
    ("BM03", "Q3c", "Doanh thu toàn sàn 1 tuần (01–07/06/2026), không lọc seller", [
        ("Không index", "SELECT sum(net_revenue), sum(quantity), count(*) FROM bench.foi_noidx WHERE date_key BETWEEN 20260601 AND 20260607"),
        ("Index (seller_key)", "SELECT sum(net_revenue), sum(quantity), count(*) FROM bench.foi_idx_seller WHERE date_key BETWEEN 20260601 AND 20260607"),
        ("Index (seller_key, date_key)", "SELECT sum(net_revenue), sum(quantity), count(*) FROM bench.foi_idx_seller_date WHERE date_key BETWEEN 20260601 AND 20260607"),
        ("Index (date_key, seller_key)", "SELECT sum(net_revenue), sum(quantity), count(*) FROM bench.foi_idx_date_seller WHERE date_key BETWEEN 20260601 AND 20260607")],
     "Mở rộng PLAN 7.4: thứ tự cột index ghép — chỉ (date_key, seller_key) phục vụ lọc theo ngày."),
]
OBJ_OF_VARIANT = {"Index (seller_key)": "ix_foi_seller", "Index (seller_key, date_key)": "ix_foi_seller_date",
                  "Index (date_key, seller_key)": "ix_foi_date_seller"}


def log(**kw):
    print(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), **kw}, ensure_ascii=False, default=str), flush=True)


def size_mb(cur, name):
    r = cur.execute("""SELECT coalesce(sum(pg_total_relation_size(c.oid)), 0) / 1048576.0 FROM pg_class c
                       JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'bench'
                       AND (c.relname = %s OR c.oid IN (SELECT inhrelid FROM pg_inherits WHERE inhparent =
                            (SELECT oid FROM pg_class WHERE relname = %s AND relnamespace = 'bench'::regnamespace)))""",
                    (name, name)).fetchone()[0]
    return round(float(r), 2)


def setup():
    with psycopg.connect(config.TARGET_URL, autocommit=True) as con:
        cur = con.cursor()
        cur.execute(META)
        cur.execute("SET maintenance_work_mem = '512MB'")
        # /dev/shm của container chỉ 64 MB: bảo trì song song (VACUUM/CREATE INDEX) xin vùng nhớ chia sẻ lớn → lỗi
        # "could not resize shared memory segment". Chỉ áp dụng cho bước dựng dữ liệu, không cho lúc đo.
        cur.execute("SET max_parallel_maintenance_workers = 0")
        for name, kind, stmts in SETUP:
            t0 = time.time()
            for s in stmts:
                cur.execute(s)
            sec = time.time() - t0
            if kind != "index":
                t1 = time.time()
                cur.execute(f"VACUUM (ANALYZE, PARALLEL 0) bench.{name}")  # visibility map + thống kê (index-only scan, planner)
                note = f"VACUUM ANALYZE {time.time() - t1:.1f} s"
            else:
                note = "thời gian = CREATE INDEX"
            rows = None if kind == "index" else cur.execute(f"SELECT count(*) FROM bench.{name}").fetchone()[0]
            if kind == "index":
                mb = round(cur.execute("SELECT pg_relation_size(%s::regclass) / 1048576.0", (f"bench.{name}",)).fetchone()[0], 2)
            else:
                mb = size_mb(cur, name)
            cur.execute("""INSERT INTO bench.bm_object (object_name, kind, row_count, size_mb, build_seconds, note)
                           VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (object_name) DO UPDATE SET kind = EXCLUDED.kind,
                           row_count = EXCLUDED.row_count, size_mb = EXCLUDED.size_mb, build_seconds = EXCLUDED.build_seconds,
                           built_at = now(), note = EXCLUDED.note""", (name, kind, rows, mb, round(sec, 3), note))
            log(event="built", object=name, kind=kind, rows=rows, size_mb=mb, sec=round(sec, 2))
        # thời gian REFRESH (chi phí của MV, BM01)
        for mv in ("mv_sales_month_category_scaled", "mv_inventory_month_category_scaled"):
            t0 = time.time()
            cur.execute(f"REFRESH MATERIALIZED VIEW bench.{mv}")
            sec = time.time() - t0
            cur.execute("UPDATE bench.bm_object SET note = note || %s WHERE object_name = %s", (f"; REFRESH {sec:.2f} s", mv))
            log(event="refreshed", mv=mv, sec=round(sec, 2))
        cur.execute("GRANT SELECT ON ALL TABLES IN SCHEMA bench TO dw_analyst")


def env(cur):
    keys = ("server_version", "shared_buffers", "work_mem", "effective_cache_size", "max_parallel_workers_per_gather", "jit",
            "random_page_cost", "enable_partition_pruning", "maintenance_work_mem", "synchronous_commit")
    e = {k: cur.execute(f"SHOW {k}").fetchone()[0] for k in keys}
    try:
        info = subprocess.run(["docker", "exec", "scripts-mock-postgres-1", "sh", "-c", "nproc; grep MemTotal /proc/meminfo"],
                              capture_output=True, text=True, timeout=20).stdout.split()
        e.update(cpu=info[0], mem_kb=info[2])
    except Exception:  # noqa: BLE001
        pass
    e["objects"] = {r[0]: {"rows": r[1], "mb": float(r[2])} for r in
                    cur.execute("SELECT object_name, row_count, size_mb FROM bench.bm_object").fetchall()}
    return e


def digest(rows):
    return hashlib.md5(repr([tuple(str(v) for v in r) for r in rows]).encode()).hexdigest()


def walk(node, acc):
    t = node.get("Node Type", "")
    if "Scan" in t:
        acc["scans"].append(t + (f" {node['Relation Name']}" if node.get("Relation Name") else ""))
        acc["rels"].add(node.get("Relation Name"))
        acc["rows"] += node.get("Actual Rows", 0) * node.get("Actual Loops", 1)
        if node.get("Index Name"):
            acc["idx"].add(node["Index Name"])
    for c in node.get("Plans", []):
        walk(c, acc)


def explain(cur, sql, path):
    plan = cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql).fetchone()[0]
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    root = plan[0]["Plan"]
    acc = {"scans": [], "rels": set(), "rows": 0, "idx": set()}
    walk(root, acc)
    scans = sorted(set(acc["scans"]))
    return dict(plan_ms=plan[0]["Execution Time"], shared_hit=root.get("Shared Hit Blocks", 0),
                shared_read=root.get("Shared Read Blocks", 0), scan_rows=int(acc["rows"]),
                relations_scanned=len(acc["rels"] - {None}), plan_root=root["Node Type"],
                scan_nodes="; ".join(scans[:6]) + (f"; … (+{len(scans) - 6})" if len(scans) > 6 else ""),
                indexes_used=", ".join(sorted(acc["idx"])) or None)


def run(only, rounds, warmup):
    run_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    (OUT / "plans").mkdir(parents=True, exist_ok=True)
    rnd = random.Random(42)
    raw = []
    with psycopg.connect(config.TARGET_URL, autocommit=True) as con:
        cur = con.cursor()
        cur.execute(META)
        seller = cur.execute("""SELECT seller_key FROM (SELECT seller_key, count(*) n FROM bench.foi_noidx WHERE seller_key > 0
                                GROUP BY 1) x ORDER BY n, seller_key OFFSET (SELECT count(DISTINCT seller_key) / 2 FROM bench.foi_noidx
                                WHERE seller_key > 0) LIMIT 1""").fetchone()[0]
        e = env(cur)
        params = dict(rounds=rounds, warmup=warmup, seed=42, seller_key=seller, only=only, copies_foi=COPIES_FOI, copies_inv=COPIES_INV)
        cur.execute("INSERT INTO bench.bm_run VALUES (%s, now(), NULL, %s, %s)", (run_id, json.dumps(e), json.dumps(params)))
        (OUT / f"env_{run_id}.json").write_text(json.dumps({"env": e, "params": params}, ensure_ascii=False, indent=1), encoding="utf-8")
        log(event="run_start", run_id=run_id, seller_key=seller, **{k: e[k] for k in ("server_version", "shared_buffers", "jit")})
        for exp, qid, desc, variants, note in EXPERIMENTS:
            if only and exp not in only:
                continue
            variants = [(v, sql.replace(S, str(seller))) for v, sql in variants]
            # 1) kết quả tương đương
            hashes, nrows = {}, {}
            for v, sql in variants:
                rows = cur.execute(sql).fetchall()
                hashes[v], nrows[v] = digest(rows), len(rows)
            base_hash = hashes[variants[0][0]]
            # 2) warm-up + đo, xáo thứ tự mỗi lượt
            times = {v: [] for v, _ in variants}
            for r in range(warmup + rounds):
                order = variants[:]
                rnd.shuffle(order)
                for v, sql in order:
                    t0 = time.perf_counter()
                    cur.execute(sql).fetchall()
                    ms = (time.perf_counter() - t0) * 1000
                    if r >= warmup:
                        times[v].append(ms)
                        raw.append(dict(run_id=run_id, experiment=exp, query_id=qid, variant=v, round=r - warmup + 1, ms=round(ms, 3)))
            base_med = statistics.median(times[variants[0][0]])
            for i, (v, sql) in enumerate(variants):
                ts = sorted(times[v])
                med = statistics.median(ts)
                p95 = ts[min(len(ts) - 1, round(0.95 * (len(ts) - 1)))]
                safe = "".join(ch if ch.isalnum() else "_" for ch in v)
                pl = explain(cur, sql, OUT / "plans" / f"{run_id}_{qid}_{safe}.json")
                obj = OBJ_OF_VARIANT.get(v)
                mb = cur.execute("SELECT size_mb FROM bench.bm_object WHERE object_name = %s", (obj,)).fetchone()[0] if obj else None
                cur.execute("""INSERT INTO bench.bm_result (run_id, experiment, query_id, query_desc, variant, is_baseline, runs,
                        median_ms, p95_ms, min_ms, max_ms, mean_ms, speedup, result_rows, result_hash, hash_match, plan_ms,
                        shared_hit, shared_read, scan_rows, relations_scanned, plan_root, scan_nodes, indexes_used, object_size_mb, note)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (run_id, exp, qid, desc, v, i == 0, len(ts), med, p95, ts[0], ts[-1], statistics.mean(ts),
                             round(base_med / med, 2) if med else None, nrows[v], hashes[v], hashes[v] == base_hash,
                             pl["plan_ms"], pl["shared_hit"], pl["shared_read"], pl["scan_rows"], pl["relations_scanned"],
                             pl["plan_root"], pl["scan_nodes"], pl["indexes_used"], mb, note))
                log(event="measured", exp=exp, q=qid, variant=v, median_ms=round(med, 2), p95_ms=round(p95, 2),
                    speedup=round(base_med / med, 2), hash_match=hashes[v] == base_hash, rels=pl["relations_scanned"],
                    hit=pl["shared_hit"], read=pl["shared_read"], idx=pl["indexes_used"])
        cur.execute("UPDATE bench.bm_run SET finished_at = now() WHERE run_id = %s", (run_id,))
    with open(OUT / f"raw_{run_id}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(raw[0]))
        w.writeheader()
        w.writerows(raw)
    log(event="run_done", run_id=run_id, measurements=len(raw))
    return run_id


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["setup", "run", "all", "clean"])
    ap.add_argument("--only", nargs="*", help="BM01 BM02 BM03")
    ap.add_argument("--rounds", type=int, default=15)
    ap.add_argument("--warmup", type=int, default=3)
    a = ap.parse_args()
    if a.cmd == "clean":  # xóa dữ liệu nhân bản (~5 GB trong docker_data.vhdx trên ổ D), GIỮ bm_run/bm_object/bm_result
        with psycopg.connect(config.TARGET_URL, autocommit=True) as con:
            for name, kind, _ in reversed(SETUP):
                if kind == "matview":
                    con.execute(f"DROP MATERIALIZED VIEW IF EXISTS bench.{name}")
                elif kind != "index":
                    con.execute(f"DROP TABLE IF EXISTS bench.{name} CASCADE")
            log(event="cleaned", objects=[n for n, k, _ in SETUP if k != "index"])
        return
    if a.cmd in ("setup", "all"):
        setup()
    if a.cmd in ("run", "all"):
        run(a.only, a.rounds, a.warmup)


if __name__ == "__main__":
    main()
