-- TAB: [P3] OLAP   (đề cương mục 4.2: roll-up, drill-down, slice, dice trên Fact_Order_Item)
-- Mọi câu đều đọc fact atomic (3.419 dòng) nối dimension; kết quả tính bằng SQL thuần, chạy < 100 ms.
-- Kỳ vọng tổng doanh thu thuần ở mọi câu "không lọc": 2.590.938.257 đ.
-- Chạy từng câu: đặt con trỏ vào câu, Ctrl+Enter.

-- ======================================================================================================
-- 1. ROLL-UP (cuộn lên): TUẦN → THÁNG → tổng bằng một câu ROLLUP (mức NGÀY xem ở câu 2c)
--    Kỳ vọng: 5 dòng tuần (tuần 1: 152.311.009; tuần 2: 646.794.568; tuần 3: 661.569.549; tuần 4: 674.212.704;
--    tuần 5: 456.050.427), dòng tháng và dòng tổng cùng 2.590.938.257. AOV tính lại ở mỗi cấp, KHÔNG cộng AOV của tuần.
-- ======================================================================================================
SELECT CASE WHEN grouping(d.month_key, d.iso_week) = 3 THEN 'TỔNG CỘNG'
            WHEN grouping(d.iso_week) = 1 THEN 'Tháng ' || d.month_key
            ELSE '   Tuần ' || d.iso_week END AS cap_tong_hop,
       count(DISTINCT f.order_id)                              AS so_don,
       sum(f.quantity)                                         AS so_mon,
       sum(f.net_revenue)                                      AS doanh_thu_thuan,
       round(sum(f.net_revenue) / count(DISTINCT f.order_id))  AS aov
FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key)
GROUP BY ROLLUP (d.month_key, d.iso_week)
ORDER BY grouping(d.month_key, d.iso_week), d.month_key, d.iso_week;

-- Roll-up theo DANH MỤC: từ lá lên danh mục gốc (cột root_category_key của dim_category) rồi tổng
-- Kỳ vọng: Điện Thoại - Máy Tính Bảng 1.437.851.000; Làm Đẹp - Sức Khỏe 375.178.713; Thời trang nữ 365.579.269;
-- Bách Hóa Online 325.230.921; Chăm sóc nhà cửa 87.098.354; tổng 2.590.938.257.
SELECT coalesce(r.category_name, 'TỔNG CỘNG') AS danh_muc_goc, count(*) AS so_dong, sum(f.net_revenue) AS doanh_thu_thuan
FROM dw.fact_order_item f
JOIN dw.dim_category c USING (category_key)
JOIN dw.dim_category r ON r.category_key = c.root_category_key
GROUP BY ROLLUP (r.category_name)
ORDER BY grouping(r.category_name), doanh_thu_thuan DESC;

-- ======================================================================================================
-- 2. DRILL-DOWN (khoan xuống): danh mục gốc → cấp 2 → cấp 3 (đi qua bảng bridge/closure để không cộng lặp), rồi thời gian: tuần → ngày
--    Fact chỉ gắn vào danh mục LÁ, nên lọc đúng danh mục cha bằng category_key = cha cho kết quả 0; phải nối bridge.
-- ======================================================================================================
-- 2a. Từ gốc "Làm Đẹp - Sức Khỏe" (1520) xuống các con cấp 2.
--     Kỳ vọng: Danh mục 1582 = 208.517.163; Danh mục 1584 = 106.464.750; Danh mục 1592 = 60.196.800;
--     cột tong_cac_con = 375.178.713 = doanh thu của gốc ở câu roll-up (cộng các con khớp, không cộng lặp).
--     (28 nút trung gian chưa có tên nên tạm gọi "Danh mục <mã>"; đây là hạn chế đã ghi trong báo cáo.)
SELECT a.category_name AS danh_muc_cap_2, a.is_leaf, sum(f.net_revenue) AS doanh_thu_thuan, sum(f.quantity) AS so_mon,
       sum(sum(f.net_revenue)) OVER () AS tong_cac_con
FROM dw.dim_category a
JOIN dw.bridge_category_hierarchy b ON b.ancestor_key = a.category_key
JOIN dw.fact_order_item f ON f.category_key = b.descendant_key
WHERE a.parent_category_key = 1520
GROUP BY a.category_name, a.is_leaf
ORDER BY doanh_thu_thuan DESC;

-- 2b. Khoan tiếp xuống cấp 3: các con của "Danh mục 1582" (1582)
--     Kỳ vọng: 1 dòng, "Sữa rửa mặt" (danh mục lá) = 208.517.163, 640 món — bằng đúng doanh thu của nút cha.
SELECT a.category_name AS danh_muc_cap_3, a.is_leaf, sum(f.net_revenue) AS doanh_thu_thuan, sum(f.quantity) AS so_mon
FROM dw.dim_category a
JOIN dw.bridge_category_hierarchy b ON b.ancestor_key = a.category_key
JOIN dw.fact_order_item f ON f.category_key = b.descendant_key
WHERE a.parent_category_key = 1582
GROUP BY a.category_name, a.is_leaf
ORDER BY doanh_thu_thuan DESC;

-- 2c. Drill-down THỜI GIAN: tuần 4 (19/01–25/01) xuống từng ngày
--     Kỳ vọng: 7 ngày, tổng 674.212.704.
SELECT d.full_date, d.day_name, count(DISTINCT f.order_id) AS so_don, sum(f.net_revenue) AS doanh_thu_thuan
FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key)
WHERE d.iso_week = 4
GROUP BY d.full_date, d.day_name
ORDER BY d.full_date;

-- ======================================================================================================
-- 3. SLICE (cắt lát): cố định MỘT chiều (kênh = App), giữ nguyên các chiều còn lại
--    Kỳ vọng: tổng 519.946.374 (kênh App); các tuần cộng lại bằng tổng này.
-- ======================================================================================================
SELECT d.iso_week AS tuan, count(DISTINCT f.order_id) AS so_don, sum(f.net_revenue) AS doanh_thu_thuan
FROM dw.fact_order_item f
JOIN dw.dim_date d USING (date_key)
JOIN dw.dim_channel c USING (channel_key)
WHERE c.channel_name = 'App'
GROUP BY d.iso_week ORDER BY d.iso_week;

-- ======================================================================================================
-- 4. DICE (cắt khối): lọc ĐỒNG THỜI nhiều chiều — kênh App, hạng seller LÚC BÁN là Mall hoặc Preferred,
--    ngày 12/01–25/01, rồi nhìn theo danh mục gốc × hạng seller (hạng lấy từ dim_seller SCD2: phiên bản có hiệu lực tại ngày bán)
--    Kỳ vọng: 7 dòng; dòng đầu "Làm Đẹp - Sức Khỏe | Preferred | 39 dòng | 13.253.400"; chỉ còn hạng Mall và Preferred.
-- ======================================================================================================
SELECT r.category_name AS danh_muc_goc, s.tier AS hang_seller_luc_ban, count(*) AS so_dong, sum(f.net_revenue) AS doanh_thu_thuan
FROM dw.fact_order_item f
JOIN dw.dim_date d USING (date_key)
JOIN dw.dim_channel c USING (channel_key)
JOIN dw.dim_seller s USING (seller_key)
JOIN dw.dim_category k USING (category_key)
JOIN dw.dim_category r ON r.category_key = k.root_category_key
WHERE c.channel_name = 'App'
  AND s.tier IN ('Mall', 'Preferred')
  AND d.full_date BETWEEN DATE '2026-01-12' AND DATE '2026-01-25'
GROUP BY r.category_name, s.tier
ORDER BY doanh_thu_thuan DESC;
