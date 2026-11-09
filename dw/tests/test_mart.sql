-- Kiểm thử mart (PLAN 8 — T5 phần dữ liệu): mỗi MV/view = truy vấn độc lập trên fact atomic.
--   docker exec -i scripts-mock-postgres-1 psql -U dw_analyst -d dwh -f - < dw/tests/test_mart.sql
-- Mỗi dòng: kiểm tra | giá trị mart | giá trị độc lập | đạt
\pset footer off
WITH t(check_name, mart_value, independent_value) AS (
  SELECT 'MV ngày×SP: Σ net', (SELECT sum(net_revenue) FROM mart.mv_sales_day_product), (SELECT sum(net_revenue) FROM dw.fact_order_item)
  UNION ALL SELECT 'MV ngày×SP: Σ số món', (SELECT sum(quantity) FROM mart.mv_sales_day_product), (SELECT sum(quantity) FROM dw.fact_order_item)
  UNION ALL SELECT 'MV ngày×SP: Σ giá vốn ước tính', (SELECT sum(cost_amount_est) FROM mart.mv_sales_day_product), (SELECT sum(cost_amount_est) FROM dw.fact_order_item)
  UNION ALL SELECT 'MV ngày×SP: Σ dòng', (SELECT sum(line_count) FROM mart.mv_sales_day_product), (SELECT count(*) FROM dw.fact_order_item)
  UNION ALL SELECT 'MV tháng×danh mục: Σ net', (SELECT sum(net_revenue) FROM mart.mv_sales_month_category), (SELECT sum(net_revenue) FROM dw.fact_order_item)
  UNION ALL SELECT 'MV tháng×kênh: số đơn từng (tháng,kênh) sai lệch',
        (SELECT count(*) FROM mart.mv_sales_month_channel m JOIN (
            SELECT d.month_key, f.channel_key, count(DISTINCT f.order_id) n FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key) GROUP BY 1, 2) x
         USING (month_key, channel_key) WHERE m.order_count_na <> x.n), 0
  UNION ALL SELECT 'MV seller tier: Σ net', (SELECT sum(net_revenue) FROM mart.mv_sales_month_seller_tier), (SELECT sum(net_revenue) FROM dw.fact_order_item)
  UNION ALL SELECT 'MV tỉnh khách: Σ net', (SELECT sum(net_revenue) FROM mart.mv_sales_month_customer_region), (SELECT sum(net_revenue) FROM dw.fact_order_item)
  -- Độc lập: lấy dòng snapshot CUỐI của từng (tháng, sản phẩm NGHIỆP VỤ, kho). Phải gom theo product_id chứ không theo
  -- product_key: sản phẩm đổi phiên bản SCD2 giữa tháng có nhiều product_key, mỗi phiên bản có "ngày cuối" riêng
  -- (lỗi của bản kiểm thử cũ, lộ ra khi có dữ liệu SCD thật từ 25/01 — xem docs/implementation/11_buoc-8_kiem-thu.md).
  UNION ALL SELECT 'MV tồn kho: Σ tồn cuối tháng (ngày snapshot cuối)', (SELECT sum(end_on_hand) FROM mart.mv_inventory_month_product),
        (SELECT sum(x.quantity_on_hand) FROM (SELECT DISTINCT ON (d.month_key, p.product_id, f.warehouse_key) f.quantity_on_hand
            FROM dw.fact_inventory_snapshot f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_product p USING (product_key)
            ORDER BY d.month_key, p.product_id, f.warehouse_key, f.date_key DESC) x)
  UNION ALL SELECT 'MV tồn kho: Σ bán xuất kho', (SELECT sum(qty_sold) FROM mart.mv_inventory_month_product), (SELECT sum(qty_sold) FROM dw.fact_inventory_snapshot)
  UNION ALL SELECT 'MV QC: Σ chi phí', (SELECT sum(cost_amount) FROM mart.mv_ads_month_channel), (SELECT sum(cost_amount) FROM dw.fact_ad_spend)
  UNION ALL SELECT 'MV voucher: Σ giảm giá phân bổ', (SELECT sum(allocated_discount) FROM mart.mv_promotion_month),
        (SELECT sum(discount_amount) FROM dw.fact_order_item WHERE promotion_group_key > 0)
  UNION ALL SELECT 'Drill-across QC: Σ doanh thu (giữ cả nhóm chỉ có bán)', (SELECT sum(net_revenue) FROM mart.v_drill_sales_ads), (SELECT sum(net_revenue) FROM dw.fact_order_item)
  UNION ALL SELECT 'Drill-across QC: Σ chi phí (giữ cả nhóm chỉ có QC)', (SELECT sum(cost_amount) FROM mart.v_drill_sales_ads), (SELECT sum(cost_amount) FROM dw.fact_ad_spend)
  UNION ALL SELECT 'Drill-across tồn kho: Σ doanh thu', (SELECT sum(net_revenue) FROM mart.v_drill_sales_inventory), (SELECT sum(net_revenue) FROM dw.fact_order_item)
  UNION ALL SELECT 'Drill-across tồn kho: Σ tồn cuối', (SELECT sum(end_on_hand) FROM mart.v_drill_sales_inventory), (SELECT sum(end_on_hand) FROM mart.mv_inventory_month_product)
  UNION ALL SELECT 'KPI tháng: AOV = Σnet/số đơn tính trực tiếp',
        (SELECT sum(aov) FROM mart.v_kpi_period WHERE period_level = 'Tháng'),
        (SELECT sum(a) FROM (SELECT round(sum(net_revenue) / count(DISTINCT order_id), 2) a FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key) GROUP BY d.month_key) x)
  UNION ALL SELECT 'KPI năm: số đơn = distinct cả năm (không cộng tháng)',
        (SELECT sum(orders) FROM mart.v_kpi_period WHERE period_level = 'Năm'),
        (SELECT count(DISTINCT (d.year, f.order_id)) FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key))
  UNION ALL SELECT 'KPI tháng: số khách mua = distinct customer_id', (SELECT sum(buyers) FROM mart.v_kpi_period WHERE period_level = 'Tháng'),
        (SELECT sum(n) FROM (SELECT count(DISTINCT c.customer_id) n FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key)
                             JOIN dw.dim_customer c USING (customer_key) WHERE f.customer_key > 0 GROUP BY d.month_key) x)
  -- Thông tin, không phải lỗi: payment đến muộn (đơn hoàn tất cuối ngày, giao dịch ghi sang ngày sau) → khóa 0 tạm thời,
  -- được cập nhật ở batch sau (PLAN 5.5 bước 5). Dòng này luôn ra INFO.
  UNION ALL SELECT 'Khóa 0 trên fact (thông tin)', (SELECT sum(unknown_0) FROM mart.v_unknown_keys), (SELECT sum(unknown_0) FROM mart.v_unknown_keys)
  UNION ALL SELECT 'Mart không cũ (batch refresh = batch SUCCESS mới nhất)', (SELECT CASE WHEN mart_stale THEN 1 ELSE 0 END FROM mart.v_data_freshness), 0
)
SELECT check_name AS kiem_tra, mart_value AS mart, independent_value AS doc_lap,
       CASE WHEN check_name LIKE '%(thông tin)%' THEN 'INFO' WHEN mart_value = independent_value THEN 'PASS' ELSE 'FAIL' END AS ket_qua
FROM t;
