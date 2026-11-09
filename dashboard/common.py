"""Hàm dùng chung của dashboard: kết nối chỉ đọc, truy vấn có cache, định dạng số, bảng kèm nút xuất CSV."""
import os

import pandas as pd
import psycopg
import streamlit as st

DSN = os.getenv("DW_DASH_URL", "postgresql://dw_analyst:dw_analyst_local@127.0.0.1:55432/dwh")


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


def short(v):
    """Tiền dạng gọn: 2,59 tỷ / 735,7 tr / 12 k."""
    v = float(v)
    a = abs(v)
    s = f"{v / 1e9:.2f} tỷ" if a >= 1e9 else f"{v / 1e6:.1f} tr" if a >= 1e6 else f"{v / 1e3:.0f} k" if a >= 1e3 else f"{v:.0f}"
    return s.replace(".", ",")
