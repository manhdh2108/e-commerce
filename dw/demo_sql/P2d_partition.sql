-- TAB: [P2d] Partition_Test   (Bước 6: partition theo tháng trên fact thật — bằng chứng "partition pruning")
-- dw.fact_order_item và dw.fact_inventory_snapshot đều PARTITION BY RANGE (date_key), mỗi tháng một partition
-- (36 partition 2025-01..2027-12 + 1 partition default).
-- Dữ liệu thật hiện chỉ nằm ở tháng 01/2026 nên khác biệt về thời gian còn nhỏ; điều cần chỉ là KẾ HOẠCH:
-- có điều kiện theo date_key thì chỉ quét đúng 1 partition, không có thì phải duyệt cả chuỗi.
-- Xem dạng sơ đồ: SQL Editor → Execute → Explain Execution Plan (kiểm tra thử trước buổi demo).

-- 1. Dữ liệu rơi vào partition nào? Kỳ vọng: chỉ fact_inventory_snapshot_202601 có dòng (565.982), các tháng khác trống
SELECT tableoid::regclass AS partition, count(*) AS so_dong, min(date_key) AS tu_ngay, max(date_key) AS den_ngay
FROM dw.fact_inventory_snapshot GROUP BY 1 ORDER BY 1;

-- 2. Số partition của hai fact lớn. Kỳ vọng: 37 mỗi bảng (36 tháng + default)
SELECT parent.relname AS bang_fact, count(*) AS so_partition
FROM pg_inherits i JOIN pg_class parent ON parent.oid = i.inhparent JOIN pg_class child ON child.oid = i.inhrelid
WHERE parent.relname IN ('fact_order_item', 'fact_inventory_snapshot') AND parent.relnamespace = 'dw'::regnamespace
GROUP BY 1 ORDER BY 1;

-- 3. CÓ điều kiện theo khóa partition: chỉ quét 1 partition
--    Kỳ vọng: trong kế hoạch chỉ có fact_inventory_snapshot_202601 (các partition khác bị loại), khoảng 9–10 ms
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
SELECT warehouse_key, sum(quantity_on_hand) FROM dw.fact_inventory_snapshot WHERE date_key = 20260115 GROUP BY 1;

-- 4. KHÔNG lọc ngày: không cắt tỉa được, phải duyệt mọi partition
--    Kỳ vọng: kế hoạch liệt kê cả chuỗi _202501 … _202712 (nhiều dòng "actual rows=0" là partition trống), khoảng 85–106 ms
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
SELECT warehouse_key, sum(quantity_on_hand) FROM dw.fact_inventory_snapshot GROUP BY 1;

-- ======================================================================================================
-- TUỲ CHỌN (chỉ khi được hỏi về quy mô lớn): bảng nhân bản của thí nghiệm BM02 trong schema bench
-- (6,6 triệu dòng tồn kho, 2 triệu dòng bán hàng; cùng dữ liệu, cùng PK). Chỉ chạy được khi chưa dọn bench.
-- Kết quả đo trong báo cáo bước 10: Q2c ×2,96 (partition nhanh hơn), Q2d ×0,84 (partition CHẬM hơn khi quét cả năm).
-- ======================================================================================================
-- Q2c: doanh thu 1 tháng, KHÔNG có index — bảng thường phải seq scan cả năm, partition chỉ đọc 1 tháng (~315 ms vs ~107 ms)
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
SELECT category_key, sum(net_revenue), sum(quantity) FROM bench.foi_noidx WHERE date_key BETWEEN 20260601 AND 20260630 GROUP BY 1 ORDER BY 1;

EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
SELECT category_key, sum(net_revenue), sum(quantity) FROM bench.foi_part WHERE date_key BETWEEN 20260601 AND 20260630 GROUP BY 1 ORDER BY 1;

-- Q2d: quét cả năm, không lọc ngày — partition KHÔNG có lợi, thậm chí chậm hơn (~700 ms vs ~836 ms) do Append nhiều partition
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
SELECT sum(quantity_on_hand), sum(qty_sold), count(*) FROM bench.inv_plain;

EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
SELECT sum(quantity_on_hand), sum(qty_sold), count(*) FROM bench.inv_part;
