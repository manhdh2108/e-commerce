"""Màn hình thống kê cho người dùng nghiệp vụ: Tổng quan, Tồn kho, Quảng cáo.

Ngôn ngữ đời thường, ít thuật ngữ kho dữ liệu; thống kê là chính, phần nhận xét chỉ vài dòng ngắn.
Biểu đồ doanh thu đọc từ tầng tổng hợp (mart.mv_*); các chỉ số đếm phân biệt (số đơn, số khách) tính từ fact.
"""
import datetime as dt

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from common import intf, num, pct, q, short, vnd

BLUE, ORANGE, GREEN, RED, GREY, PURPLE = "#2563eb", "#f97316", "#16a34a", "#dc2626", "#94a3b8", "#7c3aed"
PALETTE = [BLUE, ORANGE, GREEN, PURPLE, "#0ea5e9", GREY]
LIGHT_BLUE = "#bfdbfe"

KPI_SQL = """SELECT sum(f.net_revenue) AS net, count(DISTINCT f.order_id) AS orders, sum(f.quantity) AS items,
             sum(f.net_revenue) / nullif(count(DISTINCT f.order_id), 0) AS aov,
             count(DISTINCT cu.customer_id) FILTER (WHERE f.customer_key > 0) AS buyers
             FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_customer cu USING (customer_key)
             WHERE d.full_date BETWEEN %(d0)s AND %(d1)s AND f.channel_key = ANY(%(ch)s)"""
MV = """FROM mart.mv_sales_day_product m JOIN dw.dim_date d ON d.date_key = m.date_key
        WHERE d.full_date BETWEEN %(d0)s AND %(d1)s AND m.channel_key = ANY(%(ch)s)"""
FACT = """FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key)
          WHERE d.full_date BETWEEN %(d0)s AND %(d1)s AND f.channel_key = ANY(%(ch)s)"""


def style(fig, height=320, legend=False):
    fig.update_layout(template="plotly_white", height=height, margin=dict(t=10, b=10, l=10, r=10), showlegend=legend,
                      legend=dict(orientation="h", y=-0.15, title=None), font=dict(size=13))
    return fig


def hbar(df, x, y, color=BLUE, fmt=short, height=300):
    df = df.sort_values(x, ascending=False)
    fig = px.bar(df, x=x, y=y, orientation="h", text=df[x].map(fmt), color_discrete_sequence=[color])
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_yaxes(autorange="reversed", title=None)
    fig.update_xaxes(visible=False, range=[0, float(df[x].max()) * 1.35])
    return style(fig, height)


def donut(df, names, values, height=300):
    fig = px.pie(df, names=names, values=values, hole=0.55, color_discrete_sequence=PALETTE)
    fig.update_traces(textinfo="percent", sort=False)
    return style(fig, height, legend=True)


def block(title, hint=None):
    st.markdown(f"##### {title}")
    if hint:
        st.caption(hint)


def change(cur, old):
    if old is None or pd.isna(old) or not old:
        return None
    return f"{(cur / old - 1) * 100:+.1f}% so với kỳ trước".replace(".", ",")


# ------------------------------------------------------------------------------------------------
# Tổng quan
# ------------------------------------------------------------------------------------------------
def page_overview():
    st.caption("Doanh thu, đơn hàng và khách hàng trong kỳ đã chọn. Chọn khoảng thời gian và kênh bán ngay bên dưới.")
    bounds = q("SELECT min(full_date) AS lo, max(full_date) AS hi FROM dw.fact_order_item JOIN dw.dim_date USING (date_key)").iloc[0]
    lo, hi = bounds.lo, bounds.hi
    chans = q("SELECT channel_key, channel_name FROM dw.dim_channel WHERE channel_key > 0 ORDER BY 1")
    c1, c2 = st.columns([3, 2])
    span = c1.radio("Khoảng thời gian", ["7 ngày gần nhất", "14 ngày gần nhất", "Toàn bộ dữ liệu"], horizontal=True, key="ov_span")
    picked = c2.multiselect("Kênh bán", chans.channel_name.tolist(), key="ov_ch", placeholder="Tất cả các kênh")
    ch = chans[chans.channel_name.isin(picked)].channel_key.tolist() if picked else chans.channel_key.tolist()

    n = {"7 ngày gần nhất": 7, "14 ngày gần nhất": 14}.get(span)
    d1 = hi
    d0 = max(lo, hi - dt.timedelta(days=n - 1)) if n else lo
    prev = (d0 - dt.timedelta(days=n), d0 - dt.timedelta(days=1)) if n and d0 - dt.timedelta(days=n) >= lo else None
    st.caption(f"Số liệu từ {d0:%d/%m/%Y} đến {d1:%d/%m/%Y}" + (f", so sánh với {prev[0]:%d/%m} đến {prev[1]:%d/%m}." if prev else "."))
    p = {"d0": d0, "d1": d1, "ch": ch}

    cur = num(q(KPI_SQL, p)).iloc[0]
    if pd.isna(cur.net):
        st.info("Không có đơn hàng nào trong kỳ và kênh đã chọn.")
        return
    old = num(q(KPI_SQL, {"d0": prev[0], "d1": prev[1], "ch": ch})).iloc[0] if prev else None
    g = (lambda k: None if old is None else old[k])
    cols = st.columns(5)
    cols[0].metric("Doanh thu", short(cur.net), change(cur.net, g("net")), border=True)
    cols[1].metric("Số đơn hàng", intf(cur.orders), change(cur.orders, g("orders")), border=True)
    cols[2].metric("Giá trị mỗi đơn", vnd(cur.aov), change(cur.aov, g("aov")), border=True)
    cols[3].metric("Số món đã bán", intf(cur["items"]), change(cur["items"], g("items")), border=True)
    cols[4].metric("Khách đã mua", intf(cur.buyers), change(cur.buyers, g("buyers")), border=True)

    trend = num(q(f"SELECT d.full_date AS ngay, sum(m.net_revenue) AS doanh_thu {MV} GROUP BY 1 ORDER BY 1", p))
    left, right = st.columns([3, 2])
    with left:
        block("Doanh thu theo ngày", "Cột là doanh thu từng ngày, đường xanh là trung bình 3 ngày để dễ thấy xu hướng.")
        trend["tb3"] = trend.doanh_thu.rolling(3, min_periods=1).mean()
        fig = go.Figure()
        fig.add_bar(x=trend.ngay, y=trend.doanh_thu / 1e6, marker_color=LIGHT_BLUE, name="Doanh thu ngày")
        fig.add_scatter(x=trend.ngay, y=trend.tb3 / 1e6, mode="lines", line=dict(color=BLUE, width=3), name="Trung bình 3 ngày")
        fig.update_yaxes(title="Triệu đồng")
        fig.update_xaxes(tickformat="%d/%m")
        st.plotly_chart(style(fig, 330, legend=True))
    with right:
        block("Doanh thu theo kênh bán")
        chd = num(q(f"""SELECT chn.channel_name AS kenh, sum(m.net_revenue) AS doanh_thu {MV.replace('WHERE', 'JOIN dw.dim_channel chn ON chn.channel_key = m.channel_key WHERE')}
                        GROUP BY 1""", p))
        st.plotly_chart(donut(chd, "kenh", "doanh_thu", 330))

    cat = num(q(f"""SELECT r.category_name AS danh_muc, sum(m.net_revenue) AS doanh_thu
                    {MV.replace('WHERE', 'JOIN dw.dim_category c ON c.category_key = m.category_key JOIN dw.dim_category r ON r.category_key = c.root_category_key WHERE')}
                    GROUP BY 1""", p))
    prod = num(q(f"""SELECT p.product_id, max(p.product_name) AS san_pham, sum(m.net_revenue) AS doanh_thu
                     {MV.replace('WHERE', 'JOIN dw.dim_product p ON p.product_key = m.product_key WHERE')}
                     GROUP BY 1 ORDER BY 3 DESC LIMIT 5""", p))
    sell = num(q(f"""SELECT s.seller_id, max(s.shop_name) AS cua_hang, sum(m.net_revenue) AS doanh_thu
                     {MV.replace('WHERE', 'JOIN dw.dim_seller s ON s.seller_key = m.seller_key WHERE')}
                     GROUP BY 1 ORDER BY 3 DESC LIMIT 5""", p))
    a, b, c = st.columns(3)
    with a:
        block("Danh mục bán tốt nhất")
        st.plotly_chart(hbar(cat.nlargest(6, "doanh_thu").assign(danh_muc=lambda x: x.danh_muc.str.slice(0, 26)), "doanh_thu", "danh_muc", BLUE))
    with b:
        block("5 sản phẩm bán tốt nhất")
        st.plotly_chart(hbar(prod.assign(san_pham=prod.san_pham.str.slice(0, 28)), "doanh_thu", "san_pham", GREEN))
    with c:
        block("5 cửa hàng bán tốt nhất")
        st.plotly_chart(hbar(sell.assign(cua_hang=sell.cua_hang.fillna("(không tên)").str.slice(0, 26)), "doanh_thu", "cua_hang", ORANGE))

    geo = num(q(f"""SELECT cu.province_name AS tinh, sum(f.net_revenue) AS doanh_thu {FACT.replace('WHERE', 'JOIN dw.dim_customer cu USING (customer_key) WHERE')}
                    GROUP BY 1""", p))
    geo["tinh"] = geo.tinh.replace({"Không áp dụng": "Khách vãng lai"})
    pay = num(q(f"""SELECT pm.method_group AS hinh_thuc, sum(f.net_revenue) AS doanh_thu {FACT.replace('WHERE', 'JOIN dw.dim_payment_method pm USING (payment_method_key) WHERE')}
                    GROUP BY 1""", p))
    pay["hinh_thuc"] = pay.hinh_thuc.replace({"UNK": "Chưa rõ"})
    left, right = st.columns([3, 2])
    with left:
        block("Khách ở đâu mua nhiều?")
        st.plotly_chart(hbar(geo, "doanh_thu", "tinh", PURPLE))
    with right:
        block("Khách thanh toán bằng cách nào?")
        st.plotly_chart(donut(pay, "hinh_thuc", "doanh_thu"))

    block("Nhận xét nhanh")
    notes = []
    best = trend.loc[trend.doanh_thu.idxmax()]
    notes.append(f"Ngày bán tốt nhất là **{best.ngay:%d/%m}** với {short(best.doanh_thu)}.")
    top = cat.loc[cat.doanh_thu.idxmax()]
    notes.append(f"Danh mục dẫn đầu là **{top.danh_muc}**, chiếm {top.doanh_thu / cat.doanh_thu.sum() * 100:.0f}% doanh thu.")
    topc = chd.loc[chd.doanh_thu.idxmax()]
    notes.append(f"Kênh **{topc.kenh}** mang lại {topc.doanh_thu / chd.doanh_thu.sum() * 100:.0f}% doanh thu.")
    if prev:
        old_cat = num(q(f"""SELECT r.category_name AS danh_muc, sum(m.net_revenue) AS truoc
                            {MV.replace('WHERE', 'JOIN dw.dim_category c ON c.category_key = m.category_key JOIN dw.dim_category r ON r.category_key = c.root_category_key WHERE')}
                            GROUP BY 1""", {"d0": prev[0], "d1": prev[1], "ch": ch}))
        mg = cat.merge(old_cat, on="danh_muc")
        mg = mg[mg.truoc > 0].assign(tang=lambda x: x.doanh_thu / x.truoc - 1)
        if len(mg):
            up, down = mg.loc[mg.tang.idxmax()], mg.loc[mg.tang.idxmin()]
            parts = []
            if up.tang > 0:
                parts.append(f"**{up.danh_muc}** tăng mạnh nhất ({up.tang * 100:+.0f}%)")
            if down.tang < 0:
                parts.append(f"**{down.danh_muc}** giảm nhiều nhất ({down.tang * 100:+.0f}%)")
            if parts:
                notes.append("So với kỳ trước, " + ", ".join(parts) + ".")
    with st.container(border=True):
        for t in notes:
            st.markdown(f"- {t}")


# ------------------------------------------------------------------------------------------------
# Tồn kho
# ------------------------------------------------------------------------------------------------
INV = "dw.fact_inventory_snapshot"


def page_inventory():
    st.caption("Hiện còn bao nhiêu hàng, kho nào đang giữ nhiều nhất, và hàng vào ra mỗi ngày ra sao.")
    rng = q(f"SELECT min(full_date) AS lo, max(full_date) AS hi FROM {INV} JOIN dw.dim_date USING (date_key)").iloc[0]
    d = st.date_input("Xem tồn kho tại ngày", rng.hi, min_value=rng.lo, max_value=rng.hi, format="DD/MM/YYYY", key="st_inv_day")
    if isinstance(d, (list, tuple)):
        d = d[0] if d else rng.hi
    key = int(d.strftime("%Y%m%d"))
    week = max(d - dt.timedelta(days=7), rng.lo)
    wkey = int(week.strftime("%Y%m%d"))
    first_key = int(q(f"SELECT min(date_key) AS k FROM {INV}").k.iloc[0])
    p = {"k": key, "w": wkey}

    k = num(q(f"""SELECT sum(quantity_on_hand) AS on_hand, sum(inventory_value_est) AS val, count(DISTINCT product_key) FILTER (WHERE quantity_on_hand > 0) AS sp,
                  sum(quantity_reserved) AS giu FROM {INV} WHERE date_key = %(k)s""", p)).iloc[0]
    het = int(q(f"""SELECT count(*) AS n FROM (SELECT product_key FROM {INV} WHERE date_key = %(k)s
                    GROUP BY 1 HAVING sum(quantity_on_hand) = 0) x""", p).n.iloc[0])
    before = num(q(f"SELECT sum(quantity_on_hand) AS on_hand FROM {INV} WHERE date_key = %(w)s", p)).on_hand.iloc[0]
    cols = st.columns(5)
    cols[0].metric("Tổng hàng tồn (món)", intf(k.on_hand), f"{k.on_hand - before:+,.0f} so với 7 ngày trước".replace(",", ".") if key != wkey else None, border=True)
    cols[1].metric("Giá trị tồn ước tính", short(k.val), border=True)
    cols[2].metric("Số sản phẩm đang có tồn", intf(k.sp), border=True)
    cols[3].metric("Sản phẩm hết hàng", intf(het), border=True)
    cols[4].metric("Hàng đang giữ cho đơn", intf(k.giu), border=True)

    left, right = st.columns(2)
    wh = num(q(f"""SELECT w.warehouse_name AS kho, w.region AS vung, sum(f.quantity_on_hand) AS ton FROM {INV} f
                   JOIN dw.dim_warehouse w USING (warehouse_key) WHERE f.date_key = %(k)s GROUP BY 1, 2""", p))
    with left:
        block("Kho nào đang giữ nhiều hàng nhất?")
        fig = px.bar(wh.sort_values("ton", ascending=False), x="ton", y="kho", color="vung", orientation="h", color_discrete_sequence=PALETTE,
                     text=wh.sort_values("ton", ascending=False).ton.map(intf), labels={"vung": "Vùng"})
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_yaxes(categoryorder="total ascending", title=None)
        fig.update_xaxes(visible=False, range=[0, float(wh.ton.max()) * 1.25])
        st.plotly_chart(style(fig, 320, legend=True))
    cat = num(q(f"""SELECT r.category_name AS danh_muc, sum(f.quantity_on_hand) AS ton FROM {INV} f
                    JOIN dw.dim_category c ON c.category_key = f.category_key JOIN dw.dim_category r ON r.category_key = c.root_category_key
                    WHERE f.date_key = %(k)s GROUP BY 1""", p))
    with right:
        block("Nhóm hàng nào tồn nhiều nhất?")
        st.plotly_chart(hbar(cat.nlargest(6, "ton").assign(danh_muc=lambda x: x.danh_muc.str.slice(0, 26)), "ton", "danh_muc", BLUE, fmt=intf, height=320))

    block("Hàng vào và ra mỗi ngày", "Hàng vào gồm nhập kho và khách trả; hàng ra là bán xuất kho. "
          "Ngày đầu tiên của kho là lần nạp tồn ban đầu nên không vẽ.")
    flow = num(q(f"""SELECT dd.full_date AS ngay, sum(f.qty_imported) + sum(f.qty_returned) AS vao, sum(f.qty_sold) AS ra
                     FROM {INV} f JOIN dw.dim_date dd USING (date_key) WHERE f.date_key > {first_key} AND f.date_key <= %(k)s
                     GROUP BY 1 ORDER BY 1""", p))
    if len(flow):
        fig = go.Figure()
        fig.add_scatter(x=flow.ngay, y=flow.vao, mode="lines+markers", name="Hàng vào", line=dict(color=GREEN, width=3))
        fig.add_scatter(x=flow.ngay, y=flow.ra, mode="lines+markers", name="Hàng ra (bán)", line=dict(color=ORANGE, width=3))
        fig.update_yaxes(title="Số món")
        fig.update_xaxes(tickformat="%d/%m")
        st.plotly_chart(style(fig, 300, legend=True))

    a14 = int((d - dt.timedelta(days=13)).strftime("%Y%m%d"))
    a14 = max(a14, first_key)
    hot = num(q(f"""WITH s AS (SELECT pr.product_id, sum(f.qty_sold) AS ban FROM {INV} f JOIN dw.dim_product pr USING (product_key)
                               WHERE f.date_key BETWEEN %(a)s AND %(k)s GROUP BY 1),
                         e AS (SELECT pr.product_id, sum(f.quantity_on_hand) AS ton FROM {INV} f JOIN dw.dim_product pr USING (product_key)
                               WHERE f.date_key = %(k)s GROUP BY 1),
                         n AS (SELECT DISTINCT ON (product_id) product_id, product_name FROM dw.dim_product WHERE product_id > 0
                               ORDER BY product_id, valid_from DESC)
                    SELECT n.product_name AS san_pham, s.ban AS ban_14_ngay, e.ton AS ton_hien_co
                    FROM s JOIN e USING (product_id) JOIN n USING (product_id) ORDER BY s.ban DESC, e.ton LIMIT 10""", {**p, "a": a14}))
    big = num(q(f"""WITH s AS (SELECT pr.product_id, sum(f.qty_sold) AS ban FROM {INV} f JOIN dw.dim_product pr USING (product_key)
                               WHERE f.date_key BETWEEN %(a)s AND %(k)s GROUP BY 1),
                         e AS (SELECT pr.product_id, sum(f.quantity_on_hand) AS ton FROM {INV} f JOIN dw.dim_product pr USING (product_key)
                               WHERE f.date_key = %(k)s GROUP BY 1),
                         n AS (SELECT DISTINCT ON (product_id) product_id, product_name FROM dw.dim_product WHERE product_id > 0
                               ORDER BY product_id, valid_from DESC)
                    SELECT n.product_name AS san_pham, coalesce(s.ban, 0) AS ban_14_ngay, e.ton AS ton_hien_co
                    FROM e LEFT JOIN s USING (product_id) JOIN n USING (product_id) ORDER BY e.ton DESC LIMIT 10""", {**p, "a": a14}))
    left, right = st.columns(2)
    cfg = {"san_pham": st.column_config.TextColumn("Sản phẩm", width="medium"),
           "ban_14_ngay": st.column_config.NumberColumn("Bán 14 ngày", format="%d", width="small"),
           "ton_hien_co": st.column_config.NumberColumn("Tồn hiện có", format="%d", width="small")}
    hot["san_pham"] = hot.san_pham.str.slice(0, 44)
    big["san_pham"] = big.san_pham.str.slice(0, 44)
    with left:
        block("10 sản phẩm bán nhiều nhất", "Xem lượng tồn của các mặt hàng bán chạy để kịp nhập thêm.")
        st.dataframe(hot, hide_index=True, column_config=cfg)
    with right:
        block("10 sản phẩm tồn nhiều nhất", "Tồn lớn mà bán ít là hàng đang giữ vốn.")
        st.dataframe(big, hide_index=True, column_config=cfg)

    block("Nhận xét nhanh")
    sold_all = num(q(f"SELECT coalesce(sum(qty_sold), 0) AS ban FROM {INV} WHERE date_key BETWEEN %(a)s AND %(k)s", {**p, "a": a14})).ban.iloc[0]
    with st.container(border=True):
        st.markdown(f"- Kho giữ nhiều hàng nhất là **{wh.loc[wh.ton.idxmax()].kho}** ({wh.ton.max() / wh.ton.sum() * 100:.0f}% tổng tồn).")
        st.markdown(f"- Trong 14 ngày gần nhất bán xuất kho **{intf(sold_all)} món**, rất nhỏ so với {intf(k.on_hand)} món đang tồn "
                    "(dữ liệu tồn kho mô phỏng khá lớn).")
        st.markdown(f"- Hiện có **{intf(het)}** sản phẩm hết hàng ở mọi kho.")


# ------------------------------------------------------------------------------------------------
# Quảng cáo
# ------------------------------------------------------------------------------------------------
def page_ads():
    st.caption("Chi bao nhiêu tiền cho quảng cáo, hiệu quả ra sao và kênh nào chưa được quảng cáo.")
    camp = num(q("""SELECT c.campaign_key, c.campaign_name AS chien_dich, ch.channel_name AS kenh, c.budget_amount AS ngan_sach,
                    sum(a.cost_amount) AS chi_phi, sum(a.impressions) AS hien_thi, sum(a.clicks) AS luot_click
                    FROM dw.fact_ad_spend a JOIN dw.dim_campaign c USING (campaign_key) JOIN dw.dim_channel ch ON ch.channel_key = a.channel_key
                    GROUP BY 1, 2, 3, 4 ORDER BY 1"""))
    if camp.empty:
        st.info("Kho chưa có dữ liệu quảng cáo.")
        return
    att = num(q("""SELECT campaign_key, count(DISTINCT order_id) AS don, sum(net_revenue) AS doanh_thu FROM dw.fact_order_item
                   WHERE campaign_key > 0 GROUP BY 1"""))
    camp = camp.merge(att, on="campaign_key", how="left").fillna({"don": 0, "doanh_thu": 0})
    t = camp[["ngan_sach", "chi_phi", "hien_thi", "luot_click", "don", "doanh_thu"]].sum()
    cols = st.columns(5)
    cols[0].metric("Tiền đã chi", short(t.chi_phi), f"{t.chi_phi / t.ngan_sach * 100:.0f}% ngân sách".replace(".", ","), delta_color="off", border=True)
    cols[1].metric("Lượt hiển thị", intf(t.hien_thi), border=True)
    cols[2].metric("Lượt click", intf(t.luot_click), f"{t.luot_click / t.hien_thi * 100:.2f}% hiển thị".replace(".", ","), delta_color="off", border=True)
    cols[3].metric("Chi phí mỗi click", vnd(t.chi_phi / t.luot_click) if t.luot_click else "—", border=True)
    cols[4].metric("Doanh thu từ chiến dịch", short(t.doanh_thu), f"{t.doanh_thu / t.chi_phi:,.0f} đồng thu/1 đồng chi".replace(",", "."),
                   delta_color="off", border=True)

    left, right = st.columns(2)
    with left:
        block("Ngân sách và số tiền đã chi", "Mỗi chiến dịch đã dùng bao nhiêu phần ngân sách.")
        fig = go.Figure()
        fig.add_bar(y=camp.chien_dich, x=camp.ngan_sach, orientation="h", name="Ngân sách", marker_color="#cbd5e1")
        fig.add_bar(y=camp.chien_dich, x=camp.chi_phi, orientation="h", name="Đã chi", marker_color=BLUE,
                    text=[f"{short(a)} ({a / b * 100:.0f}%)" for a, b in zip(camp.chi_phi, camp.ngan_sach)], textposition="inside")
        fig.update_layout(barmode="overlay")
        fig.update_xaxes(visible=False)
        st.plotly_chart(style(fig, 300, legend=True))
    ch = num(q("""SELECT chn.channel_name AS kenh, sum(m.campaign_net_revenue) AS co_chien_dich,
                  sum(m.net_revenue) - sum(m.campaign_net_revenue) AS khong_chien_dich
                  FROM mart.mv_sales_month_channel m JOIN dw.dim_channel chn ON chn.channel_key = m.channel_key GROUP BY 1 ORDER BY 1"""))
    with right:
        block("Doanh thu mỗi kênh: có và chưa có chiến dịch")
        melt = ch.melt(id_vars="kenh", var_name="loai", value_name="doanh_thu")
        melt["loai"] = melt.loai.map({"co_chien_dich": "Đơn thuộc chiến dịch", "khong_chien_dich": "Đơn khác"})
        melt["trieu"] = melt.doanh_thu / 1e6
        fig = px.bar(melt, x="kenh", y="trieu", color="loai", barmode="stack", text=melt.doanh_thu.map(lambda v: short(v) if v else ""),
                     color_discrete_map={"Đơn thuộc chiến dịch": BLUE, "Đơn khác": "#cbd5e1"}, labels={"kenh": "", "trieu": "Triệu đồng", "loai": ""})
        st.plotly_chart(style(fig, 300, legend=True))

    block("Chi tiết từng chiến dịch")
    show = camp.assign(ctr=camp.luot_click / camp.hien_thi * 100, cpc=camp.chi_phi / camp.luot_click)[
        ["chien_dich", "kenh", "ngan_sach", "chi_phi", "hien_thi", "luot_click", "ctr", "cpc", "don", "doanh_thu"]]
    st.dataframe(show, hide_index=True, column_config={
        "chien_dich": "Chiến dịch", "kenh": "Kênh", "ngan_sach": st.column_config.NumberColumn("Ngân sách (đ)", format="%d"),
        "chi_phi": st.column_config.NumberColumn("Đã chi (đ)", format="%d"), "hien_thi": st.column_config.NumberColumn("Hiển thị", format="%d"),
        "luot_click": st.column_config.NumberColumn("Click", format="%d"), "ctr": st.column_config.NumberColumn("Tỷ lệ click", format="%.2f%%"),
        "cpc": st.column_config.NumberColumn("Chi phí/click (đ)", format="%d"), "don": st.column_config.NumberColumn("Đơn", format="%d"),
        "doanh_thu": st.column_config.NumberColumn("Doanh thu (đ)", format="%d")})

    block("Nhận xét nhanh")
    none = ch[ch.co_chien_dich == 0]
    with st.container(border=True):
        st.markdown(f"- Đã dùng **{t.chi_phi / t.ngan_sach * 100:.0f}%** ngân sách quảng cáo; cứ 1.000 lượt hiển thị có khoảng **{t.luot_click / t.hien_thi * 1000:.0f}** lượt click.")
        if len(none):
            st.markdown(f"- Kênh **{', '.join(none.kenh)}** chưa chạy quảng cáo nhưng vẫn có doanh thu {short(none.khong_chien_dich.sum())}.")
        st.markdown("- Doanh thu từ chiến dịch chỉ là số tham khảo, chưa chứng minh được quảng cáo là nguyên nhân tạo ra đơn hàng.")
