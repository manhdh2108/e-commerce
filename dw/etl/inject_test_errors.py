"""PLAN 5.3.5 — Tạo batch kiểm thử có lỗi cài sẵn để chứng minh cơ chế cách ly (G4: OLTP quá sạch).

    cd <repo> && .venv/bin/python -m dw.etl.inject_test_errors --source-batch 1

- KHÔNG bao giờ ghi vào OLTP. Chỉ tạo batch mới (batch_type = TEST_ERRORS) trong raw: sao chép raw của batch
  nguồn, các dòng bị chọn được chèn lại ở dạng lỗi (raw vẫn chỉ INSERT — bất biến).
- Chọn dòng theo thứ tự id cố định → tái lập được.
Ca lỗi (kỳ vọng quy tắc bắt được):
  E1  5 dòng hàng quantity = -1                    → DQ-02 (và DQ-03)
  E2  3 dòng hàng net_amount lệch +1.000đ          → DQ-03
  E3  4 bản ghi chi phí QC channel_code = 'TIKTOK' → DQ-04
  E4  3 dòng tồn kho SKU không tồn tại             → DQ-04
  E5  2 đơn Completed thiếu completed_at            → DQ-05 (mọi dòng của 2 đơn)
  E6  5 khách bị trùng (bản sao updated_at +1 ngày) → DQ-07 (giữ bản mới nhất)
  E7  3 khách email sai định dạng                   → DQ-08 (WARN, vẫn nạp)
"""
import argparse
import json

import psycopg

from . import config
from .extract import log

RAW_TABLES = ["products", "categories", "sellers", "customers", "channels", "payment_methods", "warehouses",
              "marketing_campaigns", "promotions", "seller_commission_rates", "orders", "order_items", "payments",
              "order_item_promotions", "returns", "inventory_daily_balance", "inventory_movements", "ad_spend_logs",
              "tiki_product_category"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-batch", type=int, default=1)
    a = ap.parse_args(argv)
    s = a.source_batch
    with psycopg.connect(config.TARGET_URL) as con:
        cur = con.cursor()
        wf, wt = cur.execute("SELECT watermark_from, watermark_to FROM audit.batch_log WHERE batch_id = %s", (s,)).fetchone()
        b = cur.execute("""INSERT INTO audit.batch_log (batch_type, status, watermark_from, watermark_to, source_snapshot, message)
                           VALUES ('TEST_ERRORS', 'EXTRACTED', %s, %s, %s, 'batch kiểm thử cách ly lỗi — không phải dữ liệu nguồn')
                           RETURNING batch_id""", (wf, wt, f"copy of batch {s} + injected errors")).fetchone()[0]

        # Chọn dòng sẽ bị làm lỗi (cố định theo id)
        sales = """SELECT oi.id FROM raw.order_items oi JOIN raw.orders o ON o.id = oi.order_id AND o.batch_id = oi.batch_id
                   WHERE oi.batch_id = %s AND o.order_status = 'Completed' AND oi.item_status = 'Fulfilled'
                     AND oi.discount_amount = 0 ORDER BY oi.id"""
        lines = [r[0] for r in cur.execute(sales, (s,)).fetchall()]
        e1, e2 = lines[:5], lines[5:8]
        e5 = [r[0] for r in cur.execute("""SELECT o.id FROM raw.orders o WHERE o.batch_id = %s AND o.order_status = 'Completed'
                 AND o.id NOT IN (SELECT order_id FROM raw.order_items WHERE id = ANY(%s)) ORDER BY o.id LIMIT 2""",
                                        (s, e1 + e2)).fetchall()]
        e3 = [r[0] for r in cur.execute("SELECT id FROM raw.ad_spend_logs WHERE batch_id = %s ORDER BY id LIMIT 4", (s,)).fetchall()]
        e6 = [r[0] for r in cur.execute("SELECT id FROM raw.customers WHERE batch_id = %s ORDER BY id LIMIT 5", (s,)).fetchall()]
        e7 = [r[0] for r in cur.execute("SELECT id FROM raw.customers WHERE batch_id = %s ORDER BY id OFFSET 5 LIMIT 3", (s,)).fetchall()]
        exclude = {"order_items": e1 + e2, "orders": e5, "ad_spend_logs": e3, "customers": e7}

        # 1) Sao chép raw nguyên trạng, trừ các dòng sẽ được chèn lại ở dạng lỗi
        for t in RAW_TABLES:
            cols = [r[0] for r in cur.execute("""SELECT column_name FROM information_schema.columns WHERE table_schema='raw'
                      AND table_name=%s AND column_name <> 'batch_id' ORDER BY ordinal_position""", (t,)).fetchall()]
            cl = ", ".join(f'"{c}"' for c in cols)
            where = "batch_id = %s" + (" AND id <> ALL(%s)" if t in exclude else "")
            params = (s, exclude[t]) if t in exclude else (s,)
            cur.execute(f'INSERT INTO raw."{t}" (batch_id, {cl}) SELECT {b}, {cl} FROM raw."{t}" WHERE {where}', params)

        def reinsert(table, ids, set_expr):
            cols = [r[0] for r in cur.execute("""SELECT column_name FROM information_schema.columns WHERE table_schema='raw'
                      AND table_name=%s AND column_name NOT IN ('batch_id','row_hash') ORDER BY ordinal_position""", (table,)).fetchall()]
            sel = ", ".join(set_expr.get(c, f'"{c}"') for c in cols)
            cl = ", ".join(f'"{c}"' for c in cols)
            cur.execute(f"""INSERT INTO raw."{table}" (batch_id, row_hash, {cl})
                            SELECT {b}, 'TEST_ERROR', {sel} FROM raw."{table}" WHERE batch_id = %s AND id = ANY(%s)""", (s, ids))
            return cur.rowcount

        n = {}
        n["E1"] = reinsert("order_items", e1, {"quantity": "-1"})
        n["E2"] = reinsert("order_items", e2, {"net_amount": "net_amount + 1000"})
        n["E3"] = reinsert("ad_spend_logs", e3, {"channel_code": "'TIKTOK'"})
        n["E5"] = reinsert("orders", e5, {"completed_at": "NULL"})
        n["E7"] = reinsert("customers", e7, {"email": "'email-sai-dinh-dang'"})
        # E6: bản sao trùng khóa (bản gốc đã được sao chép ở bước 1) với updated_at mới hơn
        n["E6"] = reinsert("customers", e6, {"updated_at": "coalesce(updated_at, registration_date) + interval '1 day'"})
        # E4: 3 dòng tồn kho có SKU không tồn tại (id mới, không trùng)
        cur.execute(f"""INSERT INTO raw.inventory_daily_balance (batch_id, extracted_at, row_hash, id, balance_date, warehouse_id,
                          sku, quantity_on_hand, quantity_reserved)
                        SELECT {b}, extracted_at, 'TEST_ERROR', -id, balance_date, warehouse_id, 'SKU-KHONG-TON-TAI-' || id, 10, 0
                        FROM raw.inventory_daily_balance WHERE batch_id = %s ORDER BY id LIMIT 3""", (s,))
        n["E4"] = cur.rowcount
        lines_e5 = cur.execute("SELECT count(*) FROM raw.order_items WHERE batch_id = %s AND order_id = ANY(%s)", (b, e5)).fetchone()[0]
        for t in RAW_TABLES:
            cur.execute(f'ANALYZE raw."{t}"')
        con.commit()
    expect = {"E1 DQ-02": e1, "E2 DQ-03": e2, "E3 DQ-04": e3, "E5 DQ-05 orders": e5, "E6 DQ-07": e6, "E7 DQ-08": e7}
    log(event="test_batch_created", batch_id=b, source_batch=s, injected=n, e5_order_lines=lines_e5,
        ids=json.loads(json.dumps(expect)))
    return b


if __name__ == "__main__":
    main()
