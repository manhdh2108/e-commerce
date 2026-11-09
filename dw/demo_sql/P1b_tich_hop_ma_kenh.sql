-- TAB: [P1b] Tich_Hop   (Bước 2 — Integrated / quy tắc IR-03)
-- Marketing gọi kênh là WEB / APP / LIVESTREAM, bảng kênh của hệ đơn hàng gọi là Web / App / Livestream
-- (tài liệu schema còn ghi MOBILE_APP / LIVE). Kho chuẩn hóa về MỘT khóa kênh dùng chung cho cả bán hàng lẫn quảng cáo.

-- Mã nguồn marketing → tên chuẩn trong kho
SELECT marketing_code AS ma_goc_marketing, channel_name AS ma_chuan_dw, channel_key
FROM dw.dim_channel WHERE channel_key > 0 ORDER BY channel_key;

-- Hệ quả: hai fact khác hệ nguồn nối được với nhau qua cùng channel_key
SELECT c.channel_name,
       (SELECT round(sum(net_revenue)) FROM dw.fact_order_item f WHERE f.channel_key = c.channel_key) AS doanh_thu_ban_hang,
       (SELECT sum(cost_amount) FROM dw.fact_ad_spend a WHERE a.channel_key = c.channel_key) AS chi_phi_quang_cao
FROM dw.dim_channel c WHERE c.channel_key > 0 ORDER BY c.channel_key;
