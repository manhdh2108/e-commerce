-- TAB: [P2e] Summary_vs_Atomic_BoSung   (tuỳ chọn: thêm hai cặp so sánh Summary với Atomic cùng cách làm như [P2b])
-- Chạy mỗi cặp hai lần, lấy lần hai, chỉ vào dòng "Execution Time". Mỗi cặp kèm câu chứng minh hai cách ra CÙNG kết quả.

-- ======================================================================================================
-- A. Tồn kho theo tháng × kho: ATOMIC (fact 565.982 dòng) so với SUMMARY (MV 18.260 dòng)
--    Kỳ vọng: khoảng 127–197 ms so với 8–14 ms (nhanh khoảng 15 lần)
-- ======================================================================================================
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
SELECT d.month_key, f.warehouse_key, sum(f.qty_sold) AS qty_sold, sum(f.qty_imported) AS qty_imported
FROM dw.fact_inventory_snapshot f JOIN dw.dim_date d USING (date_key) GROUP BY 1,2 ORDER BY 1,2;

EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
SELECT month_key, warehouse_key, sum(qty_sold) AS qty_sold, sum(qty_imported) AS qty_imported
FROM mart.mv_inventory_month_product GROUP BY 1,2 ORDER BY 1,2;

-- Hai cách cho cùng kết quả: số dòng khác nhau phải là 0
SELECT count(*) AS dong_khac_nhau FROM (
  (SELECT d.month_key, f.warehouse_key, sum(f.qty_sold)::bigint, sum(f.qty_imported)::bigint
   FROM dw.fact_inventory_snapshot f JOIN dw.dim_date d USING (date_key) GROUP BY 1,2)
  EXCEPT
  (SELECT month_key, warehouse_key, sum(qty_sold)::bigint, sum(qty_imported)::bigint
   FROM mart.mv_inventory_month_product GROUP BY 1,2)) x;

-- ======================================================================================================
-- B. SCD: doanh thu theo hạng seller lúc bán và hạng hiện tại — ATOMIC (fact nối dim_seller hai lần) so với SUMMARY (MV)
--    Kỳ vọng: khoảng 8 ms so với 1,1 ms. Nói thẳng: fact bán hàng thật mới có 3.419 dòng nên chênh lệch tuyệt đối chỉ
--    vài mili giây, nhưng MV đã chứa sẵn cả hai cách nhìn SCD (hạng lúc bán và hạng hiện tại).
-- ======================================================================================================
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
SELECT d.month_key, s.tier AS hang_luc_ban, cur.tier AS hang_hien_tai, sum(f.net_revenue)
FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key)
JOIN dw.dim_seller s ON s.seller_key = f.seller_key
LEFT JOIN dw.dim_seller cur ON cur.seller_id = s.seller_id AND cur.is_current
GROUP BY 1,2,3 ORDER BY 1,2,3;

EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
SELECT month_key, tier_at_sale, tier_current, sum(net_revenue)
FROM mart.mv_sales_month_seller_tier GROUP BY 1,2,3 ORDER BY 1,2,3;

-- Hai cách cho cùng kết quả: số dòng khác nhau phải là 0
SELECT count(*) AS dong_khac_nhau FROM (
  (SELECT d.month_key, s.tier, cur.tier, sum(f.net_revenue)
   FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key)
   JOIN dw.dim_seller s ON s.seller_key = f.seller_key
   LEFT JOIN dw.dim_seller cur ON cur.seller_id = s.seller_id AND cur.is_current GROUP BY 1,2,3)
  EXCEPT
  (SELECT month_key, tier_at_sale, tier_current, sum(net_revenue)
   FROM mart.mv_sales_month_seller_tier GROUP BY 1,2,3)) x;
