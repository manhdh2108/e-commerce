"""PLAN 5.2 — Extract (B1): OLTP + crawler Tiki → raw.* của một batch.

    cd <repo> && .venv/bin/python -m dw.etl.extract [--until YYYY-MM-DD] [--from YYYY-MM-DD] [--type RERUN]

Nguyên tắc (M1 §1.4, PLAN 5.2):
- Watermark: (watermark_from, watermark_to] là ngày mô phỏng ĐÃ HOÀN TẤT. watermark_to = last_day của Mock Studio;
  watermark_from = watermark_to của batch SUCCESS gần nhất (lần đầu: 2025-12-31).
- Đọc OLTP bằng dw_reader trong MỘT transaction REPEATABLE READ READ ONLY → mọi bảng cùng một snapshot
  dù engine mock đang ghi.
- Bảng giao dịch: theo cửa sổ thời gian. Bảng con không có cột thời gian (order_items, order_item_promotions):
  theo khóa cha. Bảng dimension/danh mục: full snapshot (để so SCD).
- raw bất biến (NV-01): chỉ INSERT, mỗi dòng có batch_id, extracted_at, row_hash = md5(dòng nguồn).
- Mỗi bảng ghi audit.batch_table_log (stage EXTRACT): số dòng, checksum = md5 các row_hash theo thứ tự khóa.
"""
import argparse
import datetime as dt
import json
import sqlite3
import sys
import time

import psycopg
import requests

from . import config

# ------------------------------------------------------------------------------------------------
# Đặc tả trích xuất. {F}/{T}: đầu/cuối cửa sổ dạng timestamp '…' (F gồm, T không gồm);
# {DF}/{DT}: cửa sổ dạng date (DF không gồm, DT gồm). ORDERS_IN_WINDOW: đơn phát sinh/đổi trong cửa sổ.
# ------------------------------------------------------------------------------------------------
TS = "({c} >= {F} AND {c} < {T})"
ORDERS_IN_WINDOW = """SELECT o.id FROM orders o
 WHERE (o.created_at >= {F} AND o.created_at < {T}) OR (o.updated_at >= {F} AND o.updated_at < {T})
    OR (o.completed_at >= {F} AND o.completed_at < {T}) OR (o.cancelled_at >= {F} AND o.cancelled_at < {T})
    -- payment đến muộn (vd. thu COD sau ngày hoàn tất) không cập nhật orders.updated_at (phát hiện ở bước 07)
    OR o.id IN (SELECT p.order_id FROM payments p WHERE p.transaction_time >= {F} AND p.transaction_time < {T})
    OR o.id IN (SELECT oi.order_id FROM order_items oi JOIN returns r ON r.order_item_id = oi.id
                WHERE (r.requested_at >= {F} AND r.requested_at < {T}) OR (r.approved_at >= {F} AND r.approved_at < {T})
                   OR (r.received_at >= {F} AND r.received_at < {T}) OR (r.refunded_at >= {F} AND r.refunded_at < {T}))"""

SPEC = [
    # (bảng nguồn, chế độ, điều kiện WHERE, khóa sắp xếp cho checksum, mục đích)
    ("products", "FULL", None, "id", "Dim_Product (SCD)"),
    ("categories", "FULL", None, "id", "Dim_Category"),
    ("sellers", "FULL", None, "id", "Dim_Seller (SCD)"),
    ("customers", "FULL", None, "id", "Dim_Customer (SCD)"),
    ("channels", "FULL", None, "id", "Dim_Channel"),
    ("payment_methods", "FULL", None, "id", "Dim_Payment_Method"),
    ("warehouses", "FULL", None, "id", "Dim_Warehouse"),
    ("marketing_campaigns", "FULL", None, "id", "Dim_Campaign"),
    ("promotions", "FULL", None, "id", "Dim_Promotion"),
    ("seller_commission_rates", "FULL", None, "id", "Hoa hồng theo thời gian"),
    ("orders", "WINDOW", "id IN (" + ORDERS_IN_WINDOW + ")", "id", "Fact_Order_Item"),
    ("order_items", "PARENT", "order_id IN (" + ORDERS_IN_WINDOW + ")", "id", "Fact_Order_Item (grain)"),
    ("payments", "PARENT", "order_id IN (" + ORDERS_IN_WINDOW + ")", "id", "Phương thức thanh toán"),
    ("order_item_promotions", "PARENT",
     "order_item_id IN (SELECT id FROM order_items WHERE order_id IN (" + ORDERS_IN_WINDOW + "))", "id", "Bridge khuyến mãi"),
    ("returns", "WINDOW", " OR ".join(TS.format(c=c, F="{F}", T="{T}") for c in
                                      ("requested_at", "approved_at", "received_at", "refunded_at")), "id", "is_returned"),
    ("inventory_daily_balance", "WINDOW", "balance_date > {DF} AND balance_date <= {DT}", "id", "Fact_Inventory_Snapshot"),
    ("inventory_movements", "WINDOW", TS.format(c="movement_date", F="{F}", T="{T}"), "id", "Nhập/bán/điều chỉnh"),
    ("ad_spend_logs", "WINDOW", "log_date > {DF} AND log_date <= {DT}", "id", "Fact_Ad_Spend"),
]

PG_TYPE = {"bigint": "bigint", "integer": "integer", "smallint": "smallint", "boolean": "boolean", "text": "text",
           "character varying": "text", "date": "date", "timestamp without time zone": "timestamp", "numeric": "numeric",
           "double precision": "double precision", "json": "json", "jsonb": "jsonb"}


def log(**kv):
    print(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), **kv}, ensure_ascii=False, default=str), flush=True)


def last_day():
    r = requests.get(config.MOCK_API + "/api/overview", timeout=30)
    r.raise_for_status()
    return r.json()["last_day"]


def source_columns(src, table):
    rows = src.execute("""SELECT column_name, data_type, numeric_precision, numeric_scale FROM information_schema.columns
                          WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position""", (table,)).fetchall()
    if not rows:
        raise RuntimeError(f"Bảng nguồn {table} không tồn tại")
    cols = []
    for name, typ, prec, scale in rows:
        t = PG_TYPE[typ]
        if t == "numeric" and prec:
            t = f"numeric({prec},{scale})"
        cols.append((name, t))
    return cols


def ensure_raw_table(dst, table, cols):
    """raw.<bảng> = 3 cột kỹ thuật + đúng các cột nguồn (kiểu nguồn). Thêm cột mới nếu nguồn có thêm cột."""
    body = ",\n  ".join(f'"{c}" {t}' for c, t in cols)
    dst.execute(f"""CREATE TABLE IF NOT EXISTS raw."{table}" (
  batch_id bigint NOT NULL REFERENCES audit.batch_log (batch_id),
  extracted_at timestamp NOT NULL,
  row_hash text NOT NULL,
  {body})""")
    dst.execute(f'CREATE INDEX IF NOT EXISTS "ix_raw_{table}_batch" ON raw."{table}" (batch_id)')
    for c, t in cols:
        dst.execute(f'ALTER TABLE raw."{table}" ADD COLUMN IF NOT EXISTS "{c}" {t}')
    protect_raw(dst, table)
    return body


def protect_raw(dst, table):
    """NV-01: raw bất biến — chặn UPDATE/DELETE/TRUNCATE ở mức DB, kể cả với chủ sở hữu bảng."""
    dst.execute("""CREATE OR REPLACE FUNCTION raw.forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'raw.% là bất biến (NV-01): không cho phép %', TG_TABLE_NAME, TG_OP; END $$""")
    dst.execute(f'CREATE OR REPLACE TRIGGER trg_raw_immutable BEFORE UPDATE OR DELETE ON raw."{table}" '
                'FOR EACH ROW EXECUTE FUNCTION raw.forbid_mutation()')
    dst.execute(f'CREATE OR REPLACE TRIGGER trg_raw_no_truncate BEFORE TRUNCATE ON raw."{table}" '
                'FOR EACH STATEMENT EXECUTE FUNCTION raw.forbid_mutation()')


def copy_table(src, dst, batch_id, extracted_at, table, where, cols):
    names = ", ".join(f'"{c}"' for c, _ in cols)
    q = (f"SELECT {batch_id}, '{extracted_at}'::timestamp, md5(t::text), {names} FROM public.\"{table}\" t"
         + (f" WHERE {where}" if where else ""))
    with src.cursor().copy(f"COPY ({q}) TO STDOUT") as cin, \
            dst.cursor().copy(f'COPY raw."{table}" (batch_id, extracted_at, row_hash, {names}) FROM STDIN') as cout:
        for chunk in cin:
            cout.write(chunk)


def table_stats(dst, batch_id, table, order_col):
    return dst.execute(f"""SELECT count(*), md5(coalesce(string_agg(row_hash, ',' ORDER BY "{order_col}"), ''))
                            FROM raw."{table}" WHERE batch_id = %s""", (batch_id,)).fetchone()


def extract_crawler(dst, batch_id, extracted_at):
    """Crawler Tiki: đường dẫn danh mục của từng sản phẩm (IR-04) + cặp gốc/lá."""
    dst.execute("""CREATE TABLE IF NOT EXISTS raw.tiki_product_category (
  batch_id bigint NOT NULL REFERENCES audit.batch_log (batch_id), extracted_at timestamp NOT NULL, row_hash text NOT NULL,
  product_id bigint NOT NULL, primary_category_path text, root_category_id bigint, leaf_category_id bigint,
  root_category_name text, product_category_name text)""")
    protect_raw(dst, "tiki_product_category")
    con = sqlite3.connect(f"file:{config.TIKI_DB}?mode=ro", uri=True)
    rows = con.execute("""SELECT r.product_id, json_extract(r.raw_json, '$.primary_category_path'),
                                 pc.root_category_id, pc.leaf_category_id, p.category_name,
                                 json_extract(r.raw_json, '$.visible_impression_info.amplitude.primary_category_name')
                          FROM product_raw r JOIN product_categories pc ON pc.product_id = r.product_id
                          JOIN products p ON p.id = r.product_id ORDER BY r.product_id""").fetchall()
    con.close()
    import hashlib
    with dst.cursor().copy("""COPY raw.tiki_product_category (batch_id, extracted_at, row_hash, product_id,
        primary_category_path, root_category_id, leaf_category_id, root_category_name, product_category_name) FROM STDIN""") as cp:
        for r in rows:
            cp.write_row((batch_id, extracted_at, hashlib.md5(repr(r).encode()).hexdigest(), *r))
    return len(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--until", help="watermark_to (mặc định: last_day của Mock Studio)")
    ap.add_argument("--from", dest="from_", help="watermark_from (mặc định: watermark_to của batch SUCCESS gần nhất)")
    ap.add_argument("--type", default="INCREMENTAL", choices=["INCREMENTAL", "RERUN", "TEST_ERRORS"])
    a = ap.parse_args(argv)

    mock_last = last_day()
    until = dt.date.fromisoformat(a.until or mock_last)
    if until > dt.date.fromisoformat(mock_last):
        sys.exit(f"--until {until} vượt last_day {mock_last}: không đọc ngày chưa hoàn tất (TV-05)")

    with psycopg.connect(config.TARGET_URL) as dst:
        if a.from_:
            frm = dt.date.fromisoformat(a.from_)
        else:
            frm = dst.execute("SELECT max(watermark_to) FROM audit.batch_log WHERE status = 'SUCCESS'").fetchone()[0] \
                  or dt.date.fromisoformat(config.INITIAL_WATERMARK)
        if frm >= until:
            log(event="nothing_to_do", watermark_from=frm, watermark_to=until)
            return None
        batch_id = dst.execute("""INSERT INTO audit.batch_log (batch_type, status, watermark_from, watermark_to, source_snapshot)
                                  VALUES (%s, 'RUNNING', %s, %s, %s) RETURNING batch_id""",
                               (a.type, frm, until, f"mock last_day={mock_last}")).fetchone()[0]
        dst.commit()  # batch_log tồn tại kể cả khi extract lỗi (để ghi FAILED)
    log(event="batch_start", batch_id=batch_id, watermark_from=frm, watermark_to=until, mock_last_day=mock_last)

    fmt = {"F": f"'{frm + dt.timedelta(days=1)} 00:00:00'::timestamp", "T": f"'{until + dt.timedelta(days=1)} 00:00:00'::timestamp",
           "DF": f"'{frm}'::date", "DT": f"'{until}'::date"}
    t0 = time.time()
    try:
        with psycopg.connect(config.SOURCE_URL) as src, psycopg.connect(config.TARGET_URL) as dst:
            # Một snapshot nhất quán cho mọi bảng nguồn (transaction mở ở câu lệnh đầu tiên)
            src.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
            src.read_only = True
            extracted_at = src.execute("SELECT now()::timestamp").fetchone()[0]
            for table, mode, where, order_col, purpose in SPEC:
                t1 = time.time()
                cols = source_columns(src, table)
                ensure_raw_table(dst, table, cols)
                copy_table(src, dst, batch_id, extracted_at, table, where.format(**fmt) if where else None, cols)
                n, checksum = table_stats(dst, batch_id, table, order_col)
                dst.execute("""INSERT INTO audit.batch_table_log (batch_id, stage, table_name, rows_read, rows_written, checksum)
                               VALUES (%s, 'EXTRACT', %s, %s, %s, %s)""", (batch_id, table, n, n, checksum))
                log(event="extracted", table=table, mode=mode, rows=n, checksum=checksum[:12], sec=round(time.time() - t1, 2), purpose=purpose)
            src.rollback()  # kết thúc snapshot đọc
            n = extract_crawler(dst, batch_id, extracted_at)
            n2, checksum = table_stats(dst, batch_id, "tiki_product_category", "product_id")
            dst.execute("""INSERT INTO audit.batch_table_log (batch_id, stage, table_name, rows_read, rows_written, checksum)
                           VALUES (%s, 'EXTRACT', 'tiki_product_category', %s, %s, %s)""", (batch_id, n, n2, checksum))
            log(event="extracted", table="tiki_product_category", mode="FULL", rows=n2, checksum=checksum[:12], purpose="Cây danh mục (IR-04)")
            for table, *_ in SPEC + [("tiki_product_category",)]:
                dst.execute(f'ANALYZE raw."{table}"')  # thống kê cho Transform
            dst.execute("UPDATE audit.batch_log SET status = 'EXTRACTED', message = %s WHERE batch_id = %s",
                        (f"extract {round(time.time() - t0, 1)} s", batch_id))
            dst.commit()  # raw của batch được ghi nguyên khối (all-or-nothing)
    except Exception as exc:
        with psycopg.connect(config.TARGET_URL) as dst:
            dst.execute("UPDATE audit.batch_log SET status = 'FAILED', finished_at = now(), message = %s WHERE batch_id = %s",
                        (f"EXTRACT: {exc}"[:2000], batch_id))
        log(event="batch_failed", batch_id=batch_id, error=str(exc))
        raise
    log(event="batch_extracted", batch_id=batch_id, sec=round(time.time() - t0, 1))
    return batch_id


if __name__ == "__main__":
    main()
