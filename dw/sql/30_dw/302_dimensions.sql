-- PLAN 4.2 — Dimension (cấu trúc). Dữ liệu được nạp bởi ETL (bước 08); ở đây chỉ tạo bảng
-- và hai thành viên đặc biệt: -1 = không áp dụng, 0 = chưa xác định (đề xuất mục 5).
-- Cột kỹ thuật SCD2: valid_from (bao gồm) / valid_to (không bao gồm) / is_current.

-- ===================== Cây danh mục =====================
CREATE TABLE IF NOT EXISTS dw.dim_category (
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
CREATE TABLE IF NOT EXISTS dw.bridge_category_hierarchy (
  ancestor_key   int NOT NULL REFERENCES dw.dim_category (category_key),
  descendant_key int NOT NULL REFERENCES dw.dim_category (category_key),
  depth          smallint NOT NULL CHECK (depth >= 0),
  PRIMARY KEY (ancestor_key, descendant_key)
);
CREATE INDEX IF NOT EXISTS ix_bch_desc ON dw.bridge_category_hierarchy (descendant_key);

-- ===================== Sản phẩm (SCD1 + SCD2) =====================
CREATE TABLE IF NOT EXISTS dw.dim_product (
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
CREATE UNIQUE INDEX IF NOT EXISTS ux_dim_product_current ON dw.dim_product (product_id) WHERE is_current;
CREATE INDEX IF NOT EXISTS ix_dim_product_lookup ON dw.dim_product (product_id, valid_from, valid_to);

-- ===================== Người bán (SCD1 + SCD2) + SCD3 riêng =====================
CREATE TABLE IF NOT EXISTS dw.dim_seller (
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
CREATE UNIQUE INDEX IF NOT EXISTS ux_dim_seller_current ON dw.dim_seller (seller_id) WHERE is_current;
CREATE INDEX IF NOT EXISTS ix_dim_seller_lookup ON dw.dim_seller (seller_id, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS dw.dim_seller_tier_t3 (
  seller_id        bigint PRIMARY KEY,
  current_tier     text NOT NULL,
  previous_tier    text,
  tier_changed_on  date,
  batch_id         bigint
);

-- ===================== Khách hàng (SCD1 + SCD2) + mini-dimension =====================
CREATE TABLE IF NOT EXISTS dw.dim_customer (
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
CREATE UNIQUE INDEX IF NOT EXISTS ux_dim_customer_current ON dw.dim_customer (customer_id) WHERE is_current;
CREATE INDEX IF NOT EXISTS ix_dim_customer_lookup ON dw.dim_customer (customer_id, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS dw.dim_customer_profile (
  customer_profile_key smallint PRIMARY KEY,
  membership_tier      text NOT NULL,
  spend_band_12m       text NOT NULL,
  frequency_band       text NOT NULL,
  UNIQUE (membership_tier, spend_band_12m, frequency_band)
);

-- ===================== Dimension nhỏ (SCD1) =====================
CREATE TABLE IF NOT EXISTS dw.dim_channel (
  channel_key     int PRIMARY KEY,
  channel_id      int UNIQUE,
  channel_name    text NOT NULL,
  channel_type    text NOT NULL,
  marketing_code  text NOT NULL
);
CREATE TABLE IF NOT EXISTS dw.dim_payment_method (
  payment_method_key int PRIMARY KEY,
  payment_method_id  int UNIQUE,
  method_name        text NOT NULL,
  method_group       text NOT NULL
);
CREATE TABLE IF NOT EXISTS dw.dim_warehouse (
  warehouse_key   int PRIMARY KEY,
  warehouse_id    int UNIQUE,
  warehouse_code  text NOT NULL,
  warehouse_name  text NOT NULL,
  province_code   text NOT NULL,
  province_name   text NOT NULL,
  region          text NOT NULL
);
CREATE TABLE IF NOT EXISTS dw.dim_campaign (
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
CREATE TABLE IF NOT EXISTS dw.dim_promotion (
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
-- Nhóm voucher của một dòng hàng (đề xuất Bảng 9: nhóm = toàn bộ voucher trên 1 order_item)
CREATE TABLE IF NOT EXISTS dw.dim_promotion_group (
  promotion_group_key int PRIMARY KEY,
  group_signature     text NOT NULL UNIQUE,   -- 'promotion_id:weight,…' sắp theo promotion_id
  promotion_count     smallint NOT NULL
);
CREATE TABLE IF NOT EXISTS dw.bridge_promotion_group (
  promotion_group_key int NOT NULL REFERENCES dw.dim_promotion_group (promotion_group_key),
  promotion_key       int NOT NULL REFERENCES dw.dim_promotion (promotion_key),
  weighting_factor    numeric(9,6) NOT NULL CHECK (weighting_factor > 0 AND weighting_factor <= 1),
  PRIMARY KEY (promotion_group_key, promotion_key)
);

-- ===================== Thành viên đặc biệt -1 / 0 =====================
INSERT INTO dw.dim_category VALUES
  (-1,-1,'Không áp dụng',true,NULL,0,true,NULL,'-1','Không áp dụng',NULL),
  ( 0, 0,'Chưa xác định',true,NULL,0,true,NULL,'0','Chưa xác định',NULL)
ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_product (product_key, product_id, sku, product_name, brand_name, category_key, seller_id,
  list_price, original_price, discount_rate, is_active, scd1_hash, scd2_hash, valid_from) VALUES
  (-1,-1,'N/A','Không áp dụng','N/A',-1,-1,0,0,0,false,'-','-','1900-01-01'),
  ( 0, 0,'UNKNOWN','Chưa xác định','N/A', 0, 0,0,0,0,false,'-','-','1900-01-01')
ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_seller (seller_key, seller_id, shop_name, seller_name, province_code, province_name, region,
  tier, status, scd1_hash, scd2_hash, valid_from) VALUES
  (-1,-1,'Không áp dụng','N/A','NA','Không áp dụng','NA','NA','NA','-','-','1900-01-01'),
  ( 0, 0,'Chưa xác định','N/A','UNK','Chưa xác định','UNK','UNK','UNK','-','-','1900-01-01')
ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_customer (customer_key, customer_id, full_name, gender, age_band, province_code, province_name,
  region, scd1_hash, scd2_hash, valid_from) VALUES
  (-1,-1,'Khách vãng lai','U','Không rõ','NA','Không áp dụng','NA','-','-','1900-01-01'),
  ( 0, 0,'Chưa xác định','U','Không rõ','UNK','Chưa xác định','UNK','-','-','1900-01-01')
ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_channel VALUES (-1,NULL,'Không áp dụng','NA','NA'), (0,NULL,'Chưa xác định','UNK','UNK') ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_payment_method VALUES (-1,NULL,'Không áp dụng','NA'), (0,NULL,'Chưa xác định','UNK') ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_warehouse VALUES (-1,NULL,'NA','Không áp dụng','NA','Không áp dụng','NA'), (0,NULL,'UNK','Chưa xác định','UNK','Chưa xác định','UNK') ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_campaign (campaign_key, campaign_id, campaign_code, campaign_name, campaign_type, target_channel_key) VALUES
  (-1,NULL,'NA','Không có chiến dịch','NA',-1), (0,NULL,'UNK','Chưa xác định','UNK',0) ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_promotion (promotion_key, promotion_id, promo_code, promo_name, promo_type, funded_by, apply_level) VALUES
  (-1,NULL,'NA','Không dùng voucher','NA','NA','NA'), (0,NULL,'UNK','Chưa xác định','UNK','UNK','UNK') ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_promotion_group VALUES (-1,'NONE',0), (0,'UNKNOWN',0) ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_customer_profile VALUES (-1,'NA','NA','NA'), (0,'UNK','UNK','UNK') ON CONFLICT DO NOTHING;

-- Mini-dimension: sinh trước mọi tổ hợp bucket (5 hạng × 5 nhóm chi tiêu × 5 nhóm tần suất = 125)
INSERT INTO dw.dim_customer_profile
SELECT (row_number() OVER (ORDER BY t.o, s.o, f.o))::smallint, t.v, s.v, f.v
FROM (VALUES (1,'Member'),(2,'Silver'),(3,'Gold'),(4,'Platinum'),(5,'Không rõ')) t(o,v)
CROSS JOIN (VALUES (1,'Chưa mua'),(2,'< 1 triệu'),(3,'1–5 triệu'),(4,'5–20 triệu'),(5,'> 20 triệu')) s(o,v)
CROSS JOIN (VALUES (1,'0 đơn'),(2,'1 đơn'),(3,'2–3 đơn'),(4,'4–9 đơn'),(5,'≥ 10 đơn')) f(o,v)
ON CONFLICT DO NOTHING;

-- Sequence của bảng serial bắt đầu từ 1 (không đụng -1/0)
SELECT setval(pg_get_serial_sequence('dw.dim_product','product_key'),  greatest(1,(SELECT max(product_key)  FROM dw.dim_product)),  (SELECT max(product_key)  FROM dw.dim_product)  > 0);
SELECT setval(pg_get_serial_sequence('dw.dim_seller','seller_key'),    greatest(1,(SELECT max(seller_key)   FROM dw.dim_seller)),   (SELECT max(seller_key)   FROM dw.dim_seller)   > 0);
SELECT setval(pg_get_serial_sequence('dw.dim_customer','customer_key'),greatest(1,(SELECT max(customer_key) FROM dw.dim_customer)), (SELECT max(customer_key) FROM dw.dim_customer) > 0);
