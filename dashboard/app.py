"""PLAN 6.3 — Dashboard kho dữ liệu TMĐT (Streamlit + Plotly), 5 màn hình.

    bash dashboard/run.sh            # chạy nền trong WSL → http://localhost:8501
    .venv/bin/streamlit run dashboard/app.py

Kết nối bằng role CHỈ ĐỌC dw_analyst (đổi bằng biến môi trường DW_DASH_URL). Mọi số liệu đọc từ dw/mart/audit;
KPI non-additive tính lại từ tử/mẫu theo mart.kpi_definitions. Mọi bảng có nút xuất CSV.
"""
import datetime as dt
import os

import pandas as pd
import plotly.express as px
import psycopg
import streamlit as st

DSN = os.getenv("DW_DASH_URL", "postgresql://dw_analyst:dw_analyst_local@127.0.0.1:55432/dwh")
PAGES = ["Tổng quan bán hàng", "Lịch sử thuộc tính (SCD)", "Đối soát vận hành (drill-across)",
         "Chất lượng dữ liệu", "Hiệu năng"]

st.set_page_config(page_title="DW TMĐT · Nhóm 5", page_icon="📊", layout="wide")


# ------------------------------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def q(sql, params=None):
    with psycopg.connect(DSN) as con:
        cur = con.execute(sql, params or {})
        cols = [c.name for c in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def num(df):
    """Decimal → float để Plotly/pandas tính và vẽ."""
    for c in df.columns:
        if df[c].dtype == object and len(df) and df[c].map(lambda v: type(v).__name__ == "Decimal").any():
            df[c] = df[c].astype(float)
    return df


def vnd(x):
    return "—" if x is None or pd.isna(x) else f"{float(x):,.0f} đ".replace(",", ".")


def pct(x, d=2):
    return "—" if x is None or pd.isna(x) else f"{float(x) * 100:.{d}f}%"


def intf(x):
    return "—" if x is None or pd.isna(x) else f"{float(x):,.0f}".replace(",", ".")


def table(df, name, caption=None):
    if caption:
        st.caption(caption)
    st.dataframe(df, hide_index=True)
    st.download_button(f"⬇ Xuất CSV — {name}", df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"{name}.csv", mime="text/csv", key=f"csv_{name}")


def header():
    f = q("SELECT * FROM mart.v_data_freshness")
    if f.empty:
        st.error("Kho chưa có batch SUCCESS nào.")
        st.stop()
    r = f.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Dữ liệu đến hết ngày", r.data_through.strftime("%d/%m/%Y"))
    c2.metric("Batch nạp gần nhất", f"#{r.last_success_batch}", r.loaded_at.strftime("%d/%m %H:%M"), delta_color="off")
    c3.metric("Mart refresh", "—" if pd.isna(r.mart_refreshed_at) else r.mart_refreshed_at.strftime("%d/%m %H:%M"),
              f"batch #{r.mart_batch}" if not pd.isna(r.mart_batch) else None, delta_color="off")
    c4.metric("Đơn vị tiền", "VND", "giờ VN (UTC+7)", delta_color="off")
    if r.mart_stale:
        st.warning("⚠ Mart đang hiển thị **dữ liệu cũ**: lần refresh gần nhất chưa theo kịp batch SUCCESS mới nhất.")


# ------------------------------------------------------------------------------------------------
# 1. Tổng quan bán hàng
# ------------------------------------------------------------------------------------------------
def page_sales():
    rng = q("SELECT min(full_date) AS lo, max(full_date) AS hi FROM dw.fact_order_item JOIN dw.dim_date USING (date_key)").iloc[0]
    tree = q("SELECT * FROM mart.v_category_tree ORDER BY path_names")
    with st.sidebar:
        st.subheader("Bộ lọc")
        d = st.date_input("Khoảng ngày hoàn tất", (rng.lo, rng.hi), min_value=rng.lo, max_value=rng.hi, format="DD/MM/YYYY")
        d0, d1 = (d[0], d[1]) if isinstance(d, (list, tuple)) and len(d) == 2 else (rng.lo, rng.hi)
        roots = tree[tree.level == 1]
        root = st.selectbox("Danh mục gốc", ["(Tất cả)"] + roots.category_name.tolist())
        cat_key = None
        if root != "(Tất cả)":
            cat_key = int(roots[roots.category_name == root].category_key.iloc[0])
            kids = tree[tree.parent_category_key == cat_key]
            sub = st.selectbox("Danh mục con", ["(Tất cả)"] + kids.category_name.tolist()) if len(kids) else "(Tất cả)"
            if sub != "(Tất cả)":
                cat_key = int(kids[kids.category_name == sub].category_key.iloc[0])
        tiers = st.multiselect("Hạng seller (tại thời điểm bán)", ["Mall", "Preferred", "Normal"])
        chans = q("SELECT channel_key, channel_name FROM dw.dim_channel WHERE channel_key > 0 ORDER BY 1")
        ch = st.multiselect("Kênh", chans.channel_name.tolist())
        voucher = st.radio("Khuyến mãi", ["Tất cả", "Có voucher", "Không voucher"], horizontal=True)

    where = ["d.full_date BETWEEN %(d0)s AND %(d1)s"]
    p = {"d0": d0, "d1": d1}
    if cat_key is not None:
        where.append("f.category_key IN (SELECT descendant_key FROM dw.bridge_category_hierarchy WHERE ancestor_key = %(cat)s)")
        p["cat"] = cat_key
    if tiers:
        where.append("s.tier = ANY(%(tiers)s)")
        p["tiers"] = tiers
    if ch:
        where.append("chn.channel_name = ANY(%(ch)s)")
        p["ch"] = ch
    if voucher == "Có voucher":
        where.append("f.promotion_group_key > 0")
    elif voucher == "Không voucher":
        where.append("f.promotion_group_key = -1")
    from_ = """FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_seller s USING (seller_key)
               JOIN dw.dim_channel chn USING (channel_key) JOIN dw.dim_customer cu USING (customer_key)
               JOIN dw.dim_product pr USING (product_key)"""
    where_ = "WHERE " + " AND ".join(where)
    base = f"{from_} {where_}"

    k = num(q(f"""SELECT sum(f.net_revenue) net, count(DISTINCT f.order_id) orders, sum(f.quantity) items,
                  sum(f.net_revenue) / nullif(count(DISTINCT f.order_id), 0) aov,
                  sum(f.discount_amount) / nullif(sum(f.gross_amount), 0) voucher_rate,
                  count(DISTINCT cu.customer_id) FILTER (WHERE f.customer_key > 0) buyers,
                  count(DISTINCT f.order_id) FILTER (WHERE f.customer_key = -1)::numeric / nullif(count(DISTINCT f.order_id), 0) guest,
                  sum(f.gross_margin_est) / nullif(sum(f.net_revenue), 0) margin {base}""", p))
    r = k.iloc[0]
    if pd.isna(r.net):
        st.info("Không có dòng bán nào khớp bộ lọc.")
        return
    c = st.columns(4)
    c[0].metric("Doanh thu thuần", vnd(r.net))
    c[1].metric("Số đơn", intf(r.orders))
    c[2].metric("Số món", intf(r["items"]))
    c[3].metric("AOV", vnd(r.aov))
    c = st.columns(4)
    c[0].metric("Tỷ lệ giảm giá voucher", pct(r.voucher_rate))
    c[1].metric("Số khách mua", intf(r.buyers))
    c[2].metric("Tỷ trọng đơn khách vãng lai", pct(r.guest, 1))
    c[3].metric("Biên lãi gộp ước tính 📝", pct(r.margin, 1), "giá vốn theo giả định G1", delta_color="off")

    st.subheader("Xu hướng (drill-down Năm → Quý → Tháng → Ngày)")
    grain = st.radio("Mức thời gian", ["Năm", "Quý", "Tháng", "Ngày"], index=3, horizontal=True)
    gexpr = {"Năm": "d.year::text", "Quý": "'Q' || d.quarter || '/' || d.year",
             "Tháng": "to_char(d.full_date, 'YYYY-MM')", "Ngày": "d.full_date::text"}[grain]
    tr = num(q(f"""SELECT {gexpr} AS ky, min(d.full_date) AS sort, sum(f.net_revenue) AS doanh_thu_thuan,
                   count(DISTINCT f.order_id) AS so_don, sum(f.net_revenue) / count(DISTINCT f.order_id) AS aov
                   {base} GROUP BY 1 ORDER BY 2""", p))
    fig = px.bar(tr, x="ky", y="doanh_thu_thuan", hover_data=["so_don", "aov"], labels={"ky": grain, "doanh_thu_thuan": "Doanh thu thuần (VND)"})
    st.plotly_chart(fig)
    table(tr.drop(columns="sort"), "xu_huong_doanh_thu", "Số đơn và AOV tính lại tại từng kỳ (không cộng từ kỳ nhỏ hơn).")

    left, right = st.columns(2)
    with left:
        st.subheader("Theo danh mục (cây: cấp con của lựa chọn)")
        cond = "a.parent_category_key = %(cat)s" if cat_key is not None else "a.level = 1"
        # mỗi dòng fact được quy về đúng MỘT tổ tiên ở cấp con của lựa chọn (cây một cha) → không cộng lặp
        cat = num(q(f"""SELECT a.category_name AS danh_muc, a.is_leaf AS la, sum(f.net_revenue) AS doanh_thu_thuan,
                        count(DISTINCT f.order_id) AS so_don, sum(f.quantity) AS so_mon
                        {from_}
                        JOIN dw.bridge_category_hierarchy h ON h.descendant_key = f.category_key
                        JOIN dw.dim_category a ON a.category_key = h.ancestor_key AND {cond}
                        {where_} GROUP BY 1, 2 ORDER BY 3 DESC""", p))
        if cat.empty:  # nút lá: không còn cấp con
            st.caption("Danh mục đang chọn là nút lá.")
        else:
            st.plotly_chart(px.bar(cat, x="doanh_thu_thuan", y="danh_muc", orientation="h",
                                   labels={"doanh_thu_thuan": "VND", "danh_muc": ""}))
            table(cat, "doanh_thu_theo_danh_muc", "Tổng cây con qua closure table — không cộng lặp.")
    with right:
        st.subheader("Theo kênh")
        chd = num(q(f"""SELECT chn.channel_name AS kenh, sum(f.net_revenue) AS doanh_thu_thuan, count(DISTINCT f.order_id) AS so_don,
                        sum(f.net_revenue) / count(DISTINCT f.order_id) AS aov {base} GROUP BY 1 ORDER BY 2 DESC""", p))
        st.plotly_chart(px.pie(chd, names="kenh", values="doanh_thu_thuan", hole=0.45))
        table(chd, "doanh_thu_theo_kenh")

    left, right = st.columns(2)
    with left:
        st.subheader("Top 10 sản phẩm")
        tp = num(q(f"""SELECT pr.product_id, max(pr.product_name) AS san_pham, sum(f.quantity) AS so_mon,
                       sum(f.net_revenue) AS doanh_thu_thuan {base} GROUP BY 1 ORDER BY 4 DESC LIMIT 10""", p))
        table(tp, "top_san_pham")
    with right:
        st.subheader("Top 10 seller")
        ts = num(q(f"""SELECT s.seller_id, max(s.shop_name) AS shop, string_agg(DISTINCT s.tier, ', ') AS hang_luc_ban,
                       count(DISTINCT f.order_id) AS so_don, sum(f.net_revenue) AS doanh_thu_thuan,
                       sum(f.commission_amount) AS hoa_hong {base} GROUP BY 1 ORDER BY 5 DESC LIMIT 10""", p))
        table(ts, "top_seller")

    st.subheader("Khuyến mãi (bridge, phân bổ theo trọng số)")
    pm = num(q("""SELECT m.month_label AS thang, p.promo_code, p.promo_name, p.funded_by, x.order_count_na AS so_don, x.line_count AS so_dong,
                  x.allocated_discount AS giam_gia_phan_bo, x.allocated_net_revenue AS doanh_thu_phan_bo
                  FROM mart.mv_promotion_month x JOIN dw.dim_promotion p USING (promotion_key) JOIN dw.dim_month m USING (month_key)
                  ORDER BY x.month_key, giam_gia_phan_bo DESC"""))
    table(pm, "khuyen_mai_phan_bo", "Σ discount_amount × weighting_factor — không nhân bản khi một dòng có nhiều voucher.")
    with st.expander("Định nghĩa KPI dùng chung (mart.kpi_definitions)"):
        table(q("SELECT * FROM mart.v_kpi_definitions"), "dinh_nghia_kpi")


# ------------------------------------------------------------------------------------------------
# 2. Lịch sử thuộc tính
# ------------------------------------------------------------------------------------------------
def page_scd():
    months = q("SELECT DISTINCT m.month_key, m.month_label FROM mart.mv_sales_month_seller_tier JOIN dw.dim_month m USING (month_key) ORDER BY 1")
    with st.sidebar:
        st.subheader("Bộ lọc")
        sel = st.multiselect("Tháng", months.month_label.tolist(), default=months.month_label.tolist())
    mk = months[months.month_label.isin(sel)].month_key.tolist() or months.month_key.tolist()

    st.subheader("Doanh thu theo hạng seller: tại thời điểm bán (SCD2) và hiện tại (như SCD1)")
    t = num(q("""SELECT tier_at_sale AS hang_luc_ban, tier_current AS hang_hien_tai, sum(net_revenue) AS doanh_thu_thuan,
                 count(DISTINCT seller_id) AS so_seller FROM mart.mv_sales_month_seller_tier WHERE month_key = ANY(%(m)s)
                 GROUP BY 1, 2 ORDER BY 1, 2""", {"m": mk}))
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(px.density_heatmap(t, x="hang_hien_tai", y="hang_luc_ban", z="doanh_thu_thuan", text_auto=".3s",
                                           labels={"hang_hien_tai": "Hạng hiện tại", "hang_luc_ban": "Hạng lúc bán"}))
    with c2:
        cmp_ = t.groupby("hang_luc_ban")["doanh_thu_thuan"].sum().rename("Theo hạng lúc bán (SCD2)").to_frame().join(
            t.groupby("hang_hien_tai")["doanh_thu_thuan"].sum().rename("Theo hạng hiện tại (SCD1)"), how="outer").fillna(0)
        st.plotly_chart(px.bar(cmp_.reset_index(names="hang"), x="hang", y=list(cmp_.columns), barmode="group",
                               labels={"value": "VND", "hang": "Hạng seller", "variable": ""}))
    moved = t[t.hang_luc_ban != t.hang_hien_tai]
    if moved.empty:
        st.info("Chưa có seller nào đổi hạng trong khoảng dữ liệu (kịch bản đổi hạng của Mock chạy từ ngày mô phỏng 30/01) — "
                "hai cách nhìn hiện trùng nhau. Logic đã kiểm bằng ca có kiểm soát (dw/tests/test_scd_load.py).")
    table(t, "doanh_thu_hang_seller")

    st.subheader("Khách hàng: tỉnh lúc mua (SCD2) và tỉnh hiện tại")
    cr = num(q("""SELECT province_at_sale AS tinh_luc_mua, province_current AS tinh_hien_tai, region_at_sale AS mien,
                  sum(net_revenue) AS doanh_thu_thuan, sum(order_count_na) AS so_don, sum(buyer_count_na) AS so_khach
                  FROM mart.mv_sales_month_customer_region WHERE month_key = ANY(%(m)s) GROUP BY 1, 2, 3 ORDER BY 4 DESC""", {"m": mk}))
    st.plotly_chart(px.bar(cr, x="tinh_luc_mua", y="doanh_thu_thuan", color="tinh_hien_tai",
                           labels={"tinh_luc_mua": "Tỉnh lúc mua", "doanh_thu_thuan": "VND", "tinh_hien_tai": "Tỉnh hiện tại"}))
    table(cr, "doanh_thu_tinh_khach", "Số đơn/số khách là distinct theo tháng (cộng nhiều tháng chỉ là xấp xỉ).")

    st.subheader("Tra cứu phiên bản SCD2")
    dim = st.selectbox("Dimension", ["dim_seller", "dim_customer", "dim_product"])
    bk = {"dim_seller": "seller_id", "dim_customer": "customer_id", "dim_product": "product_id"}[dim]
    stat = q(f"""SELECT count(*) AS phien_ban, count(DISTINCT {bk}) AS khoa_nghiep_vu,
                 count(*) FILTER (WHERE NOT is_current) AS phien_ban_da_dong FROM dw.{dim} WHERE {bk} > 0""")
    st.write(stat)
    multi = q(f"""SELECT {bk} FROM dw.{dim} WHERE {bk} > 0 GROUP BY 1 HAVING count(*) > 1 ORDER BY 1 LIMIT 200""")
    default = int(multi[bk].iloc[0]) if len(multi) else int(q(f"SELECT min({bk}) v FROM dw.{dim} WHERE {bk} > 0").v.iloc[0])
    key = st.number_input(f"{bk}", value=default, step=1)
    cols = {"dim_seller": "seller_key, shop_name, tier, province_name, status",
            "dim_customer": "customer_key, full_name, province_name, region",
            "dim_product": "product_key, product_name, list_price, category_key, is_active, unit_cost_est"}[dim]
    table(q(f"SELECT {cols}, valid_from, valid_to, is_current, batch_id FROM dw.{dim} WHERE {bk} = %(k)s ORDER BY valid_from",
            {"k": int(key)}), f"phien_ban_{dim}_{int(key)}")
    if multi.empty:
        st.caption("Chưa có khóa nào có từ 2 phiên bản trở lên.")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("SCD3 — hạng seller hiện tại / liền trước")
        t3 = q("""SELECT seller_id, current_tier, previous_tier, tier_changed_on FROM dw.dim_seller_tier_t3
                  ORDER BY tier_changed_on DESC NULLS LAST, seller_id LIMIT 200""")
        st.caption(f"{(t3.previous_tier.notna()).sum()} seller đã đổi hạng (hiển thị tối đa 200 dòng).")
        table(t3, "scd3_hang_seller")
    with c2:
        st.subheader("Mini-dimension hồ sơ khách tại thời điểm mua")
        mp = num(q("""SELECT cp.membership_tier AS hang, cp.spend_band_12m AS chi_tieu_12_thang, cp.frequency_band AS tan_suat,
                      count(*) AS so_dong, sum(f.net_revenue) AS doanh_thu_thuan
                      FROM dw.fact_order_item f JOIN dw.dim_customer_profile cp USING (customer_profile_key)
                      WHERE f.customer_key > 0 GROUP BY 1, 2, 3 ORDER BY 5 DESC"""))
        st.plotly_chart(px.treemap(mp, path=["hang", "chi_tieu_12_thang", "tan_suat"], values="doanh_thu_thuan"))
        table(mp, "mini_dimension_ho_so_khach")


# ------------------------------------------------------------------------------------------------
# 3. Đối soát vận hành — drill-across
# ------------------------------------------------------------------------------------------------
def page_drill():
    st.subheader("Doanh thu × chi phí quảng cáo theo tháng–kênh (FULL OUTER JOIN)")
    a = num(q("SELECT * FROM mart.v_drill_sales_ads ORDER BY month_key, channel_key"))
    a["trang_thai"] = a.apply(lambda r: "Thiếu QC" if r.missing_ads else ("Thiếu bán hàng" if r.missing_sales else "Đủ hai phía"), axis=1)
    m = a.melt(id_vars=["month_label", "channel_name", "trang_thai"], value_vars=["net_revenue", "cost_amount"],
               var_name="chi_so", value_name="vnd").fillna(0)
    st.plotly_chart(px.bar(m, x="channel_name", y="vnd", color="chi_so", barmode="group", facet_col="month_label", log_y=True,
                           labels={"vnd": "VND (thang log)", "channel_name": "Kênh"}))
    lacks = a[a.missing_ads | a.missing_sales]
    if len(lacks):
        st.warning("Nhóm chỉ có một phía (vẫn được giữ, không bị INNER JOIN làm mất): "
                   + "; ".join(f"{r.month_label} · {r.channel_name}: {r.trang_thai}" for r in lacks.itertuples()))
    table(a.drop(columns=["month_key", "channel_key"]), "drill_doanh_thu_quang_cao",
          "Doanh thu/chi phí QC chỉ là tỷ số tham khảo, không chứng minh nhân quả.")

    st.subheader("Doanh thu × tồn kho theo sản phẩm–tháng (ghép mã nghiệp vụ product_id)")
    months = q("SELECT DISTINCT v.month_key, m.month_label FROM mart.v_drill_sales_inventory v JOIN dw.dim_month m USING (month_key) ORDER BY 1")
    ml = st.selectbox("Tháng", months.month_label.tolist(), index=len(months) - 1)
    mk = int(months[months.month_label == ml].month_key.iloc[0])
    inv = num(q("SELECT * FROM mart.v_drill_sales_inventory WHERE month_key = %(m)s", {"m": mk}))
    end = q("SELECT max(end_date_key) d FROM mart.mv_inventory_month_product WHERE month_key = %(m)s", {"m": mk}).d.iloc[0]
    month_last = q("SELECT to_char(last_date, 'YYYYMMDD')::int d FROM dw.dim_month WHERE month_key = %(m)s", {"m": mk}).d.iloc[0]
    c = st.columns(4)
    c[0].metric("Sản phẩm có tồn", intf(inv.end_on_hand.notna().sum()))
    c[1].metric("…trong đó không bán được", intf((inv.missing_sales).sum()))
    c[2].metric("Tồn cuối kỳ (món)", intf(inv.end_on_hand.sum()), f"snapshot {str(end)[6:]}/{str(end)[4:6]}", delta_color="off")
    c[3].metric("Giá trị tồn ước tính 📝", vnd(inv.end_value_est.sum()))
    if end < month_last:
        st.caption(f"Tháng chưa kết thúc: tồn cuối kỳ lấy ngày snapshot gần nhất ({end}).")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Hai mốc thời gian bán hàng**")
        st.plotly_chart(px.bar(pd.DataFrame({"nguon": ["Xuất kho (inventory, theo ngày xuất)", "Hoàn tất (order item, theo ngày hoàn tất)"],
                                             "so_mon": [inv.qty_sold_warehouse.sum(), inv.sold_qty_completed.sum()]}),
                               x="nguon", y="so_mon", labels={"nguon": "", "so_mon": "Số món"}))
        st.caption("Hai số khác nhau là đúng: lệch thời gian xuất kho → hoàn tất và đơn chưa hoàn tất.")
    with c2:
        sold = inv[inv.net_revenue.notna()]
        st.plotly_chart(px.scatter(sold, x="turnover", y="net_revenue", hover_name="product_name", size="sold_qty_completed",
                                   labels={"turnover": "Vòng quay tồn kho (bán xuất kho / tồn bình quân)", "net_revenue": "Doanh thu thuần"}))
    table(inv.sort_values("net_revenue", ascending=False, na_position="last").head(200).drop(columns=["category_key"]),
          f"drill_doanh_thu_ton_kho_{mk}", "200 sản phẩm doanh thu cao nhất; tồn là semi-additive (không cộng qua tháng).")


# ------------------------------------------------------------------------------------------------
# 4. Chất lượng dữ liệu
# ------------------------------------------------------------------------------------------------
def page_dq():
    b = q("""SELECT batch_id, batch_type, status, watermark_from, watermark_to, started_at, finished_at, message
             FROM audit.batch_log ORDER BY batch_id DESC""")
    with st.sidebar:
        st.subheader("Bộ lọc")
        lo, hi = b.started_at.min().date(), b.started_at.max().date()
        d = st.date_input("Ngày nạp", (lo, hi), min_value=lo, max_value=hi, format="DD/MM/YYYY")
        d0, d1 = (d[0], d[1]) if isinstance(d, (list, tuple)) and len(d) == 2 else (lo, hi)
    bb = b[(b.started_at.dt.date >= d0) & (b.started_at.dt.date <= d1)]
    st.subheader("Các batch ETL")
    table(bb, "batch_log", "Chỉ batch SUCCESS làm mốc watermark. Batch 1–3 trích từ bộ OLTP trước khi sinh lại (không nạp).")
    if bb.empty:
        return
    bid = st.selectbox("Chọn batch", bb.batch_id.tolist())
    t = num(q("""SELECT stage, table_name, rows_read, rows_valid, rows_warn, rows_quarantined, rows_deduplicated, rows_written, checksum
                 FROM audit.batch_table_log WHERE batch_id = %(b)s ORDER BY stage, table_name""", {"b": int(bid)}))
    stages = st.multiselect("Giai đoạn", sorted(t.stage.unique()), default=sorted(t.stage.unique()))
    srcs = st.multiselect("Nguồn (bảng)", sorted(t.table_name.unique()))
    tt = t[t.stage.isin(stages) & (t.table_name.isin(srcs) if srcs else True)]
    tr = tt[tt.stage == "TRANSFORM"]
    if len(tr):
        c = st.columns(4)
        c[0].metric("Dòng đọc (Transform)", intf(tr.rows_read.sum()))
        c[1].metric("Hợp lệ", intf(tr.rows_valid.sum()))
        c[2].metric("Cảnh báo (WARN)", intf(tr.rows_warn.sum()))
        c[3].metric("Cách ly (ERROR)", intf(tr.rows_quarantined.sum()))
        st.plotly_chart(px.bar(tr, x="table_name", y=["rows_valid", "rows_warn", "rows_quarantined", "rows_deduplicated"],
                               log_y=True, labels={"value": "Số dòng (log)", "table_name": "", "variable": ""}))
    table(tt, f"batch_{bid}_bang")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Lý do cách ly / cảnh báo")
        qs = q("SELECT source_table, rule_code, severity, reason, rows, sample_pk FROM mart.v_quarantine_summary WHERE batch_id = %(b)s ORDER BY rows DESC",
               {"b": int(bid)})
        if srcs:
            qs = qs[qs.source_table.str.contains("|".join(srcs))]
        table(qs, f"batch_{bid}_cach_ly")
    with c2:
        st.subheader("Đối soát")
        rc = q("SELECT check_code, description, source_value, target_value, passed FROM audit.reconciliation WHERE batch_id = %(b)s ORDER BY check_code",
               {"b": int(bid)})
        if len(rc):
            st.metric("Kiểm tra đạt", f"{int(rc.passed.sum())}/{len(rc)}")
        table(rc, f"batch_{bid}_doi_soat")
    st.subheader("Kết quả từng quy tắc DQ (có vi phạm)")
    table(q("""SELECT rule_code, table_name, severity, rows_checked, rows_failed FROM audit.dq_result
               WHERE batch_id = %(b)s AND rows_failed > 0 ORDER BY rows_failed DESC""", {"b": int(bid)}), f"batch_{bid}_dq")
    st.subheader("Khóa đặc biệt trên fact (0 = chưa xác định, −1 = không áp dụng)")
    table(q("SELECT * FROM mart.v_unknown_keys ORDER BY fact, key_name"), "khoa_dac_biet")


# ------------------------------------------------------------------------------------------------
# 5. Hiệu năng
# ------------------------------------------------------------------------------------------------
def page_perf():
    has = q("""SELECT count(*) n FROM information_schema.tables WHERE table_schema = 'bench' AND table_name = 'bm_result'""").n.iloc[0]
    st.subheader("Thí nghiệm BM01–BM03")
    has = has and q("SELECT count(*) n FROM bench.bm_result").n.iloc[0]
    if has:
        runs = q("SELECT run_id, started_at, env, params FROM bench.bm_run WHERE finished_at IS NOT NULL ORDER BY started_at DESC")
        run_id = st.selectbox("Lần đo", runs.run_id.tolist())
        meta = runs[runs.run_id == run_id].iloc[0]
        e, p = meta.env, meta.params
        st.caption(f"PostgreSQL {e.get('server_version')} · {e.get('cpu')} CPU · RAM {int(e.get('mem_kb', 0)) // 1024} MB · "
                   f"shared_buffers {e.get('shared_buffers')} · work_mem {e.get('work_mem')} · JIT {e.get('jit')} · "
                   f"parallel/gather {e.get('max_parallel_workers_per_gather')} · {p.get('warmup')} warm-up + {p.get('rounds')} lượt đo, "
                   f"xáo thứ tự (seed {p.get('seed')}) · mock tạm dừng khi đo · dữ liệu nhân bản (không phục vụ báo cáo)")
        r = num(q("""SELECT experiment, query_id, query_desc, variant, is_baseline, median_ms, p95_ms, speedup, hash_match,
                     relations_scanned, scan_rows, shared_hit, shared_read, plan_root, indexes_used, object_size_mb, note
                     FROM bench.bm_result WHERE run_id = %(r)s ORDER BY experiment, query_id, is_baseline DESC, median_ms""", {"r": run_id}))
        exp = st.multiselect("Thí nghiệm", sorted(r.experiment.unique()), default=sorted(r.experiment.unique()))
        rr = r[r.experiment.isin(exp)]
        if not rr.hash_match.all():
            st.error("Có biến thể cho kết quả KHÁC baseline — không so sánh được thời gian.")
        else:
            st.success(f"{len(rr)} biến thể: kết quả trùng hash với baseline (so sánh hợp lệ).")
        st.plotly_chart(px.bar(rr, x="query_id", y="median_ms", color="variant", barmode="group", log_y=True,
                               hover_data=["query_desc", "p95_ms", "speedup"],
                               labels={"median_ms": "median (ms, thang log)", "query_id": "Truy vấn", "variant": "Biến thể"}))
        st.plotly_chart(px.bar(rr[~rr.is_baseline], x="query_id", y="speedup", color="variant", barmode="group",
                               labels={"speedup": "speedup = median baseline / median biến thể", "query_id": "Truy vấn"}))
        slower = rr[(~rr.is_baseline) & (rr.speedup < 1)]
        if len(slower):
            st.warning("Biến thể KHÔNG nhanh hơn baseline (ghi trung thực): "
                       + "; ".join(f"{x.query_id} · {x.variant}: ×{x.speedup}" for x in slower.itertuples()))
        table(rr, f"bench_ket_qua_{run_id}")
        st.subheader("Chi phí: kích thước & thời gian dựng đối tượng thí nghiệm")
        table(num(q("SELECT object_name, kind, row_count, size_mb, build_seconds, note FROM bench.bm_object ORDER BY kind, object_name")),
              "bench_doi_tuong")
    else:
        st.info("Chưa có kết quả benchmark (bench.bm_result) — thí nghiệm BM01 (MV), BM02 (partition), BM03 (index) "
                "thực hiện ở bước 10 của PLAN; màn hình này tự hiển thị median, p95, speedup khi có dữ liệu.")
    st.subheader("Thời gian refresh materialized view (B6)")
    rs = num(q("SELECT mv_name, batch_id, refreshed_at, row_count, seconds FROM mart.refresh_status ORDER BY seconds DESC"))
    st.plotly_chart(px.bar(rs, x="mv_name", y="seconds", labels={"mv_name": "", "seconds": "giây"}))
    table(rs, "refresh_mv")
    st.subheader("Dung lượng và partition")
    sz = num(q("""SELECT n.nspname AS schema, c.relname AS bang, c.relkind AS loai, c.reltuples::bigint AS so_dong_uoc_tinh,
                  pg_total_relation_size(c.oid) / 1024 / 1024.0 AS mb, c.relispartition AS la_partition
                  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname IN ('dw', 'mart') AND c.relkind IN ('r', 'm', 'p') ORDER BY mb DESC"""))
    sz = sz[(sz.so_dong_uoc_tinh > 0) | (sz.loai != "r")]
    table(sz, "dung_luong")


# ------------------------------------------------------------------------------------------------
st.sidebar.title("📊 DW TMĐT")
page = st.sidebar.radio("Màn hình", PAGES, key="page")
st.title(page)
try:
    header()
    {PAGES[0]: page_sales, PAGES[1]: page_scd, PAGES[2]: page_drill, PAGES[3]: page_dq, PAGES[4]: page_perf}[page]()
except psycopg.OperationalError as exc:
    st.error(f"Không kết nối được kho dữ liệu ({DSN.split('@')[-1]}). Docker/WSL đã chạy chưa?\n\n{exc}")
st.sidebar.caption(f"Kết nối: {DSN.split('@')[-1]} · role {DSN.split('//')[1].split(':')[0]} (chỉ đọc) · {dt.date.today():%d/%m/%Y}")
