-- PLAN 6 — Tầng mart: KPI dùng chung (6.1), materialized view theo tháp phân tầng (M2 §3.2), drill-across (6.2),
-- view cho dashboard (6.3). Chạy bằng dw_etl (chủ sở hữu); idempotent (DROP … CASCADE rồi tạo lại).
-- Quy tắc: MV chỉ lưu measure CỘNG ĐƯỢC + số đếm distinct đúng TẠI grain của MV (hậu tố _na: không cộng lên grain cao hơn);
-- tỷ lệ / bình quân (non-additive) tính trong view từ tử và mẫu đã tổng hợp.

-- ===================== 6.1 KPI dùng chung (Bảng 11 đề xuất) =====================
CREATE TABLE IF NOT EXISTS mart.kpi_definitions (
  kpi_code     text PRIMARY KEY,
  kpi_name     text NOT NULL,
  formula      text NOT NULL,
  source       text NOT NULL,
  additivity   text NOT NULL CHECK (additivity IN ('A','SA','NA')),
  common_error text,
  unit         text NOT NULL
);
TRUNCATE mart.kpi_definitions;
INSERT INTO mart.kpi_definitions VALUES
 ('NET_REVENUE','Doanh thu thuần','SUM(net_revenue)','fact_order_item','A','Cộng orders.final_amount (lẫn phí ship, nhân bản khi join dòng)','VND'),
 ('GROSS_REVENUE','Doanh thu gộp','SUM(gross_amount)','fact_order_item','A',NULL,'VND'),
 ('ORDERS','Số đơn','COUNT(DISTINCT (source_system, order_id))','fact_order_item','NA','COUNT(*) đếm dòng; cộng số đơn của các nhóm con','đơn'),
 ('ITEMS','Số món','SUM(quantity)','fact_order_item','A',NULL,'món'),
 ('AOV','Giá trị đơn bình quân','SUM(net_revenue) / COUNT(DISTINCT order_id) tại đúng grain đang xem','fact_order_item','NA','Trung bình của AOV theo ngày','VND/đơn'),
 ('AVG_PRICE','Giá bán bình quân','SUM(gross_amount) / SUM(quantity)','fact_order_item','NA','AVG(unit_price)','VND/món'),
 ('VOUCHER_RATE','Tỷ lệ giảm giá voucher','SUM(discount_amount) / SUM(gross_amount)','fact_order_item','NA','Trung bình tỷ lệ từng dòng','%'),
 ('LIST_DISCOUNT_RATE','Tỷ lệ giảm giá niêm yết','SUM(list_discount_amount) / SUM(list_amount)','fact_order_item','NA',NULL,'%'),
 ('COMMISSION_RATE_EFF','Tỷ lệ hoa hồng hiệu dụng','SUM(commission_amount) / SUM(net_revenue)','fact_order_item','NA','AVG(commission_rate)','%'),
 ('RETURN_RATE','Tỷ lệ trả hàng (món)','SUM(quantity) FILTER (WHERE is_returned) / SUM(quantity)','fact_order_item','NA',NULL,'%'),
 ('BUYERS','Số khách mua','COUNT(DISTINCT customer_id) FILTER (WHERE customer_key > 0)','fact_order_item + dim_customer','NA','Đếm cả -1 (khách vãng lai); đếm customer_key (nhiều phiên bản SCD2)','khách'),
 ('GUEST_ORDER_SHARE','Tỷ trọng đơn khách vãng lai','COUNT(DISTINCT order_id) FILTER (WHERE customer_key = -1) / số đơn','fact_order_item','NA',NULL,'%'),
 ('MARGIN_RATE_EST','Biên lãi gộp ước tính','SUM(gross_margin_est) / SUM(net_revenue) — giá vốn theo giả định G1','fact_order_item','NA','Không ghi chú "ước tính"','%'),
 ('VOUCHER_ALLOC','Giảm giá phân bổ theo voucher','SUM(f.discount_amount × b.weighting_factor) GROUP BY promotion_key','fact_order_item + bridge_promotion_group','A','SUM(net_revenue) sau join bridge không nhân weight','VND'),
 ('END_STOCK','Tồn cuối kỳ','quantity_on_hand tại ngày snapshot cuối kỳ, rồi cộng theo kho/sản phẩm','fact_inventory_snapshot','SA','SUM qua các ngày','món'),
 ('AVG_STOCK','Tồn bình quân kỳ','AVG theo ngày của quantity_on_hand','fact_inventory_snapshot','SA','Trung bình từng dòng của nhiều kho','món'),
 ('STOCKOUT_DAYS','Số ngày hết hàng','SUM(stockout_flag)','fact_inventory_snapshot','A',NULL,'ngày'),
 ('TURNOVER','Vòng quay tồn kho','SUM(qty_sold kỳ) / tồn bình quân kỳ','fact_inventory_snapshot','NA',NULL,'vòng'),
 ('DAYS_OF_SUPPLY','Số ngày tồn','tồn cuối kỳ / (SUM(qty_sold kỳ) / số ngày kỳ); NULL nếu không bán','fact_inventory_snapshot','NA',NULL,'ngày'),
 ('AD_COST','Chi phí quảng cáo','SUM(cost_amount)','fact_ad_spend','A',NULL,'VND'),
 ('CTR','Tỷ lệ nhấp','SUM(clicks) / SUM(impressions)','fact_ad_spend','NA','Trung bình CTR các chiến dịch','%'),
 ('CPC','Chi phí mỗi lượt nhấp','SUM(cost_amount) / SUM(clicks)','fact_ad_spend','NA',NULL,'VND'),
 ('CPM','Chi phí mỗi nghìn hiển thị','SUM(cost_amount) / SUM(impressions) × 1000','fact_ad_spend','NA',NULL,'VND'),
 ('REVENUE_PER_AD_COST','Doanh thu / chi phí QC (tháng–kênh)','SUM(net_revenue) / SUM(cost_amount), ghép FULL OUTER JOIN theo (month_key, channel_key)','drill-across','NA','INNER JOIN làm mất kênh chỉ có một phía; diễn giải như nhân quả','lần');
CREATE OR REPLACE VIEW mart.v_kpi_definitions AS SELECT * FROM mart.kpi_definitions ORDER BY source, kpi_code;

-- ===================== Trạng thái refresh (dashboard hiển thị "thời điểm dữ liệu") =====================
CREATE TABLE IF NOT EXISTS mart.refresh_status (
  mv_name       text PRIMARY KEY,
  batch_id      bigint,
  refreshed_at  timestamp NOT NULL,
  row_count     bigint,
  seconds       numeric(10,3)
);

-- ===================== Materialized view (tầng 2–3) =====================
DROP MATERIALIZED VIEW IF EXISTS mart.mv_sales_day_product CASCADE;
CREATE MATERIALIZED VIEW mart.mv_sales_day_product AS   -- Tầng 2: ngày × sản phẩm (phiên bản) × seller × kênh
SELECT f.date_key, d.month_key, f.product_key, p.product_id, f.category_key, f.seller_key, f.channel_key,
       count(*) AS line_count, count(DISTINCT f.order_id) AS order_count_na,
       sum(f.quantity) AS quantity, sum(f.list_amount) AS list_amount, sum(f.gross_amount) AS gross_amount,
       sum(f.list_discount_amount) AS list_discount_amount, sum(f.discount_amount) AS discount_amount,
       sum(f.net_revenue) AS net_revenue, sum(f.commission_amount) AS commission_amount,
       sum(f.seller_net_amount) AS seller_net_amount, sum(f.cost_amount_est) AS cost_amount_est,
       sum(f.gross_margin_est) AS gross_margin_est, coalesce(sum(f.quantity) FILTER (WHERE f.is_returned), 0) AS returned_quantity
FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_product p USING (product_key)
GROUP BY 1, 2, 3, 4, 5, 6, 7;
CREATE UNIQUE INDEX ux_mv_sales_day_product ON mart.mv_sales_day_product (date_key, product_key, seller_key, channel_key);
CREATE INDEX ix_mv_sdp_month ON mart.mv_sales_day_product (month_key, category_key);

DROP MATERIALIZED VIEW IF EXISTS mart.mv_sales_month_category CASCADE;
CREATE MATERIALIZED VIEW mart.mv_sales_month_category AS   -- Tầng 3: tháng × danh mục lá × kênh
SELECT d.month_key, f.category_key, f.channel_key,
       count(*) AS line_count, count(DISTINCT f.order_id) AS order_count_na,
       count(DISTINCT dc.customer_id) FILTER (WHERE f.customer_key > 0) AS buyer_count_na,
       sum(f.quantity) AS quantity, sum(f.gross_amount) AS gross_amount, sum(f.discount_amount) AS discount_amount,
       sum(f.net_revenue) AS net_revenue, sum(f.commission_amount) AS commission_amount, sum(f.gross_margin_est) AS gross_margin_est
FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_customer dc USING (customer_key)
GROUP BY 1, 2, 3;
CREATE UNIQUE INDEX ux_mv_sales_month_category ON mart.mv_sales_month_category (month_key, category_key, channel_key);

DROP MATERIALIZED VIEW IF EXISTS mart.mv_sales_month_channel CASCADE;
CREATE MATERIALIZED VIEW mart.mv_sales_month_channel AS   -- Tầng 3: tháng × kênh (phía bán hàng của drill-across)
SELECT d.month_key, f.channel_key,
       count(*) AS line_count, count(DISTINCT f.order_id) AS order_count_na,
       count(DISTINCT dc.customer_id) FILTER (WHERE f.customer_key > 0) AS buyer_count_na,
       count(DISTINCT f.order_id) FILTER (WHERE f.campaign_key > 0) AS campaign_order_count_na,
       sum(f.quantity) AS quantity, sum(f.gross_amount) AS gross_amount, sum(f.net_revenue) AS net_revenue,
       coalesce(sum(f.net_revenue) FILTER (WHERE f.campaign_key > 0), 0) AS campaign_net_revenue
FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_customer dc USING (customer_key)
GROUP BY 1, 2;
CREATE UNIQUE INDEX ux_mv_sales_month_channel ON mart.mv_sales_month_channel (month_key, channel_key);

DROP MATERIALIZED VIEW IF EXISTS mart.mv_sales_month_seller_tier CASCADE;
CREATE MATERIALIZED VIEW mart.mv_sales_month_seller_tier AS   -- SCD2 vs SCD1: thuộc tính seller TẠI THỜI ĐIỂM BÁN và HIỆN TẠI
SELECT d.month_key, f.seller_key, s.seller_id, s.shop_name AS shop_name,
       s.tier AS tier_at_sale, s.province_name AS province_at_sale, s.status AS status_at_sale,
       cur.tier AS tier_current, cur.province_name AS province_current, cur.status AS status_current,
       count(DISTINCT f.order_id) AS order_count_na, sum(f.quantity) AS quantity,
       sum(f.gross_amount) AS gross_amount, sum(f.net_revenue) AS net_revenue, sum(f.commission_amount) AS commission_amount
FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key)
JOIN dw.dim_seller s ON s.seller_key = f.seller_key
LEFT JOIN dw.dim_seller cur ON cur.seller_id = s.seller_id AND cur.is_current
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10;
CREATE UNIQUE INDEX ux_mv_sales_month_seller_tier ON mart.mv_sales_month_seller_tier (month_key, seller_key);

DROP MATERIALIZED VIEW IF EXISTS mart.mv_sales_month_customer_region CASCADE;
CREATE MATERIALIZED VIEW mart.mv_sales_month_customer_region AS   -- SCD2 khách: tỉnh lúc mua vs tỉnh hiện tại
SELECT d.month_key,
       CASE WHEN f.customer_key = -1 THEN 'Khách vãng lai' ELSE c.province_name END AS province_at_sale,
       CASE WHEN f.customer_key = -1 THEN 'NA' ELSE c.region END AS region_at_sale,
       CASE WHEN f.customer_key = -1 THEN 'Khách vãng lai' ELSE cur.province_name END AS province_current,
       count(DISTINCT f.order_id) AS order_count_na,
       count(DISTINCT c.customer_id) FILTER (WHERE f.customer_key > 0) AS buyer_count_na,
       sum(f.net_revenue) AS net_revenue, sum(f.quantity) AS quantity
FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key)
JOIN dw.dim_customer c ON c.customer_key = f.customer_key
LEFT JOIN dw.dim_customer cur ON cur.customer_id = c.customer_id AND cur.is_current
GROUP BY 1, 2, 3, 4;
CREATE UNIQUE INDEX ux_mv_sales_month_customer_region ON mart.mv_sales_month_customer_region (month_key, province_at_sale, region_at_sale, province_current);

DROP MATERIALIZED VIEW IF EXISTS mart.mv_inventory_month_product CASCADE;
CREATE MATERIALIZED VIEW mart.mv_inventory_month_product AS   -- Tầng 3: tháng × sản phẩm (mã nghiệp vụ) × kho; semi-additive
WITH s AS (
  SELECT d.month_key, p.product_id, f.warehouse_key, f.date_key, f.quantity_on_hand, f.quantity_reserved,
         f.quantity_available, f.inventory_value_est, f.qty_sold, f.qty_imported, f.qty_returned, f.qty_adjusted, f.stockout_flag,
         row_number() OVER (PARTITION BY d.month_key, p.product_id, f.warehouse_key ORDER BY f.date_key DESC) AS rn
  FROM dw.fact_inventory_snapshot f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_product p USING (product_key))
SELECT month_key, product_id, warehouse_key,
       max(date_key) AS end_date_key, count(*) AS days_present,
       max(quantity_on_hand) FILTER (WHERE rn = 1) AS end_on_hand,          -- tồn cuối kỳ (SA)
       max(quantity_available) FILTER (WHERE rn = 1) AS end_available,
       max(inventory_value_est) FILTER (WHERE rn = 1) AS end_value_est,     -- 📝 ước tính (G1)
       round(avg(quantity_on_hand), 2) AS avg_on_hand,                       -- tồn bình quân ngày (SA)
       sum(qty_sold) AS qty_sold, sum(qty_imported) AS qty_imported, sum(qty_returned) AS qty_returned,
       sum(qty_adjusted) AS qty_adjusted, sum(stockout_flag) AS stockout_days
FROM s GROUP BY 1, 2, 3;
CREATE UNIQUE INDEX ux_mv_inventory_month_product ON mart.mv_inventory_month_product (month_key, product_id, warehouse_key);

DROP MATERIALIZED VIEW IF EXISTS mart.mv_ads_month_channel CASCADE;
CREATE MATERIALIZED VIEW mart.mv_ads_month_channel AS   -- Tầng 3: tháng × kênh (phía quảng cáo của drill-across)
SELECT month_key, channel_key, count(DISTINCT campaign_key) AS campaign_count_na,
       sum(cost_amount) AS cost_amount, sum(impressions) AS impressions, sum(clicks) AS clicks,
       sum(active_days) AS campaign_days      -- Σ ngày chạy của các chiến dịch (không phải số ngày lịch)
FROM dw.fact_ad_spend GROUP BY 1, 2;
CREATE UNIQUE INDEX ux_mv_ads_month_channel ON mart.mv_ads_month_channel (month_key, channel_key);

DROP MATERIALIZED VIEW IF EXISTS mart.mv_promotion_month CASCADE;
CREATE MATERIALIZED VIEW mart.mv_promotion_month AS   -- Bridge: giảm giá phân bổ theo voucher (nhân weight)
SELECT d.month_key, b.promotion_key, count(DISTINCT f.order_id) AS order_count_na, count(*) AS line_count,
       sum(f.discount_amount * b.weighting_factor)::numeric(18,2) AS allocated_discount,
       sum(f.net_revenue * b.weighting_factor)::numeric(18,2) AS allocated_net_revenue
FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key)
JOIN dw.bridge_promotion_group b USING (promotion_group_key)
GROUP BY 1, 2;
CREATE UNIQUE INDEX ux_mv_promotion_month ON mart.mv_promotion_month (month_key, promotion_key);

-- ===================== KPI theo kỳ (tầng 3–4), tính trực tiếp từ fact atomic → non-additive đúng ở mọi cấp =====================
CREATE OR REPLACE VIEW mart.v_kpi_period AS
SELECT CASE WHEN GROUPING(d.quarter) = 1 THEN 'Năm' WHEN GROUPING(d.month_key) = 1 THEN 'Quý' ELSE 'Tháng' END AS period_level,
       d.year, d.quarter, d.month_key,
       sum(f.net_revenue) AS net_revenue, sum(f.gross_amount) AS gross_amount, sum(f.quantity) AS items,
       count(DISTINCT f.order_id) AS orders,
       round(sum(f.net_revenue) / nullif(count(DISTINCT f.order_id), 0), 2) AS aov,
       round(sum(f.gross_amount) / nullif(sum(f.quantity), 0), 2) AS avg_price,
       round(sum(f.discount_amount) / nullif(sum(f.gross_amount), 0), 6) AS voucher_rate,
       round(sum(f.list_discount_amount) / nullif(sum(f.list_amount), 0), 6) AS list_discount_rate,
       round(sum(f.commission_amount) / nullif(sum(f.net_revenue), 0), 6) AS commission_rate_eff,
       round(coalesce(sum(f.quantity) FILTER (WHERE f.is_returned), 0)::numeric / nullif(sum(f.quantity), 0), 6) AS return_rate,
       count(DISTINCT dc.customer_id) FILTER (WHERE f.customer_key > 0) AS buyers,
       round(count(DISTINCT f.order_id) FILTER (WHERE f.customer_key = -1)::numeric / nullif(count(DISTINCT f.order_id), 0), 6) AS guest_order_share,
       round(sum(f.gross_margin_est) / nullif(sum(f.net_revenue), 0), 6) AS margin_rate_est
FROM dw.fact_order_item f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_customer dc USING (customer_key)
GROUP BY GROUPING SETS ((d.year), (d.year, d.quarter), (d.year, d.quarter, d.month_key));

-- ===================== 6.2 Drill-across =====================
-- Doanh thu – quảng cáo theo (tháng, kênh): FULL OUTER JOIN trên dimension dùng chung, giữ nhóm chỉ có một phía
CREATE OR REPLACE VIEW mart.v_drill_sales_ads AS
SELECT coalesce(s.month_key, a.month_key) AS month_key, m.month_label,
       coalesce(s.channel_key, a.channel_key) AS channel_key, ch.channel_name, ch.marketing_code,
       s.net_revenue, s.order_count_na AS orders, s.campaign_net_revenue, a.cost_amount, a.impressions, a.clicks,
       round(s.net_revenue / nullif(a.cost_amount, 0), 2) AS revenue_per_ad_cost,
       round(a.clicks::numeric / nullif(a.impressions, 0), 6) AS ctr,
       round(a.cost_amount / nullif(a.clicks, 0), 2) AS cpc,
       (s.month_key IS NULL) AS missing_sales, (a.month_key IS NULL) AS missing_ads
FROM mart.mv_sales_month_channel s
FULL OUTER JOIN mart.mv_ads_month_channel a ON a.month_key = s.month_key AND a.channel_key = s.channel_key
JOIN dw.dim_month m ON m.month_key = coalesce(s.month_key, a.month_key)
JOIN dw.dim_channel ch ON ch.channel_key = coalesce(s.channel_key, a.channel_key);

-- Doanh thu – tồn kho theo (sản phẩm, tháng): ghép bằng MÃ NGHIỆP VỤ product_id (không bằng surrogate key — SCD2)
CREATE OR REPLACE VIEW mart.v_drill_sales_inventory AS
WITH s AS (SELECT month_key, product_id, sum(quantity) AS sold_qty_completed, sum(net_revenue) AS net_revenue,
                  sum(order_count_na) AS order_lines_approx
           FROM mart.mv_sales_day_product GROUP BY 1, 2),
     i AS (SELECT month_key, product_id, max(end_date_key) AS end_date_key, sum(end_on_hand) AS end_on_hand,
                  sum(avg_on_hand) AS avg_on_hand, sum(qty_sold) AS qty_sold_warehouse, sum(qty_imported) AS qty_imported,
                  sum(stockout_days) AS stockout_days, max(days_present) AS days_present, sum(end_value_est) AS end_value_est
           FROM mart.mv_inventory_month_product GROUP BY 1, 2)
SELECT coalesce(s.month_key, i.month_key) AS month_key, coalesce(s.product_id, i.product_id) AS product_id,
       p.product_name, p.category_key, c.path_names AS category_path, p.list_price,
       s.sold_qty_completed, s.net_revenue, i.qty_sold_warehouse, i.qty_imported, i.end_date_key, i.end_on_hand, i.avg_on_hand,
       i.stockout_days, i.end_value_est,
       round(i.qty_sold_warehouse / nullif(i.avg_on_hand, 0), 4) AS turnover,
       round(i.end_on_hand / nullif(i.qty_sold_warehouse::numeric / nullif(i.days_present, 0), 0), 1) AS days_of_supply,
       (s.product_id IS NULL) AS missing_sales, (i.product_id IS NULL) AS missing_inventory
FROM s FULL OUTER JOIN i ON i.month_key = s.month_key AND i.product_id = s.product_id
JOIN dw.dim_product p ON p.product_id = coalesce(s.product_id, i.product_id) AND p.is_current
JOIN dw.dim_category c ON c.category_key = p.category_key;

-- ===================== Hỗ trợ dashboard =====================
CREATE OR REPLACE VIEW mart.v_category_tree AS
SELECT c.category_key, c.category_id, c.category_name, c.level, c.is_leaf, c.parent_category_key, c.root_category_key,
       r.category_name AS root_name, c.path_names, c.is_named
FROM dw.dim_category c LEFT JOIN dw.dim_category r ON r.category_key = c.root_category_key
WHERE c.category_key > 0;

CREATE OR REPLACE VIEW mart.v_data_freshness AS
SELECT b.batch_id AS last_success_batch, b.watermark_to AS data_through, b.finished_at AS loaded_at,
       (SELECT min(batch_id) FROM mart.refresh_status) AS mart_batch, (SELECT max(refreshed_at) FROM mart.refresh_status) AS mart_refreshed_at,
       coalesce((SELECT min(batch_id) FROM mart.refresh_status), -1) <> b.batch_id AS mart_stale
FROM audit.batch_log b WHERE b.status = 'SUCCESS' ORDER BY b.watermark_to DESC, b.batch_id DESC LIMIT 1;

CREATE OR REPLACE VIEW mart.v_dq_batch AS
SELECT b.batch_id, b.batch_type, b.status, b.watermark_from, b.watermark_to, b.started_at, b.finished_at, b.message,
       t.stage, sum(t.rows_read) AS rows_read, sum(t.rows_valid) AS rows_valid, sum(t.rows_warn) AS rows_warn,
       sum(t.rows_quarantined) AS rows_quarantined, sum(t.rows_deduplicated) AS rows_deduplicated, sum(t.rows_written) AS rows_written
FROM audit.batch_log b LEFT JOIN audit.batch_table_log t USING (batch_id)
GROUP BY b.batch_id, b.batch_type, b.status, b.watermark_from, b.watermark_to, b.started_at, b.finished_at, b.message, t.stage;

CREATE OR REPLACE VIEW mart.v_quarantine_summary AS
SELECT batch_id, source_table, rule_code, severity, reason, count(*) AS rows, min(source_pk) AS sample_pk,
       count(*) FILTER (WHERE resolved_batch_id IS NOT NULL) AS resolved
FROM audit.quarantine GROUP BY 1, 2, 3, 4, 5;

CREATE OR REPLACE VIEW mart.v_unknown_keys AS
SELECT 'fact_order_item' AS fact, k.key_name, count(*) FILTER (WHERE k.v = 0) AS unknown_0, count(*) FILTER (WHERE k.v = -1) AS not_applicable_m1,
       count(*) AS rows
FROM dw.fact_order_item f
CROSS JOIN LATERAL (VALUES ('product_key', f.product_key), ('seller_key', f.seller_key), ('customer_key', f.customer_key),
                           ('customer_profile_key', f.customer_profile_key::int), ('channel_key', f.channel_key),
                           ('payment_method_key', f.payment_method_key), ('campaign_key', f.campaign_key),
                           ('promotion_group_key', f.promotion_group_key), ('category_key', f.category_key)) k(key_name, v)
GROUP BY 1, 2
UNION ALL
SELECT 'fact_inventory_snapshot', k.key_name, count(*) FILTER (WHERE k.v = 0), count(*) FILTER (WHERE k.v = -1), count(*)
FROM dw.fact_inventory_snapshot f
CROSS JOIN LATERAL (VALUES ('product_key', f.product_key), ('warehouse_key', f.warehouse_key), ('category_key', f.category_key)) k(key_name, v)
GROUP BY 1, 2
UNION ALL
SELECT 'fact_ad_spend', k.key_name, count(*) FILTER (WHERE k.v = 0), count(*) FILTER (WHERE k.v = -1), count(*)
FROM dw.fact_ad_spend f CROSS JOIN LATERAL (VALUES ('campaign_key', f.campaign_key), ('channel_key', f.channel_key)) k(key_name, v)
GROUP BY 1, 2;

-- ===================== Refresh (B6 của batch: chỉ chạy sau khi batch SUCCESS) =====================
CREATE OR REPLACE FUNCTION mart.refresh_all(p_batch bigint) RETURNS TABLE (mv_name text, row_count bigint, seconds numeric)
LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE mv text; t0 timestamptz; n bigint;
BEGIN
  FOREACH mv IN ARRAY ARRAY['mv_sales_day_product','mv_sales_month_category','mv_sales_month_channel',
                            'mv_sales_month_seller_tier','mv_sales_month_customer_region','mv_inventory_month_product',
                            'mv_ads_month_channel','mv_promotion_month'] LOOP
    t0 := clock_timestamp();
    EXECUTE format('REFRESH MATERIALIZED VIEW CONCURRENTLY mart.%I', mv);
    EXECUTE format('SELECT count(*) FROM mart.%I', mv) INTO n;
    INSERT INTO mart.refresh_status AS r VALUES (mv, p_batch, now()::timestamp, n,
                                                 extract(epoch FROM clock_timestamp() - t0))
    ON CONFLICT (mv_name) DO UPDATE SET batch_id = EXCLUDED.batch_id, refreshed_at = EXCLUDED.refreshed_at,
                                        row_count = EXCLUDED.row_count, seconds = EXCLUDED.seconds;
    mv_name := mv; row_count := n; seconds := round(extract(epoch FROM clock_timestamp() - t0)::numeric, 3);
    RETURN NEXT;
  END LOOP;
END $$;

-- Quyền: dw_analyst đọc mart (MV/view tạo lại cần cấp lại) và bench (màn hình Hiệu năng)
GRANT USAGE ON SCHEMA mart TO dw_analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA mart TO dw_analyst;
GRANT USAGE ON SCHEMA bench TO dw_analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA bench TO dw_analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA bench GRANT SELECT ON TABLES TO dw_analyst;

COMMENT ON MATERIALIZED VIEW mart.mv_sales_day_product IS 'Tầng 2: ngày × sản phẩm × seller × kênh. Measure cộng được; order_count_na chỉ đúng tại grain này.';
COMMENT ON MATERIALIZED VIEW mart.mv_inventory_month_product IS 'Tồn cuối tháng (ngày snapshot cuối) và tồn bình quân — semi-additive: không SUM qua tháng.';
COMMENT ON VIEW mart.v_drill_sales_ads IS 'Drill-across doanh thu × chi phí QC theo (tháng, kênh), FULL OUTER JOIN — PLAN 6.2.';
COMMENT ON VIEW mart.v_drill_sales_inventory IS 'Drill-across doanh thu × tồn kho theo (product_id, tháng) — ghép mã nghiệp vụ.';
