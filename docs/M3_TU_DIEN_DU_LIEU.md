# Milestone 3.3 — Từ điển dữ liệu (schema `dw`)

File này được **sinh tự động** từ `audit.data_dictionary` (catalog Postgres + `COMMENT ON` + `audit.column_lineage`) bằng `python dw/tools/export_dictionary.py`. Đừng sửa tay — sửa `dw/sql/50_audit/502_dictionary_metadata.sql` rồi chạy lại.

Cột *Cộng*: Additive / Semi-additive (không cộng theo thời gian) / Non-additive (tính lại từ tử và mẫu). Cột *SCD*: 1 ghi đè, 2 phiên bản lịch sử, 3 giữ giá trị trước, mini = mini-dimension.

Tổng: **19 bảng**, **199 cột**.

## Mục lục

- [`fact_ad_spend`](#fact_ad_spend) — Fact periodic chi phí quảng cáo. Grain: 1 chiến dịch × 1 kênh × 1 tháng (gộp từ stg.ad_spend_daily).
- [`fact_inventory_snapshot`](#fact_inventory_snapshot) — Fact periodic snapshot tồn kho. Grain: 1 sản phẩm × 1 kho × cuối 1 ngày (thưa: chỉ cặp kho–SKU đang kinh doanh
- [`fact_order_item`](#fact_order_item) — Fact giao dịch bán hàng. Grain: 1 dòng sản phẩm của 1 đơn Completed (item Fulfilled/Returned). Partition theo 
- [`dim_campaign`](#dim_campaign) — Chiến dịch marketing.
- [`dim_category`](#dim_category) — Cây danh mục một cha, sâu 2–4 cấp (77 nút), dựng từ primary_category_path cắt tại danh mục OLTP (IR-04).
- [`dim_channel`](#dim_channel) — Kênh bán / kênh đích quảng cáo (conformed giữa Fact_Order_Item và Fact_Ad_Spend).
- [`dim_customer`](#dim_customer) — Khách hàng đã đăng ký (SCD2: tỉnh; SCD1: tên, SĐT, email). -1 = khách vãng lai.
- [`dim_customer_profile`](#dim_customer_profile) — Mini-dimension hồ sơ khách: hạng thành viên × nhóm chi tiêu 12 tháng × nhóm tần suất (125 tổ hợp).
- [`dim_date`](#dim_date) — Chiều thời gian mức ngày (tĩnh). Grain: 1 ngày. Role-playing: ngày hoàn tất (date_key) và ngày đặt (order_date
- [`dim_month`](#dim_month) — Chiều tháng (conformed với dim_date qua month_key). Grain của Fact_Ad_Spend.
- [`dim_payment_method`](#dim_payment_method) — Phương thức thanh toán.
- [`dim_product`](#dim_product) — Sản phẩm (SCD2: giá niêm yết, danh mục, is_active; SCD1: tên, thương hiệu). Nguồn: crawler Tiki qua mock_oltp.
- [`dim_promotion`](#dim_promotion) — Voucher / khuyến mãi.
- [`dim_promotion_group`](#dim_promotion_group) — Nhóm voucher áp trên một dòng hàng (đề xuất Bảng 9).
- [`dim_seller`](#dim_seller) — Người bán (SCD2: hạng, tỉnh, trạng thái; SCD1: tên shop, liên hệ).
- [`dim_seller_tier_t3`](#dim_seller_tier_t3) — Minh họa SCD3: hạng seller hiện tại và hạng trước gần nhất (không giữ toàn bộ lịch sử).
- [`dim_warehouse`](#dim_warehouse) — Kho (fulfillment center do sàn vận hành).
- [`bridge_category_hierarchy`](#bridge_category_hierarchy) — Closure table của cây danh mục: mọi cặp (tổ tiên, con cháu), để cộng doanh thu theo cây con không cộng lặp.
- [`bridge_promotion_group`](#bridge_promotion_group) — Bridge nhóm voucher → voucher với weighting_factor; số tiền phân bổ = fact.discount_amount × weighting_factor.

## fact_ad_spend

Fact periodic chi phí quảng cáo. Grain: 1 chiến dịch × 1 kênh × 1 tháng (gộp từ stg.ad_spend_daily).

| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |
|---|---|---|---|---|---|---|---|---|
| 1 | `month_key` | integer | không | Tháng phát sinh chi phí | ad_spend_logs.log_date | yyyymm | Khóa | - |
| 2 | `campaign_key` | integer | không | Chiến dịch | ad_spend_logs.campaign_id |  | Khóa | - |
| 3 | `channel_key` | integer | không | Kênh đích của quảng cáo (conformed với kênh bán) | ad_spend_logs.channel_code | map_channel (IR-03) | Khóa | - |
| 4 | `cost_amount` | numeric(18,2) | không | Chi phí quảng cáo trong tháng | ad_spend_logs.cost_amount | Σ theo tháng | Additive | - |
| 5 | `impressions` | bigint | không | Lượt hiển thị | ad_spend_logs.impressions | Σ | Additive | - |
| 6 | `clicks` | bigint | không | Lượt nhấp | ad_spend_logs.clicks | Σ | Additive | - |
| 7 | `active_days` | smallint | không | Số ngày có chi phí trong tháng | ad_spend_logs.log_date | count distinct | Additive | - |
| 8 | `batch_id` | bigint | không | Batch nạp | audit.batch_log |  | Kỹ thuật | - |

## fact_inventory_snapshot

Fact periodic snapshot tồn kho. Grain: 1 sản phẩm × 1 kho × cuối 1 ngày (thưa: chỉ cặp kho–SKU đang kinh doanh). Partition theo tháng.

| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |
|---|---|---|---|---|---|---|---|---|
| 1 | `date_key` | integer | không | Ngày snapshot (cuối ngày) | inventory_daily_balance.balance_date |  | Khóa | - |
| 2 | `product_key` | integer | không | Phiên bản sản phẩm có hiệu lực tại ngày snapshot | inventory_daily_balance.sku | sku → product_id (IR-01) → SCD2 | Khóa | - |
| 3 | `warehouse_key` | integer | không | Kho | inventory_daily_balance.warehouse_id |  | Khóa | - |
| 4 | `category_key` | integer | không | Danh mục lá của sản phẩm tại ngày snapshot | products.category_id |  | Khóa | - |
| 5 | `quantity_on_hand` | integer | không | Tồn vật lý cuối ngày | inventory_daily_balance.quantity_on_hand | không cộng theo ngày | Semi-additive | - |
| 6 | `quantity_reserved` | integer | không | Đã giữ cho đơn chưa xuất | inventory_daily_balance.quantity_reserved |  | Semi-additive | - |
| 7 | `quantity_available` | integer | không | Có thể bán | tính | on_hand − reserved | Semi-additive | - |
| 8 | `qty_imported` | integer | không | Nhập trong ngày | inventory_movements (Import) | Σ quantity_change | Additive | - |
| 9 | `qty_sold` | integer | không | Xuất bán trong ngày (số dương) | inventory_movements (Sale) | −Σ quantity_change | Additive | - |
| 10 | `qty_adjusted` | integer | không | Điều chỉnh trong ngày (giữ dấu) | inventory_movements (Adjustment) | Σ quantity_change | Additive | - |
| 11 | `stockout_flag` | smallint | không | 1 nếu hết hàng cuối ngày | tính | quantity_available = 0 | Additive | - |
| 12 | `inventory_value_est` | numeric(18,2) | có | Giá trị tồn ước tính (GIẢ ĐỊNH giá vốn) | tính | on_hand × unit_cost_est | Semi-additive | - |
| 13 | `batch_id` | bigint | không | Batch nạp | audit.batch_log |  | Kỹ thuật | - |

## fact_order_item

Fact giao dịch bán hàng. Grain: 1 dòng sản phẩm của 1 đơn Completed (item Fulfilled/Returned). Partition theo tháng của date_key (ngày hoàn tất).

| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |
|---|---|---|---|---|---|---|---|---|
| 1 | `source_system` | text | không | Hệ thống nguồn của dòng (phần của khóa nghiệp vụ) | hằng 'mock_oltp' |  | Khóa | - |
| 2 | `order_id` | bigint | không | Mã đơn nguồn (khóa nghiệp vụ) | orders.id |  | Khóa | - |
| 3 | `line_number` | integer | không | Số thứ tự dòng trong đơn (khóa nghiệp vụ) | order_items.line_number |  | Khóa | - |
| 4 | `order_code` | text | không | Mã đơn hiển thị — degenerate dimension | orders.order_code |  | Thuộc tính | - |
| 5 | `date_key` | integer | không | Ngày đơn hoàn tất (Date_Key chính của doanh thu) | orders.completed_at | yyyymmdd của date(completed_at) | Khóa | - |
| 6 | `order_date_key` | integer | không | Ngày đặt hàng (role-playing Dim_Date) | orders.created_at | yyyymmdd | Khóa | - |
| 7 | `product_key` | integer | không | Phiên bản sản phẩm có hiệu lực lúc hoàn tất | order_items.product_id | tra dim_product: valid_from ≤ date(completed_at) < valid_to | Khóa | - |
| 8 | `category_key` | integer | không | Danh mục lá của sản phẩm lúc bán | products.category_id (IR-04) | tra dim_category | Khóa | - |
| 9 | `seller_key` | integer | không | Phiên bản người bán lúc hoàn tất (hạng, tỉnh tại thời điểm bán) | orders.seller_id | tra SCD2 theo completed_at | Khóa | - |
| 10 | `customer_key` | integer | không | Phiên bản khách lúc hoàn tất; -1 = khách vãng lai | orders.customer_id | NULL → -1 (IR-05); không tra được → 0 | Khóa | - |
| 11 | `customer_profile_key` | smallint | không | Hồ sơ khách (mini-dimension) TRƯỚC giao dịch | tính từ fact_order_item lịch sử + customers.membership_tier | bucket chi tiêu 12 tháng, tần suất | Khóa | mini |
| 12 | `channel_key` | integer | không | Kênh bán (Web/App/Livestream) | orders.channel_id |  | Khóa | - |
| 13 | `payment_method_key` | integer | không | Phương thức thanh toán | payments.payment_method_id | 1 payment/đơn: ưu tiên Success, mới nhất; không có → 0 | Khóa | - |
| 14 | `campaign_key` | integer | không | Chiến dịch dẫn tới đơn; -1 = không có | orders.campaign_id | NULL → -1 | Khóa | - |
| 15 | `promotion_group_key` | integer | không | Nhóm voucher của dòng (qua bridge_promotion_group); -1 = không dùng voucher | order_item_promotions | chữ ký nhóm promotion_id:weight | Khóa | - |
| 16 | `quantity` | integer | không | Số món trên dòng | order_items.quantity |  | Additive | - |
| 17 | `list_price` | numeric(18,2) | không | Giá niêm yết / món lúc đặt | order_items.list_price |  | Non-additive | - |
| 18 | `unit_price` | numeric(18,2) | không | Giá bán / món trước voucher | order_items.unit_price |  | Non-additive | - |
| 19 | `list_amount` | numeric(18,2) | không | Thành tiền theo giá niêm yết | order_items | quantity × list_price | Additive | - |
| 20 | `gross_amount` | numeric(18,2) | không | Doanh thu gộp trước voucher | order_items | quantity × unit_price | Additive | - |
| 21 | `list_discount_amount` | numeric(18,2) | không | Giảm giá niêm yết của seller | order_items | list_amount − gross_amount | Additive | - |
| 22 | `discount_amount` | numeric(18,2) | không | Giảm giá voucher phân bổ vào dòng (không gồm freeship) | order_items.discount_amount | = Σ applied_discount_amount (RC-03) | Additive | - |
| 23 | `net_revenue` | numeric(18,2) | không | Doanh thu thuần của dòng | order_items.net_amount | gross_amount − discount_amount (DQ-03) | Additive | - |
| 24 | `commission_rate` | numeric(6,4) | không | Tỷ lệ hoa hồng sàn áp lúc bán | order_items.commission_rate | tỷ lệ 0–1 (IR-10) | Non-additive | - |
| 25 | `commission_amount` | numeric(18,2) | không | Hoa hồng sàn thu trên dòng | order_items | round(net_revenue × commission_rate, 2) | Additive | - |
| 26 | `seller_net_amount` | numeric(18,2) | không | Phần seller nhận trước hoàn | order_items | net_revenue − commission_amount | Additive | - |
| 27 | `cost_amount_est` | numeric(18,2) | có | Giá vốn ước tính (GIẢ ĐỊNH, nguồn không có giá vốn) | products.price × cost_ratio (R-PRD-05) | quantity × unit_cost_est của phiên bản sản phẩm | Additive | - |
| 28 | `gross_margin_est` | numeric(18,2) | có | Lãi gộp ước tính (GIẢ ĐỊNH) | tính | net_revenue − cost_amount_est | Additive | - |
| 29 | `is_returned` | boolean | không | Dòng đã trả hàng (không trừ khỏi net_revenue) | order_items.item_status | = 'Returned'; cập nhật khi đến muộn | Thuộc tính | - |
| 30 | `line_count` | smallint | không | Đếm dòng (hằng 1) |  | 1 | Additive | - |
| 31 | `batch_id` | bigint | không | Batch nạp dòng lần đầu | audit.batch_log |  | Kỹ thuật | - |
| 32 | `updated_batch_id` | bigint | có | Batch cập nhật gần nhất (vd. đổi is_returned) | audit.batch_log |  | Kỹ thuật | - |

## dim_campaign

Chiến dịch marketing.

| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |
|---|---|---|---|---|---|---|---|---|
| 1 | `campaign_key` | integer | không | Khóa chiến dịch; -1 = không có |  |  | Khóa | - |
| 2 | `campaign_id` | integer | có | Mã nguồn | marketing_campaigns.id |  | Khóa | - |
| 3 | `campaign_code` | text | không | Mã chiến dịch | marketing_campaigns.campaign_code |  | Thuộc tính | 1 |
| 4 | `campaign_name` | text | không | Tên chiến dịch | marketing_campaigns.campaign_name |  | Thuộc tính | 1 |
| 5 | `campaign_type` | text | không | Loại chiến dịch | marketing_campaigns.campaign_type |  | Thuộc tính | 1 |
| 6 | `target_channel_key` | integer | không | Kênh đích | marketing_campaigns.target_channel_code | map_channel | Khóa | 1 |
| 7 | `budget_amount` | numeric(18,2) | có | Ngân sách (không đưa vào fact để tránh nhân bản) | marketing_campaigns.budget_amount |  | Non-additive | 1 |
| 8 | `start_date` | date | có | Ngày bắt đầu | marketing_campaigns.start_date |  | Thuộc tính | 1 |
| 9 | `end_date` | date | có | Ngày kết thúc | marketing_campaigns.end_date |  | Thuộc tính | 1 |

## dim_category

Cây danh mục một cha, sâu 2–4 cấp (77 nút), dựng từ primary_category_path cắt tại danh mục OLTP (IR-04).

| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |
|---|---|---|---|---|---|---|---|---|
| 1 | `category_key` | integer | không | Khóa danh mục (= category_id Tiki) |  |  | Khóa | - |
| 2 | `category_id` | integer | không | Mã danh mục Tiki | categories.id / primary_category_path |  | Khóa | - |
| 3 | `category_name` | text | không | Tên danh mục | categories.category_name | nút chưa có tên → 'Danh mục <id>' | Thuộc tính | 1 |
| 4 | `is_named` | boolean | không | Có tên thật từ nguồn |  |  | Thuộc tính | - |
| 5 | `parent_category_key` | integer | có | Danh mục cha | primary_category_path |  | Khóa | - |
| 6 | `level` | smallint | không | Cấp (1 = gốc) |  |  | Thuộc tính | - |
| 7 | `is_leaf` | boolean | không | Là lá (danh mục gắn sản phẩm) |  |  | Thuộc tính | - |
| 8 | `root_category_key` | integer | có | Danh mục gốc |  |  | Khóa | - |
| 9 | `path_ids` | text | không | Đường dẫn mã từ gốc |  | '1520/1582/1583' | Thuộc tính | - |
| 10 | `path_names` | text | không | Đường dẫn tên từ gốc |  | 'A > B > C' | Thuộc tính | - |
| 11 | `batch_id` | bigint | có | Batch | audit.batch_log |  | Kỹ thuật | - |

## dim_channel

Kênh bán / kênh đích quảng cáo (conformed giữa Fact_Order_Item và Fact_Ad_Spend).

| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |
|---|---|---|---|---|---|---|---|---|
| 1 | `channel_key` | integer | không | Khóa kênh |  |  | Khóa | - |
| 2 | `channel_id` | integer | có | Mã kênh nguồn | channels.id |  | Khóa | - |
| 3 | `channel_name` | text | không | Web / App / Livestream | channels.channel_name |  | Thuộc tính | 1 |
| 4 | `channel_type` | text | không | Loại kênh | channels.channel_type |  | Thuộc tính | 1 |
| 5 | `marketing_code` | text | không | Mã kênh phía marketing | map_channel | WEB/APP/LIVESTREAM (IR-03) | Thuộc tính | 1 |

## dim_customer

Khách hàng đã đăng ký (SCD2: tỉnh; SCD1: tên, SĐT, email). -1 = khách vãng lai.

| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |
|---|---|---|---|---|---|---|---|---|
| 1 | `customer_key` | integer | không | Surrogate key phiên bản khách; -1 = khách vãng lai |  |  | Khóa | - |
| 2 | `customer_id` | bigint | không | Mã khách nghiệp vụ | customers.id |  | Khóa | - |
| 3 | `full_name` | text | không | Họ tên | customers.full_name |  | Thuộc tính | 1 |
| 4 | `phone_masked` | text | có | SĐT đã che | customers.phone_number |  | Thuộc tính | 1 |
| 5 | `email_domain` | text | có | Tên miền email | customers.email |  | Thuộc tính | 1 |
| 6 | `gender` | char(1) | không | Giới tính M/F/U | customers.gender | NULL → U (IR-09) | Thuộc tính | 1 |
| 7 | `birth_year` | smallint | có | Năm sinh | customers.date_of_birth |  | Thuộc tính | 1 |
| 8 | `age_band` | text | không | Nhóm tuổi | customers.date_of_birth | 18–24/25–34/35–44/45+/Không rõ | Thuộc tính | 1 |
| 9 | `province_code` | text | không | Mã tỉnh cư trú | customers.province | CUS-02 đổi tỉnh | Thuộc tính | 2 |
| 10 | `province_name` | text | không | Tên tỉnh | customers.province |  | Thuộc tính | 2 |
| 11 | `region` | text | không | Vùng | map_province |  | Thuộc tính | 2 |
| 12 | `registration_date` | date | có | Ngày đăng ký | customers.registration_date |  | Thuộc tính | 1 |
| 13 | `scd1_hash` | text | không | md5 cột SCD1 |  |  | Kỹ thuật | - |
| 14 | `scd2_hash` | text | không | md5 cột SCD2 |  | province_code | Kỹ thuật | - |
| 15 | `valid_from` | date | không | Ngày bắt đầu hiệu lực |  |  | Kỹ thuật | 2 |
| 16 | `valid_to` | date | không | Ngày hết hiệu lực |  |  | Kỹ thuật | 2 |
| 17 | `is_current` | boolean | không | Phiên bản hiện hành |  |  | Kỹ thuật | 2 |
| 18 | `batch_id` | bigint | có | Batch | audit.batch_log |  | Kỹ thuật | - |

## dim_customer_profile

Mini-dimension hồ sơ khách: hạng thành viên × nhóm chi tiêu 12 tháng × nhóm tần suất (125 tổ hợp).

| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |
|---|---|---|---|---|---|---|---|---|
| 1 | `customer_profile_key` | smallint | không | Khóa mini-dimension |  | sinh trước 125 tổ hợp | Khóa | mini |
| 2 | `membership_tier` | text | không | Hạng thành viên | customers.membership_tier | SYS-03 đổi hạng | Thuộc tính | mini |
| 3 | `spend_band_12m` | text | không | Nhóm chi tiêu 12 tháng trước giao dịch | fact_order_item | Σ net_revenue 365 ngày trước | Thuộc tính | mini |
| 4 | `frequency_band` | text | không | Nhóm số đơn 12 tháng trước giao dịch | fact_order_item | count distinct order | Thuộc tính | mini |

## dim_date

Chiều thời gian mức ngày (tĩnh). Grain: 1 ngày. Role-playing: ngày hoàn tất (date_key) và ngày đặt (order_date_key) của Fact_Order_Item; ngày snapshot của Fact_Inventory_Snapshot.

| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |
|---|---|---|---|---|---|---|---|---|
| 1 | `date_key` | integer | không | Khóa ngày yyyymmdd |  |  | Khóa | - |
| 2 | `full_date` | date | không | Ngày dương lịch |  |  | Thuộc tính | - |
| 3 | `day_of_month` | smallint | không | Ngày trong tháng |  |  | Thuộc tính | - |
| 4 | `day_of_week` | smallint | không | Thứ (ISO 1 = Thứ Hai) |  |  | Thuộc tính | - |
| 5 | `day_name` | text | không | Tên thứ (tiếng Việt) |  |  | Thuộc tính | - |
| 6 | `iso_week` | smallint | không | Tuần ISO |  |  | Thuộc tính | - |
| 7 | `iso_year` | smallint | không | Năm ISO của tuần |  |  | Thuộc tính | - |
| 8 | `month_key` | integer | không | Tháng (FK dim_month) |  |  | Khóa | - |
| 9 | `month` | smallint | không | Tháng 1–12 |  |  | Thuộc tính | - |
| 10 | `month_name` | text | không | Tên tháng |  |  | Thuộc tính | - |
| 11 | `quarter` | smallint | không | Quý 1–4 |  |  | Thuộc tính | - |
| 12 | `year` | smallint | không | Năm |  |  | Thuộc tính | - |
| 13 | `is_weekend` | boolean | không | Thứ Bảy/Chủ Nhật |  |  | Thuộc tính | - |
| 14 | `is_holiday` | boolean | không | Ngày lễ VN |  |  | Thuộc tính | - |
| 15 | `holiday_name` | text | có | Tên ngày lễ |  |  | Thuộc tính | - |
| 16 | `is_double_day` | boolean | không | Ngày đôi (ngày = tháng) |  |  | Thuộc tính | - |
| 17 | `is_month_end` | boolean | không | Ngày cuối tháng (dùng lấy tồn cuối kỳ) |  |  | Thuộc tính | - |

## dim_month

Chiều tháng (conformed với dim_date qua month_key). Grain của Fact_Ad_Spend.

| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |
|---|---|---|---|---|---|---|---|---|
| 1 | `month_key` | integer | không | Khóa tháng yyyymm |  |  | Khóa | - |
| 2 | `year` | smallint | không | Năm |  |  | Thuộc tính | - |
| 3 | `quarter` | smallint | không | Quý |  |  | Thuộc tính | - |
| 4 | `month` | smallint | không | Tháng |  |  | Thuộc tính | - |
| 5 | `month_label` | text | không | Nhãn tháng T01/2026 |  |  | Thuộc tính | - |
| 6 | `quarter_label` | text | không | Nhãn quý Q1/2026 |  |  | Thuộc tính | - |
| 7 | `first_date` | date | không | Ngày đầu tháng |  |  | Thuộc tính | - |
| 8 | `last_date` | date | không | Ngày cuối tháng |  |  | Thuộc tính | - |
| 9 | `days_in_month` | smallint | không | Số ngày trong tháng (tính tồn bình quân) |  |  | Thuộc tính | - |

## dim_payment_method

Phương thức thanh toán.

| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |
|---|---|---|---|---|---|---|---|---|
| 1 | `payment_method_key` | integer | không | Khóa phương thức |  |  | Khóa | - |
| 2 | `payment_method_id` | integer | có | Mã nguồn | payment_methods.id |  | Khóa | - |
| 3 | `method_name` | text | không | COD/Momo/ZaloPay/Credit Card/Bank Transfer | payment_methods.method_name |  | Thuộc tính | 1 |
| 4 | `method_group` | text | không | COD/E-Wallet/Card/Bank Transfer | payment_methods.method_group |  | Thuộc tính | 1 |

## dim_product

Sản phẩm (SCD2: giá niêm yết, danh mục, is_active; SCD1: tên, thương hiệu). Nguồn: crawler Tiki qua mock_oltp.products.

| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |
|---|---|---|---|---|---|---|---|---|
| 1 | `product_key` | integer | không | Surrogate key phiên bản sản phẩm |  | serial; -1/0 đặc biệt | Khóa | - |
| 2 | `product_id` | bigint | không | Mã sản phẩm nghiệp vụ (ổn định qua phiên bản; dùng để drill-across) | products.id |  | Khóa | - |
| 3 | `sku` | text | không | Mã SKU (khóa của hệ thống kho) | products.sku | IR-01 | Thuộc tính | 1 |
| 4 | `product_name` | text | không | Tên sản phẩm | products.name (Tiki thật) | trim, NFC | Thuộc tính | 1 |
| 5 | `brand_name` | text | không | Thương hiệu | products.brand_name | rỗng → 'Không rõ thương hiệu' | Thuộc tính | 1 |
| 6 | `category_key` | integer | không | Danh mục lá | products.category_id | IR-04 | Thuộc tính | 2 |
| 7 | `seller_id` | bigint | không | Người bán sở hữu | products.seller_id |  | Thuộc tính | 1 |
| 8 | `list_price` | numeric(18,2) | không | Giá niêm yết | products.price |  | Thuộc tính | 2 |
| 9 | `original_price` | numeric(18,2) | không | Giá gốc | products.original_price | NULL → price | Thuộc tính | 1 |
| 10 | `discount_rate` | numeric(6,4) | không | Tỷ lệ giảm niêm yết (0–1) | products.discount_rate | /100 (IR-10) | Thuộc tính | 1 |
| 11 | `unit_cost_est` | numeric(18,2) | có | Giá vốn ước tính / món (GIẢ ĐỊNH) | products.price × cost_ratio | round_1000 (R-PRD-05) | Thuộc tính | 2 |
| 12 | `is_active` | boolean | không | Đang được bán (hiển thị), không phải tồn kho | products.is_active | đổi khi seller bị khóa (MGR-02) | Thuộc tính | 2 |
| 13 | `scd1_hash` | text | không | md5 các cột SCD1 |  | name ‖ brand ‖ original_price ‖ discount_rate | Kỹ thuật | - |
| 14 | `scd2_hash` | text | không | md5 các cột SCD2 |  | list_price ‖ category ‖ is_active | Kỹ thuật | - |
| 15 | `valid_from` | date | không | Ngày bắt đầu hiệu lực (gồm) |  | đầu ngày của updated_at (TV-03) | Kỹ thuật | 2 |
| 16 | `valid_to` | date | không | Ngày hết hiệu lực (không gồm); 9999-12-31 = hiện hành |  |  | Kỹ thuật | 2 |
| 17 | `is_current` | boolean | không | Phiên bản hiện hành |  | đúng 1 / product_id | Kỹ thuật | 2 |
| 18 | `batch_id` | bigint | có | Batch tạo/cập nhật phiên bản | audit.batch_log |  | Kỹ thuật | - |

## dim_promotion

Voucher / khuyến mãi.

| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |
|---|---|---|---|---|---|---|---|---|
| 1 | `promotion_key` | integer | không | Khóa voucher; -1 = không dùng |  |  | Khóa | - |
| 2 | `promotion_id` | bigint | có | Mã nguồn | promotions.id |  | Khóa | - |
| 3 | `promo_code` | text | không | Mã voucher | promotions.promo_code |  | Thuộc tính | 1 |
| 4 | `promo_name` | text | không | Tên voucher | promotions.promo_name |  | Thuộc tính | 1 |
| 5 | `promo_type` | text | không | Platform / Seller / Freeship Voucher | promotions.promo_type |  | Thuộc tính | 1 |
| 6 | `funded_by` | text | không | Bên tài trợ Platform/Seller | order_item_promotions.funded_by / promotions.seller_id |  | Thuộc tính | 1 |
| 7 | `apply_level` | text | không | Order / Shipping | promotions.apply_level |  | Thuộc tính | 1 |
| 8 | `discount_type` | text | có | Kiểu giảm | promotions.discount_type |  | Thuộc tính | 1 |
| 9 | `discount_value` | numeric(18,2) | có | Mức giảm | promotions.discount_value |  | Non-additive | 1 |
| 10 | `min_order_value` | numeric(18,2) | có | Đơn tối thiểu | promotions.min_order_value |  | Non-additive | 1 |
| 11 | `seller_id` | bigint | có | Seller phát hành (voucher seller) | promotions.seller_id |  | Thuộc tính | 1 |
| 12 | `start_ts` | timestamp without time zone | có | Bắt đầu hiệu lực | promotions.start_date |  | Thuộc tính | 1 |
| 13 | `end_ts` | timestamp without time zone | có | Hết hiệu lực | promotions.end_date |  | Thuộc tính | 1 |

## dim_promotion_group

Nhóm voucher áp trên một dòng hàng (đề xuất Bảng 9).

| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |
|---|---|---|---|---|---|---|---|---|
| 1 | `promotion_group_key` | integer | không | Khóa nhóm voucher của một dòng hàng; -1 = không voucher |  |  | Khóa | - |
| 2 | `group_signature` | text | không | Chữ ký nhóm: promotion_id:weight sắp theo id |  |  | Thuộc tính | - |
| 3 | `promotion_count` | smallint | không | Số voucher trong nhóm |  |  | Thuộc tính | - |

## dim_seller

Người bán (SCD2: hạng, tỉnh, trạng thái; SCD1: tên shop, liên hệ).

| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |
|---|---|---|---|---|---|---|---|---|
| 1 | `seller_key` | integer | không | Surrogate key phiên bản người bán |  |  | Khóa | - |
| 2 | `seller_id` | bigint | không | Mã người bán nghiệp vụ | sellers.id |  | Khóa | - |
| 3 | `shop_name` | text | không | Tên gian hàng | sellers.shop_name | SEL-01 đổi tên | Thuộc tính | 1 |
| 4 | `seller_name` | text | không | Tên chủ shop | sellers.seller_name |  | Thuộc tính | 1 |
| 5 | `email_domain` | text | có | Tên miền email (không lưu email đầy đủ) | sellers.email | phần sau @ | Thuộc tính | 1 |
| 6 | `phone_masked` | text | có | SĐT đã che | sellers.phone | 3 số đầu + **** + 3 số cuối | Thuộc tính | 1 |
| 7 | `province_code` | text | không | Mã tỉnh kinh doanh | sellers.province | map_province (IR-08) | Thuộc tính | 2 |
| 8 | `province_name` | text | không | Tên tỉnh chuẩn | sellers.province |  | Thuộc tính | 2 |
| 9 | `region` | text | không | Vùng Bắc/Trung/Nam | map_province |  | Thuộc tính | 2 |
| 10 | `tier` | text | không | Hạng người bán Mall/Preferred/Normal | sellers.tier | MGR-01 đổi hạng | Thuộc tính | 2 |
| 11 | `status` | text | không | Trạng thái Active/Suspended | sellers.status | MGR-02 khóa shop | Thuộc tính | 2 |
| 12 | `scd1_hash` | text | không | md5 cột SCD1 |  |  | Kỹ thuật | - |
| 13 | `scd2_hash` | text | không | md5 cột SCD2 |  | tier ‖ province_code ‖ status | Kỹ thuật | - |
| 14 | `valid_from` | date | không | Ngày bắt đầu hiệu lực |  |  | Kỹ thuật | 2 |
| 15 | `valid_to` | date | không | Ngày hết hiệu lực |  |  | Kỹ thuật | 2 |
| 16 | `is_current` | boolean | không | Phiên bản hiện hành |  |  | Kỹ thuật | 2 |
| 17 | `batch_id` | bigint | có | Batch | audit.batch_log |  | Kỹ thuật | - |

## dim_seller_tier_t3

Minh họa SCD3: hạng seller hiện tại và hạng trước gần nhất (không giữ toàn bộ lịch sử).

| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |
|---|---|---|---|---|---|---|---|---|
| 1 | `seller_id` | bigint | không | Mã người bán | sellers.id |  | Khóa | 3 |
| 2 | `current_tier` | text | không | Hạng hiện tại | sellers.tier |  | Thuộc tính | 3 |
| 3 | `previous_tier` | text | có | Hạng trước gần nhất (SCD3: chỉ giữ 1 giá trị trước) | sellers.tier |  | Thuộc tính | 3 |
| 4 | `tier_changed_on` | date | có | Ngày đổi hạng gần nhất | sellers.updated_at |  | Thuộc tính | 3 |
| 5 | `batch_id` | bigint | có | Batch | audit.batch_log |  | Kỹ thuật | - |

## dim_warehouse

Kho (fulfillment center do sàn vận hành).

| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |
|---|---|---|---|---|---|---|---|---|
| 1 | `warehouse_key` | integer | không | Khóa kho |  |  | Khóa | - |
| 2 | `warehouse_id` | integer | có | Mã kho nguồn | warehouses.id |  | Khóa | - |
| 3 | `warehouse_code` | text | không | Mã kho | warehouses.warehouse_code |  | Thuộc tính | 1 |
| 4 | `warehouse_name` | text | không | Tên kho | warehouses.warehouse_name |  | Thuộc tính | 1 |
| 5 | `province_code` | text | không | Mã tỉnh | warehouses.province | IR-08 | Thuộc tính | 1 |
| 6 | `province_name` | text | không | Tên tỉnh | warehouses.province |  | Thuộc tính | 1 |
| 7 | `region` | text | không | Vùng |  |  | Thuộc tính | 1 |

## bridge_category_hierarchy

Closure table của cây danh mục: mọi cặp (tổ tiên, con cháu), để cộng doanh thu theo cây con không cộng lặp.

| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |
|---|---|---|---|---|---|---|---|---|
| 1 | `ancestor_key` | integer | không | Danh mục tổ tiên (kể cả chính nó) |  | closure table | Khóa | - |
| 2 | `descendant_key` | integer | không | Danh mục con cháu |  |  | Khóa | - |
| 3 | `depth` | smallint | không | Khoảng cách cấp (0 = chính nó) |  |  | Thuộc tính | - |

## bridge_promotion_group

Bridge nhóm voucher → voucher với weighting_factor; số tiền phân bổ = fact.discount_amount × weighting_factor.

| # | Cột | Kiểu | NULL | Mô tả | Nguồn | Quy tắc | Cộng | SCD |
|---|---|---|---|---|---|---|---|---|
| 1 | `promotion_group_key` | integer | không | Nhóm |  |  | Khóa | - |
| 2 | `promotion_key` | integer | không | Voucher |  |  | Khóa | - |
| 3 | `weighting_factor` | numeric(9,6) | không | Tỷ trọng phân bổ giảm giá; Σ = 1 mỗi nhóm | order_item_promotions.applied_discount_amount | applied / Σ applied trong cùng order_item | Non-additive | - |
