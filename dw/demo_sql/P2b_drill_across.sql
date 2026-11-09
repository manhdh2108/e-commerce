-- TAB: [P2b] Drill_Across   (Bước 3 & 6: Atomic vs Summary — truy vấn ghép HAI fact, chênh lệch rõ nhất)
-- Chạy mỗi cặp hai lần, lấy lần hai, chỉ vào dòng "Execution Time" cuối kế hoạch.
-- Kỳ vọng: ATOMIC ~418–588 ms, SUMMARY ~21–24 ms (nhanh khoảng 18–24 lần).
-- Xem dạng sơ đồ: SQL Editor → Execute → Explain Execution Plan (kiểm tra thử trước buổi demo).

-- ATOMIC: gom từ cả hai fact rồi FULL JOIN
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
WITH s AS (SELECT d.month_key, p.product_id, sum(f.quantity) AS sold_qty, sum(f.net_revenue) AS net
           FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_product p USING (product_key) GROUP BY 1,2),
     i AS (SELECT d.month_key, p.product_id, sum(f.qty_sold) AS qty_sold_wh
           FROM dw.fact_inventory_snapshot f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_product p USING (product_key) GROUP BY 1,2)
SELECT count(*), sum(s.net), sum(i.qty_sold_wh) FROM s FULL JOIN i USING (month_key, product_id);

-- SUMMARY: đọc view dựng trên hai MV
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
SELECT count(*), sum(net_revenue), sum(qty_sold_warehouse) FROM mart.v_drill_sales_inventory;

-- Hai cách cho CÙNG một kết quả (không có EXPLAIN): 3532 | 2590938257.00 | 4273
WITH s AS (SELECT d.month_key, p.product_id, sum(f.quantity) AS sold_qty, sum(f.net_revenue) AS net
           FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_product p USING (product_key) GROUP BY 1,2),
     i AS (SELECT d.month_key, p.product_id, sum(f.qty_sold) AS qty_sold_wh
           FROM dw.fact_inventory_snapshot f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_product p USING (product_key) GROUP BY 1,2)
SELECT count(*), sum(s.net), sum(i.qty_sold_wh) FROM s FULL JOIN i USING (month_key, product_id);

SELECT count(*), sum(net_revenue), sum(qty_sold_warehouse) FROM mart.v_drill_sales_inventory;
