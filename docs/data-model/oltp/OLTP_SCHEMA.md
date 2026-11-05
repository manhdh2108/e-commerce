# OLTP Schema — Sàn thương mại điện tử (nguồn cho Data Warehouse)

Tài liệu mô tả schema nguồn OLTP đầy đủ cho kho dữ liệu sàn TMĐT đa người bán.

Bảng `products` là dữ liệu **thật**, thu thập bằng crawler (`scripts/crawl_tiki.py`)
từ API công khai của Tiki. Tất cả các bảng còn lại là **dữ liệu mô phỏng**, vì
hệ thống nội bộ thật của sàn (đơn hàng, khách hàng, thanh toán, kho vận, quảng
cáo...) không được public.

Nguyên tắc chung:

- OLTP chỉ giữ **trạng thái hiện tại** như hệ thống thật. Lịch sử SCD do Data
  Warehouse tự dựng bằng cách so sánh các batch extract theo ngày.
- Bộ sinh ghi vào OLTP **theo từng ngày mô phỏng**. Thông tin chủ thay đổi theo
  vận hành thật (seller đổi hạng, khách chuyển tỉnh, sản phẩm đổi giá hoặc danh
  mục). ETL đọc dữ liệu theo lịch riêng của mình.
- Luật sinh dữ liệu cho từng bảng: [DATA_GENERATION_RULES.md](DATA_GENERATION_RULES.md).
- Ký hiệu **[mới]** đánh dấu bảng hoặc cột được bổ sung khi mở rộng phạm vi.

---

## 0. Phân chia hệ thống nguồn

Dữ liệu đến từ 6 hệ thống tách biệt. Mỗi hệ thống dùng mã định danh riêng của
mình, nên một số mã không thống nhất giữa các hệ thống (xem mục 10).

| Hệ thống nguồn | Bảng |
|---|---|
| Danh mục sản phẩm & người bán | `products`, `categories`, `sellers` |
| Đơn hàng | `customers`, `customer_addresses`, `channels`, `payment_methods`, `orders`, `order_items`, `payments`, `order_item_promotions`, `returns`, `product_reviews` |
| Kho vận | `warehouses`, `inventory_levels`, `inventory_movements`, `inventory_daily_balance`, `carriers`, `shipments` |
| Marketing | `promotions`, `marketing_campaigns`, `ad_spend_logs` |
| Web analytics (clickstream) | `sessions`, `page_events`, `cart_items` |
| Tài chính | `seller_commission_rates`, `seller_payouts` |

---

## 1. Nhóm Sản phẩm & Danh mục

### 1.1 `products` (dữ liệu crawl thật)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | Product ID trên Tiki |
| `sku` | varchar | Mã dùng bởi hệ thống kho vận |
| `name` | varchar | |
| `url_key` | varchar | |
| `price` | decimal | Giá bán hiện tại |
| `original_price` | decimal | Giá niêm yết; fallback từ `list_price` |
| `discount` | decimal | |
| `discount_rate` | decimal | |
| `brand_name` | varchar | |
| `rating_average` | decimal | |
| `review_count` | int | |
| `thumbnail_url` | varchar | |
| `category_id` | int, FK → `categories.id` | Danh mục **lá** (trong crawl DB cột này là danh mục gốc) |
| `category_name` | varchar | |
| `quantity_sold` | int | Số lũy kế do Tiki trả |
| `crawl_date` | date | Ngày quan sát (local) |
| `is_active` | boolean, nullable | |
| `seller_id` | bigint, FK → `sellers.id` | |
| `seller_product_id` | varchar | |
| `url_path` | varchar | |
| `inventory_status` | varchar | Trạng thái do Tiki trả, không phải số lượng thật |
| `stock_item` | text (JSON) | |
| `short_description` | text | |
| `type` | varchar | |
| `cost_price` | decimal | Giá vốn (mô phỏng) — cho gross margin và `inventory_value` |
| `created_at` | timestamp | **[mới]** Ngày lên sàn (mô phỏng) |
| `updated_at` | timestamp | **[mới]** Thời điểm thay đổi gần nhất; DW dùng làm `valid_from` |

> Giá thật chỉ có giá trị hiện tại. Giá quá khứ được mô phỏng quanh giá thật
> (ví dụ giảm mạnh vào ngày sale) và thể hiện qua các batch theo ngày.

### 1.2 `categories`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | int, PK | |
| `category_name` | varchar | |
| `parent_id` | int, FK tự tham chiếu → `categories.id`, nullable | |
| `level` | int | 1 = gốc |
| `slug` | varchar | |

---

## 2. Nhóm Người bán

### 2.1 `sellers`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | Lấy `seller_id` từ Tiki; thông tin chi tiết mô phỏng |
| `seller_name` | varchar | |
| `shop_name` | varchar | |
| `tier` | varchar | `Mall`, `Preferred`, `Normal` — DW làm SCD2 |
| `province` | varchar | DW làm SCD2 |
| `city` | varchar | |
| `email` | varchar | |
| `phone` | varchar | |
| `status` | varchar | `Active`, `Suspended` |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

---

## 3. Nhóm Khách hàng

### 3.1 `customers`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `full_name` | varchar | |
| `email` | varchar | |
| `phone_number` | varchar | |
| `gender` | varchar | |
| `date_of_birth` | date | |
| `province` | varchar | Tỉnh cư trú khai báo trong hồ sơ — DW làm SCD2 |
| `city` | varchar | |
| `membership_tier` | varchar | **[mới]** `Member`, `Silver`, `Gold`, `Platinum` — nguồn cho `Customer_Profile` |
| `registration_date` | timestamp | |
| `updated_at` | timestamp | **[mới]** |

### 3.2 `customer_addresses`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `customer_id` | bigint, FK → `customers.id`, **nullable** | NULL = địa chỉ dùng một lần của khách vãng lai |
| `recipient_name` | varchar | |
| `phone` | varchar | |
| `address_detail` | varchar | |
| `ward` | varchar | |
| `district` | varchar, nullable | NULL theo mô hình hành chính 2 cấp (từ 01/07/2025) |
| `province` | varchar | Tỉnh giao hàng — dùng cho báo cáo địa lý theo đơn |
| `is_default` | boolean | |

---

## 4. Nhóm Đơn hàng & Thanh toán

### 4.1 `channels`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | int, PK | |
| `channel_name` | varchar | `Web`, `App`, `Livestream` |
| `channel_type` | varchar | Nhóm kênh |

### 4.2 `payment_methods`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | int, PK | |
| `method_name` | varchar | `COD`, `Momo`, `ZaloPay`, `Credit Card`, `Bank Transfer` |
| `method_group` | varchar | `COD`, `E-Wallet`, `Card`, `Bank Transfer` |

### 4.3 `orders`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `order_code` | varchar, unique | |
| `customer_id` | bigint, FK → `customers.id`, **nullable** | NULL = khách vãng lai (DW gán khóa -1) |
| `seller_id` | bigint, FK → `sellers.id` | Đơn tách theo shop |
| `channel_id` | int, FK → `channels.id` | |
| `session_id` | bigint, FK → `sessions.id`, nullable | **[mới]** Phiên dẫn tới đơn hàng |
| `campaign_id` | int, FK → `marketing_campaigns.id`, nullable | **[mới]** Chiến dịch được gán (attribution) |
| `order_status` | varchar | `Pending`, `Processing`, `Completed`, `Cancelled` |
| `total_gross_amount` | decimal | |
| `total_discount_amount` | decimal | |
| `shipping_fee` | decimal | Phí ship trước giảm |
| `shipping_discount_amount` | decimal | **[mới]** Số tiền freeship được giảm, 0 nếu không có |
| `shipping_promotion_id` | bigint, FK → `promotions.id`, nullable | **[mới]** Voucher freeship đã dùng |
| `final_amount` | decimal | |
| `shipping_address_id` | bigint, FK → `customer_addresses.id` | |
| `created_at` | timestamp | Thời điểm đặt hàng |
| `completed_at` | timestamp, nullable | **[mới]** Thời điểm giao thành công — `Date_Key` của `Fact_Order_Item` |
| `cancelled_at` | timestamp, nullable | **[mới]** |
| `updated_at` | timestamp | |

### 4.4 `order_items`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `order_id` | bigint, FK → `orders.id` | |
| `line_number` | int | **[mới]** Số thứ tự dòng trong đơn (`line_id` trong khóa nghiệp vụ) |
| `product_id` | bigint, FK → `products.id` | |
| `quantity` | int | |
| `list_price` | decimal | **[mới]** Giá niêm yết tại thời điểm mua |
| `unit_price` | decimal | Giá bán thực tế tại thời điểm mua |
| `discount_amount` | decimal | Tổng giảm giá đã phân bổ xuống dòng (gồm phần phân bổ từ voucher cấp đơn) |
| `net_amount` | decimal | |
| `item_status` | varchar | `Pending` (chưa giao), `Fulfilled`, `Cancelled`, `Returned` |

### 4.5 `payments`

Bảng là sổ giao dịch: mỗi lần thử thanh toán hoặc mỗi lần hoàn tiền là một dòng.
Một đơn có thể có nhiều lần thanh toán (thất bại rồi thành công). Payment method
của fact lấy theo lần thanh toán `Success`. Hoàn tiền là dòng mới trạng thái
`Refunded` với `paid_amount` âm.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `order_id` | bigint, FK → `orders.id` | |
| `payment_method_id` | int, FK → `payment_methods.id` | |
| `payment_status` | varchar | `Pending`, `Success`, `Failed`, `Refunded` |
| `paid_amount` | decimal | |
| `transaction_time` | timestamp | |

### 4.6 `returns` [mới]

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `order_item_id` | bigint, FK → `order_items.id` | Chỉ dòng đã giao thành công |
| `quantity` | int | ≤ `order_items.quantity` |
| `return_reason` | varchar | `Damaged`, `Wrong Item`, `Not As Described`, `Changed Mind` |
| `refund_amount` | decimal | ≤ `order_items.net_amount` |
| `status` | varchar | `Requested`, `Approved`, `Rejected`, `Refunded` |
| `requested_at` | timestamp | |
| `refunded_at` | timestamp, nullable | |

### 4.7 `product_reviews` [mới]

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `order_item_id` | bigint, FK → `order_items.id` | Chỉ review khi đã mua |
| `product_id` | bigint, FK → `products.id` | |
| `customer_id` | bigint, FK → `customers.id` | |
| `rating` | int | 1–5 |
| `comment` | text | |
| `created_at` | timestamp | Sau `orders.completed_at` |

---

## 5. Nhóm Khuyến mại

### 5.1 `promotions`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `promo_code` | varchar | |
| `promo_name` | varchar | **[mới]** |
| `promo_type` | varchar | `Platform Voucher`, `Seller Voucher`, `Freeship Voucher` |
| `seller_id` | bigint, FK → `sellers.id`, nullable | NULL = voucher sàn |
| `apply_level` | varchar | **[mới]** `Order` (áp cả đơn, phải phân bổ xuống dòng), `Item` (một sản phẩm), `Shipping` (giảm phí ship) |
| `product_id` | bigint, FK → `products.id`, nullable | **[mới]** Bắt buộc khi `apply_level = Item` |
| `eligibility` | varchar | **[mới]** `All`, `New Customer`, `Gold+`, `Platinum`, `Livestream Only` |
| `discount_type` | varchar | `Fixed Amount`, `Percentage` |
| `discount_value` | decimal | |
| `min_order_value` | decimal | |
| `max_discount_amount` | decimal, nullable | **[mới]** Trần giảm của voucher % |
| `usage_limit` | int, nullable | **[mới]** Tổng số lượt; NULL = không giới hạn |
| `per_customer_limit` | int | **[mới]** Số lượt tối đa mỗi khách |
| `start_date` | timestamp | |
| `end_date` | timestamp | |

### 5.2 `order_item_promotions`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `order_item_id` | bigint, FK → `order_items.id` | |
| `promotion_id` | bigint, FK → `promotions.id` | |
| `applied_discount_amount` | decimal | Số tiền voucher này giảm trên dòng (đã phân bổ nếu là voucher cấp đơn) |

---

## 6. Nhóm Kho vận

Hệ thống kho định danh sản phẩm bằng `sku`, không dùng `product_id`.

### 6.1 `warehouses`

Giả định: mọi kho do sàn vận hành (fulfillment center).

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | int, PK | |
| `warehouse_code` | varchar | |
| `warehouse_name` | varchar | |
| `province` | varchar | |
| `city` | varchar | |
| `address` | text | |

### 6.2 `inventory_levels`

Tồn kho hiện tại. Tồn cuối mỗi ngày được lưu riêng ở `inventory_daily_balance`
(mục 6.6).

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `warehouse_id` | int, FK → `warehouses.id` | |
| `sku` | varchar | Ánh xạ sang `products.sku` ở staging |
| `quantity_on_hand` | int | ≥ 0 |
| `quantity_reserved` | int | |
| `updated_at` | timestamp | |

### 6.3 `inventory_movements`

Sổ cái nhập/xuất kho. Dùng để đối soát với `inventory_levels` và dựng lại tồn
kho nếu thiếu batch.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `warehouse_id` | int, FK → `warehouses.id` | |
| `sku` | varchar | |
| `movement_type` | varchar | `Import`, `Sale`, `Return`, `Adjustment` |
| `quantity_change` | int | Dương = nhập, âm = xuất |
| `reference_code` | varchar, nullable | **[mới]** `order_code` khi là `Sale`/`Return` |
| `movement_date` | timestamp | |

### 6.4 `carriers` [mới]

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | int, PK | |
| `carrier_code` | varchar | `GHN`, `GHTK`, `VTP`, ... |
| `carrier_name` | varchar | |

### 6.5 `shipments` [mới]

Nguồn cho fact accumulating snapshot về xử lý đơn.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `order_code` | varchar | Hệ thống kho tham chiếu bằng mã đơn, không dùng `orders.id` |
| `warehouse_id` | int, FK → `warehouses.id` | |
| `carrier_id` | int, FK → `carriers.id` | |
| `tracking_code` | varchar, unique | |
| `shipment_status` | varchar | `Created`, `Picked`, `In Transit`, `Delivered`, `Failed` |
| `shipping_cost` | decimal | Chi phí thực trả cho đơn vị vận chuyển |
| `created_at` | timestamp | |
| `picked_at` | timestamp, nullable | |
| `delivered_at` | timestamp, nullable | |
| `failed_at` | timestamp, nullable | |

### 6.6 `inventory_daily_balance` [mới]

Báo cáo tồn cuối ngày của hệ thống kho. Nguồn trực tiếp cho
`Fact_Inventory_Snapshot`. Có dòng cho mọi cặp (kho, SKU) đang hoạt động, kể cả
khi tồn bằng 0.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `balance_date` | date | Unique cùng `warehouse_id`, `sku` |
| `warehouse_id` | int, FK → `warehouses.id` | |
| `sku` | varchar | Ánh xạ sang `products.sku` ở staging |
| `quantity_on_hand` | int | Tồn lúc 23:59:59 |
| `quantity_reserved` | int | Lượng đang giữ cho đơn chưa lấy hàng |

---

## 7. Nhóm Marketing

Hệ thống marketing dùng **mã kênh riêng** (`WEB`, `MOBILE_APP`, `LIVE`) thay vì
`channels.id`.

### 7.1 `marketing_campaigns`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | int, PK | |
| `campaign_code` | varchar | |
| `campaign_name` | varchar | |
| `campaign_type` | varchar | **[mới]** `Mega Sale`, `Flash Sale`, `Brand Awareness`, `Retargeting`, `Livestream Show` |
| `target_channel_code` | varchar | `WEB`, `MOBILE_APP`, `LIVE` |
| `budget_amount` | decimal | Ngân sách kế hoạch |
| `start_date` | date | |
| `end_date` | date | |

### 7.2 `ad_spend_logs`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `campaign_id` | int, FK → `marketing_campaigns.id` | |
| `channel_code` | varchar | `WEB`, `MOBILE_APP`, `LIVE` |
| `log_date` | date | Theo ngày; DW tổng hợp lên tháng |
| `cost_amount` | decimal | |
| `impressions` | bigint | |
| `clicks` | bigint | ≥ số `sessions` được gán cho campaign trong ngày |

---

## 8. Nhóm Clickstream [mới]

Clickstream có dung lượng gấp nhiều lần số đơn. Bộ sinh có thể giới hạn khoảng
thời gian hoặc nhóm khách mẫu để vừa sức PostgreSQL trên máy cá nhân.

### 8.1 `sessions`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `customer_id` | bigint, FK → `customers.id`, nullable | NULL = khách chưa đăng nhập |
| `channel_id` | int, FK → `channels.id` | |
| `campaign_id` | int, FK → `marketing_campaigns.id`, nullable | Phiên đến từ quảng cáo |
| `traffic_source` | varchar | `Organic`, `Paid Ads`, `Social`, `Direct`, `Email` |
| `device_type` | varchar | `Desktop`, `Mobile`, `Tablet` |
| `started_at` | timestamp | |
| `ended_at` | timestamp | |

### 8.2 `page_events`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `session_id` | bigint, FK → `sessions.id` | |
| `event_type` | varchar | `view_product`, `search`, `add_to_cart`, `remove_from_cart`, `begin_checkout`, `purchase` |
| `product_id` | bigint, FK → `products.id`, nullable | |
| `order_id` | bigint, FK → `orders.id`, nullable | Chỉ có khi `event_type = purchase` |
| `event_time` | timestamp | Trong khoảng `[started_at, ended_at]` của phiên |

### 8.3 `cart_items`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `session_id` | bigint, FK → `sessions.id` | |
| `customer_id` | bigint, FK → `customers.id`, nullable | |
| `product_id` | bigint, FK → `products.id` | |
| `quantity` | int | |
| `cart_status` | varchar | `Active`, `Ordered`, `Abandoned`, `Removed` |
| `added_at` | timestamp | |
| `closed_at` | timestamp, nullable | |

---

## 9. Nhóm Tài chính [mới]

### 9.1 `seller_commission_rates`

Bảng cấu hình phí hoa hồng. Có khoảng hiệu lực vì là chính sách nghiệp vụ,
không phải lịch sử SCD.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | int, PK | |
| `category_id` | int, FK → `categories.id` | |
| `seller_tier` | varchar | `Mall`, `Preferred`, `Normal` |
| `commission_rate` | decimal | VD: 0.05 = 5% |
| `effective_from` | date | |
| `effective_to` | date, nullable | |

### 9.2 `seller_payouts`

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `seller_id` | bigint, FK → `sellers.id` | |
| `period_start` | date | |
| `period_end` | date | |
| `gross_sales` | decimal | Σ khoản ghi có cho seller (`net_amount` + phần voucher sàn) của các dòng giao thành công trong kỳ |
| `refund_amount` | decimal | Khoản trừ của seller do hoàn hàng trong kỳ, tính theo khoản ghi có |
| `commission_amount` | decimal | Σ (khoản ghi có × tỷ lệ hiệu lực theo ngày đặt), trừ phần của hàng hoàn |
| `payout_amount` | decimal | `gross_sales − refund_amount − commission_amount` |
| `payout_status` | varchar | `Pending`, `Paid` |
| `paid_at` | timestamp, nullable | |

---

## 10. Mã định danh riêng của từng hệ thống

Các hệ thống không dùng chung khóa. Khi tích hợp, ETL cần ánh xạ các mã sau về
khóa thống nhất:

| Thực thể | Hệ thống đơn hàng | Hệ thống khác |
|---|---|---|
| Sản phẩm | `product_id` | Kho vận dùng `sku` |
| Đơn hàng | `orders.id` | Kho vận (`shipments`, `inventory_movements`) dùng `order_code` |
| Kênh | `channels.id` (`Web`, `App`, `Livestream`) | Marketing dùng `WEB`, `MOBILE_APP`, `LIVE` |

---

## 11. Hạ tầng crawler (không thuộc mô hình nghiệp vụ)

- `product_checkpoints`: product ID, hash nội dung, first/last seen, last changed (UTC).
- `product_raw`: JSON đầy đủ, mới nhất từ API.
- `product_categories`: cặp product/root/leaf category đã quan sát.

---

## 12. ERD tổng thể

Xem sơ đồ Mermaid trong [OLTP_ERD.md](OLTP_ERD.md): một sơ đồ tổng quan quan hệ
và một sơ đồ chi tiết đủ cột.

---

## 13. Mapping sang Fact / Dimension

| Fact / Dimension | Nguồn OLTP |
|---|---|
| `Fact_Order_Item` | `order_items` (`item_status` là `Fulfilled` hoặc `Returned`, đơn `Completed`), `orders`, `payments`, `order_item_promotions` |
| `Fact_Inventory_Snapshot` | `inventory_daily_balance`, đối soát bằng `inventory_movements` |
| `Fact_Ad_Spend` | `ad_spend_logs`, `marketing_campaigns` |
| `Fact_Customer_Activity` [mới] | `sessions`, `page_events`, `cart_items` |
| `Fact_Order_Fulfillment` [mới] | `orders`, `shipments`, `payments` |
| `Fact_Return` [mới] | `returns`, `order_items` |
| `Fact_Product_Daily_Snapshot` [mới] | `products` (crawl theo ngày), `product_reviews` |
| `Fact_Seller_Settlement` [mới] | `seller_payouts`, `seller_commission_rates` |
| `Dim_Product` / `Dim_Category` | `products`, `categories` |
| `Dim_Seller` (SCD1/2) | `sellers` |
| `Dim_Customer` + `Customer_Profile` | `customers`, `customer_addresses`, tổng hợp từ `orders` |
| `Dim_Channel` | `channels` + ánh xạ mã marketing |
| `Dim_Payment_Method` | `payment_methods` |
| `Dim_Promotion` + Bridge | `promotions`, `order_item_promotions` |
| `Dim_Warehouse` | `warehouses` |
| `Dim_Carrier` [mới] | `carriers` |
| `Dim_Campaign` | `marketing_campaigns` |
| `Dim_Return_Reason` [mới] | `returns.return_reason` |
| `Dim_Device` / `Dim_Traffic_Source` [mới] | `sessions` |

---

## 14. Tổng số bảng

- **27 bảng nghiệp vụ**: 17 bảng ban đầu + 10 bảng mới (`returns`,
  `product_reviews`, `carriers`, `shipments`, `inventory_daily_balance`,
  `sessions`, `page_events`, `cart_items`, `seller_commission_rates`,
  `seller_payouts`).
- **3 bảng hạ tầng crawler**.
