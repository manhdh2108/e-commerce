# OLTP Schema — Sàn thương mại điện tử (nguồn cho Data Warehouse)

Tài liệu này mô tả schema nguồn OLTP đầy đủ phục vụ xây dựng kho dữ liệu với 3 Fact
chính: `Fact_Order_Item`, `Fact_Inventory_Snapshot`, `Fact_Ad_Spend`.

Bảng `products` là dữ liệu **thật**, thu thập bằng crawler (`scripts/crawl_tiki.py`)
từ API công khai của Tiki. Tất cả các bảng còn lại trong tài liệu này là **dữ liệu
mô phỏng (simulated OLTP)**, vì các hệ thống nội bộ thật của sàn (đơn hàng, khách
hàng, thanh toán, kho vận, quảng cáo...) không được public.

---

## 1. Nhóm Sản phẩm & Danh mục

### 1.1 `products` (đã có — dữ liệu crawl thật)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | Product ID trên Tiki |
| `sku` | varchar | |
| `name` | varchar | |
| `url_key` | varchar | |
| `price` | decimal | Giá bán hiện tại |
| `original_price` | decimal | Fallback từ `list_price` nếu thiếu |
| `discount` | decimal | |
| `discount_rate` | decimal | |
| `brand_name` | varchar | |
| `rating_average` | decimal | |
| `review_count` | int | |
| `thumbnail_url` | varchar | |
| `category_id` | int, FK → `categories.id` | Category gốc được chọn khi crawl |
| `category_name` | varchar | |
| `quantity_sold` | int | Trích từ field `value` lồng trong API |
| `crawl_date` | date | Ngày quan sát (local) |
| `is_active` | boolean, nullable | Từ `is_active`/`is_visible`; NULL nếu API không trả |
| `seller_id` | bigint, FK → `sellers.id` | |
| `seller_product_id` | varchar | |
| `url_path` | varchar | |
| `inventory_status` | varchar | Trạng thái tồn kho do Tiki trả (không phải số lượng thật) |
| `stock_item` | text (JSON) | |
| `short_description` | text | |
| `type` | varchar | |
| `cost_price` | decimal | **[bổ sung]** Giá vốn — cần cho tính gross margin ở `Fact_Order_Item` |

> Không có bảng lịch sử giá riêng: giá bán thực tế tại thời điểm mua đã được
> chốt lại trong `order_items.unit_price`.

### 1.2 `categories` (bổ sung)

Cây danh mục nhiều cấp, phục vụ Dim_Category dạng parent-child.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | int, PK | |
| `category_name` | varchar | |
| `parent_id` | int, FK tự tham chiếu → `categories.id`, nullable | |
| `level` | int | Cấp độ trong cây (1 = gốc) |
| `slug` | varchar | |

---

## 2. Nhóm Người bán (Sellers)

### 2.1 `sellers` (bổ sung)

Phục vụ `Dim_Seller` (SCD Loại 1 cho email/phone, SCD Loại 2 cho `tier`/`province`).

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `seller_name` | varchar | |
| `shop_name` | varchar | |
| `tier` | varchar | `Mall`, `Preferred`, `Normal` — track SCD2 |
| `province` | varchar | Track SCD2 khi đổi địa chỉ/kho |
| `city` | varchar | |
| `email` | varchar | |
| `phone` | varchar | |
| `status` | varchar | `Active`, `Suspended` |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

---

## 3. Nhóm Khách hàng (Customers)

### 3.1 `customers` (bổ sung)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `full_name` | varchar | |
| `email` | varchar | |
| `phone_number` | varchar | |
| `gender` | varchar | |
| `date_of_birth` | date | |
| `province` | varchar | Tỉnh/thành đăng ký |
| `city` | varchar | |
| `registration_date` | timestamp | |

### 3.2 `customer_addresses` (bổ sung)

Nhiều địa chỉ giao hàng / khách hàng.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `customer_id` | bigint, FK → `customers.id` | |
| `recipient_name` | varchar | |
| `phone` | varchar | |
| `address_detail` | varchar | |
| `ward` | varchar | |
| `district` | varchar | |
| `province` | varchar | |
| `is_default` | boolean | |

---

## 4. Nhóm Đơn hàng & Thanh toán

Nguồn trực tiếp cho `Fact_Order_Item` (grain: 1 dòng sản phẩm trong 1 đơn).

### 4.1 `channels` (bổ sung — chuẩn hoá)

Bảng tra cứu dùng chung, tránh text tự do rải rác ở nhiều bảng (`orders`,
`ad_spend_logs`, `marketing_campaigns`) → nguồn ổn định cho `Dim_Channel`.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | int, PK | |
| `channel_name` | varchar | `Web`, `App`, `Livestream`, ... |
| `channel_type` | varchar | Nhóm kênh, VD: `Online Owned`, `Social`, `Marketplace` |

### 4.2 `payment_methods` (bổ sung — chuẩn hoá)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | int, PK | |
| `method_name` | varchar | `COD`, `Momo`, `ZaloPay`, `Credit Card`, `Bank Transfer` |
| `method_group` | varchar | `COD`, `E-Wallet`, `Card`, `Bank Transfer` |

### 4.3 `orders` (bổ sung)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `order_code` | varchar, unique | |
| `customer_id` | bigint, FK → `customers.id` | |
| `seller_id` | bigint, FK → `sellers.id` | Đơn tách theo shop |
| `channel_id` | int, FK → `channels.id` | |
| `order_status` | varchar | `Pending`, `Processing`, `Completed`, `Cancelled` |
| `total_gross_amount` | decimal | |
| `total_discount_amount` | decimal | |
| `shipping_fee` | decimal | |
| `final_amount` | decimal | |
| `shipping_address_id` | bigint, FK → `customer_addresses.id` | |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

### 4.4 `order_items` (bổ sung)

Grain chính của `Fact_Order_Item`.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `order_id` | bigint, FK → `orders.id` | |
| `product_id` | bigint, FK → `products.id` | |
| `quantity` | int | |
| `unit_price` | decimal | Giá bán thực tế tại thời điểm mua |
| `discount_amount` | decimal | Giảm giá phân bổ trên dòng |
| `net_amount` | decimal | |
| `item_status` | varchar | **[bổ sung]** `Fulfilled`, `Cancelled`, `Returned` — vì trạng thái có thể khác cấp đơn |

### 4.5 `payments` (bổ sung)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `order_id` | bigint, FK → `orders.id` | |
| `payment_method_id` | int, FK → `payment_methods.id` | |
| `payment_status` | varchar | `Pending`, `Success`, `Failed` |
| `paid_amount` | decimal | |
| `transaction_time` | timestamp | |

---

## 5. Nhóm Khuyến mại (Promotions & Bridge)

Phục vụ kỹ thuật Bridge Table: một dòng hàng có thể áp dụng nhiều voucher.

### 5.1 `promotions` (bổ sung)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `promo_code` | varchar | |
| `promo_type` | varchar | `Platform Voucher`, `Seller Voucher` |
| `seller_id` | bigint, FK → `sellers.id`, nullable | **[bổ sung]** NULL = voucher sàn; có giá trị = voucher của seller đó |
| `discount_type` | varchar | `Fixed Amount`, `Percentage` |
| `discount_value` | decimal | |
| `min_order_value` | decimal | |
| `start_date` | timestamp | |
| `end_date` | timestamp | |

### 5.2 `order_item_promotions` (bổ sung)

Bảng nối M:N — nguồn trực tiếp cho Bridge Table trong DW.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `order_item_id` | bigint, FK → `order_items.id` | |
| `promotion_id` | bigint, FK → `promotions.id` | |
| `applied_discount_amount` | decimal | Số tiền giảm giá do voucher này áp dụng |

---

## 6. Nhóm Kho vận & Tồn kho

Phục vụ `Fact_Inventory_Snapshot` (grain: sản phẩm – kho – ngày).

### 6.1 `warehouses` (bổ sung)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | int, PK | |
| `warehouse_code` | varchar | |
| `warehouse_name` | varchar | |
| `province` | varchar | |
| `city` | varchar | |
| `address` | text | |

### 6.2 `inventory_levels` (bổ sung)

Trạng thái tồn kho **hiện tại** (giống OLTP thật: chỉ giữ state mới nhất).

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `warehouse_id` | int, FK → `warehouses.id` | |
| `product_id` | bigint, FK → `products.id` | |
| `quantity_on_hand` | int | |
| `quantity_reserved` | int | Hàng đang trong đơn chờ đóng gói |
| `updated_at` | timestamp | |

### 6.3 `inventory_movements` (bổ sung — **bắt buộc**)

Sổ cái giao dịch kho. Bắt buộc phải có vì `inventory_levels` chỉ cho biết số
lượng *hiện tại*, không đủ để dựng lại lịch sử tồn kho theo ngày cho
`Fact_Inventory_Snapshot`. ETL sẽ replay các dòng này để tính tồn kho tại mỗi
thời điểm trong quá khứ.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `warehouse_id` | int, FK → `warehouses.id` | |
| `product_id` | bigint, FK → `products.id` | |
| `movement_type` | varchar | `Import`, `Sale`, `Return`, `Adjustment` |
| `quantity_change` | int | Dương = nhập, âm = xuất |
| `movement_date` | timestamp | |

---

## 7. Nhóm Marketing & Quảng cáo

Phục vụ `Fact_Ad_Spend` (grain: chiến dịch – kênh – tháng).

### 7.1 `marketing_campaigns` (bổ sung)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | int, PK | |
| `campaign_code` | varchar | |
| `campaign_name` | varchar | |
| `channel_id` | int, FK → `channels.id` | |
| `budget_amount` | decimal | **[bổ sung]** Ngân sách kế hoạch — so sánh planned vs actual spend |
| `start_date` | date | |
| `end_date` | date | |

### 7.2 `ad_spend_logs` (bổ sung)

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | bigint, PK | |
| `campaign_id` | int, FK → `marketing_campaigns.id` | |
| `channel_id` | int, FK → `channels.id` | |
| `log_date` | date | Ghi nhận theo ngày; DW tổng hợp lên tháng |
| `cost_amount` | decimal | |
| `impressions` | bigint | |
| `clicks` | bigint | |

---

## 8. Hạ tầng crawler (không thuộc mô hình OLTP nghiệp vụ)

Các bảng sau phục vụ riêng cho crawler, không map trực tiếp vào DW:

- `product_checkpoints`: product ID, hash nội dung nguồn, first/last seen,
  last changed (UTC) — trạng thái dedup, không phải checkpoint phân trang.
- `product_raw`: JSON đầy đủ, mới nhất từ API cho mỗi product.
- `product_categories`: các cặp product/root/leaf category đã quan sát được.

---

## 9. ERD tổng thể

```text
[customers] ──< [customer_addresses]
     │
     v
[orders] >── [sellers] >── [products] >── [categories]
   │  │           │              │
   │  │           │              v
   │  │           │      [inventory_levels] >── [warehouses]
   │  │           │              │
   │  │           │      [inventory_movements]
   │  │           v
   │  │     [promotions] (seller_id nullable)
   │  │           ^
   │  v           │
   │ [order_items] ──< [order_item_promotions]
   │
   v
[payments] >── [payment_methods]

[orders] >── [channels] ──< [marketing_campaigns] ──< [ad_spend_logs]
```

## 10. Tổng hợp mapping sang Fact / Dimension

| Fact / Dimension | Nguồn OLTP |
|---|---|
| `Fact_Order_Item` | `order_items`, `orders`, `payments`, `order_item_promotions` |
| `Fact_Inventory_Snapshot` | `inventory_movements` (replay), `inventory_levels` (baseline) |
| `Fact_Ad_Spend` | `ad_spend_logs`, `marketing_campaigns` |
| `Dim_Seller` (SCD1/2) | `sellers` |
| `Dim_Customer` | `customers`, `customer_addresses` |
| `Dim_Channel` | `channels` |
| `Dim_Payment_Method` | `payment_methods` |
| `Dim_Promotion` + Bridge | `promotions`, `order_item_promotions` |
| `Dim_Warehouse` | `warehouses` |
| `Dim_Campaign` | `marketing_campaigns` |
| `Dim_Product` / `Dim_Category` | `products`, `categories` |
