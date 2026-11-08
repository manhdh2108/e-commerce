-- PLAN 4.3 / 4.8 — Ba bảng fact (galaxy schema). Grain theo M2_GRAIN_PHAN_TANG.md.
-- Fact_Order_Item và Fact_Inventory_Snapshot: partition RANGE theo date_key (tháng) — dùng cho BM02.

-- ===================== Fact_Order_Item (transaction) =====================
CREATE TABLE IF NOT EXISTS dw.fact_order_item (
  source_system        text          NOT NULL DEFAULT 'mock_oltp',
  order_id             bigint        NOT NULL,
  line_number          int           NOT NULL,
  order_code           text          NOT NULL,                    -- degenerate dimension
  date_key             int           NOT NULL REFERENCES dw.dim_date (date_key),   -- ngày hoàn tất
  order_date_key       int           NOT NULL REFERENCES dw.dim_date (date_key),   -- ngày đặt (role-playing)
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
  PRIMARY KEY (date_key, source_system, order_id, line_number)     -- khóa nghiệp vụ + khóa partition
) PARTITION BY RANGE (date_key);

-- ===================== Fact_Inventory_Snapshot (periodic snapshot, thưa) =====================
CREATE TABLE IF NOT EXISTS dw.fact_inventory_snapshot (
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
) PARTITION BY RANGE (date_key);

-- ===================== Fact_Ad_Spend (periodic, tháng) =====================
CREATE TABLE IF NOT EXISTS dw.fact_ad_spend (
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

-- ===================== Partition theo tháng (2025-01 .. 2027-12) + default =====================
DO $$
DECLARE m date; tbl text;
BEGIN
  FOREACH tbl IN ARRAY ARRAY['fact_order_item','fact_inventory_snapshot'] LOOP
    FOR m IN SELECT generate_series('2025-01-01'::date, '2027-12-01'::date, interval '1 month')::date LOOP
      EXECUTE format('CREATE TABLE IF NOT EXISTS dw.%I PARTITION OF dw.%I FOR VALUES FROM (%s) TO (%s)',
                     tbl || '_' || to_char(m, 'YYYYMM'), tbl,
                     to_char(m, 'YYYYMMDD'), to_char((m + interval '1 month')::date, 'YYYYMMDD'));
    END LOOP;
    EXECUTE format('CREATE TABLE IF NOT EXISTS dw.%I PARTITION OF dw.%I DEFAULT', tbl || '_default', tbl);
  END LOOP;
END $$;

-- Bổ sung sau khi phát hiện movement_type 'Return' ở nguồn (bước 07)
ALTER TABLE dw.fact_inventory_snapshot ADD COLUMN IF NOT EXISTS qty_returned int NOT NULL DEFAULT 0 CHECK (qty_returned >= 0);

-- Index FK phục vụ join/drill (BM03 sẽ thử thêm index ghép riêng ở schema bench)
CREATE INDEX IF NOT EXISTS ix_foi_product  ON dw.fact_order_item (product_key);
CREATE INDEX IF NOT EXISTS ix_foi_seller   ON dw.fact_order_item (seller_key);
CREATE INDEX IF NOT EXISTS ix_foi_customer ON dw.fact_order_item (customer_key);
CREATE INDEX IF NOT EXISTS ix_foi_order    ON dw.fact_order_item (order_id);
CREATE INDEX IF NOT EXISTS ix_fis_product  ON dw.fact_inventory_snapshot (product_key);
