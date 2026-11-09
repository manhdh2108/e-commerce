CREATE TABLE dw.dim_month (
month_key      int PRIMARY KEY,                 
  year           smallint NOT NULL,
  quarter        smallint NOT NULL CHECK (quarter BETWEEN 1 AND 4),
  month          smallint NOT NULL CHECK (month BETWEEN 1 AND 12),
  month_label    text NOT NULL,                   
  quarter_label  text NOT NULL,                   
  first_date     date NOT NULL,
  last_date      date NOT NULL,
  days_in_month  smallint NOT NULL
);

CREATE TABLE dw.dim_date (
date_key       int PRIMARY KEY,                 
  full_date      date NOT NULL UNIQUE,
  day_of_month   smallint NOT NULL,
  day_of_week    smallint NOT NULL,               
  day_name       text NOT NULL,
  iso_week       smallint NOT NULL,
  iso_year       smallint NOT NULL,
  month_key      int NOT NULL REFERENCES dw.dim_month (month_key),
  month          smallint NOT NULL,
  month_name     text NOT NULL,
  quarter        smallint NOT NULL,
  year           smallint NOT NULL,
  is_weekend     boolean NOT NULL,
  is_holiday     boolean NOT NULL,
  holiday_name   text,
  is_double_day  boolean NOT NULL,                
  is_month_end   boolean NOT NULL
);

CREATE TABLE dw.dim_category (
category_key        int PRIMARY KEY,
  category_id         int NOT NULL UNIQUE,
  category_name       text NOT NULL,
  is_named            boolean NOT NULL DEFAULT true,
  parent_category_key int REFERENCES dw.dim_category (category_key),
  level               smallint NOT NULL,
  is_leaf             boolean NOT NULL,
  root_category_key   int,
  path_ids            text NOT NULL,
  path_names          text NOT NULL,
  batch_id            bigint
);

CREATE TABLE dw.bridge_category_hierarchy (
ancestor_key   int NOT NULL REFERENCES dw.dim_category (category_key),
  descendant_key int NOT NULL REFERENCES dw.dim_category (category_key),
  depth          smallint NOT NULL CHECK (depth >= 0),
  PRIMARY KEY (ancestor_key, descendant_key)
);

CREATE TABLE dw.dim_product (
product_key       serial PRIMARY KEY,
  product_id        bigint NOT NULL,
  sku               text NOT NULL,
  product_name      text NOT NULL,
  brand_name        text NOT NULL,
  category_key      int NOT NULL REFERENCES dw.dim_category (category_key),
  seller_id         bigint NOT NULL,
  list_price        numeric(18,2) NOT NULL,
  original_price    numeric(18,2) NOT NULL,
  discount_rate     numeric(6,4) NOT NULL,
  unit_cost_est     numeric(18,2),
  is_active         boolean NOT NULL,
  scd1_hash         text NOT NULL,
  scd2_hash         text NOT NULL,
  valid_from        date NOT NULL,
  valid_to          date NOT NULL DEFAULT '9999-12-31',
  is_current        boolean NOT NULL DEFAULT true,
  batch_id          bigint,
  CHECK (valid_from < valid_to),
  UNIQUE (product_id, valid_from)
);

CREATE TABLE dw.dim_seller (
seller_key      serial PRIMARY KEY,
  seller_id       bigint NOT NULL,
  shop_name       text NOT NULL,
  seller_name     text NOT NULL,
  email_domain    text,
  phone_masked    text,
  province_code   text NOT NULL,
  province_name   text NOT NULL,
  region          text NOT NULL,
  tier            text NOT NULL,
  status          text NOT NULL,
  scd1_hash       text NOT NULL,
  scd2_hash       text NOT NULL,
  valid_from      date NOT NULL,
  valid_to        date NOT NULL DEFAULT '9999-12-31',
  is_current      boolean NOT NULL DEFAULT true,
  batch_id        bigint,
  CHECK (valid_from < valid_to),
  UNIQUE (seller_id, valid_from)
);

CREATE TABLE dw.dim_seller_tier_t3 (
seller_id        bigint PRIMARY KEY,
  current_tier     text NOT NULL,
  previous_tier    text,
  tier_changed_on  date,
  batch_id         bigint
);

CREATE TABLE dw.dim_customer (
customer_key      serial PRIMARY KEY,
  customer_id       bigint NOT NULL,
  full_name         text NOT NULL,
  phone_masked      text,
  email_domain      text,
  gender            char(1) NOT NULL CHECK (gender IN ('M','F','U')),
  birth_year        smallint,
  age_band          text NOT NULL,
  province_code     text NOT NULL,
  province_name     text NOT NULL,
  region            text NOT NULL,
  registration_date date,
  scd1_hash         text NOT NULL,
  scd2_hash         text NOT NULL,
  valid_from        date NOT NULL,
  valid_to          date NOT NULL DEFAULT '9999-12-31',
  is_current        boolean NOT NULL DEFAULT true,
  batch_id          bigint,
  CHECK (valid_from < valid_to),
  UNIQUE (customer_id, valid_from)
);

CREATE TABLE dw.dim_customer_profile (
customer_profile_key smallint PRIMARY KEY,
  membership_tier      text NOT NULL,
  spend_band_12m       text NOT NULL,
  frequency_band       text NOT NULL,
  UNIQUE (membership_tier, spend_band_12m, frequency_band)
);

CREATE TABLE dw.dim_channel (
channel_key     int PRIMARY KEY,
  channel_id      int UNIQUE,
  channel_name    text NOT NULL,
  channel_type    text NOT NULL,
  marketing_code  text NOT NULL
);

CREATE TABLE dw.dim_payment_method (
payment_method_key int PRIMARY KEY,
  payment_method_id  int UNIQUE,
  method_name        text NOT NULL,
  method_group       text NOT NULL
);

CREATE TABLE dw.dim_warehouse (
warehouse_key   int PRIMARY KEY,
  warehouse_id    int UNIQUE,
  warehouse_code  text NOT NULL,
  warehouse_name  text NOT NULL,
  province_code   text NOT NULL,
  province_name   text NOT NULL,
  region          text NOT NULL
);

CREATE TABLE dw.dim_campaign (
campaign_key        int PRIMARY KEY,
  campaign_id         int UNIQUE,
  campaign_code       text NOT NULL,
  campaign_name       text NOT NULL,
  campaign_type       text NOT NULL,
  target_channel_key  int NOT NULL REFERENCES dw.dim_channel (channel_key),
  budget_amount       numeric(18,2),
  start_date          date,
  end_date            date
);

CREATE TABLE dw.dim_promotion (
promotion_key     int PRIMARY KEY,
  promotion_id      bigint UNIQUE,
  promo_code        text NOT NULL,
  promo_name        text NOT NULL,
  promo_type        text NOT NULL,
  funded_by         text NOT NULL,
  apply_level       text NOT NULL,
  discount_type     text,
  discount_value    numeric(18,2),
  min_order_value   numeric(18,2),
  seller_id         bigint,
  start_ts          timestamp,
  end_ts            timestamp
);

CREATE TABLE dw.dim_promotion_group (
promotion_group_key int PRIMARY KEY,
  group_signature     text NOT NULL UNIQUE,   
  promotion_count     smallint NOT NULL
);

CREATE TABLE dw.bridge_promotion_group (
promotion_group_key int NOT NULL REFERENCES dw.dim_promotion_group (promotion_group_key),
  promotion_key       int NOT NULL REFERENCES dw.dim_promotion (promotion_key),
  weighting_factor    numeric(9,6) NOT NULL CHECK (weighting_factor > 0 AND weighting_factor <= 1),
  PRIMARY KEY (promotion_group_key, promotion_key)
);

CREATE TABLE dw.fact_order_item (
source_system        text          NOT NULL DEFAULT 'mock_oltp',
  order_id             bigint        NOT NULL,
  line_number          int           NOT NULL,
  order_code           text          NOT NULL,                    
  date_key             int           NOT NULL REFERENCES dw.dim_date (date_key),   
  order_date_key       int           NOT NULL REFERENCES dw.dim_date (date_key),   
  product_key          int           NOT NULL REFERENCES dw.dim_product (product_key),
  category_key         int           NOT NULL REFERENCES dw.dim_category (category_key),
  seller_key           int           NOT NULL REFERENCES dw.dim_seller (seller_key),
  customer_key         int           NOT NULL REFERENCES dw.dim_customer (customer_key),
  customer_profile_key smallint      NOT NULL REFERENCES dw.dim_customer_profile (customer_profile_key),
  channel_key          int           NOT NULL REFERENCES dw.dim_channel (channel_key),
  payment_method_key   int           NOT NULL REFERENCES dw.dim_payment_method (payment_method_key),
  campaign_key         int           NOT NULL REFERENCES dw.dim_campaign (campaign_key),
  promotion_group_key  int           NOT NULL REFERENCES dw.dim_promotion_group (promotion_group_key),
  quantity             int           NOT NULL CHECK (quantity > 0),
  list_price           numeric(18,2) NOT NULL,
  unit_price           numeric(18,2) NOT NULL CHECK (unit_price >= 0),
  list_amount          numeric(18,2) NOT NULL,
  gross_amount         numeric(18,2) NOT NULL,
  list_discount_amount numeric(18,2) NOT NULL,
  discount_amount      numeric(18,2) NOT NULL CHECK (discount_amount >= 0),
  net_revenue          numeric(18,2) NOT NULL CHECK (net_revenue >= 0),
  commission_rate      numeric(6,4)  NOT NULL CHECK (commission_rate BETWEEN 0 AND 1),
  commission_amount    numeric(18,2) NOT NULL,
  seller_net_amount    numeric(18,2) NOT NULL,
  cost_amount_est      numeric(18,2),
  gross_margin_est     numeric(18,2),
  is_returned          boolean       NOT NULL DEFAULT false,
  line_count           smallint      NOT NULL DEFAULT 1,
  batch_id             bigint        NOT NULL,
  updated_batch_id     bigint,
  CHECK (gross_amount = quantity * unit_price),
  CHECK (net_revenue = gross_amount - discount_amount),
  PRIMARY KEY (date_key, source_system, order_id, line_number)
);

CREATE TABLE dw.fact_inventory_snapshot (
date_key             int           NOT NULL REFERENCES dw.dim_date (date_key),
  product_key          int           NOT NULL REFERENCES dw.dim_product (product_key),
  warehouse_key        int           NOT NULL REFERENCES dw.dim_warehouse (warehouse_key),
  category_key         int           NOT NULL REFERENCES dw.dim_category (category_key),
  quantity_on_hand     int           NOT NULL CHECK (quantity_on_hand >= 0),
  quantity_reserved    int           NOT NULL CHECK (quantity_reserved >= 0),
  quantity_available   int           NOT NULL CHECK (quantity_available >= 0),
  qty_imported         int           NOT NULL DEFAULT 0 CHECK (qty_imported >= 0),
  qty_sold             int           NOT NULL DEFAULT 0 CHECK (qty_sold >= 0),
  qty_returned         int           NOT NULL DEFAULT 0 CHECK (qty_returned >= 0),
  qty_adjusted         int           NOT NULL DEFAULT 0,
  stockout_flag        smallint      NOT NULL CHECK (stockout_flag IN (0,1)),
  inventory_value_est  numeric(18,2),
  batch_id             bigint        NOT NULL,
  CHECK (quantity_reserved <= quantity_on_hand),
  CHECK (quantity_available = quantity_on_hand - quantity_reserved),
  PRIMARY KEY (date_key, product_key, warehouse_key)
);

CREATE TABLE dw.fact_ad_spend (
month_key    int           NOT NULL REFERENCES dw.dim_month (month_key),
  campaign_key int           NOT NULL REFERENCES dw.dim_campaign (campaign_key),
  channel_key  int           NOT NULL REFERENCES dw.dim_channel (channel_key),
  cost_amount  numeric(18,2) NOT NULL CHECK (cost_amount >= 0),
  impressions  bigint        NOT NULL CHECK (impressions >= 0),
  clicks       bigint        NOT NULL CHECK (clicks >= 0),
  active_days  smallint      NOT NULL CHECK (active_days BETWEEN 1 AND 31),
  batch_id     bigint        NOT NULL,
  CHECK (impressions >= clicks),
  PRIMARY KEY (month_key, campaign_key, channel_key)
);
