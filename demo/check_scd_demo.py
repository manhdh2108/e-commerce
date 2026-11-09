"""Kiểm tra kết quả SCD trên dwh_demo theo danh sách thay đổi ở mock_oltp_demo.demo.case_log. Chỉ đọc.

    cd <repo> && .venv/bin/python -m demo.check_scd_demo
"""
import psycopg

SRC = "postgresql://mock:local_mock_only@127.0.0.1:55432/mock_oltp_demo"
DW = "postgresql://dw_analyst:dw_analyst_local@127.0.0.1:55432/dwh_demo"
RESULTS = []


def check(code, name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'} {code} {name}" + (f"\n       {detail}" if detail else ""))


def versions(cur, dim, sk, bk, entity_id, col):
    return cur.execute(f"""SELECT {sk}, {col}, valid_from, valid_to, is_current FROM dw.{dim}
                           WHERE {bk} = %s ORDER BY valid_from""", (entity_id,)).fetchall()


def scd2(cur, code, dim, sk, bk, entity_id, col, old, new, e, fact_col):
    v = versions(cur, dim, sk, bk, entity_id, col)
    ok = (len(v) == 2 and str(v[0][1]) == old and str(v[1][1]) == new and v[0][3] == e and v[1][2] == e
          and not v[0][4] and v[1][4])
    check(code, f"{dim}: 2 phiên bản, đóng và mở đúng ngày {e}", ok, str([(str(x[1]), str(x[2]), str(x[3]), x[4]) for x in v]))
    if fact_col and len(v) == 2:
        k = [x[0] for x in v]
        r = cur.execute(f"""SELECT {fact_col}, min(date_key), max(date_key), count(*), sum(net_revenue)
                            FROM dw.fact_order_item WHERE {fact_col} = ANY(%s) GROUP BY 1""", (k,)).fetchall()
        day = int(e.strftime("%Y%m%d"))
        got = {x[0]: x for x in r}
        ok_old = k[0] in got and got[k[0]][2] < day
        ok_new = k[1] in got and got[k[1]][1] >= day
        check(code, "Fact: đơn trước ngày đổi trỏ khóa cũ, từ ngày đổi trỏ khóa mới", ok_old and ok_new,
              "; ".join(f"khóa {x[0]}: {x[1]}–{x[2]}, {x[3]} dòng, {x[4]:,.0f} đ" for x in r))


def main():
    with psycopg.connect(SRC) as s:
        cases = {r[0]: r for r in s.execute(
            "SELECT code, technique, entity, entity_id, attr, old_value, new_value, effective_date FROM demo.case_log")}
    with psycopg.connect(DW) as con:
        cur = con.cursor()
        b = cur.execute("SELECT max(batch_id), max(status) FROM audit.batch_log WHERE status = 'SUCCESS'").fetchone()
        print(f"Kho demo: batch SUCCESS mới nhất {b[0]}\n")
        by = lambda c: cases[c]

        _, _, _, i, _, old, new, e = by("S1")
        scd2(cur, "S1", "dim_seller", "seller_key", "seller_id", i, "tier", old, new, e, "seller_key")
        r = cur.execute("SELECT current_tier, previous_tier, tier_changed_on FROM dw.dim_seller_tier_t3 WHERE seller_id = %s", (i,)).fetchone()
        check("S1", "SCD3: hạng hiện tại, hạng trước và ngày đổi", r == (new, old, e), str(r))

        _, _, _, i, _, old, new, e = by("S2")
        v = versions(cur, "dim_seller", "seller_key", "seller_id", i, "province_name")
        old_label, new_label = v[0][1], v[-1][1]
        scd2(cur, "S2", "dim_seller", "seller_key", "seller_id", i, "province_name", old_label, new_label, e, "seller_key")
        check("S2", "Tỉnh phiên bản mới đúng giá trị đã đổi", new_label == new, f"{old_label} → {new_label}")

        _, _, _, i, _, old, new, e = by("S3")
        r = cur.execute("SELECT count(*), max(shop_name) FROM dw.dim_seller WHERE seller_id = %s", (i,)).fetchone()
        check("S3", "SCD1 tên shop: vẫn 1 phiên bản, tên mới", r == (1, new), str(r))

        _, _, _, i, _, old, new, e = by("S4")
        scd2(cur, "S4", "dim_seller", "seller_key", "seller_id", i, "status", old, new, e, "seller_key")
        r = cur.execute("""SELECT count(*) FROM dw.dim_product WHERE seller_id = %s AND is_current AND is_active""", (i,)).fetchone()[0]
        n = cur.execute("""SELECT count(*) FROM dw.dim_product WHERE seller_id = %s AND is_current AND NOT is_active AND valid_from = %s""", (i, e)).fetchone()[0]
        check("S4", "SCD2 is_active: sản phẩm của seller bị khóa có phiên bản ngừng bán", r == 0 and n > 0, f"{n} sản phẩm ngừng bán, {r} còn bán")

        _, _, _, i, _, old, new, e = by("C1")
        v = versions(cur, "dim_customer", "customer_key", "customer_id", i, "province_name")
        scd2(cur, "C1", "dim_customer", "customer_key", "customer_id", i, "province_name", v[0][1], v[-1][1], e, "customer_key")
        check("C1", "Tỉnh phiên bản mới đúng giá trị đã đổi", v[-1][1] == new, f"{v[0][1]} → {v[-1][1]}")

        _, _, _, i, _, old, new, e = by("C2")
        r = cur.execute("SELECT count(*), max(full_name) FROM dw.dim_customer WHERE customer_id = %s", (i,)).fetchone()
        check("C2", "SCD1 tên khách: vẫn 1 phiên bản, tên mới", r == (1, new), str(r))

        _, _, _, i, _, old, new, e = by("C3")
        n = cur.execute("SELECT count(*) FROM dw.dim_customer WHERE customer_id = %s", (i,)).fetchone()[0]
        r = cur.execute("""SELECT f.batch_id, p.membership_tier, count(*), min(f.date_key), max(f.date_key)
            FROM dw.fact_order_item f JOIN dw.dim_customer c USING (customer_key)
            JOIN dw.dim_customer_profile p USING (customer_profile_key)
            WHERE c.customer_id = %s GROUP BY 1, 2 ORDER BY 1""", (i,)).fetchall()
        tiers = {x[1] for x in r}
        check("C3", "Mini-dimension: dim_customer 1 dòng; fact có hồ sơ hạng cũ và hạng mới", n == 1 and {old, new} <= tiers,
              f"dim_customer {n} dòng; " + "; ".join(f"batch {x[0]}: {x[1]}, {x[2]} dòng, {x[3]}–{x[4]}" for x in r))

        _, _, _, i, _, old, new, e = by("P1")
        scd2(cur, "P1", "dim_product", "product_key", "product_id", i, "list_price", old, new, e, "product_key")

        _, _, _, i, _, old, new, e = by("P2")
        v = versions(cur, "dim_product", "product_key", "product_id", i, "category_key")
        scd2(cur, "P2", "dim_product", "product_key", "product_id", i, "category_key", old, new, e, "product_key")
        r = cur.execute("""SELECT category_key, count(*) FROM dw.fact_order_item WHERE product_key = ANY(%s) GROUP BY 1 ORDER BY 1""",
                        ([x[0] for x in v],)).fetchall()
        check("P2", "Fact: doanh thu nằm ở cả danh mục cũ và mới", len(r) == 2, str(r))

        # Toàn vẹn và số liệu tổng
        for dim, bk in (("dim_product", "product_id"), ("dim_seller", "seller_id"), ("dim_customer", "customer_id")):
            bad = cur.execute(f"SELECT count(*) FROM (SELECT {bk} FROM dw.{dim} GROUP BY 1 HAVING count(*) FILTER (WHERE is_current) <> 1) x").fetchone()[0]
            lap = cur.execute(f"""SELECT count(*) FROM dw.{dim} a JOIN dw.{dim} c ON a.{bk} = c.{bk} AND a.valid_from < c.valid_from
                                  WHERE a.valid_to > c.valid_from""").fetchone()[0]
            check("INT", f"{dim}: mỗi khóa đúng 1 current, không chồng lấn", bad == 0 and lap == 0, f"sai current {bad}, chồng lấn {lap}")
        r = cur.execute("""SELECT count(*) FILTER (WHERE passed), count(*) FROM audit.reconciliation
                           WHERE batch_id = (SELECT max(batch_id) FROM audit.batch_log WHERE status = 'SUCCESS')""").fetchone()
        check("INT", "Đối soát batch demo đạt toàn bộ", r[0] == r[1] and r[1] > 0, f"{r[0]}/{r[1]}")
    print(f"\n{sum(RESULTS)}/{len(RESULTS)} PASS")
    raise SystemExit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
