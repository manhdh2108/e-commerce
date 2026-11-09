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

for page in ["Tổng quan bán hàng", "Lịch sử thuộc tính (SCD)", "Đối soát vận hành (drill-across)",
             "Chất lượng dữ liệu", "Hiệu năng"]:
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["page"] = page
    at.run()
    ex = [e.value for e in at.exception]
    print(f"{'FAIL' if ex else 'PASS'} {page}: metric={len(at.metric)} dataframe={len(at.dataframe)} "
          f"chart={len(at.get('plotly_chart'))} warning={len(at.warning)} info={len(at.info)}")
    for e in ex:
        print("   ", e[:500])
    fails += bool(ex)
    if page == "Tổng quan bán hàng" and not ex:
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
