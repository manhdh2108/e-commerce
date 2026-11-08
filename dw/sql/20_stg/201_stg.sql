-- PLAN 5.3 — Tầng stg: bảng ánh xạ (nạp từ dw/etl/mappings/*.csv) và dữ liệu đã chuẩn hóa theo batch.
-- stg KHÔNG bất biến: Transform xóa và ghi lại toàn bộ dòng của batch đang xử lý (chạy lại an toàn).
-- Mọi bảng dữ liệu có batch_id + dq_status ('VALID' | 'WARN'); dòng lỗi ERROR nằm ở audit.quarantine.

-- ===================== Bảng ánh xạ (IR-03, IR-08, IR-09, R-PRD-05) =====================
CREATE TABLE IF NOT EXISTS stg.map_channel   (source_code text PRIMARY KEY, channel_id int NOT NULL, note text);
CREATE TABLE IF NOT EXISTS stg.map_province  (source_name text PRIMARY KEY, province_code text NOT NULL, province_name text NOT NULL,
                                              region text NOT NULL CHECK (region IN ('Bắc','Trung','Nam')));
CREATE TABLE IF NOT EXISTS stg.map_gender    (source_value text PRIMARY KEY, gender char(1) NOT NULL CHECK (gender IN ('M','F','U')));
CREATE TABLE IF NOT EXISTS stg.map_cost_ratio(root_category_id bigint PRIMARY KEY, cost_group text NOT NULL,
                                              cost_ratio_min numeric(4,3), cost_ratio_max numeric(4,3), cost_ratio numeric(4,3) NOT NULL, note text);

-- ===================== Dimension đã chuẩn hóa =====================
CREATE TABLE IF NOT EXISTS stg.category (
  batch_id bigint NOT NULL, dq_status text NOT NULL,
  category_id bigint NOT NULL, parent_id bigint, level smallint NOT NULL, category_name text NOT NULL,
  is_named boolean NOT NULL, is_leaf boolean, root_id bigint, path_ids text, path_names text, parent_count int,
  PRIMARY KEY (batch_id, category_id));

CREATE TABLE IF NOT EXISTS stg.product (
  batch_id bigint NOT NULL, dq_status text NOT NULL,
  product_id bigint NOT NULL, sku text NOT NULL, product_name text NOT NULL, brand_name text NOT NULL,
  leaf_category_id bigint, root_category_id bigint, seller_id bigint NOT NULL,
  list_price numeric(18,2) NOT NULL, original_price numeric(18,2) NOT NULL, discount_rate numeric(6,4) NOT NULL,
  cost_ratio numeric(4,3), unit_cost_est numeric(18,2), is_active boolean NOT NULL,
  updated_at timestamp, effective_date date NOT NULL, scd1_hash text NOT NULL, scd2_hash text NOT NULL,
  PRIMARY KEY (batch_id, product_id));

CREATE TABLE IF NOT EXISTS stg.seller (
  batch_id bigint NOT NULL, dq_status text NOT NULL,
  seller_id bigint NOT NULL, shop_name text NOT NULL, seller_name text NOT NULL, email_domain text, phone_masked text,
  province_code text, province_name text, region text, tier text NOT NULL, status text NOT NULL,
  updated_at timestamp, effective_date date NOT NULL, scd1_hash text NOT NULL, scd2_hash text NOT NULL,
  PRIMARY KEY (batch_id, seller_id));

CREATE TABLE IF NOT EXISTS stg.customer (
  batch_id bigint NOT NULL, dq_status text NOT NULL,
  customer_id bigint NOT NULL, full_name text NOT NULL, phone_masked text, email_domain text, gender char(1) NOT NULL,
  birth_year smallint, age_band text NOT NULL, province_code text, province_name text, region text,
  membership_tier text NOT NULL, registration_date date, updated_at timestamp, effective_date date NOT NULL,
  scd1_hash text NOT NULL, scd2_hash text NOT NULL,
  PRIMARY KEY (batch_id, customer_id));

CREATE TABLE IF NOT EXISTS stg.channel (batch_id bigint NOT NULL, dq_status text NOT NULL, channel_id int NOT NULL,
  channel_name text NOT NULL, channel_type text NOT NULL, marketing_code text, PRIMARY KEY (batch_id, channel_id));
CREATE TABLE IF NOT EXISTS stg.payment_method (batch_id bigint NOT NULL, dq_status text NOT NULL, payment_method_id int NOT NULL,
  method_name text NOT NULL, method_group text NOT NULL, PRIMARY KEY (batch_id, payment_method_id));
CREATE TABLE IF NOT EXISTS stg.warehouse (batch_id bigint NOT NULL, dq_status text NOT NULL, warehouse_id int NOT NULL,
  warehouse_code text NOT NULL, warehouse_name text NOT NULL, province_code text, province_name text, region text,
  PRIMARY KEY (batch_id, warehouse_id));
CREATE TABLE IF NOT EXISTS stg.promotion (batch_id bigint NOT NULL, dq_status text NOT NULL, promotion_id bigint NOT NULL,
  promo_code text NOT NULL, promo_name text NOT NULL, promo_type text NOT NULL, funded_by text NOT NULL, apply_level text NOT NULL,
  discount_type text, discount_value numeric(18,2), min_order_value numeric(18,2), seller_id bigint, start_ts timestamp, end_ts timestamp,
  PRIMARY KEY (batch_id, promotion_id));
CREATE TABLE IF NOT EXISTS stg.campaign (batch_id bigint NOT NULL, dq_status text NOT NULL, campaign_id int NOT NULL,
  campaign_code text NOT NULL, campaign_name text NOT NULL, campaign_type text NOT NULL, target_channel_code text,
  target_channel_id int, budget_amount numeric(18,2), start_date date, end_date date, PRIMARY KEY (batch_id, campaign_id));

-- ===================== Nguồn của fact =====================
CREATE TABLE IF NOT EXISTS stg.order_item_sales (
  batch_id bigint NOT NULL, dq_status text NOT NULL, source_system text NOT NULL,
  order_id bigint NOT NULL, line_number int NOT NULL, order_item_id bigint NOT NULL, order_code text NOT NULL,
  completed_at timestamp NOT NULL, date_key int NOT NULL, ordered_at timestamp NOT NULL, order_date_key int NOT NULL,
  product_id bigint NOT NULL, seller_id bigint NOT NULL, customer_id bigint, channel_id int NOT NULL,
  campaign_id int, payment_method_id int,
  quantity int NOT NULL, list_price numeric(18,2) NOT NULL, unit_price numeric(18,2) NOT NULL,
  list_amount numeric(18,2) NOT NULL, gross_amount numeric(18,2) NOT NULL, list_discount_amount numeric(18,2) NOT NULL,
  discount_amount numeric(18,2) NOT NULL, net_revenue numeric(18,2) NOT NULL,
  commission_rate numeric(6,4) NOT NULL, commission_amount numeric(18,2) NOT NULL,
  item_status text NOT NULL, is_returned boolean NOT NULL,
  PRIMARY KEY (batch_id, order_id, line_number));

CREATE TABLE IF NOT EXISTS stg.order_item_promotion (
  batch_id bigint NOT NULL, dq_status text NOT NULL, order_item_id bigint NOT NULL, promotion_id bigint NOT NULL,
  applied_discount_amount numeric(18,2) NOT NULL, funded_by text, weighting_factor numeric(9,6) NOT NULL, group_signature text NOT NULL,
  PRIMARY KEY (batch_id, order_item_id, promotion_id));

CREATE TABLE IF NOT EXISTS stg.inventory_daily (
  batch_id bigint NOT NULL, dq_status text NOT NULL, balance_date date NOT NULL, date_key int NOT NULL,
  warehouse_id int NOT NULL, sku text NOT NULL, product_id bigint NOT NULL,
  quantity_on_hand int NOT NULL, quantity_reserved int NOT NULL, quantity_available int NOT NULL,
  qty_imported int NOT NULL, qty_sold int NOT NULL, qty_returned int NOT NULL, qty_adjusted int NOT NULL, stockout_flag smallint NOT NULL,
  PRIMARY KEY (batch_id, balance_date, warehouse_id, sku));

-- Chi phí QC mức ngày (atomic của nguồn, M2 §2.1.3). Giữ qua các batch để tính lại tháng chưa kết thúc.
CREATE TABLE IF NOT EXISTS stg.ad_spend_daily (
  batch_id bigint NOT NULL, dq_status text NOT NULL, ad_spend_log_id bigint NOT NULL, campaign_id int NOT NULL,
  channel_code text NOT NULL, channel_id int NOT NULL, log_date date NOT NULL, month_key int NOT NULL,
  cost_amount numeric(18,2) NOT NULL, impressions bigint NOT NULL, clicks bigint NOT NULL,
  PRIMARY KEY (batch_id, ad_spend_log_id));

COMMENT ON SCHEMA stg IS 'Dữ liệu đã chuẩn hóa theo batch (Transform, PLAN 5.3) và bảng ánh xạ stg.map_* nạp từ dw/etl/mappings/*.csv.';
