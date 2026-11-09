-- TAB: [P2c] Index_Test   (Bước 6: tác dụng của index trên fact thật)
-- Kỳ vọng: CÓ index ~1,3–4 ms (Bitmap Index Scan); KHÔNG index ~49–61 ms (Parallel Seq Scan) → nhanh khoảng 12–45 lần.
-- !!! Sau khi xong PHẢI chạy hai lệnh RESET ở cuối (hoặc đóng kết nối) !!!

-- CÓ index
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
SELECT d.full_date, sum(f.quantity_on_hand) FROM dw.fact_inventory_snapshot f JOIN dw.dim_date d USING (date_key)
WHERE f.product_key = 3631 GROUP BY 1 ORDER BY 1;

-- Tắt tạm index trong phiên này (không ảnh hưởng ai khác)
SET enable_indexscan = off;
SET enable_bitmapscan = off;

-- KHÔNG dùng index
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
SELECT d.full_date, sum(f.quantity_on_hand) FROM dw.fact_inventory_snapshot f JOIN dw.dim_date d USING (date_key)
WHERE f.product_key = 3631 GROUP BY 1 ORDER BY 1;

RESET enable_indexscan;
RESET enable_bitmapscan;
