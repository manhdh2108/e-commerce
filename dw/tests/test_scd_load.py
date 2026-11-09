"""Kiểm thử SCD1/SCD2/SCD3 của bước Load bằng ca có kiểm soát (PLAN 4.2: "logic SCD2 vẫn cài và kiểm thử bằng ca
có kiểm soát ở stg"; tiêu chí T4). Chạy TRONG MỘT TRANSACTION RỒI ROLLBACK — kho không đổi.

    cd <repo> && .venv/bin/python -m dw.tests.test_scd_load

Kịch bản (dựa trên batch SUCCESS mới nhất, mặc định batch 4):
  Batch giả X1 (hiệu lực 2026-02-01):
    customer A  đổi tỉnh             → SCD2: đóng bản cũ, mở bản mới
    customer B  đổi tên              → SCD1: ghi đè, không thêm phiên bản
    seller S    đổi hạng             → SCD2 dim_seller + SCD3 dim_seller_tier_t3
    product P   đổi giá + đổi tên    → SCD2 (giá) và SCD1 (tên ghi đè cả phiên bản cũ)
  Batch giả X2:
    seller S    đổi hạng lần nữa cùng ngày 2026-02-01 → sửa tại chỗ (không thêm phiên bản)
    customer A  đổi tỉnh với ngày 2026-01-20 (< 2026-02-01) → đến muộn: cách ly DQ-23, không sửa hồi tố
  Tra cứu theo thời điểm: product P ngày 2026-01-15 và 2026-02-05 phải ra hai product_key khác nhau.
"""
import psycopg

from dw.etl import config
from dw.etl import load as L

X1, X2 = 900001, 900002
CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def copy_batch(cur, src, dst):
    for t in ("product", "seller", "customer"):
        cols = [r[0] for r in cur.execute("""SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'stg' AND table_name = %s AND column_name <> 'batch_id' ORDER BY ordinal_position""", (t,))]
        cur.execute(f"INSERT INTO stg.{t} (batch_id, {', '.join(cols)}) SELECT {dst}, {', '.join(cols)} FROM stg.{t} WHERE batch_id = {src}")
    cur.execute(f"""INSERT INTO audit.batch_log (batch_id, batch_type, status, watermark_from, watermark_to, message)
                    VALUES ({dst}, 'TEST_ERRORS', 'TRANSFORMED', '2026-01-31', '2026-02-01', 'test_scd_load (rollback)')""")


def run_dims(cur, b):
    out = {}
    for dim, sk, bk, scd1, scd2, select in L.SCD_DIMS:
        out[dim] = L.load_scd(cur, b, dim, sk, bk, scd1, scd2, select)
    out["t3"] = L.load_seller_t3(cur, b)
    return out


def main():
    with psycopg.connect(config.TARGET_URL) as con:
        cur = con.cursor()
        base = cur.execute("SELECT max(batch_id) FROM audit.batch_log WHERE status = 'SUCCESS'").fetchone()[0]
        A, B = cur.execute(f"SELECT min(customer_id), max(customer_id) FROM stg.customer WHERE batch_id = {base}").fetchone()
        S = cur.execute(f"SELECT min(seller_id) FROM stg.seller WHERE batch_id = {base}").fetchone()[0]
        P = cur.execute(f"SELECT min(product_id) FROM stg.product WHERE batch_id = {base}").fetchone()[0]
        before = {t: cur.execute(f"SELECT count(*) FROM dw.{t}").fetchone()[0] for t in ("dim_product", "dim_seller", "dim_customer")}
        prov = cur.execute(f"SELECT province_code FROM stg.customer WHERE batch_id = {base} AND customer_id = {A}").fetchone()[0]
        newp = cur.execute(f"""SELECT province_code, province_name, region FROM stg.map_province
                               WHERE province_code <> '{prov}' ORDER BY province_code LIMIT 1""").fetchone()
        tier = cur.execute(f"SELECT tier FROM stg.seller WHERE batch_id = {base} AND seller_id = {S}").fetchone()[0]
        t1 = "Mall" if tier != "Mall" else "Preferred"
        t2 = "Normal" if t1 != "Normal" and tier != "Normal" else "Preferred"
        print(f"base batch {base}; customer A={A}, B={B}; seller S={S} ({tier}→{t1}→{t2}); product P={P}")

        # ---------- X1 ----------
        copy_batch(cur, base, X1)
        cur.execute(f"""UPDATE stg.customer SET province_code = %s, province_name = %s, region = %s,
                        scd2_hash = md5(%s), effective_date = '2026-02-01' WHERE batch_id = {X1} AND customer_id = {A}""",
                    (newp[0], newp[1], newp[2], newp[0]))
        cur.execute(f"""UPDATE stg.customer SET full_name = full_name || ' (đổi tên)', scd1_hash = md5(scd1_hash || 'x'),
                        effective_date = '2026-02-01' WHERE batch_id = {X1} AND customer_id = {B}""")
        cur.execute(f"""UPDATE stg.seller SET tier = '{t1}', scd2_hash = md5(scd2_hash || '{t1}'), effective_date = '2026-02-01'
                        WHERE batch_id = {X1} AND seller_id = {S}""")
        cur.execute(f"""UPDATE stg.product SET list_price = list_price * 1.1, unit_cost_est = unit_cost_est * 1.1,
                        product_name = product_name || ' (tên mới)', scd1_hash = md5(scd1_hash || 'x'),
                        scd2_hash = md5(scd2_hash || 'x'), effective_date = '2026-02-01'
                        WHERE batch_id = {X1} AND product_id = {P}""")
        s1 = run_dims(cur, X1)
        print("X1:", {k: {kk: vv for kk, vv in v.items() if kk != "sec"} for k, v in s1.items()})

        v = cur.execute(f"""SELECT count(*), count(*) FILTER (WHERE is_current),
                                   max(valid_to) FILTER (WHERE NOT is_current), max(valid_from) FILTER (WHERE is_current),
                                   max(province_code) FILTER (WHERE is_current)
                            FROM dw.dim_customer WHERE customer_id = {A}""").fetchone()
        check("SCD2 customer: đổi tỉnh → 2 phiên bản, 1 current, bản cũ đóng 2026-02-01",
              v[0] == 2 and v[1] == 1 and str(v[2]) == "2026-02-01" and str(v[3]) == "2026-02-01" and v[4] == newp[0], str(v))
        v = cur.execute(f"SELECT count(*), max(full_name) FROM dw.dim_customer WHERE customer_id = {B}").fetchone()
        check("SCD1 customer: đổi tên → vẫn 1 phiên bản, tên mới", v[0] == 1 and v[1].endswith("(đổi tên)"), str(v))
        v = cur.execute(f"SELECT count(*), max(tier) FILTER (WHERE is_current), max(tier) FILTER (WHERE NOT is_current) "
                        f"FROM dw.dim_seller WHERE seller_id = {S}").fetchone()
        check("SCD2 seller: đổi hạng → 2 phiên bản", v[0] == 2 and v[1] == t1 and v[2] == tier, str(v))
        v = cur.execute(f"SELECT current_tier, previous_tier, tier_changed_on FROM dw.dim_seller_tier_t3 WHERE seller_id = {S}").fetchone()
        check("SCD3 seller: current/previous/tier_changed_on", v[0] == t1 and v[1] == tier and str(v[2]) == "2026-02-01", str(v))
        v = cur.execute(f"""SELECT count(*), count(DISTINCT list_price), bool_and(product_name LIKE '%(tên mới)')
                            FROM dw.dim_product WHERE product_id = {P}""").fetchone()
        check("SCD2+SCD1 product: 2 phiên bản giá, tên mới ghi đè CẢ hai phiên bản", v[0] == 2 and v[1] == 2 and v[2], str(v))
        k1, k2 = (cur.execute(f"""SELECT product_key, list_price FROM dw.dim_product WHERE product_id = {P}
                                  AND DATE '{d}' >= valid_from AND DATE '{d}' < valid_to""").fetchone()
                  for d in ("2026-01-15", "2026-02-05"))
        check("Tra cứu theo thời điểm: 15/01 và 05/02 ra 2 khóa khác nhau", k1[0] != k2[0], f"15/01→{k1}, 05/02→{k2}")
        after = {t: cur.execute(f"SELECT count(*) FROM dw.{t}").fetchone()[0] for t in before}
        check("Số phiên bản tăng đúng 1 mỗi dimension (chỉ các khóa đổi SCD2)",
              all(after[t] - before[t] == 1 for t in before), f"{before} → {after}")

        # ---------- X2 ----------
        copy_batch(cur, X1, X2)
        cur.execute(f"""UPDATE stg.seller SET tier = '{t2}', scd2_hash = md5(scd2_hash || '{t2}'), effective_date = '2026-02-01'
                        WHERE batch_id = {X2} AND seller_id = {S}""")
        cur.execute(f"""UPDATE stg.customer SET province_code = %s, scd2_hash = md5(scd2_hash || 'late'), effective_date = '2026-01-20'
                        WHERE batch_id = {X2} AND customer_id = {A}""", (prov,))
        s2 = run_dims(cur, X2)
        print("X2:", {k: {kk: vv for kk, vv in v.items() if kk != "sec"} for k, v in s2.items()})
        v = cur.execute(f"SELECT count(*), max(tier) FILTER (WHERE is_current) FROM dw.dim_seller WHERE seller_id = {S}").fetchone()
        check("Cùng ngày hiệu lực: sửa tại chỗ phiên bản current, không thêm phiên bản", v[0] == 2 and v[1] == t2, str(v))
        v = cur.execute(f"SELECT count(*), max(province_code) FILTER (WHERE is_current) FROM dw.dim_customer WHERE customer_id = {A}").fetchone()
        q = cur.execute(f"SELECT count(*) FROM audit.quarantine WHERE batch_id = {X2} AND rule_code = 'DQ-23'").fetchone()[0]
        check("Đến muộn: cách ly DQ-23, không sửa hồi tố", v[0] == 2 and v[1] == newp[0] and q == 1, f"{v}, quarantine={q}")
        rc = [r for r in L.reconcile(cur, X2) if r[0].startswith("SCD")]
        check("SCD-01/02 sau kịch bản: không chồng lấn, đúng 1 current", all(r[4] for r in rc),
              "; ".join(f"{r[0]}={r[3]}" for r in rc))
        con.rollback()
    n_fail = sum(not ok for _, ok, _ in CHECKS)
    print(f"\n{len(CHECKS) - n_fail}/{len(CHECKS)} PASS — đã ROLLBACK, kho không thay đổi")
    raise SystemExit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
