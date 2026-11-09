-- Kiểm thử measure (PLAN 4.8.7) — PHÍA KHO: đọc ngược fact về mã nguồn (qua dimension) theo đúng thứ tự/định dạng
-- của measure_src.sql để so từng dòng.
\pset format unaligned
\pset tuples_only on

CREATE TEMP TABLE l AS
SELECT f.order_id, f.line_number, f.order_code, f.date_key, f.order_date_key, p.product_id, s.seller_id,
       CASE WHEN f.customer_key = -1 THEN NULL ELSE c.customer_id END AS customer_id, ch.channel_id,
       CASE WHEN f.campaign_key = -1 THEN NULL ELSE cm.campaign_id END AS campaign_id,
       f.quantity, f.list_price, f.unit_price, f.list_amount, f.gross_amount, f.discount_amount, f.net_revenue,
       f.commission_rate, f.commission_amount, f.is_returned
FROM dw.fact_order_item f
JOIN dw.dim_product p USING (product_key) JOIN dw.dim_seller s USING (seller_key) JOIN dw.dim_customer c USING (customer_key)
JOIN dw.dim_channel ch USING (channel_key) JOIN dw.dim_campaign cm USING (campaign_key);
SELECT 'FOI rows', count(*) FROM l;
SELECT 'FOI orders', count(DISTINCT order_id) FROM l;
SELECT 'FOI md5 (keys + 20 cot / dong)', md5(string_agg(concat_ws('|', order_id, line_number, order_code, date_key, order_date_key,
       product_id, seller_id, customer_id, channel_id, campaign_id, quantity, list_price, unit_price, list_amount, gross_amount,
       discount_amount, net_revenue, commission_rate, commission_amount, is_returned), ',' ORDER BY order_id, line_number)) FROM l;
SELECT 'FOI sum qty|list|gross|disc|net|comm', sum(quantity), sum(list_amount), sum(gross_amount), sum(discount_amount),
       sum(net_revenue), sum(commission_amount) FROM l;
SELECT 'FOI net theo ngay', date_key, sum(net_revenue) FROM l GROUP BY 2 ORDER BY 2;
-- Phân bổ qua bridge: discount_amount × weighting_factor
SELECT 'PROMO disc by promotion_id', dp.promotion_id, sum(f.discount_amount * b.weighting_factor)::numeric(18,2)
FROM dw.fact_order_item f JOIN dw.bridge_promotion_group b USING (promotion_group_key) JOIN dw.dim_promotion dp USING (promotion_key)
GROUP BY 2 ORDER BY 2;

CREATE TEMP TABLE inv AS
SELECT to_date(f.date_key::text, 'YYYYMMDD') AS balance_date, w.warehouse_id, p.sku, f.quantity_on_hand, f.quantity_reserved,
       f.qty_imported AS imp, f.qty_sold AS sold, f.qty_returned AS ret, f.qty_adjusted AS adj
FROM dw.fact_inventory_snapshot f JOIN dw.dim_product p USING (product_key) JOIN dw.dim_warehouse w USING (warehouse_key);
SELECT 'INV rows', count(*) FROM inv;
SELECT 'INV md5 (sku,kho,ngay + 6 measure)', md5(string_agg(concat_ws('|', balance_date, warehouse_id, sku, quantity_on_hand,
       quantity_reserved, imp, sold, ret, adj), ',' ORDER BY balance_date, warehouse_id, sku)) FROM inv;
SELECT 'INV sum onhand|reserved|imp|sold|ret|adj', sum(quantity_on_hand), sum(quantity_reserved), sum(imp), sum(sold), sum(ret), sum(adj) FROM inv;
SELECT 'INV movement khong co dong ton', 0;

SELECT 'AD month|campaign|channel|cost|imp|clicks|days', f.month_key, cm.campaign_id, ch.marketing_code, f.cost_amount,
       f.impressions, f.clicks, f.active_days
FROM dw.fact_ad_spend f JOIN dw.dim_campaign cm USING (campaign_key) JOIN dw.dim_channel ch USING (channel_key) ORDER BY 2, 3, 4;
