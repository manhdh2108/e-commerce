"""Kiểm thử dashboard không cần trình duyệt (streamlit.testing.AppTest): chạy từng màn hình, báo exception,
đếm số chỉ số/bảng/biểu đồ, và so KPI hiển thị với truy vấn SQL độc lập (T5).

    .venv/bin/python dashboard/test_app.py
"""
import pathlib
import sys

import psycopg
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
APP = str(pathlib.Path(__file__).with_name("app.py"))
DSN = "postgresql://dw_analyst:dw_analyst_local@127.0.0.1:55432/dwh"
fails = 0

PAGES = [("Thống kê", "Tổng quan"), ("Thống kê", "Bán hàng chi tiết"), ("Thống kê", "Tồn kho"), ("Thống kê", "Quảng cáo"),
         ("Kỹ thuật kho dữ liệu", "3 bảng Fact và kỹ thuật (SCD, bridge)"), ("Kỹ thuật kho dữ liệu", "Lịch sử thuộc tính (SCD)"),
         ("Kỹ thuật kho dữ liệu", "Đối soát vận hành (drill-across)"), ("Kỹ thuật kho dữ liệu", "Chất lượng dữ liệu"),
         ("Kỹ thuật kho dữ liệu", "Hiệu năng")]
for mode, page in PAGES:
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["mode"] = mode
    at.session_state[f"page_{mode}"] = page
    at.run()
    ex = [e.value for e in at.exception]
    print(f"{'FAIL' if ex else 'PASS'} {page}: metric={len(at.metric)} dataframe={len(at.dataframe)} "
          f"chart={len(at.get('plotly_chart'))} warning={len(at.warning)} info={len(at.info)}")
    for e in ex:
        print("   ", e[:500])
    fails += bool(ex)
    if page == "Tổng quan" and not ex:
        at.radio(key="ov_span").set_value("Toàn bộ dữ liệu").run()
        shown = {m.label: m.value for m in at.metric}
        with psycopg.connect(DSN) as con:
            net, orders, buyers = con.execute("""SELECT sum(f.net_revenue), count(DISTINCT f.order_id),
                count(DISTINCT cu.customer_id) FILTER (WHERE f.customer_key > 0)
                FROM dw.fact_order_item f JOIN dw.dim_customer cu USING (customer_key)""").fetchone()
        exp = {"Doanh thu": f"{float(net) / 1e9:.2f} tỷ".replace(".", ","), "Số đơn hàng": f"{orders:,}".replace(",", "."),
               "Khách đã mua": f"{buyers:,}".replace(",", ".")}
        for k, v in exp.items():
            ok = shown.get(k) == v
            fails += not ok
            print(f"   {'PASS' if ok else 'FAIL'} Tổng quan '{k}': dashboard={shown.get(k)} | SQL độc lập={v}")
        ex2 = [e.value for e in at.exception]
        fails += bool(ex2)
        print(f"   {'FAIL' if ex2 else 'PASS'} Tổng quan chọn 'Toàn bộ dữ liệu': chart={len(at.get('plotly_chart'))}")
    if page.startswith("3 bảng Fact") and not ex:
        ok = len(at.tabs) == 3
        fails += not ok
        print(f"   {'PASS' if ok else 'FAIL'} 3 tab theo 3 bảng fact: {[t.label for t in at.tabs]}")
        shown = {m.label: m.value for m in at.metric}
        with psycopg.connect(DSN) as con:
            net = con.execute("SELECT sum(net_revenue) FROM dw.fact_order_item").fetchone()[0]
            cost = con.execute("SELECT sum(cost_amount) FROM dw.fact_ad_spend").fetchone()[0]
            onh = con.execute("SELECT sum(quantity_on_hand) FROM dw.fact_inventory_snapshot WHERE date_key = (SELECT max(date_key) FROM dw.fact_inventory_snapshot)").fetchone()[0]
        for label, exp in (("Doanh thu thuần", f"{float(net) / 1e9:.2f} tỷ".replace(".", ",")),
                           ("Tồn cuối kỳ (món)", f"{float(onh):,.0f}".replace(",", ".")),
                           ("Chi phí quảng cáo", f"{float(cost) / 1e6:.1f} tr".replace(".", ","))):
            ok = shown.get(label) == exp
            fails += not ok
            print(f"   {'PASS' if ok else 'FAIL'} '{label}': dashboard={shown.get(label)} | SQL độc lập={exp}")
    if page == "Bán hàng chi tiết" and not ex:
        shown = {m.label: m.value for m in at.metric}
        with psycopg.connect(DSN) as con:
            net, orders, aov = con.execute("""SELECT sum(net_revenue), count(DISTINCT order_id),
                                              sum(net_revenue) / count(DISTINCT order_id) FROM dw.fact_order_item""").fetchone()
        exp = {"Doanh thu thuần": f"{float(net):,.0f} đ".replace(",", "."), "Số đơn": f"{orders:,}".replace(",", "."),
               "AOV": f"{float(aov):,.0f} đ".replace(",", ".")}
        for k, v in exp.items():
            ok = shown.get(k) == v
            fails += not ok
            print(f"   {'PASS' if ok else 'FAIL'} KPI '{k}': dashboard={shown.get(k)} | SQL độc lập={v}")
        # bộ lọc: chọn kênh Web → doanh thu = SQL độc lập
        at.sidebar.multiselect[1].select("Web").run()
        with psycopg.connect(DSN) as con:
            web = con.execute("""SELECT sum(f.net_revenue) FROM dw.fact_order_item f JOIN dw.dim_channel c USING (channel_key)
                                 WHERE c.channel_name = 'Web'""").fetchone()[0]
        got = {m.label: m.value for m in at.metric}.get("Doanh thu thuần")
        ok = got == f"{float(web):,.0f} đ".replace(",", ".")
        fails += not ok
        print(f"   {'PASS' if ok else 'FAIL'} Bộ lọc kênh Web: dashboard={got} | SQL độc lập={float(web):,.0f}")

print(f"\n{'OK' if not fails else 'CÓ LỖI'}: {fails} lỗi")
sys.exit(1 if fails else 0)
