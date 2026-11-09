-- Kiểm thử measure (PLAN 4.8.7) — PHÍA NGUỒN: tính lại measure trực tiếp từ OLTP gốc (mock_oltp),
-- độc lập với raw/stg/ETL. Chạy cùng measure_dw.sql rồi so từng dòng kết quả (dw/tests/run_measure_tests.sh).
-- Tham số: :until = ngày cuối cửa sổ đã nạp (watermark_to của batch SUCCESS mới nhất).
\pset format unaligned
\pset tuples_only on
\set until_ts '''' :until ' 23:59:59.999999' ''''

-- Fact_Order_Item: grain = dòng Fulfilled/Returned của đơn Completed, hoàn tất <= :until
CREATE TEMP TABLE l AS
SELECT o.id AS order_id, oi.line_number, o.order_code,
       to_char(o.completed_at, 'YYYYMMDD')::int AS date_key, to_char(o.created_at, 'YYYYMMDD')::int AS order_date_key,
       oi.product_id, o.seller_id, o.customer_id, o.channel_id, o.campaign_id,
       oi.quantity, oi.list_price::numeric(18,2) AS list_price, oi.unit_price::numeric(18,2) AS unit_price,
       (oi.quantity * oi.list_price)::numeric(18,2) AS list_amount, (oi.quantity * oi.unit_price)::numeric(18,2) AS gross_amount,
       oi.discount_amount::numeric(18,2) AS discount_amount, oi.net_amount::numeric(18,2) AS net_revenue,
       oi.commission_rate::numeric(6,4) AS commission_rate,
       round(oi.net_amount * oi.commission_rate, 2)::numeric(18,2) AS commission_amount,
       (oi.item_status = 'Returned') AS is_returned
FROM order_items oi JOIN orders o ON o.id = oi.order_id
WHERE o.order_status = 'Completed' AND o.completed_at <= :until_ts::timestamp
  AND oi.item_status IN ('Fulfilled', 'Returned');
SELECT 'FOI rows', count(*) FROM l;
SELECT 'FOI orders', count(DISTINCT order_id) FROM l;
SELECT 'FOI md5 (keys + 20 cot / dong)', md5(string_agg(concat_ws('|', order_id, line_number, order_code, date_key, order_date_key,
       product_id, seller_id, customer_id, channel_id, campaign_id, quantity, list_price, unit_price, list_amount, gross_amount,
       discount_amount, net_revenue, commission_rate, commission_amount, is_returned), ',' ORDER BY order_id, line_number)) FROM l;
SELECT 'FOI sum qty|list|gross|disc|net|comm', sum(quantity), sum(list_amount), sum(gross_amount), sum(discount_amount),
       sum(net_revenue), sum(commission_amount) FROM l;
SELECT 'FOI net theo ngay', date_key, sum(net_revenue) FROM l GROUP BY 2 ORDER BY 2;
-- Giảm giá theo voucher: tổng applied_discount_amount nguồn
SELECT 'PROMO disc by promotion_id', p.promotion_id, sum(p.applied_discount_amount)::numeric(18,2)
FROM order_item_promotions p JOIN order_items oi ON oi.id = p.order_item_id
JOIN l ON l.order_id = oi.order_id AND l.line_number = oi.line_number GROUP BY 2 ORDER BY 2;

-- Fact_Inventory_Snapshot: inventory_daily_balance + biến động trong ngày theo loại
CREATE TEMP TABLE inv AS
WITH mv AS (
  SELECT movement_date::date AS d, warehouse_id, sku,
         coalesce(sum(quantity_change) FILTER (WHERE movement_type = 'Import'), 0) AS imp,
         coalesce(-sum(quantity_change) FILTER (WHERE movement_type = 'Sale'), 0) AS sold,
         coalesce(sum(quantity_change) FILTER (WHERE movement_type = 'Return'), 0) AS ret,
         coalesce(sum(quantity_change) FILTER (WHERE movement_type = 'Adjustment'), 0) AS adj
  FROM inventory_movements WHERE movement_date <= :until_ts::timestamp GROUP BY 1, 2, 3)
SELECT b.balance_date, b.warehouse_id, b.sku, b.quantity_on_hand, b.quantity_reserved,
       coalesce(mv.imp, 0) AS imp, coalesce(mv.sold, 0) AS sold, coalesce(mv.ret, 0) AS ret, coalesce(mv.adj, 0) AS adj
FROM inventory_daily_balance b
LEFT JOIN mv ON mv.d = b.balance_date AND mv.warehouse_id = b.warehouse_id AND mv.sku = b.sku
WHERE b.balance_date <= :'until';
SELECT 'INV rows', count(*) FROM inv;
SELECT 'INV md5 (sku,kho,ngay + 6 measure)', md5(string_agg(concat_ws('|', balance_date, warehouse_id, sku, quantity_on_hand,
       quantity_reserved, imp, sold, ret, adj), ',' ORDER BY balance_date, warehouse_id, sku)) FROM inv;
SELECT 'INV sum onhand|reserved|imp|sold|ret|adj', sum(quantity_on_hand), sum(quantity_reserved), sum(imp), sum(sold), sum(ret), sum(adj) FROM inv;
-- Biến động không có dòng tồn tương ứng (nếu > 0 thì qty_* của fact bị thiếu)
SELECT 'INV movement khong co dong ton', count(*) FROM (
  SELECT movement_date::date AS d, warehouse_id, sku FROM inventory_movements WHERE movement_date <= :until_ts::timestamp GROUP BY 1, 2, 3) m
WHERE NOT EXISTS (SELECT 1 FROM inventory_daily_balance b WHERE b.balance_date = m.d AND b.warehouse_id = m.warehouse_id AND b.sku = m.sku);

-- Fact_Ad_Spend: gộp tháng × chiến dịch × kênh
SELECT 'AD month|campaign|channel|cost|imp|clicks|days', to_char(log_date, 'YYYYMM')::int, campaign_id, channel_code,
       sum(cost_amount)::numeric(18,2), sum(impressions), sum(clicks), count(DISTINCT log_date)
FROM ad_spend_logs WHERE log_date <= :'until' GROUP BY 2, 3, 4 ORDER BY 2, 3, 4;
