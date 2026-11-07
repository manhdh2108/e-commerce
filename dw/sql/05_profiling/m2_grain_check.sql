-- PLAN 3 / Milestone 2 — Kiểm tra grain atomic của 3 fact trên nguồn thật và đo kích thước cho tháp phân tầng.
--   psql -U dw_reader -d mock_oltp -f m2_grain_check.sql
\pset footer off

\echo '=== G1. Fact_Order_Item — khóa grain (order_id, line_number) duy nhất?'
select count(*) as dong, count(distinct (order_id, line_number)) as khoa_duy_nhat,
       count(*) - count(distinct (order_id, line_number)) as trung from order_items;

\echo '=== G2. Dòng nào thuộc fact (đơn Completed, item Fulfilled/Returned)'
select o.order_status, oi.item_status, count(*) as dong, count(o.completed_at) as co_completed_at
from order_items oi join orders o on o.id = oi.order_id group by 1, 2 order by 1, 2;

\echo '=== G3. Mỗi đơn có 1 seller, 1 kênh? (để seller/channel là thuộc tính cấp dòng hợp lệ)'
select count(*) as don, count(seller_id) as co_seller, count(channel_id) as co_kenh from orders;
select count(*) as checkout_tach_nhieu_don from (select checkout_id from orders where checkout_id is not null group by 1 having count(*) > 1) x;

\echo '=== G4. Số dòng mỗi đơn và mỗi dòng (đơn nhiều dòng?)'
select so_dong, count(*) as so_don from (select order_id, count(*) so_dong from order_items group by 1) x group by 1 order by 1;

\echo '=== G5. Độ trễ đặt → hoàn tất (late-arriving theo Date_Key = ngày completed)'
select (completed_at::date - created_at::date) as tre_ngay, count(*) from orders where completed_at is not null group by 1 order by 1;

\echo '=== G6. Fact_Inventory_Snapshot — khóa (balance_date, warehouse_id, sku) duy nhất? Dày hay thưa?'
select count(*) as dong, count(distinct (balance_date, warehouse_id, sku)) as khoa_duy_nhat,
       count(distinct balance_date) as so_ngay, count(distinct (warehouse_id, sku)) as cap_kho_sku,
       (select count(*) from products) * (select count(*) from warehouses) as neu_day_du
from inventory_daily_balance;
select balance_date, count(*) from inventory_daily_balance group by 1 order by 1 desc limit 3;

\echo '=== G7. Fact_Ad_Spend — nguồn theo ngày: khóa (campaign, channel, log_date) duy nhất?'
select count(*) as dong, count(distinct (campaign_id, channel_code, log_date)) as khoa_duy_nhat,
       count(distinct (campaign_id, channel_code, date_trunc('month', log_date))) as dong_neu_gop_thang from ad_spend_logs;

\echo '=== G8. Kích thước tầng tổng hợp (ước lượng số nhóm)'
select 'ngay x san_pham x kenh (Fact 1)' as tang, count(*) from (select distinct o.completed_at::date, oi.product_id, o.channel_id from order_items oi join orders o on o.id = oi.order_id where o.order_status='Completed') x
union all select 'ngay x danh_muc_la x kenh', count(*) from (select distinct o.completed_at::date, p.category_id, o.channel_id from order_items oi join orders o on o.id = oi.order_id join products p on p.id = oi.product_id where o.order_status='Completed') x
union all select 'ngay x seller', count(*) from (select distinct o.completed_at::date, o.seller_id from orders o where o.order_status='Completed') x
union all select 'ton kho: ngay x danh_muc_la x kho', count(*) from (select distinct b.balance_date, p.category_id, b.warehouse_id from inventory_daily_balance b join products p on p.sku = b.sku) x;
