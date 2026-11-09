-- Màn hình tổng duyệt tính nhất quán (dùng cho demo và kiểm tra nhanh): MỘT view, mỗi dòng là một kiểm tra,
-- cột ket_qua = PASS khi gia_tri = ky_vong. Mọi kiểm tra tính độc lập với mã ETL (không dùng lại SQL của load.py).
--   SELECT * FROM mart.v_consistency_check;
--   SELECT ket_qua, count(*) FROM mart.v_consistency_check GROUP BY 1;
-- Bộ kiểm thử đầy đủ T1–T7 vẫn là dw/tests/run_tests.py; view này là bản rút gọn chạy trong ~1 giây.

CREATE OR REPLACE VIEW mart.v_consistency_check AS
WITH chk (thu_tu, nhom, kiem_tra, gia_tri, ky_vong) AS (
  -- A. Khóa ngoại: không có dòng fact trỏ tới dimension không tồn tại
  -- Mỗi dimension một anti-join riêng rồi cộng lại. KHÔNG gộp thành "NOT EXISTS … OR NOT EXISTS …": planner sẽ chạy
  -- từng dòng với subplan (đo được 37,8 giây cho 3.419 dòng, so với vài chục mili giây khi tách riêng).
  SELECT 10, 'A. Khóa ngoại', 'fact_order_item: số lượt khóa ngoại mồ côi (9 dimension, cộng lại)',
         (SELECT count(*) FROM dw.fact_order_item f LEFT JOIN dw.dim_product x ON x.product_key = f.product_key WHERE x.product_key IS NULL)
       + (SELECT count(*) FROM dw.fact_order_item f LEFT JOIN dw.dim_customer x ON x.customer_key = f.customer_key WHERE x.customer_key IS NULL)
       + (SELECT count(*) FROM dw.fact_order_item f LEFT JOIN dw.dim_seller x ON x.seller_key = f.seller_key WHERE x.seller_key IS NULL)
       + (SELECT count(*) FROM dw.fact_order_item f LEFT JOIN dw.dim_category x ON x.category_key = f.category_key WHERE x.category_key IS NULL)
       + (SELECT count(*) FROM dw.fact_order_item f LEFT JOIN dw.dim_channel x ON x.channel_key = f.channel_key WHERE x.channel_key IS NULL)
       + (SELECT count(*) FROM dw.fact_order_item f LEFT JOIN dw.dim_payment_method x ON x.payment_method_key = f.payment_method_key WHERE x.payment_method_key IS NULL)
       + (SELECT count(*) FROM dw.fact_order_item f LEFT JOIN dw.dim_campaign x ON x.campaign_key = f.campaign_key WHERE x.campaign_key IS NULL)
       + (SELECT count(*) FROM dw.fact_order_item f LEFT JOIN dw.dim_promotion_group x ON x.promotion_group_key = f.promotion_group_key WHERE x.promotion_group_key IS NULL)
       + (SELECT count(*) FROM dw.fact_order_item f LEFT JOIN dw.dim_date x ON x.date_key = f.date_key WHERE x.date_key IS NULL), 0::numeric
  -- Tồn kho (566 nghìn dòng): đếm khóa NGOẠI PHÂN BIỆT không có trong dimension (nhanh hơn kiểm từng dòng ~6 lần)
  UNION ALL SELECT 11, 'A. Khóa ngoại', 'fact_inventory_snapshot: số khóa (sản phẩm, kho, ngày) không có trong dimension',
         (SELECT count(*) FROM (SELECT DISTINCT product_key AS k FROM dw.fact_inventory_snapshot) a
           WHERE NOT EXISTS (SELECT 1 FROM dw.dim_product d WHERE d.product_key = a.k))
       + (SELECT count(*) FROM (SELECT DISTINCT warehouse_key AS k FROM dw.fact_inventory_snapshot) a
           WHERE NOT EXISTS (SELECT 1 FROM dw.dim_warehouse d WHERE d.warehouse_key = a.k))
       + (SELECT count(*) FROM (SELECT DISTINCT date_key AS k FROM dw.fact_inventory_snapshot) a
           WHERE NOT EXISTS (SELECT 1 FROM dw.dim_date d WHERE d.date_key = a.k)), 0
  -- B. Mức hạt: mỗi dòng fact là một grain duy nhất
  UNION ALL SELECT 20, 'B. Mức hạt', 'fact_order_item: số dòng − số (đơn, dòng hàng) duy nhất',
         (SELECT count(*) - count(DISTINCT (source_system, order_id, line_number)) FROM dw.fact_order_item)::numeric, 0
  -- Khóa chính (ngày, product_key, kho) đã đảm bảo duy nhất ở mức phiên bản; chỉ sản phẩm có ≥ 2 phiên bản SCD2 mới có thể
  -- trùng ở mức sản phẩm nghiệp vụ, nên chỉ cần kiểm nhóm đó (nhanh hơn kiểm toàn bảng ~3 lần, cùng ý nghĩa).
  UNION ALL SELECT 21, 'B. Mức hạt', 'fact_inventory_snapshot: số nhóm (ngày, sản phẩm nghiệp vụ, kho) có hơn 1 dòng',
         (SELECT count(*) FROM (SELECT 1 FROM dw.fact_inventory_snapshot f JOIN dw.dim_product p USING (product_key)
                                WHERE p.product_id IN (SELECT product_id FROM dw.dim_product GROUP BY 1 HAVING count(*) > 1)
                                GROUP BY f.date_key, p.product_id, f.warehouse_key HAVING count(*) > 1) g)::numeric, 0
  UNION ALL SELECT 22, 'B. Mức hạt', 'fact_ad_spend: số dòng − số (tháng, chiến dịch, kênh) duy nhất',
         (SELECT count(*) - count(DISTINCT (month_key, campaign_key, channel_key)) FROM dw.fact_ad_spend)::numeric, 0
  -- C. SCD2: khoảng hiệu lực liền mạch, đúng một phiên bản hiện hành
  UNION ALL SELECT 30, 'C. SCD2 khoảng hiệu lực', 'dim_seller: phiên bản chồng lấn/hở + khóa không đúng 1 phiên bản hiện hành',
         (SELECT count(*) FROM (SELECT valid_from, lag(valid_to) OVER (PARTITION BY seller_id ORDER BY valid_from) AS prev_to FROM dw.dim_seller) x
           WHERE prev_to IS NOT NULL AND prev_to <> valid_from)
       + (SELECT count(*) FROM (SELECT seller_id FROM dw.dim_seller GROUP BY 1 HAVING count(*) FILTER (WHERE is_current) <> 1) y), 0
  UNION ALL SELECT 31, 'C. SCD2 khoảng hiệu lực', 'dim_customer: phiên bản chồng lấn/hở + khóa không đúng 1 phiên bản hiện hành',
         (SELECT count(*) FROM (SELECT valid_from, lag(valid_to) OVER (PARTITION BY customer_id ORDER BY valid_from) AS prev_to FROM dw.dim_customer) x
           WHERE prev_to IS NOT NULL AND prev_to <> valid_from)
       + (SELECT count(*) FROM (SELECT customer_id FROM dw.dim_customer GROUP BY 1 HAVING count(*) FILTER (WHERE is_current) <> 1) y), 0
  UNION ALL SELECT 32, 'C. SCD2 khoảng hiệu lực', 'dim_product: phiên bản chồng lấn/hở + khóa không đúng 1 phiên bản hiện hành',
         (SELECT count(*) FROM (SELECT valid_from, lag(valid_to) OVER (PARTITION BY product_id ORDER BY valid_from) AS prev_to FROM dw.dim_product) x
           WHERE prev_to IS NOT NULL AND prev_to <> valid_from)
       + (SELECT count(*) FROM (SELECT product_id FROM dw.dim_product GROUP BY 1 HAVING count(*) FILTER (WHERE is_current) <> 1) y), 0
  -- D. Fact trỏ đúng phiên bản dimension có hiệu lực tại ngày hoàn tất
  UNION ALL SELECT 40, 'D. Fact → đúng phiên bản', 'fact_order_item trỏ sai phiên bản seller',
         (SELECT count(*) FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_seller s USING (seller_key)
           WHERE d.full_date < s.valid_from OR d.full_date >= s.valid_to)::numeric, 0
  UNION ALL SELECT 41, 'D. Fact → đúng phiên bản', 'fact_order_item trỏ sai phiên bản khách hàng',
         (SELECT count(*) FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_customer c USING (customer_key)
           WHERE f.customer_key > 0 AND (d.full_date < c.valid_from OR d.full_date >= c.valid_to))::numeric, 0
  UNION ALL SELECT 42, 'D. Fact → đúng phiên bản', 'fact_order_item trỏ sai phiên bản sản phẩm',
         (SELECT count(*) FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_product p USING (product_key)
           WHERE d.full_date < p.valid_from OR d.full_date >= p.valid_to)::numeric, 0
  -- E. Tiền: fact khớp mọi tầng summary
  UNION ALL SELECT 50, 'E. Tiền khớp giữa các tầng', 'Σ doanh thu thuần: fact − mv_sales_day_product',
         (SELECT sum(net_revenue) FROM dw.fact_order_item) - (SELECT sum(net_revenue) FROM mart.mv_sales_day_product), 0
  UNION ALL SELECT 51, 'E. Tiền khớp giữa các tầng', 'Σ doanh thu thuần: fact − mv_sales_month_category',
         (SELECT sum(net_revenue) FROM dw.fact_order_item) - (SELECT sum(net_revenue) FROM mart.mv_sales_month_category), 0
  UNION ALL SELECT 52, 'E. Tiền khớp giữa các tầng', 'Σ doanh thu thuần: fact − mv_sales_month_seller_tier',
         (SELECT sum(net_revenue) FROM dw.fact_order_item) - (SELECT sum(net_revenue) FROM mart.mv_sales_month_seller_tier), 0
  UNION ALL SELECT 53, 'E. Tiền khớp giữa các tầng', 'Σ doanh thu thuần: fact − mv_sales_month_customer_region',
         (SELECT sum(net_revenue) FROM dw.fact_order_item) - (SELECT sum(net_revenue) FROM mart.mv_sales_month_customer_region), 0
  UNION ALL SELECT 54, 'E. Tiền khớp giữa các tầng', 'Σ chi phí quảng cáo: fact_ad_spend − mv_ads_month_channel',
         (SELECT coalesce(sum(cost_amount), 0) FROM dw.fact_ad_spend) - (SELECT coalesce(sum(cost_amount), 0) FROM mart.mv_ads_month_channel), 0
  -- F. Đẳng thức tiền trong từng dòng fact và bridge khuyến mãi
  UNION ALL SELECT 60, 'F. Đẳng thức tiền', 'dòng có gross − giảm giá ≠ doanh thu thuần',
         (SELECT count(*) FROM dw.fact_order_item WHERE abs(gross_amount - discount_amount - net_revenue) > 0.5)::numeric, 0
  UNION ALL SELECT 61, 'F. Đẳng thức tiền', 'dòng có doanh thu thuần − hoa hồng ≠ phần seller nhận',
         (SELECT count(*) FROM dw.fact_order_item WHERE abs(net_revenue - commission_amount - seller_net_amount) > 0.5)::numeric, 0
  UNION ALL SELECT 62, 'F. Đẳng thức tiền', 'dòng có số lượng ≤ 0 hoặc doanh thu âm',
         (SELECT count(*) FROM dw.fact_order_item WHERE quantity <= 0 OR net_revenue < 0)::numeric, 0
  UNION ALL SELECT 63, 'F. Đẳng thức tiền', 'bridge khuyến mãi: nhóm voucher có Σ trọng số ≠ 1',
         (SELECT count(*) FROM (SELECT promotion_group_key FROM dw.bridge_promotion_group GROUP BY 1
                                HAVING abs(sum(weighting_factor) - 1) > 0.000001) z)::numeric, 0
  -- G. Đối soát của ETL ở batch SUCCESS mới nhất
  UNION ALL SELECT 70, 'G. Đối soát ETL', 'kiểm tra RC/SCD không đạt ở batch SUCCESS mới nhất',
         (SELECT count(*) FROM audit.reconciliation r
           WHERE r.batch_id = (SELECT max(batch_id) FROM audit.batch_log WHERE status = 'SUCCESS') AND NOT r.passed)::numeric, 0
)
SELECT nhom, kiem_tra, gia_tri, ky_vong, CASE WHEN gia_tri = ky_vong THEN 'PASS' ELSE 'FAIL' END AS ket_qua
FROM chk ORDER BY thu_tu;

COMMENT ON VIEW mart.v_consistency_check IS 'Màn hình tổng duyệt nhất quán: mỗi dòng một kiểm tra, PASS khi gia_tri = ky_vong (dùng cho demo, bản rút gọn của dw/tests/run_tests.py).';
GRANT SELECT ON mart.v_consistency_check TO dw_analyst;
