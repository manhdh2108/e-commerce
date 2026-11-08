-- PLAN 2 / Milestone 1 — Profiling nguồn OLTP làm bằng chứng cho bản đồ nguồn và quy tắc tích hợp.
-- Chạy bằng role CHỈ ĐỌC:  psql -U dw_reader -d mock_oltp -f m1_source_profile.sql
\pset footer off
\pset null '∅'

\echo '=== P0. Mốc dữ liệu (ngày mô phỏng có dữ liệu)'
select min(created_at)::date as tu_ngay, max(created_at)::date as den_ngay, count(*) as so_don from orders;

\echo '=== P1. Số dòng theo hệ thống nguồn (33 bảng)'
with t(he_thong, bang) as (values
 ('1 Catalog & Seller','categories'),('1 Catalog & Seller','products'),('1 Catalog & Seller','sellers'),('1 Catalog & Seller','seller_commission_rates'),
 ('2 Đơn hàng','customers'),('2 Đơn hàng','customer_addresses'),('2 Đơn hàng','channels'),('2 Đơn hàng','payment_methods'),('2 Đơn hàng','checkouts'),('2 Đơn hàng','checkout_lines'),('2 Đơn hàng','orders'),('2 Đơn hàng','order_items'),('2 Đơn hàng','payments'),('2 Đơn hàng','returns'),('2 Đơn hàng','refunds'),('2 Đơn hàng','product_reviews'),
 ('3 Kho & Vận chuyển','warehouses'),('3 Kho & Vận chuyển','inventory_levels'),('3 Kho & Vận chuyển','inventory_movements'),('3 Kho & Vận chuyển','inventory_daily_balance'),('3 Kho & Vận chuyển','carriers'),('3 Kho & Vận chuyển','shipments'),('3 Kho & Vận chuyển','delivery_attempts'),
 ('4 Marketing','marketing_campaigns'),('4 Marketing','ad_spend_logs'),('4 Marketing','promotions'),('4 Marketing','order_item_promotions'),('4 Marketing','promotion_usages'),
 ('5 Clickstream','sessions'),('5 Clickstream','page_events'),('5 Clickstream','cart_items'),
 ('6 Tài chính','seller_payouts'),('6 Tài chính','seller_payout_items'))
select he_thong, bang,
       (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I', bang), false, true, '')))[1]::text::bigint as so_dong
from t order by he_thong, bang;

\echo '=== P2. Cột thời gian dùng cho trích xuất incremental (bảng nào KHÔNG có cột thời gian)'
select c.table_name,
       string_agg(c.column_name, ', ' order by c.ordinal_position) filter (where c.data_type like 'timestamp%' or c.data_type = 'date') as cot_thoi_gian,
       bool_or(c.column_name = 'updated_at') as co_updated_at
from information_schema.columns c where c.table_schema = 'public'
group by c.table_name order by (string_agg(c.column_name, ',') filter (where c.data_type like 'timestamp%' or c.data_type = 'date')) nulls first, c.table_name;

\echo '=== P3. Kiểu dữ liệu thời gian (có/không múi giờ) — IR-07'
select data_type, count(*) from information_schema.columns
where table_schema = 'public' and (data_type like 'timestamp%' or data_type = 'date') group by 1;

\echo '=== IR-01. Kho dùng sku, đơn hàng dùng product_id'
select 'inventory_daily_balance' as bang, count(distinct b.sku) as so_sku, count(distinct b.sku) filter (where p.id is null) as sku_khong_map
from inventory_daily_balance b left join products p on p.sku = b.sku
union all
select 'inventory_movements', count(distinct m.sku), count(distinct m.sku) filter (where p.id is null)
from inventory_movements m left join products p on p.sku = m.sku
union all
select 'products (sku trùng?)', count(*), count(*) - count(distinct sku) from products;

\echo '=== IR-02. shipments nối đơn bằng order_code'
select count(*) as so_van_don, count(o.id) as map_duoc_order_id, count(*) - count(o.id) as khong_map,
       count(*) - count(distinct s.order_code) as van_don_trung_ma_don
from shipments s left join orders o on o.order_code = s.order_code;

\echo '=== IR-03. Mã kênh: marketing vs bảng channels'
select 'channels.channel_name' as nguon, channel_name as gia_tri, count(*) from channels group by 2
union all select 'marketing_campaigns.target_channel_code', target_channel_code, count(*) from marketing_campaigns group by 2
union all select 'ad_spend_logs.channel_code', channel_code, count(*) from ad_spend_logs group by 2
order by 1, 2;

\echo '=== IR-04. Danh mục: products.category_id là gốc hay lá?'
select c.level, count(*) as so_san_pham from products p join categories c on c.id = p.category_id group by 1;
select level, count(*) as so_danh_muc, count(parent_id) as co_cha from categories group by 1 order by 1;

\echo '=== IR-05. Khách vãng lai (customer_id NULL)'
select count(*) as so_don, count(*) filter (where customer_id is null) as don_khach_vang_lai,
       round(100.0 * count(*) filter (where customer_id is null) / count(*), 1) as phan_tram from orders;
select count(*) filter (where customer_id is null) as phien_khach_vang_lai, count(*) as tong_phien from sessions;

\echo '=== IR-06. Tiền: kiểu nguồn và phần lẻ'
select table_name, column_name, data_type, numeric_precision, numeric_scale from information_schema.columns
where table_schema='public' and table_name in ('order_items','orders','ad_spend_logs') and data_type='numeric' order by 1,2;
select count(*) filter (where unit_price <> round(unit_price)) as unit_price_le,
       count(*) filter (where discount_amount <> round(discount_amount)) as discount_le,
       count(*) filter (where net_amount <> round(net_amount)) as net_le, count(*) as tong_dong from order_items;

\echo '=== IR-08. Tỉnh/thành: tập giá trị ở các bảng'
select 'customers' as bang, province, count(*) from customers group by 2
union all select 'sellers', province, count(*) from sellers group by 2
union all select 'warehouses', province, count(*) from warehouses group by 2
union all select 'customer_addresses', province, count(*) from customer_addresses group by 2
order by 1, 2;

\echo '=== IR-09. Giá trị thiếu ở thuộc tính khách'
select count(*) as tong, count(*) filter (where gender is null) as thieu_gioi_tinh,
       count(*) filter (where date_of_birth is null) as thieu_ngay_sinh, count(*) filter (where province is null) as thieu_tinh from customers;

\echo '=== IR-10. discount_rate của products: phần trăm hay tỷ lệ?'
select min(discount_rate), max(discount_rate), count(*) filter (where discount_rate > 1) as lon_hon_1 from products;

\echo '=== T1. Không có lịch sử trong OLTP (chỉ trạng thái hiện tại)'
select 'customers' as bang, count(*) filter (where updated_at > registration_date) as da_bi_ghi_de, count(*) from customers
union all select 'sellers', count(*) filter (where updated_at > created_at), count(*) from sellers
union all select 'products', count(*) filter (where updated_at > created_at), count(*) from products;

\echo '=== T2. Bảng con không có thời gian, phải trích theo khóa cha'
select 'order_items không có cột thời gian' as ghi_chu, count(*) from order_items;

\echo '=== K. Toàn vẹn khóa quan trọng (mồ côi)'
select 'order_items→orders' as quan_he, count(*) from order_items oi left join orders o on o.id = oi.order_id where o.id is null
union all select 'order_items→products', count(*) from order_items oi left join products p on p.id = oi.product_id where p.id is null
union all select 'orders→sellers', count(*) from orders o left join sellers s on s.id = o.seller_id where s.id is null
union all select 'orders→customers (không tính vãng lai)', count(*) from orders o left join customers c on c.id = o.customer_id where o.customer_id is not null and c.id is null
union all select 'payments→orders', count(*) from payments p left join orders o on o.id = p.order_id where o.id is null
union all select 'order_item_promotions→order_items', count(*) from order_item_promotions x left join order_items oi on oi.id = x.order_item_id where oi.id is null
union all select 'products→sellers', count(*) from products p left join sellers s on s.id = p.seller_id where s.id is null;
