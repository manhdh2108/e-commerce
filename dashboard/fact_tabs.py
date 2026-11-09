"""Màn hình "Phân tích theo bảng Fact": 3 tab, mỗi tab một bảng fact.

Mỗi tab có hai phần:
  A. Bài toán kinh doanh mà bảng fact được xây để trả lời (biểu đồ + kết luận).
  B. Kỹ thuật kho dữ liệu thể hiện trên chính bảng fact đó (SCD2/SCD3, mini-dimension, bridge, semi-additive,
     drill-across), có chọn đối tượng cụ thể (khách, seller, sản phẩm) để xem trực tiếp.
"""
import datetime as dt

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from common import intf, num, pct, q, short, table, vnd

BLUE, ORANGE, GREEN, RED, GREY, PURPLE, INK = "#2563eb", "#f97316", "#16a34a", "#dc2626", "#94a3b8", "#7c3aed", "#111827"
TIER_COLORS = {"Normal": GREY, "Preferred": BLUE, "Mall": ORANGE}
FOI = "FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key)"
W1 = "d.full_date BETWEEN %(d0)s AND %(d1)s"


# ------------------------------------------------------------------------------------------------
# Tiện ích
# ------------------------------------------------------------------------------------------------
def kicker(answers, grain):
    st.markdown(f"**Bảng fact này trả lời:** {answers}")
    st.caption(f"Mức hạt (grain): {grain}")


def date_range(label, key, lo, hi):
    d = st.date_input(label, (lo, hi), min_value=lo, max_value=hi, key=key, format="DD/MM/YYYY")
    return (d[0], d[1]) if isinstance(d, (list, tuple)) and len(d) == 2 else (lo, hi)


def waterfall(labels, values, measures, height=380, fmt=short):
    fig = go.Figure(go.Waterfall(x=labels, y=values, measure=measures, text=[fmt(v) for v in values], textposition="outside",
                                 connector=dict(line=dict(color=GREY)), increasing=dict(marker=dict(color=GREEN)),
                                 decreasing=dict(marker=dict(color=RED)), totals=dict(marker=dict(color=BLUE))))
    fig.update_layout(height=height, margin=dict(t=20, b=10), showlegend=False)
    return fig


def bridge_category(key, from_sql, measure, where, params, unit):
    """Kỹ thuật bridge (closure table): tổng của cả cây con khi chọn một danh mục cha, không cộng lặp."""
    tree = q("SELECT * FROM mart.v_category_tree ORDER BY path_names")
    roots = tree[tree.level == 1]
    root = st.selectbox("Chọn danh mục cha", roots.category_name.tolist(), key=f"{key}_root")
    rk = int(roots[roots.category_name == root].category_key.iloc[0])
    p = {**params, "rk": rk}
    total = num(q(f"""SELECT sum({measure}) v FROM {from_sql} JOIN dw.bridge_category_hierarchy b ON b.descendant_key = f.category_key
                      WHERE b.ancestor_key = %(rk)s AND {where}""", p)).v.iloc[0]
    direct = num(q(f"SELECT sum({measure}) v FROM {from_sql} WHERE f.category_key = %(rk)s AND {where}", p)).v.iloc[0]
    kids = num(q(f"""WITH x AS (SELECT k.category_key AS kid, k.category_name AS kname, k.is_named, c.category_name AS leaf, sum({measure}) AS v
                                 FROM {from_sql} JOIN dw.bridge_category_hierarchy b ON b.descendant_key = f.category_key
                                 JOIN dw.dim_category k ON k.category_key = b.ancestor_key
                                 JOIN dw.dim_category c ON c.category_key = f.category_key
                                 WHERE k.parent_category_key = %(rk)s AND {where} GROUP BY 1, 2, 3, 4)
                     SELECT CASE WHEN bool_or(is_named) THEN max(kname)
                                 ELSE max(kname) || ' (gồm ' || (array_agg(leaf ORDER BY v DESC))[1] || '…)' END AS danh_muc_con,
                            sum(v) AS gia_tri FROM x GROUP BY kid ORDER BY 2 DESC""", p))
    total = 0.0 if pd.isna(total) else float(total)
    direct = 0.0 if pd.isna(direct) else float(direct)
    c = st.columns(3)
    c[0].metric(f"Chỉ lọc đúng category_key = '{root}'", unit(direct), "bỏ sót toàn bộ cây con", delta_color="off")
    c[1].metric("Qua bridge (cả cây con)", unit(total))
    ok = abs(kids.gia_tri.sum() + direct - total) < 1
    c[2].metric("Σ các con + phần gắn trực tiếp", unit(kids.gia_tri.sum() + direct), "khớp, không cộng lặp" if ok else "LỆCH", delta_color="off" if ok else "inverse")
    if len(kids):
        fig = px.bar(kids, x="gia_tri", y="danh_muc_con", orientation="h", labels={"gia_tri": "Giá trị của cả cây con", "danh_muc_con": ""})
        fig.update_layout(yaxis=dict(autorange="reversed"), height=max(220, 36 * len(kids) + 60), margin=dict(t=10))
        fig.update_traces(marker_color=BLUE)
        st.plotly_chart(fig)
    else:
        st.info("Danh mục này không có dữ liệu trong khoảng đã chọn.")


# ------------------------------------------------------------------------------------------------
# Tab 1 · Fact_Order_Item
# ------------------------------------------------------------------------------------------------
def tab_order_item():
    kicker("bán được bao nhiêu, bán ở đâu, bán cho ai, và doanh thu bị giảm giá và hoa hồng lấy đi bao nhiêu.",
           "một dòng sản phẩm trong một đơn đã hoàn tất, ghi vào ngày hoàn tất. Số lượng và tiền cộng được trên mọi chiều.")
    rng = q(f"SELECT min(full_date) lo, max(full_date) hi {FOI}").iloc[0]
    d0, d1 = date_range("Khoảng ngày hoàn tất", "foi_range", rng.lo, rng.hi)
    p = {"d0": d0, "d1": d1}
    k = num(q(f"""SELECT sum(f.net_revenue) net, count(DISTINCT f.order_id) orders, sum(f.quantity) items,
                  sum(f.net_revenue) / nullif(count(DISTINCT f.order_id), 0) aov, sum(f.commission_amount) comm,
                  sum(f.gross_margin_est) / nullif(sum(f.net_revenue), 0) margin {FOI} WHERE {W1}""", p)).iloc[0]
    if pd.isna(k.net):
        st.info("Không có dòng bán nào trong khoảng đã chọn.")
        return
    c = st.columns(6)
    c[0].metric("Doanh thu thuần", short(k.net))
    c[1].metric("Số đơn", intf(k.orders))
    c[2].metric("Giá trị đơn TB (AOV)", vnd(k.aov))
    c[3].metric("Số món bán", intf(k["items"]))
    c[4].metric("Hoa hồng sàn thu", short(k.comm))
    c[5].metric("Biên lãi gộp ước tính", pct(k.margin, 1), "giá vốn là giả định", delta_color="off")

    st.markdown("## A. Bài toán kinh doanh")

    st.markdown("#### 1. Doanh thu chạy theo nhịp nào trong tháng?")
    day = num(q(f"""SELECT d.full_date AS ngay, d.is_weekend, sum(f.net_revenue) AS doanh_thu, count(DISTINCT f.order_id) AS so_don
                    {FOI} WHERE {W1} GROUP BY 1, 2 ORDER BY 1""", p))
    fig = go.Figure()
    for wk, name, col in ((False, "Ngày thường", BLUE), (True, "Cuối tuần", ORANGE)):
        s = day[day.is_weekend == wk]
        fig.add_bar(x=s.ngay, y=s.doanh_thu, name=name, marker_color=col)
    fig.add_scatter(x=day.ngay, y=day.so_don, name="Số đơn", yaxis="y2", mode="lines+markers", line=dict(color=INK, width=2))
    fig.update_layout(height=380, margin=dict(t=30), legend=dict(orientation="h", y=1.12),
                      yaxis=dict(title="Doanh thu thuần (VND)"),
                      yaxis2=dict(title="Số đơn", overlaying="y", side="right", showgrid=False))
    st.plotly_chart(fig)
    best = day.loc[day.doanh_thu.idxmax()]
    msg = f"Ngày cao nhất là {best.ngay:%d/%m} với {short(best.doanh_thu)} từ {int(best.so_don)} đơn."
    avg = day.groupby("is_weekend").doanh_thu.mean()
    if len(avg) == 2:
        ratio = avg.loc[True] / avg.loc[False] - 1
        msg += f" Bình quân một ngày cuối tuần {'cao hơn' if ratio >= 0 else 'thấp hơn'} ngày thường {abs(ratio) * 100:.0f}%."
    st.info(msg)

    st.markdown("#### 2. Tiền đi đâu? Từ giá niêm yết đến phần seller thực nhận")
    w = num(q(f"""SELECT sum(f.list_amount) lst, sum(f.list_discount_amount) ld, sum(f.discount_amount) vd, sum(f.net_revenue) net,
                  sum(f.commission_amount) comm, sum(f.seller_net_amount) sn, sum(f.cost_amount_est) cost, sum(f.gross_margin_est) gm
                  {FOI} WHERE {W1}""", p)).iloc[0]
    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(waterfall(["Giá niêm yết", "Giảm giá niêm yết", "Giảm giá voucher", "Doanh thu thuần", "Hoa hồng sàn", "Seller thực nhận"],
                                  [w.lst, -w.ld, -w.vd, w.net, -w.comm, w.sn],
                                  ["absolute", "relative", "relative", "total", "relative", "total"]))
    with right:
        st.plotly_chart(waterfall(["Doanh thu thuần", "Giá vốn ước tính", "Lãi gộp ước tính"], [w.net, -w.cost, w.gm],
                                  ["absolute", "relative", "total"]))
    st.info(f"Giảm giá niêm yết lấy đi {w.ld / w.lst * 100:.1f}% giá niêm yết, voucher chỉ {w.vd / w.lst * 100:.2f}%; "
            f"sàn giữ {w.comm / w.net * 100:.1f}% doanh thu thuần làm hoa hồng. Giá vốn là giả định nên lãi gộp chỉ để tham khảo.")

    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### 3. Danh mục nào đóng góp nhiều nhất?")
        cat = num(q(f"""SELECT r.category_name AS danh_muc_goc, c.category_name AS danh_muc, sum(f.net_revenue) AS doanh_thu
                        {FOI} JOIN dw.dim_category c ON c.category_key = f.category_key
                        JOIN dw.dim_category r ON r.category_key = c.root_category_key WHERE {W1} GROUP BY 1, 2""", p))
        fig = px.treemap(cat, path=["danh_muc_goc", "danh_muc"], values="doanh_thu", color="danh_muc_goc")
        fig.update_layout(height=400, margin=dict(t=10, l=0, r=0, b=0), showlegend=False)
        st.plotly_chart(fig)
    with right:
        st.markdown("#### 4. Khách trả tiền bằng cách nào, qua kênh nào?")
        pay = num(q(f"""SELECT chn.channel_name AS kenh, pm.method_group AS phuong_thuc, sum(f.net_revenue) AS doanh_thu
                        {FOI} JOIN dw.dim_channel chn USING (channel_key) JOIN dw.dim_payment_method pm USING (payment_method_key)
                        WHERE {W1} GROUP BY 1, 2""", p))
        fig = px.bar(pay, x="kenh", y="doanh_thu", color="phuong_thuc", barmode="stack", labels={"kenh": "", "doanh_thu": "Doanh thu thuần"})
        fig.update_layout(height=400, margin=dict(t=10), legend=dict(orientation="h", y=-0.15))
        st.plotly_chart(fig)

    left, right = st.columns(2)
    with left:
        st.markdown("#### 5. Top 10 seller, tô màu theo hạng tại thời điểm bán")
        ts = num(q(f"""SELECT s.seller_id::text || ' · ' || left(coalesce(s.shop_name, ''), 22) AS seller, s.tier AS hang_luc_ban,
                       sum(f.net_revenue) AS doanh_thu
                       {FOI} JOIN dw.dim_seller s USING (seller_key)
                       WHERE {W1} AND s.seller_id IN (SELECT s2.seller_id FROM dw.fact_order_item f2 JOIN dw.dim_date d2 USING (date_key)
                                                      JOIN dw.dim_seller s2 USING (seller_key)
                                                      WHERE d2.full_date BETWEEN %(d0)s AND %(d1)s
                                                      GROUP BY 1 ORDER BY sum(f2.net_revenue) DESC LIMIT 10)
                       GROUP BY 1, 2""", p))
        ts["tong"] = ts.groupby("seller").doanh_thu.transform("sum")
        ts = ts.sort_values(["tong", "hang_luc_ban"], ascending=[False, True])
        fig = px.bar(ts, x="doanh_thu", y="seller", color="hang_luc_ban", orientation="h", color_discrete_map=TIER_COLORS,
                     labels={"doanh_thu": "Doanh thu thuần", "seller": "", "hang_luc_ban": "Hạng lúc bán"})
        fig.update_layout(height=420, margin=dict(t=10), legend=dict(orientation="h", y=-0.15), yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig)
    with right:
        st.markdown("#### 6. Khách ở đâu mua nhiều?")
        geo = num(q(f"""SELECT cu.province_name AS tinh, cu.region AS vung, sum(f.net_revenue) AS doanh_thu
                        {FOI} JOIN dw.dim_customer cu USING (customer_key) WHERE {W1} GROUP BY 1, 2 ORDER BY 3 DESC""", p))
        geo["tinh"] = geo.tinh.replace({"Không áp dụng": "Khách vãng lai"})
        fig = px.bar(geo.sort_values("doanh_thu", ascending=False), x="doanh_thu", y="tinh", color="vung", orientation="h",
                     labels={"doanh_thu": "Doanh thu thuần", "tinh": "", "vung": "Vùng"})
        fig.update_layout(height=420, margin=dict(t=10), legend=dict(orientation="h", y=-0.15), yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig)

    st.markdown("## B. Kỹ thuật kho dữ liệu thể hiện trên bảng fact này")
    scd_customer(rng, p)
    st.divider()
    scd_seller()
    st.divider()
    mini_dimension(p)
    st.divider()
    bridge_promotion(p)
    st.divider()
    st.markdown("#### Kỹ thuật 5 · Bridge cây danh mục (closure table): chọn danh mục cha, tính đúng tổng cả cây con")
    st.caption("Fact chỉ gắn vào danh mục lá. Bảng bridge liệt kê mọi cặp (tổ tiên, hậu duệ) nên một phép nối là có tổng của cả cây, không phải lặp truy vấn đệ quy.")
    bridge_category("foi", "dw.fact_order_item f JOIN dw.dim_date d USING (date_key)", "f.net_revenue", W1, p, short)


def scd_customer(rng, p):
    st.markdown("#### Kỹ thuật 1 · SCD loại 2 trên khách hàng: khách ở nơi này rồi chuyển đi nơi khác, doanh số tính cho tỉnh nào?")
    st.caption("OLTP chỉ giữ tỉnh hiện tại. Kho giữ mỗi lần đổi tỉnh thành một phiên bản (valid_from → valid_to), "
               "và mỗi dòng bán trỏ đúng phiên bản có hiệu lực vào ngày hoàn tất.")
    v = num(q("""WITH m AS (SELECT customer_id FROM dw.dim_customer WHERE customer_id > 0 GROUP BY 1 HAVING count(*) > 1)
                 SELECT c.customer_id, c.customer_key, c.province_name, c.valid_from, c.valid_to, c.is_current,
                        coalesce(x.lines, 0) AS lines, coalesce(x.net, 0) AS net
                 FROM dw.dim_customer c JOIN m USING (customer_id)
                 LEFT JOIN (SELECT customer_key, count(*) lines, sum(net_revenue) net FROM dw.fact_order_item GROUP BY 1) x USING (customer_key)
                 ORDER BY c.customer_id, c.valid_from"""))
    if v.empty:
        st.info("Chưa có khách nào đổi tỉnh trong kho.")
        return
    summ = v.groupby("customer_id").agg(lines=("lines", "sum"), de=("province_name", "first"), den=("province_name", "last"))
    summ = summ.sort_values("lines", ascending=False, kind="stable")
    cid = st.selectbox("Chọn một khách đã chuyển tỉnh (khách có đơn hàng xếp trước)", summ.index.tolist(),
                       format_func=lambda c: f"Khách {c} · {summ.loc[c, 'de']} → {summ.loc[c, 'den']} · {int(summ.loc[c, 'lines'])} dòng bán",
                       key="scd_cust")
    sv = v[v.customer_id == cid].reset_index(drop=True)
    orders = num(q("""SELECT d.full_date AS ngay, f.order_id, f.net_revenue, cu.province_name AS tinh_luc_mua
                      FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_customer cu USING (customer_key)
                      WHERE cu.customer_id = %(c)s ORDER BY 1""", {"c": int(cid)}))
    cur_prov = sv[sv.is_current].province_name.iloc[0]
    lo, hi = rng.lo, rng.hi + dt.timedelta(days=1)
    tl = pd.DataFrame({"khach": f"Khách {cid}",
                       "tu": [pd.Timestamp(min(max(x, lo), hi)) for x in sv.valid_from],
                       "den": [pd.Timestamp(min(max(x, lo), hi)) for x in sv.valid_to],
                       "phien_ban": [f"Phiên bản {i + 1}: {r.province_name}" for i, r in sv.iterrows()]})
    left, right = st.columns([3, 2])
    with left:
        fig = px.timeline(tl, x_start="tu", x_end="den", y="khach", color="phien_ban", color_discrete_sequence=[BLUE, ORANGE, GREEN])
        if len(orders):
            by_day = orders.groupby("ngay").net_revenue.sum().reset_index()
            fig.add_scatter(x=pd.to_datetime(by_day.ngay), y=[f"Khách {cid}"] * len(by_day), mode="markers+text", name="Đơn hoàn tất",
                            marker=dict(size=16, color=INK, symbol="diamond", line=dict(color="white", width=2)),
                            text=[short(x) for x in by_day.net_revenue], textposition="top center",
                            textfont=dict(color="white", size=14))
        fig.update_yaxes(visible=False)
        fig.update_layout(height=260, margin=dict(t=10), legend=dict(orientation="h", y=-0.3))
        st.plotly_chart(fig)
    with right:
        if len(orders):
            at_sale = orders.groupby("tinh_luc_mua").net_revenue.sum().reset_index().rename(columns={"tinh_luc_mua": "tinh", "net_revenue": "doanh_so"})
            at_sale["cach_nhin"] = "SCD2: tỉnh lúc mua"
            now = pd.DataFrame({"tinh": [cur_prov], "doanh_so": [orders.net_revenue.sum()], "cach_nhin": ["Ghi đè (SCD1): tỉnh hiện tại"]})
            fig = px.bar(pd.concat([at_sale, now]), x="cach_nhin", y="doanh_so", color="tinh", text_auto=".3s", labels={"cach_nhin": "", "doanh_so": "Doanh số", "tinh": "Tỉnh"})
            fig.update_layout(height=260, margin=dict(t=10), legend=dict(orientation="h", y=-0.3))
            st.plotly_chart(fig)
        else:
            st.info("Khách này chưa có đơn hoàn tất trong kho. Chọn khách xếp đầu danh sách để thấy doanh số.")
    if len(orders):
        moved = orders[orders.tinh_luc_mua != cur_prov]
        st.success(f"Khách {cid} mua {len(orders)} dòng, tổng {vnd(orders.net_revenue.sum())}, lúc đó ở **{orders.tinh_luc_mua.iloc[0]}**; "
                   f"hiện ở **{cur_prov}**. Nếu ghi đè tỉnh (SCD1), {vnd(moved.net_revenue.sum())} bị tính nhầm cho {cur_prov}; "
                   f"SCD2 giữ đúng {orders.tinh_luc_mua.iloc[0]}.")
    table(sv.drop(columns=["customer_key"]).rename(columns={"province_name": "tinh", "lines": "dong_ban", "net": "doanh_so"}), f"scd2_khach_{cid}")

    st.markdown("**Tác động trên toàn bộ doanh thu trong khoảng đã chọn:** doanh thu theo tỉnh hiện tại trừ doanh thu theo tỉnh lúc mua")
    imp = num(q(f"""SELECT cu.province_name AS tinh_luc_mua, cur.province_name AS tinh_hien_tai, sum(f.net_revenue) AS doanh_thu,
                    count(DISTINCT cu.customer_id) AS so_khach
                    {FOI} JOIN dw.dim_customer cu USING (customer_key)
                    JOIN dw.dim_customer cur ON cur.customer_id = cu.customer_id AND cur.is_current
                    WHERE {W1} AND f.customer_key > 0 GROUP BY 1, 2""", p))
    moved = imp[imp.tinh_luc_mua != imp.tinh_hien_tai]
    c = st.columns(3)
    c[0].metric("Doanh thu của khách có tài khoản", short(imp.doanh_thu.sum()))
    c[1].metric("…thuộc khách đã chuyển tỉnh", vnd(moved.doanh_thu.sum()), f"{int(moved.so_khach.sum())} khách", delta_color="off")
    c[2].metric("Tỷ lệ bị gán sai nếu dùng tỉnh hiện tại", pct(moved.doanh_thu.sum() / imp.doanh_thu.sum(), 3))
    if len(moved):
        gain = moved.groupby("tinh_hien_tai").doanh_thu.sum()
        lose = moved.groupby("tinh_luc_mua").doanh_thu.sum()
        diff = gain.sub(lose, fill_value=0).rename_axis("tinh").reset_index(name="chenh_lech")
        diff["mau"] = diff.chenh_lech.map(lambda x: "Được cộng thêm" if x > 0 else "Bị trừ đi")
        fig = px.bar(diff, x="chenh_lech", y="tinh", orientation="h", color="mau",
                     color_discrete_map={"Được cộng thêm": GREEN, "Bị trừ đi": RED}, text=diff.chenh_lech.map(vnd),
                     labels={"chenh_lech": "Chênh lệch doanh thu (tỉnh hiện tại − tỉnh lúc mua)", "tinh": "", "mau": ""})
        fig.update_layout(height=max(200, 70 * len(diff)), margin=dict(t=10), legend=dict(orientation="h", y=-0.3))
        st.plotly_chart(fig)
    st.caption("Mock chỉ đổi tỉnh khách từ 25/01 nên chưa có khách nào mua ở cả hai phiên bản; khi mô phỏng chạy xa hơn, chênh lệch sẽ lớn dần.")


def scd_seller():
    st.markdown("#### Kỹ thuật 2 · SCD loại 2 và loại 3 trên seller: hạng hoặc tỉnh đổi giữa chừng, doanh thu trước và sau thuộc phiên bản nào?")
    st.caption("SCD2 giữ mọi phiên bản (phân tích đúng thời điểm bán). SCD3 chỉ giữ cặp 'hạng hiện tại / hạng liền trước' trên một dòng để đọc nhanh.")
    v = num(q("""WITH m AS (SELECT seller_id FROM dw.dim_seller WHERE seller_id > 0 GROUP BY 1 HAVING count(*) > 1)
                 SELECT s.seller_id, s.seller_key, s.shop_name, s.tier, s.province_name, s.status, s.valid_from, s.valid_to, s.is_current,
                        coalesce(x.lines, 0) AS lines, coalesce(x.net, 0) AS net
                 FROM dw.dim_seller s JOIN m USING (seller_id)
                 LEFT JOIN (SELECT seller_key, count(*) lines, sum(net_revenue) net FROM dw.fact_order_item GROUP BY 1) x USING (seller_key)
                 ORDER BY s.seller_id, s.valid_from"""))
    if v.empty:
        st.info("Chưa có seller nào đổi thuộc tính SCD2.")
        return
    summ = v.groupby("seller_id").agg(shop=("shop_name", "first"), lines=("lines", "sum")).sort_values("lines", ascending=False, kind="stable")
    sid = st.selectbox("Chọn một seller đã đổi thuộc tính", summ.index.tolist(), key="scd_sel",
                       format_func=lambda s: f"Seller {s} · {summ.loc[s, 'shop']} · {int(summ.loc[s, 'lines'])} dòng bán")
    sv = v[v.seller_id == sid].reset_index(drop=True)
    day = num(q("""SELECT d.full_date AS ngay, s.tier || ' · ' || s.province_name || ' · ' || s.status AS phien_ban, sum(f.net_revenue) AS doanh_thu
                   FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_seller s USING (seller_key)
                   WHERE s.seller_id = %(s)s GROUP BY 1, 2 ORDER BY 1""", {"s": int(sid)}))
    fig = px.bar(day, x="ngay", y="doanh_thu", color="phien_ban", labels={"ngay": "Ngày hoàn tất", "doanh_thu": "Doanh thu thuần", "phien_ban": "Phiên bản seller"})
    for r in sv[sv.valid_from > pd.Timestamp("1901-01-01").date()].itertuples():
        fig.add_shape(type="line", x0=str(r.valid_from), x1=str(r.valid_from), y0=0, y1=1, yref="paper", line=dict(color=RED, dash="dash", width=2))
        fig.add_annotation(x=str(r.valid_from), y=1, yref="paper", text=f"đổi thuộc tính {r.valid_from:%d/%m}", showarrow=False, yshift=12, font=dict(color=RED))
    fig.update_layout(height=380, margin=dict(t=40), legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig)
    t3 = q("SELECT current_tier, previous_tier, tier_changed_on FROM dw.dim_seller_tier_t3 WHERE seller_id = %(s)s", {"s": int(sid)})
    by = sv.groupby(["tier", "province_name", "status"], sort=False).agg(lines=("lines", "sum"), net=("net", "sum")).reset_index()
    if len(day):
        txt = "; ".join(f"{vnd(r.net)} ({int(r.lines)} dòng) thuộc phiên bản **{r.tier} · {r.province_name} · {r.status}**" for r in by.itertuples())
        st.success(f"Doanh thu của seller {sid}: {txt}. Nếu chỉ lưu giá trị hiện tại (SCD1), toàn bộ {vnd(sv.net.sum())} bị gán cho phiên bản mới nhất.")
    else:
        st.info("Seller này chưa có đơn hoàn tất trong kho; chọn seller xếp đầu danh sách để thấy doanh thu.")
    if len(t3):
        r = t3.iloc[0]
        st.caption(f"SCD3 (dim_seller_tier_t3): hạng hiện tại = {r.current_tier}, hạng liền trước = {r.previous_tier or '—'}, "
                   f"đổi ngày {r.tier_changed_on if pd.notna(r.tier_changed_on) else '—'}.")
    table(sv.drop(columns=["seller_key", "seller_id"]).rename(columns={"lines": "dong_ban", "net": "doanh_thu"}), f"scd2_seller_{sid}")


def mini_dimension(p):
    st.markdown("#### Kỹ thuật 3 · Mini-dimension: hồ sơ khách tại thời điểm mua mà không làm phình dim_customer")
    st.caption("Hạng thành viên, nhóm chi tiêu 12 tháng và tần suất mua đổi liên tục. Dùng SCD2 thì mỗi lần đổi là một dòng mới (cấu hình mock có thể tới ~8.500 lượt đổi hạng); "
               "mini-dimension chỉ có 125 tổ hợp cố định, mỗi dòng bán gắn đúng tổ hợp lúc mua.")
    mp = num(q(f"""SELECT cp.membership_tier AS hang, cp.spend_band_12m AS chi_tieu_12_thang, cp.frequency_band AS tan_suat,
                   sum(f.net_revenue) AS doanh_thu {FOI} JOIN dw.dim_customer_profile cp USING (customer_profile_key)
                   WHERE {W1} AND f.customer_profile_key > 0 GROUP BY 1, 2, 3""", p))
    if mp.empty:
        st.info("Không có dòng nào gắn hồ sơ khách trong khoảng đã chọn.")
        return
    by = mp.groupby(["hang", "chi_tieu_12_thang"], as_index=False).doanh_thu.sum()
    fig = px.bar(by, x="hang", y="doanh_thu", color="chi_tieu_12_thang", barmode="stack", text=by.doanh_thu.map(short),
                 labels={"hang": "Hạng thành viên lúc mua", "doanh_thu": "Doanh thu thuần", "chi_tieu_12_thang": "Chi tiêu 12 tháng trước đó"})
    fig.update_layout(height=360, margin=dict(t=10), legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(fig)
    new_share = by[by.chi_tieu_12_thang.str.contains("Chưa", case=False)].doanh_thu.sum() / by.doanh_thu.sum()
    st.info(f"{new_share * 100:.0f}% doanh thu đến từ khách chưa có lịch sử mua trong 12 tháng trước (kho mới có khoảng một tháng dữ liệu); "
            "khi dữ liệu dài hơn, các nhóm chi tiêu cao sẽ tách rõ. Dùng cách này, đổi hạng hay đổi nhóm chi tiêu không tạo thêm dòng nào trong dim_customer.")


def bridge_promotion(p):
    st.markdown("#### Kỹ thuật 4 · Bridge khuyến mãi: một dòng bán có thể dùng nhiều voucher mà không nhân đôi doanh thu")
    st.caption("Quan hệ nhiều-nhiều giữa dòng bán và voucher đi qua nhóm khuyến mãi (promotion_group). "
               "Mỗi voucher trong nhóm có weighting_factor, tổng các trọng số của nhóm bằng 1 nên giảm giá phân bổ vẫn cộng lại đúng.")
    g = num(q("""SELECT count(*) AS nhom, count(*) FILTER (WHERE so_voucher >= 2) AS nhom_nhieu_voucher,
                 bool_and(abs(tong_trong_so - 1) < 0.000001) AS trong_so_hop_le
                 FROM (SELECT promotion_group_key, count(*) so_voucher, sum(weighting_factor) tong_trong_so
                       FROM dw.bridge_promotion_group GROUP BY 1) x""")).iloc[0]
    rec = num(q(f"""SELECT (SELECT sum(f.discount_amount) {FOI} WHERE {W1} AND f.promotion_group_key > 0) AS fact_discount,
                    sum(f.discount_amount) AS join_khong_trong_so, sum(f.discount_amount * b.weighting_factor) AS phan_bo
                    {FOI} JOIN dw.bridge_promotion_group b USING (promotion_group_key) WHERE {W1} AND f.promotion_group_key > 0""", p)).fillna(0).iloc[0]
    c = st.columns(4)
    c[0].metric("Nhóm khuyến mãi", intf(g.nhom), f"{intf(g.nhom_nhieu_voucher)} nhóm có ≥ 2 voucher", delta_color="off")
    c[1].metric("Σ giảm giá trên fact", vnd(rec.fact_discount))
    c[2].metric("Σ nối bridge, không trọng số", vnd(rec.join_khong_trong_so), "sẽ nhân đôi nếu có nhóm 2 voucher", delta_color="off")
    ok = abs(rec.phan_bo - rec.fact_discount) < 1
    c[3].metric("Σ phân bổ theo trọng số", vnd(rec.phan_bo), "khớp fact" if ok else "LỆCH", delta_color="off" if ok else "inverse")
    pm = num(q(f"""SELECT p.promo_code || ' · ' || p.promo_name AS voucher, p.funded_by AS nguon_chi, sum(f.discount_amount * b.weighting_factor) AS giam_gia_phan_bo,
                   sum(f.net_revenue * b.weighting_factor) AS doanh_thu_phan_bo
                   {FOI} JOIN dw.bridge_promotion_group b USING (promotion_group_key) JOIN dw.dim_promotion p USING (promotion_key)
                   WHERE {W1} GROUP BY 1, 2 ORDER BY 3 DESC""", p))
    if len(pm):
        fig = px.bar(pm, x="giam_gia_phan_bo", y="voucher", color="nguon_chi", orientation="h",
                     labels={"giam_gia_phan_bo": "Giảm giá phân bổ (VND)", "voucher": "", "nguon_chi": "Bên chịu chi phí"})
        fig.update_layout(height=max(200, 60 * len(pm) + 80), margin=dict(t=10), yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig)
    st.caption("Hiện mỗi dòng bán chỉ dùng một voucher nên cách nối có và không có trọng số cho cùng kết quả; "
               "trọng số mới có tác dụng khi một dòng dùng từ hai voucher (chưa xuất hiện trong dữ liệu mock hiện có).")


# ------------------------------------------------------------------------------------------------
# Tab 2 · Fact_Inventory_Snapshot
# ------------------------------------------------------------------------------------------------
INV = "dw.fact_inventory_snapshot"


def tab_inventory():
    kicker("còn bao nhiêu hàng, kho nào giữ, hàng nào sắp hết và hàng nào đang tồn dư.",
           "tồn của một sản phẩm tại một kho vào cuối một ngày. Tồn kho là semi-additive: cộng được qua sản phẩm và kho, không cộng qua ngày.")
    rng = q(f"SELECT min(full_date) lo, max(full_date) hi FROM {INV} JOIN dw.dim_date USING (date_key)").iloc[0]
    d0, d1 = date_range("Khoảng ngày", "inv_range", rng.lo, rng.hi)
    if d0 >= d1:
        st.info("Chọn khoảng từ hai ngày trở lên để thấy biến động tồn kho.")
        return
    s_key, e_key = int(d0.strftime("%Y%m%d")), int(d1.strftime("%Y%m%d"))
    first_key = int(q(f"SELECT min(date_key) k FROM {INV}").k.iloc[0])
    p = {"s": s_key, "e": e_key}
    k = num(q(f"""SELECT sum(quantity_on_hand) on_hand, sum(quantity_reserved) reserved, sum(inventory_value_est) val,
                  count(DISTINCT product_key) sp, count(*) FILTER (WHERE quantity_on_hand = 0) zero, coalesce(sum(stockout_flag), 0) so
                  FROM {INV} WHERE date_key = %(e)s""", p)).iloc[0]
    st0 = num(q(f"SELECT sum(quantity_on_hand) on_hand FROM {INV} WHERE date_key = %(s)s", p)).on_hand.iloc[0]
    c = st.columns(5)
    c[0].metric("Tồn cuối kỳ (món)", intf(k.on_hand), f"{k.on_hand - st0:+,.0f} so với đầu kỳ".replace(",", "."), delta_color="off")
    c[1].metric("Giá trị tồn ước tính", short(k.val), "giá vốn là giả định", delta_color="off")
    c[2].metric("Sản phẩm có tồn", intf(k.sp))
    c[3].metric("Đang giữ chỗ cho đơn", intf(k.reserved))
    c[4].metric("Dòng hết hàng", intf(k.zero), "stockout_flag = " + intf(k.so), delta_color="off")

    st.markdown("## A. Bài toán kinh doanh")

    st.markdown("#### 1. Hàng vào ra thế nào và tồn kho biến động ra sao?")
    flow = num(q(f"""SELECT d.full_date AS ngay, sum(f.qty_imported) AS nhap, sum(f.qty_returned) AS hoan, sum(f.qty_sold) AS ban,
                     sum(f.qty_adjusted) AS dieu_chinh, sum(f.quantity_on_hand) AS ton
                     FROM {INV} f JOIN dw.dim_date d USING (date_key) WHERE f.date_key BETWEEN %(s)s AND %(e)s AND f.date_key > {first_key}
                     GROUP BY 1 ORDER BY 1""", p))
    fig = go.Figure()
    fig.add_bar(x=flow.ngay, y=flow.nhap, name="Nhập kho", marker_color=GREEN)
    fig.add_bar(x=flow.ngay, y=flow.hoan, name="Khách trả hàng", marker_color=PURPLE)
    fig.add_bar(x=flow.ngay, y=-flow.ban, name="Bán xuất kho", marker_color=ORANGE)
    fig.add_bar(x=flow.ngay, y=flow.dieu_chinh, name="Điều chỉnh kiểm kê", marker_color=GREY)
    fig.add_scatter(x=flow.ngay, y=flow.ton, name="Tồn cuối ngày (trục phải)", yaxis="y2", mode="lines+markers", line=dict(color=INK, width=2))
    fig.update_layout(barmode="relative", height=400, margin=dict(t=30), legend=dict(orientation="h", y=1.12),
                      yaxis=dict(title="Số món vào (+) / ra (−) trong ngày"),
                      yaxis2=dict(title="Tồn cuối ngày", overlaying="y", side="right", showgrid=False))
    st.plotly_chart(fig)
    if s_key == first_key:
        st.caption("Ngày đầu tiên của kho là lần nạp tồn ban đầu (hàng triệu món), không vẽ để không che các biến động nhỏ hằng ngày.")

    st.markdown("#### 2. Đối soát dòng chảy: tồn đầu kỳ + nhập + trả − bán ± điều chỉnh = tồn cuối kỳ")
    fl = num(q(f"""SELECT coalesce(sum(qty_imported), 0) nhap, coalesce(sum(qty_returned), 0) hoan, coalesce(sum(qty_sold), 0) ban,
                   coalesce(sum(qty_adjusted), 0) dc FROM {INV} WHERE date_key > %(s)s AND date_key <= %(e)s""", p)).iloc[0]
    vals = [st0, fl.nhap, fl.hoan, fl.dc, -fl.ban, k.on_hand]
    levels = [st0, st0 + fl.nhap, st0 + fl.nhap + fl.hoan, st0 + fl.nhap + fl.hoan + fl.dc, k.on_hand, k.on_hand]
    fig = waterfall(["Tồn đầu kỳ", "Nhập kho", "Khách trả", "Điều chỉnh", "Bán xuất kho", "Tồn cuối kỳ"], vals,
                    ["absolute", "relative", "relative", "relative", "relative", "total"], height=360, fmt=intf)
    pad = max((max(levels) - min(levels)) * 0.25, 5)
    fig.update_yaxes(range=[min(levels) - pad, max(levels) + pad], title="Số món (trục được cắt để thấy chênh lệch)")
    st.plotly_chart(fig)
    diff = st0 + fl.nhap + fl.hoan + fl.dc - fl.ban - k.on_hand
    (st.success if abs(diff) < 1 else st.warning)(
        f"Tồn đầu {intf(st0)} + nhập {intf(fl.nhap)} + trả {intf(fl.hoan)} + điều chỉnh {intf(fl.dc)} − bán {intf(fl.ban)} = "
        f"{intf(st0 + fl.nhap + fl.hoan + fl.dc - fl.ban)}; tồn cuối trong kho {intf(k.on_hand)}. "
        + ("Khớp tuyệt đối." if abs(diff) < 1 else f"Lệch {intf(diff)} món."))

    st.markdown("#### 3. Hàng nào bán chạy mà tồn thấp, hàng nào tồn nhiều mà ít bán?")
    pr = num(q(f"""WITH s AS (SELECT p.product_id, sum(f.qty_sold) sold FROM {INV} f JOIN dw.dim_product p USING (product_key)
                              WHERE f.date_key BETWEEN %(s)s AND %(e)s GROUP BY 1),
                        e AS (SELECT p.product_id, sum(f.quantity_on_hand) on_hand, sum(f.inventory_value_est) val
                              FROM {INV} f JOIN dw.dim_product p USING (product_key) WHERE f.date_key = %(e)s GROUP BY 1),
                        n AS (SELECT DISTINCT ON (product_id) product_id, product_name FROM dw.dim_product WHERE product_id > 0
                              ORDER BY product_id, valid_from DESC)
                   SELECT e.product_id, n.product_name, coalesce(s.sold, 0) AS ban, e.on_hand AS ton, e.val AS gia_tri_ton
                   FROM e LEFT JOIN s USING (product_id) JOIN n USING (product_id)""", p))
    sold = pr[pr.ban > 0].copy()
    days = max((d1 - d0).days, 1)
    if len(sold):
        mx, my = sold.ban.median(), sold.ton.median()
        sold["nhom"] = sold.apply(lambda r: ("Bán chạy · tồn thấp (cần nhập)" if r.ton <= my else "Bán chạy · tồn cao (khỏe)")
                                  if r.ban >= mx else ("Bán chậm · tồn thấp (ổn)" if r.ton <= my else "Bán chậm · tồn cao (tồn dư)"), axis=1)
        sold["ngay_du_ban"] = sold.ton / (sold.ban / days)
        order4 = ["Bán chậm · tồn cao (tồn dư)", "Bán chạy · tồn cao (khỏe)", "Bán chậm · tồn thấp (ổn)", "Bán chạy · tồn thấp (cần nhập)"]
        grid = sold.groupby("nhom").agg(sp=("product_id", "count"), ton=("ton", "sum")).reindex(order4).fillna(0)
        cells = [(order4[0], 0, 1, ORANGE), (order4[1], 1, 1, GREEN), (order4[2], 0, 0, GREY), (order4[3], 1, 0, RED)]
        fig = go.Figure()
        for name, cx, cy, col in cells:
            fig.add_shape(type="rect", x0=cx, x1=cx + 1, y0=cy, y1=cy + 1, fillcolor=col, line=dict(color="white", width=5))
            fig.add_annotation(x=cx + 0.5, y=cy + 0.5, showarrow=False, font=dict(color="white", size=16),
                               text=f"<b>{name}</b><br>{intf(grid.loc[name, 'sp'])} sản phẩm<br>tồn {intf(grid.loc[name, 'ton'])} món")
        fig.add_annotation(x=1, y=-0.12, text="Bán chậm  ◄  số món bán trong kỳ  ►  Bán chạy", showarrow=False, font=dict(size=13))
        fig.add_annotation(x=-0.1, y=1, text="Tồn thấp  ◄  tồn cuối kỳ  ►  Tồn cao", showarrow=False, textangle=-90, font=dict(size=13))
        fig.update_xaxes(range=[-0.15, 2], visible=False)
        fig.update_yaxes(range=[-0.2, 2], visible=False)
        fig.update_layout(height=430, margin=dict(t=10, b=10), plot_bgcolor="white")
        l3, r3 = st.columns([3, 2])
        with l3:
            st.plotly_chart(fig)
        with r3:
            st.markdown("**Cách đọc**")
            st.markdown(f"- Chia bốn nhóm theo trung vị: bán **{intf(mx)} món** và tồn **{intf(my)} món** trong khoảng đã chọn.\n"
                        "- **Đỏ** (bán chạy, tồn thấp): ứng viên nhập thêm.\n"
                        "- **Cam** (bán chậm, tồn cao): vốn bị giữ, cân nhắc xả hàng.\n"
                        "- **Xanh**: bán tốt, còn đủ hàng.\n"
                        f"- Ngoài lưới còn **{intf((pr.ban == 0).sum())}** sản phẩm không bán được món nào.")
        left, right = st.columns(2)
        with left:
            st.markdown("**Cần nhập sớm nhất** (số ngày tồn đủ bán theo tốc độ bán trong kỳ, thấp nhất)")
            st.caption("Tồn mô phỏng rất lớn so với tốc độ bán nên số ngày đủ bán lớn; dùng để xếp hạng tương đối, không phải dự báo thật.")
            low = sold.sort_values("ngay_du_ban").head(10)
            fig = px.bar(low, x="ngay_du_ban", y=low.product_name.str.slice(0, 40), orientation="h",
                         labels={"ngay_du_ban": "Số ngày đủ bán", "y": ""}, color_discrete_sequence=[RED])
            fig.update_layout(height=380, margin=dict(t=10), yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig)
        with right:
            nosale = pr[pr.ban == 0].sort_values("gia_tri_ton", ascending=False).head(10)
            st.markdown(f"**Tồn dư không bán được** ({intf((pr.ban == 0).sum())} sản phẩm không bán món nào trong kỳ; 10 sản phẩm giữ nhiều vốn nhất)")
            fig = px.bar(nosale, x="gia_tri_ton", y=nosale.product_name.str.slice(0, 40), orientation="h",
                         labels={"gia_tri_ton": "Giá trị tồn ước tính (VND)", "y": ""}, color_discrete_sequence=[ORANGE])
            fig.update_layout(height=380, margin=dict(t=10), yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig)
        st.info(f"{intf(len(sold))} sản phẩm có bán trong kỳ, {intf((pr.ban == 0).sum())} sản phẩm không bán. "
                f"Nhóm đỏ có {intf(grid.loc[order4[3], 'sp'])} sản phẩm là ứng viên nhập thêm.")
    else:
        st.info("Không có sản phẩm nào bán trong khoảng đã chọn.")

    st.markdown("#### 4. Kho nào đang giữ nhiều hàng và nhiều vốn nhất?")
    wh = num(q(f"""SELECT w.warehouse_name AS kho, w.region AS vung, sum(f.quantity_on_hand) AS ton, sum(f.quantity_reserved) AS giu_cho,
                   sum(f.inventory_value_est) AS gia_tri FROM {INV} f JOIN dw.dim_warehouse w USING (warehouse_key)
                   WHERE f.date_key = %(e)s GROUP BY 1, 2 ORDER BY 3 DESC""", p))
    left, right = st.columns(2)
    with left:
        fig = px.bar(wh, x="ton", y="kho", color="vung", orientation="h", labels={"ton": "Tồn cuối kỳ (món)", "kho": "", "vung": "Vùng"})
        fig.update_layout(height=330, margin=dict(t=10), yaxis=dict(autorange="reversed"), legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(fig)
    with right:
        fig = px.pie(wh, names="kho", values="gia_tri", hole=0.45)
        fig.update_layout(height=330, margin=dict(t=10), legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(fig)

    st.markdown("## B. Kỹ thuật kho dữ liệu thể hiện trên bảng fact này")
    semi_additive(p, s_key, e_key)
    st.divider()
    scd_product(p, s_key, e_key)
    st.divider()
    st.markdown("#### Kỹ thuật 3 · Bridge cây danh mục: giá trị tồn của một danh mục cha gồm cả cây con")
    st.caption("Cùng bảng bridge với fact bán hàng. Một phép nối cho tổng cả cây, không cần truy vấn đệ quy và không cộng lặp.")
    bridge_category("inv", f"{INV} f", "f.inventory_value_est", "f.date_key = %(e)s", p, short)


def semi_additive(p, s_key, e_key):
    st.markdown("#### Kỹ thuật 1 · Measure semi-additive: tồn kho không được cộng qua các ngày")
    st.caption("Tồn là số dư tại một thời điểm. Cộng được qua sản phẩm và kho, nhưng cộng qua ngày thì cùng một món hàng bị đếm lại mỗi ngày. "
               "Qua thời gian phải lấy tồn cuối kỳ hoặc bình quân ngày.")
    r = num(q(f"""SELECT sum(quantity_on_hand) AS cong_qua_ngay, count(DISTINCT date_key) AS so_ngay,
                  sum(quantity_on_hand) FILTER (WHERE date_key = %(e)s) AS cuoi_ky FROM {INV} WHERE date_key BETWEEN %(s)s AND %(e)s""", p)).iloc[0]
    avg = r.cong_qua_ngay / r.so_ngay
    df = pd.DataFrame({"cach_tinh": ["SUM qua các ngày (SAI)", "Tồn cuối kỳ (đúng)", "Bình quân theo ngày (đúng)"], "so_mon": [r.cong_qua_ngay, r.cuoi_ky, avg],
                       "loai": ["Sai", "Đúng", "Đúng"]})
    fig = px.bar(df, x="cach_tinh", y="so_mon", color="loai", color_discrete_map={"Sai": RED, "Đúng": GREEN}, text=df.so_mon.map(intf),
                 labels={"cach_tinh": "", "so_mon": "Số món", "loai": ""})
    fig.update_layout(height=340, margin=dict(t=10))
    st.plotly_chart(fig)
    st.error(f"Cộng tồn qua {int(r.so_ngay)} ngày cho {intf(r.cong_qua_ngay)} món, gấp {r.cong_qua_ngay / r.cuoi_ky:.0f} lần tồn thật ({intf(r.cuoi_ky)}). "
             "Dashboard dùng tồn ngày cuối kỳ (mart.mv_inventory_month_product) để tránh lỗi này.")


def scd_product(p, s_key, e_key):
    st.markdown("#### Kỹ thuật 2 · SCD loại 2 trên sản phẩm: đổi phiên bản thì khóa đổi, tồn kho có bị đứt hoặc đếm đôi không?")
    st.caption("Khi seller bị khóa (27/01), các sản phẩm của seller đó chuyển is_active = false và có phiên bản mới với product_key mới. "
               "Fact tồn kho trỏ đúng phiên bản theo ngày, nên muốn gộp theo sản phẩm phải dùng product_id (mã nghiệp vụ), không phải product_key.")
    v = num(q("""WITH m AS (SELECT product_id FROM dw.dim_product WHERE product_id > 0 GROUP BY 1 HAVING count(*) > 1)
                 SELECT p.product_id, p.product_key, p.product_name, p.is_active, p.list_price, p.unit_cost_est, p.valid_from, p.valid_to
                 FROM dw.dim_product p JOIN m USING (product_id) ORDER BY p.product_id, p.valid_from"""))
    if v.empty:
        st.info("Chưa có sản phẩm nào có từ hai phiên bản.")
        return
    names = v.groupby("product_id").product_name.first()
    pid = st.selectbox("Chọn một sản phẩm đã đổi phiên bản", names.index.tolist(), key="scd_prod",
                       format_func=lambda x: f"{x} · {names.loc[x][:50]}")
    sv = v[v.product_id == pid].reset_index(drop=True)
    lab = {r.product_key: f"Phiên bản {i + 1}: {'đang bán' if r.is_active else 'ngừng bán'} từ {r.valid_from:%d/%m}" if i else
           f"Phiên bản {i + 1}: {'đang bán' if r.is_active else 'ngừng bán'}" for i, r in sv.iterrows()}
    day = num(q(f"""SELECT d.full_date AS ngay, f.product_key, sum(f.quantity_on_hand) AS ton FROM {INV} f
                    JOIN dw.dim_date d USING (date_key) JOIN dw.dim_product p USING (product_key) WHERE p.product_id = %(i)s GROUP BY 1, 2 ORDER BY 1""",
                  {"i": int(pid)}))
    day["phien_ban"] = day.product_key.map(lab)
    fig = px.line(day, x="ngay", y="ton", color="phien_ban", markers=True, color_discrete_sequence=[BLUE, ORANGE, GREEN],
                  labels={"ngay": "Ngày", "ton": "Tồn của sản phẩm (mọi kho)", "phien_ban": ""})
    fig.update_yaxes(rangemode="tozero")
    for r in sv.iloc[1:].itertuples():
        fig.add_shape(type="line", x0=str(r.valid_from), x1=str(r.valid_from), y0=0, y1=1, yref="paper", line=dict(color=RED, dash="dash", width=2))
        fig.add_annotation(x=str(r.valid_from), y=1, yref="paper", text=f"đổi phiên bản {r.valid_from:%d/%m}", showarrow=False, yshift=12, font=dict(color=RED))
    fig.update_layout(height=340, margin=dict(t=30), legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(fig)
    st.caption("Đường tồn đổi màu đúng ngày đổi phiên bản nhưng liền mạch, vì mã nghiệp vụ product_id không đổi.")
    naive = num(q(f"""SELECT sum(t) v FROM (SELECT DISTINCT ON (product_key, warehouse_key) quantity_on_hand AS t FROM {INV}
                      WHERE date_key BETWEEN %(s)s AND %(e)s ORDER BY product_key, warehouse_key, date_key DESC) x""", p)).v.iloc[0]
    good = num(q(f"""SELECT sum(t) v FROM (SELECT DISTINCT ON (pr.product_id, f.warehouse_key) f.quantity_on_hand AS t FROM {INV} f
                     JOIN dw.dim_product pr USING (product_key) WHERE f.date_key BETWEEN %(s)s AND %(e)s
                     ORDER BY pr.product_id, f.warehouse_key, f.date_key DESC) x""", p)).v.iloc[0]
    c = st.columns(3)
    c[0].metric("Tồn cuối kỳ: gom theo product_key (SAI)", intf(naive), "mỗi phiên bản lấy 'ngày cuối' riêng", delta_color="off")
    c[1].metric("Tồn cuối kỳ: gom theo product_id (ĐÚNG)", intf(good))
    c[2].metric("Chênh lệch", intf(naive - good), "món bị đếm đôi" if naive != good else "không lệch", delta_color="inverse" if naive != good else "off")
    st.caption("Đây là lỗi bộ kiểm thử T5 đã tự phát hiện: công thức độc lập gom theo product_key làm tổng tồn lệch 11.688 món khi kỳ qua 25/01; mart gom theo product_id nên đúng.")
    table(sv.drop(columns=["product_key", "product_id"]).rename(columns={"product_name": "san_pham"}), f"scd2_san_pham_{pid}")


# ------------------------------------------------------------------------------------------------
# Tab 3 · Fact_Ad_Spend
# ------------------------------------------------------------------------------------------------
def tab_ads():
    kicker("tiền quảng cáo bỏ ra có tạo ra doanh thu không, kênh nào được đầu tư, ngân sách dùng hết chưa.",
           "chi phí của một chiến dịch trên một kênh trong một tháng. Chi phí, lượt hiển thị, lượt click cộng được; CTR, CPC, ROAS là tỷ số, luôn tính lại từ tử và mẫu.")
    months = q("SELECT DISTINCT a.month_key, m.month_label FROM dw.fact_ad_spend a JOIN dw.dim_month m USING (month_key) ORDER BY 1")
    if months.empty:
        st.info("Kho chưa có chi phí quảng cáo.")
        return
    sel = st.multiselect("Tháng", months.month_label.tolist(), default=months.month_label.tolist(), key="ads_months")
    mk = months[months.month_label.isin(sel)].month_key.tolist() or months.month_key.tolist()
    p = {"m": mk}
    camp = num(q("""SELECT c.campaign_key, c.campaign_name, c.campaign_type, ch.channel_name, c.budget_amount, c.start_date, c.end_date,
                    sum(a.cost_amount) AS chi_phi, sum(a.impressions) AS hien_thi, sum(a.clicks) AS click, sum(a.active_days) AS ngay_chay
                    FROM dw.fact_ad_spend a JOIN dw.dim_campaign c USING (campaign_key) JOIN dw.dim_channel ch ON ch.channel_key = a.channel_key
                    WHERE a.month_key = ANY(%(m)s) GROUP BY 1, 2, 3, 4, 5, 6, 7 ORDER BY 1""", p))
    att = num(q(f"""SELECT f.campaign_key, count(DISTINCT f.order_id) AS don, sum(f.net_revenue) AS doanh_thu {FOI}
                    WHERE d.month_key = ANY(%(m)s) AND f.campaign_key > 0 GROUP BY 1""", p))
    camp = camp.merge(att, on="campaign_key", how="left").fillna({"don": 0, "doanh_thu": 0})
    tot = camp[["chi_phi", "hien_thi", "click", "don", "doanh_thu", "budget_amount"]].sum()
    c = st.columns(6)
    c[0].metric("Chi phí quảng cáo", short(tot.chi_phi))
    c[1].metric("Ngân sách đã dùng", pct(tot.chi_phi / tot.budget_amount, 1) if tot.budget_amount else "—")
    c[2].metric("CTR (click / hiển thị)", pct(tot.click / tot.hien_thi))
    c[3].metric("CPC (chi phí / click)", vnd(tot.chi_phi / tot.click) if tot.click else "—")
    c[4].metric("Doanh thu gắn chiến dịch", short(tot.doanh_thu))
    c[5].metric("ROAS (thu / chi)", f"{tot.doanh_thu / tot.chi_phi:,.0f} lần".replace(",", ".") if tot.chi_phi else "—", "chỉ tham khảo", delta_color="off")

    st.markdown("## A. Bài toán kinh doanh")
    left, right = st.columns(2)
    with left:
        st.markdown("#### 1. Phễu quảng cáo: từ hiển thị đến đơn hàng")
        fun = pd.DataFrame({"buoc": ["Lượt hiển thị", "Lượt click", "Đơn gắn chiến dịch"], "so": [tot.hien_thi, tot.click, tot.don]})
        fig = px.funnel(fun, x="so", y="buoc", color_discrete_sequence=[BLUE], labels={"so": "Số lượng", "buoc": ""})
        fig.update_traces(texttemplate="%{x:,.0f}")
        fig.update_layout(height=340, margin=dict(t=10))
        st.plotly_chart(fig)
        st.caption(f"Click/hiển thị = {pct(tot.click / tot.hien_thi)}; đơn/click = {pct(tot.don / tot.click) if tot.click else '—'} (đơn gắn chiến dịch, không phải mọi click đều ghi nhận đơn).")
    with right:
        st.markdown("#### 2. Ngân sách đã dùng bao nhiêu so với kế hoạch?")
        fig = go.Figure()
        fig.add_bar(y=camp.campaign_name, x=camp.budget_amount, name="Ngân sách", orientation="h", marker_color="#cbd5e1")
        fig.add_bar(y=camp.campaign_name, x=camp.chi_phi, name="Đã chi", orientation="h", marker_color=BLUE,
                    text=[f"{short(a)} ({a / b * 100:.0f}%)" if b else short(a) for a, b in zip(camp.chi_phi, camp.budget_amount)], textposition="inside")
        fig.update_layout(barmode="overlay", height=340, margin=dict(t=10), legend=dict(orientation="h", y=-0.2), xaxis_title="VND")
        st.plotly_chart(fig)
        st.caption("Ngân sách là của cả chiến dịch; chi phí cộng dồn qua các tháng đã chọn.")

    st.markdown("#### 3. Chiến dịch nào hiệu quả? Chi phí so với doanh thu gắn chiến dịch")
    cmp_ = camp.melt(id_vars=["campaign_name"], value_vars=["chi_phi", "doanh_thu"], var_name="chi_so", value_name="vnd")
    cmp_["chi_so"] = cmp_.chi_so.map({"chi_phi": "Chi phí quảng cáo", "doanh_thu": "Doanh thu đơn gắn chiến dịch"})
    left, right = st.columns([3, 2])
    with left:
        fig = px.bar(cmp_, x="campaign_name", y="vnd", color="chi_so", barmode="group", log_y=True, text=cmp_.vnd.map(short),
                     color_discrete_map={"Chi phí quảng cáo": RED, "Doanh thu đơn gắn chiến dịch": GREEN},
                     labels={"campaign_name": "", "vnd": "VND (thang log vì chênh nhau hàng trăm lần)", "chi_so": ""})
        fig.update_layout(height=340, margin=dict(t=10), legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig)
    with right:
        camp["roas"] = camp.doanh_thu / camp.chi_phi
        camp["cpc"] = camp.chi_phi / camp.click
        fig = px.bar(camp, x="campaign_name", y="roas", text=camp.roas.map(lambda x: f"{x:,.0f}×"), color_discrete_sequence=[GREEN],
                     labels={"campaign_name": "", "roas": "ROAS (doanh thu / chi phí)"})
        fig.update_layout(height=340, margin=dict(t=10))
        st.plotly_chart(fig)

    st.markdown("#### 4. Doanh thu gắn chiến dịch rơi vào những ngày nào?")
    dd = num(q(f"""SELECT d.full_date AS ngay, sum(f.net_revenue) FILTER (WHERE f.campaign_key > 0) AS gan_chien_dich,
                   sum(f.net_revenue) FILTER (WHERE f.campaign_key = -1) AS khong_gan {FOI} WHERE d.month_key = ANY(%(m)s) GROUP BY 1 ORDER BY 1""", p)).fillna(0)
    fig = go.Figure()
    fig.add_bar(x=dd.ngay, y=dd.khong_gan, name="Đơn không gắn chiến dịch", marker_color="#cbd5e1")
    fig.add_bar(x=dd.ngay, y=dd.gan_chien_dich, name="Đơn gắn chiến dịch", marker_color=BLUE)
    for r in camp.itertuples():
        fig.add_shape(type="rect", x0=str(max(r.start_date, dd.ngay.min())), x1=str(min(r.end_date, dd.ngay.max())), y0=0, y1=1, yref="paper",
                      fillcolor="rgba(37,99,235,0.07)", line_width=0)
    fig.update_layout(barmode="stack", height=340, margin=dict(t=10), legend=dict(orientation="h", y=-0.2), yaxis_title="Doanh thu thuần (VND)")
    st.plotly_chart(fig)
    st.caption("Vùng xanh nhạt là thời gian hiệu lực của chiến dịch. Fact quảng cáo chỉ có mức tháng nên so sánh với bán hàng được ở mức tháng–kênh, còn mức ngày lấy từ fact bán hàng.")
    table(camp.drop(columns=["campaign_key"]), "chien_dich_quang_cao")

    st.markdown("## B. Kỹ thuật kho dữ liệu thể hiện trên bảng fact này")
    drill_across(p)


def drill_across(p):
    st.markdown("#### Kỹ thuật 1 · Conformed dimension và drill-across bằng FULL OUTER JOIN: kênh bán nhưng chưa chạy quảng cáo")
    st.caption("dim_channel và dim_month dùng chung cho Fact_Order_Item và Fact_Ad_Spend nên ghép được hai fact theo (tháng, kênh). "
               "INNER JOIN sẽ làm mất kênh chỉ có một phía; FULL OUTER JOIN giữ lại và đánh dấu.")
    a = num(q("SELECT * FROM mart.v_drill_sales_ads WHERE month_key = ANY(%(m)s) ORDER BY month_key, channel_key", p))
    if a.empty:
        st.info("Chưa có dữ liệu ghép.")
        return
    a["trang_thai"] = a.apply(lambda r: "Có bán, chưa có quảng cáo" if r.missing_ads else ("Có quảng cáo, không có bán" if r.missing_sales else "Đủ hai phía"), axis=1)
    lost = a[a.missing_ads].net_revenue.sum()
    left, right = st.columns([3, 2])
    with left:
        fig = px.bar(a, x="channel_name", y="net_revenue", color="trang_thai", facet_col="month_label",
                     color_discrete_map={"Đủ hai phía": BLUE, "Có bán, chưa có quảng cáo": ORANGE, "Có quảng cáo, không có bán": RED},
                     text=a.net_revenue.map(short), labels={"channel_name": "Kênh", "net_revenue": "Doanh thu thuần", "trang_thai": ""})
        fig.update_layout(height=360, margin=dict(t=30), legend=dict(orientation="h", y=-0.25))
        fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
        st.plotly_chart(fig)
    with right:
        st.metric("Doanh thu sẽ biến mất nếu dùng INNER JOIN", vnd(lost), f"{lost / a.net_revenue.sum() * 100:.1f}% doanh thu các tháng đã chọn", delta_color="off")
        st.metric("Kênh có bán nhưng chưa có quảng cáo", ", ".join(a[a.missing_ads].channel_name.unique()) or "—")
    st.warning("Doanh thu/chi phí ở bảng dưới chỉ là tỷ số tham khảo: kênh không có quảng cáo thì ô chi phí để trống (NULL), không phải 0.")
    table(a.drop(columns=["month_key", "channel_key", "missing_sales", "missing_ads"]), "drill_doanh_thu_quang_cao_theo_kenh")
    st.caption("CTR, CPC, ROAS là measure non-additive: dashboard luôn tính Σ click / Σ hiển thị, Σ chi phí / Σ click… từ các số cộng được, không lấy trung bình các tỷ số.")


# ------------------------------------------------------------------------------------------------
def render():
    t1, t2, t3 = st.tabs(["Fact_Order_Item · Bán hàng", "Fact_Inventory_Snapshot · Tồn kho", "Fact_Ad_Spend · Quảng cáo"])
    with t1:
        tab_order_item()
    with t2:
        tab_inventory()
    with t3:
        tab_ads()
