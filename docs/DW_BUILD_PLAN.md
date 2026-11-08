# Kế hoạch xây dựng kho dữ liệu — Sàn TMĐT đa người bán (Nhóm 5)

Tài liệu này là kế hoạch thực thi chi tiết, bám theo:

- Đề xuất `DeXuat_KhoDuLieu_TMDT.pdf` (mục tiêu M1–M5, tiêu chí T1–T7, thí nghiệm BM01–BM03).
- Lộ trình 5 milestone (Inmon → Kimball → ETL/SCD → Kiểm thử/Blueprint).
- OLTP thực tế do Mock Studio sinh ra (`mock_oltp`, 33 bảng) và crawler Tiki (`data/tiki_crawl.db`).
- Đánh giá trong [FACT_REVIEW.md](FACT_REVIEW.md).

Ký hiệu trạng thái dữ liệu: ✅ đã đủ · ⚙️ cần bật hành động trong mock · 📝 ETL tự xử lý, phải ghi giả định.

---

## 0. Hiện trạng và ràng buộc

### 0.1. Nguồn dữ liệu đã có

| Nguồn | Vị trí | Ghi chú |
|---|---|---|
| OLTP mô phỏng | PostgreSQL `127.0.0.1:55432/mock_oltp` | 33 bảng, sinh theo ngày từ 01/01/2026, seed 42, ~100 lượt đặt/ngày |
| Crawler Tiki | SQLite `data/tiki_crawl.db` (đọc bản `data/tiki_crawl_share.db`) | 3.532 sản phẩm; `product_raw.primary_category_path` có cây danh mục sâu 4–8 cấp |
| Điều khiển mock | `mock_control`, API `http://127.0.0.1:8765/api/overview` | `last_day` = ngày cuối đã hoàn tất — dùng làm watermark |

Sinh dữ liệu chạy nền bằng [scripts/mock_runner/start_all.sh](../../../scripts/mock_runner/start_all.sh), ~15 phút/ngày mô phỏng.

### 0.2. Những điểm dữ liệu đã kiểm chứng

- `order_items.net_amount = quantity × unit_price − discount_amount` đúng 100%.
- `orders.final_amount = Σ net_amount + shipping_fee − shipping_discount_amount` đúng 100%.
- `inventory_daily_balance` = replay `inventory_movements` đúng 100%; 3.532/3.532 SKU map được sản phẩm.
- Tổng `order_item_promotions.applied_discount_amount` = `order_items.discount_amount`.
- 53% đơn là khách vãng lai (`orders.customer_id IS NULL`).

### 0.3. Khoảng trống phải xử lý

| # | Khoảng trống | Ảnh hưởng | Cách xử lý (bước) |
|---|---|---|---|
| G1 | `products.cost_price` NULL toàn bộ | `inventory_value`, biên lợi nhuận | 📝 Giá vốn theo tỷ lệ danh mục (R-PRD-05) — bước 4.5 |
| G2 | Hầu như không có thay đổi thuộc tính dimension | SCD1/2/3 (M2, T4) | ✅ Đã bật hành động mock từ 30/01 — bước 1.0 (riêng Product: không có đổi giá/danh mục) |
| G3 | Chi phí quảng cáo chỉ kênh WEB, 1 chiến dịch/tháng, ngân sách cạn sau ~10 ngày | Drill-across doanh thu–quảng cáo theo kênh | ✅ Từ 30/01: 3 kênh, ngân sách đủ tháng — bước 1.0 |
| G4 | OLTP rất sạch | Cách ly lỗi (M5, T2) | 📝 Chèn lỗi có kiểm soát ở `raw` — bước 4.3 |
| G5 | `categories` chỉ 2 cấp | Cây danh mục | ✅ Dựng từ `primary_category_path`, cắt tại danh mục OLTP: 77 nút, sâu 2–4 cấp (đo ở M1) — bước 4.6 |
| G6 | Seller Voucher chưa được dùng; mỗi dòng ≤ 1 voucher | Bridge nhiều voucher | ⚙️ Theo dõi; nếu thiếu, dùng ca kiểm thử ở `stg` |
| G7 | Engine không có hành động đổi giá | SCD2 giá, SCD3 giá trước | Chuyển SCD3 sang **hạng seller** |

### 0.4. Thời gian còn lại

Theo lịch học (hôm nay 07/11/2026): **10/11** nộp 5.1 (kiểm thử & tối ưu), **17/11** nộp 5.2 (Blueprint & slide). Milestone 1–4 trên lịch đã qua hạn nên kế hoạch dưới đây gói gọn trong **10 ngày** (mục 10). Ưu tiên phần **bắt buộc** của đề xuất; phần mở rộng làm sau.

---

## 1. Kiến trúc và môi trường

### 1.0. Việc làm ở phía nguồn — ✅ đã làm 07/11/2026

Chi tiết thực hiện: [docs/implementation/01_buoc-1.0_cau-hinh-mock-scd.md](../../implementation/01_buoc-1.0_cau-hinh-mock-scd.md).

Phiên bản cấu hình mới `dw-scd-2026.json` (sinh bằng `scripts/mock_runner/make_dw_scd_config.py`, không đổi code engine) áp dụng từ **30/01/2026**:

| Hành động | Mục đích | Tần suất |
|---|---|---|
| `SYS-03` Xét hạng thành viên | Mini-dimension / SCD2 hạng khách | 25/ngày |
| `CUS-02` Đổi nơi cư trú | SCD2 tỉnh khách | 3/ngày |
| `MGR-01` Xét hạng người bán | SCD2 + SCD3 hạng seller | 1/ngày |
| `SEL-03` Đổi địa điểm kinh doanh | SCD2 tỉnh seller | 1 lần / 4 ngày |
| `MGR-02` Khóa người bán | SCD2 trạng thái seller, sản phẩm ngừng bán | 4 lần/năm |
| `SEL-01` Đổi tên shop (tên tự sinh) | SCD1 seller | 1 lần / 10 ngày |
| `SEL-02` Đổi liên hệ shop (đã có) | SCD1 seller | 12 lần/năm |
| `MKT-01` | 3 chiến dịch WEB/APP/LIVESTREAM mỗi đợt, ngân sách 12 triệu/31 ngày | ngày 1 hằng tháng + ngày đôi |
| `ADS-01` | Báo cáo chi phí cho mỗi chiến dịch đang chạy | 4/ngày |

Không bật (đã kiểm tra code engine): `CUS-01`, `SEL-04` (để trống tên mới thì giữ nguyên tên → không tạo thay đổi); `CAT-01` (cần `SEL-08` gán mọi sản phẩm vào **một** danh mục cố định → không thực tế). Hệ quả: **Dim_Product không có thay đổi SCD2 giá/danh mục**; SCD2 sản phẩm chỉ có trạng thái bán (`is_active`, khi seller bị khóa). Phát hiện thêm: ngân sách chiến dịch cũ (3 triệu) cạn sau ~10 ngày nên tháng 1 chỉ có ~10 ngày chi phí quảng cáo kênh WEB.

### 1.1. Cơ sở dữ liệu kho — ✅ đã làm 07/11/2026

Chi tiết: [docs/implementation/02_buoc-1.1_khoi-tao-dwh.md](../../implementation/02_buoc-1.1_khoi-tao-dwh.md); SQL: [dw/sql/00_init/](../../../dw/sql/00_init/).

- Tạo database riêng **`dwh`** trong cùng container Postgres (không dùng `mock_oltp`/`mock_control`).
- Tạo role **`dw_reader`** chỉ có `SELECT` trên `mock_oltp` cho ETL; role **`dw_analyst`** chỉ đọc `dw`, `mart` (người dùng phân tích, Bảng 3).
- Schema logic theo đề xuất:

| Schema | Nội dung | Quy tắc |
|---|---|---|
| `raw` | Bản trích nguyên trạng từng batch (`raw.<bảng>` + `batch_id`) | Bất biến, chỉ INSERT |
| `stg` | Dữ liệu đã chuẩn hóa kiểu, ánh xạ mã, gắn cờ kiểm tra | Làm mới theo batch |
| `dw` | Dimension + Fact + Bridge | Chỉ nạp dữ liệu đạt kiểm tra |
| `mart` | View/MV phục vụ báo cáo, KPI dùng chung | Refresh sau mỗi batch thành công |
| `audit` | `batch_log`, `quarantine`, `reconciliation`, `dq_result` | Lịch sử nạp và lỗi |
| `bench` | Bản sao biến thể cho thí nghiệm | Không ảnh hưởng `mart` |

### 1.2. Cấu trúc repo đề xuất

```
dw/
├── sql/
│   ├── 00_init/        # database, role, schema
│   ├── 10_raw/         # DDL raw
│   ├── 20_stg/         # DDL stg + hàm chuẩn hóa
│   ├── 30_dw/          # DDL dimension, fact, bridge
│   ├── 40_mart/        # view, materialized view
│   ├── 50_audit/       # DDL audit
│   ├── 60_bench/       # BM01–BM03
│   └── 90_tests/       # truy vấn kiểm thử T1–T6
├── etl/
│   ├── config.yaml     # kết nối, watermark, danh sách bảng
│   ├── extract.py      # OLTP/SQLite → raw
│   ├── transform.py    # raw → stg, cách ly lỗi
│   ├── load_dims.py    # SCD1/2/3, mini-dim, cây danh mục
│   ├── load_facts.py   # fact + bridge
│   ├── reconcile.py    # đối soát
│   └── run_etl.py      # điều phối: --until YYYY-MM-DD, --rerun BATCH
├── bench/run_bench.py  # đo median/p95, lưu EXPLAIN JSON
└── dashboard/app.py    # Streamlit + Plotly
```

Công nghệ: Python 3.12, `psycopg`/SQLAlchemy, SQL thuần cho biến đổi; Streamlit, Plotly cho giao diện.

---

## 2. Milestone 1 — Khảo sát nguồn, chủ đề, quy tắc tích hợp

> ✅ Đã làm 07/11/2026. Sản phẩm M1 (bản chính thức, có số liệu đo): [M1_KHAO_SAT_NGUON_CHU_DE_TICH_HOP.md](M1_KHAO_SAT_NGUON_CHU_DE_TICH_HOP.md). Ghi chép: [docs/implementation/03_buoc-2_m1-khao-sat-nguon.md](../../implementation/03_buoc-2_m1-khao-sat-nguon.md). Phần dưới là kế hoạch gốc, đã sửa IR-04 và bổ sung IR-08..10 theo kết quả đo.

### 2.1. Bản đồ hệ thống nguồn (Sub-milestone 1.1)

| Hệ thống nguồn (OLTP) | Bảng chính | Grain nguồn | Dùng cho |
|---|---|---|---|
| Catalog & Seller | `products`, `categories`, `sellers`, `seller_commission_rates` + SQLite Tiki | Thực thể | Dim_Product, Dim_Category, Dim_Seller |
| Đơn hàng | `orders`, `order_items`, `payments`, `customers`, `customer_addresses`, `checkouts` | Dòng hàng | Fact_Order_Item, Dim_Customer |
| Kho vận | `inventory_daily_balance`, `inventory_movements`, `warehouses`, `shipments`, `carriers` | SKU–kho–ngày | Fact_Inventory_Snapshot |
| Marketing | `marketing_campaigns`, `ad_spend_logs`, `promotions`, `order_item_promotions`, `promotion_usages` | Chiến dịch–kênh–ngày | Fact_Ad_Spend, Bridge khuyến mãi |
| Clickstream | `sessions`, `page_events`, `cart_items` | Sự kiện | Ngoài phạm vi (đề xuất mục 2) |
| Tài chính | `seller_payouts`, `seller_payout_items`, `refunds`, `returns` | Kỳ / dòng | Mở rộng |

**Sản phẩm:** sơ đồ ranh giới OLTP ↔ DW (Hình 1 đề xuất, bổ sung `raw`), và đoạn phân tích vì sao không báo cáo trực tiếp trên OLTP:

- OLTP chỉ lưu trạng thái hiện tại (không có lịch sử hạng, tỉnh, danh mục).
- Khóa và mã không thống nhất giữa 6 hệ thống.
- Truy vấn tổng hợp dài hạn tranh tài nguyên với giao dịch (engine dùng advisory lock và transaction ngắn; đo được độ trễ khi chạy truy vấn nặng song song).

### 2.2. Chủ đề cốt lõi (Sub-milestone 1.2)

1. **Bán hàng** (đơn, dòng hàng, thanh toán, khuyến mãi) — quy trình trọng tâm.
2. **Sản phẩm & Người bán** (catalog, danh mục, hạng).
3. **Tồn kho** (kho, SKU, cuối ngày).
4. **Marketing** (chiến dịch, kênh, chi phí).

Khách hàng là chủ đề dùng chung của 1 và 4.

### 2.3. Quy tắc tích hợp (Sub-milestone 1.3) — tối thiểu 3 xung đột, ở đây có 6

| Mã | Xung đột thực tế | Quy tắc chuẩn hóa |
|---|---|---|
| IR-01 | Kho định danh sản phẩm bằng `sku`; đơn hàng dùng `product_id` | Khóa nghiệp vụ chuẩn = `product_id`; `stg.map_sku_product(sku → product_id)` từ `products.sku`; SKU không map được → cách ly |
| IR-02 | `shipments` nối đơn bằng `order_code`; các bảng khác dùng `order_id` | Chuẩn hóa về `order_id` qua `orders.order_code` |
| IR-03 | Marketing dùng `channel_code` `WEB`/`APP`/`LIVESTREAM` (engine thực tế; tài liệu OLTP_SCHEMA §10 ghi `MOBILE_APP`/`LIVE`); `channels.channel_name` là `Web`/`App`/`Livestream` | Bảng ánh xạ `stg.map_channel` nhận cả hai bộ mã (`WEB→Web`, `APP`/`MOBILE_APP→App`, `LIVESTREAM`/`LIVE→Livestream`); mã lạ → cách ly |
| IR-04 | OLTP `products.category_id` là danh mục **lá cấp 2** (= `leaf_category_id` của crawler, 3.532/3.532), cha là gốc; `primary_category_path` sâu hơn (bắt đầu `1/2` là gốc hệ thống Tiki) | Danh mục chuẩn = `products.category_id` OLTP (khớp `commission_category_id`). Cây = path bỏ 2 nút đầu, cắt tại danh mục OLTP → 77 nút, sâu 2–4, không nút 2 cha (đã đo ở [M1](M1_KHAO_SAT_NGUON_CHU_DE_TICH_HOP.md)) |
| IR-05 | Khách vãng lai không có `customer_id` | `Customer_Key = -1` (không áp dụng); khóa không tra được = `0` |
| IR-06 | Tiền là `decimal(24,6)` ở OLTP; giá là VND nguyên nhưng `discount_amount`/`net_amount` có phần lẻ khi giảm giá cấp đơn được phân bổ xuống dòng (26/1.474 dòng ngày 10/01) | Lưu tiền ở DW bằng `numeric(18,2)`, **không làm tròn** trước khi đối soát; chỉ làm tròn khi hiển thị |
| IR-07 | Thời gian UTC+7 không kèm múi giờ | Giữ nguyên `timestamp without time zone`, ghi rõ trong từ điển |
| IR-08 | Tỉnh/thành là tên tự do ở 4 bảng | `stg.map_province` → `province_code` + vùng (34 tỉnh) |
| IR-09 | Thiếu giới tính (14,9%), ngày sinh (25,6%) | `U`, `Không rõ`; không loại khách |
| IR-10 | `products.discount_rate` tính bằng phần trăm (0–62), `commission_rate` là tỷ lệ | Chuẩn mọi tỷ lệ về 0–1 |

### 2.4. Quy tắc lưu vết (Nonvolatile & Time-variant)

- `raw` chỉ INSERT; mỗi batch có `batch_id`, không sửa/xóa.
- `dw` không DELETE fact; sửa sai chỉ bằng batch bù có ghi audit.
- Dimension lưu lịch sử bằng SCD2 `[valid_from, valid_to)`, phiên bản hiện hành `valid_to = '9999-12-31'`, `is_current = true`.
- Vì OLTP không lưu lịch sử, **lịch sử được tạo bằng cách so sánh snapshot mỗi batch** (snapshot-diff CDC), thời điểm hiệu lực = đầu ngày của `updated_at` nguồn (quy tắc đề xuất mục 5).

**Sản phẩm M1:** bảng Data Integration Rules (2.3), bảng quy tắc lưu vết (2.4), sơ đồ nguồn (2.1).

---

## 3. Milestone 2 — Mức hạt và tháp phân tầng

> ✅ Đã làm 07/11/2026. Sản phẩm: [M2_GRAIN_PHAN_TANG.md](M2_GRAIN_PHAN_TANG.md) (grain đã kiểm chứng duy nhất; snapshot tồn kho **thưa** 86%; độ trễ hoàn tất 2–6 ngày). Ghi chép: [04_buoc-3_m2-grain-phan-tang.md](../../implementation/04_buoc-3_m2-grain-phan-tang.md).

### 3.1. Mức hạt atomic

| Fact | Grain | Khóa nghiệp vụ | Lý do |
|---|---|---|---|
| `Fact_Order_Item` | 1 dòng hàng của 1 đơn `Completed`, `item_status ∈ {Fulfilled, Returned}` | `(source_system, order_id, line_number)` | Chi tiết nhất có doanh thu; tổng hợp được mọi cấp |
| `Fact_Inventory_Snapshot` | 1 sản phẩm × 1 kho × cuối 1 ngày | `(product_id, warehouse_id, date)` | Trả lời "tồn tại ngày bất kỳ" |
| `Fact_Ad_Spend` | 1 chiến dịch × 1 kênh × 1 tháng | `(campaign_id, channel, month)` | Theo đề xuất; nguồn là ngày nên giữ thêm `stg` theo ngày |

Chốt các quyết định còn mở (FACT_REVIEW):

- **`Date_Key` = ngày `orders.completed_at`**; `Order_Date_Key` = ngày `orders.created_at` (role-playing).
- **`gross_amount = quantity × unit_price`**; `list_amount = quantity × list_price` (đo giảm giá niêm yết).
- **Phí ship** ở mức đơn, **không** vào `net_revenue`; lưu ở `mart.order_summary` (mở rộng).
- Dòng `Returned` vẫn nạp (đã bán), cờ `is_returned = true`, **không trừ** khỏi `net_revenue` (hoàn tiền từng phần ngoài phạm vi).
- Partition `Fact_Order_Item` theo **`Date_Key` (tháng hoàn tất)**; BM02 dùng đúng cột này.

### 3.2. Tháp phân tầng

```
Tầng 4  mart.kpi_quarter_*            (quý — ban điều hành)
Tầng 3  mart.mv_sales_month_category  (tháng × danh mục / seller / kênh)
        mart.mv_ads_month_channel     (tháng × kênh)
        mart.mv_inventory_month_product (tồn cuối tháng, trung bình ngày)
Tầng 2  mart.mv_sales_day_product     (ngày × sản phẩm × kênh)
Tầng 1  dw.fact_*                     (atomic)
Tầng 0  stg.* / raw.*                 (nguồn đã chuẩn hóa / nguyên trạng)
```

Quy tắc tổng hợp: chỉ cộng measure additive; tồn kho lấy cuối kỳ hoặc trung bình ngày; tỷ lệ (AOV, CTR, tỷ lệ giảm giá) tính lại từ tử và mẫu đã cộng (Bảng 11 đề xuất).

**Sản phẩm M2:** bản đặc tả atomic (3.1), sơ đồ tháp (3.2).

---

## 4. Milestone 3 — Mô hình chiều, Star/Galaxy Schema, từ điển dữ liệu

> ✅ Đã làm 07/11/2026 — cấu trúc đã tạo trong `dwh.dw`. Sản phẩm: [M3_THIET_KE_VAT_LY_STAR_SCHEMA.md](M3_THIET_KE_VAT_LY_STAR_SCHEMA.md), [M3_TU_DIEN_DU_LIEU.md](M3_TU_DIEN_DU_LIEU.md). Ghi chép: [05_buoc-4_m3-thiet-ke-vat-ly.md](../../implementation/05_buoc-4_m3-thiet-ke-vat-ly.md). Thay đổi so với bản nháp: bridge bỏ `allocated_discount` (D4); PK fact = khóa nghiệp vụ + `date_key` (D2).

### 4.1. Quy trình trọng tâm (Sub-milestone 3.1)

**Bán hàng**: khách đặt → thanh toán → giao thành công. Câu hỏi chính: doanh thu theo tháng/danh mục/seller/kênh; top sản phẩm/seller; ảnh hưởng voucher; doanh thu theo hạng seller và giá niêm yết tại thời điểm bán.

### 4.2. Dimension

Quy ước chung: surrogate key `*_key serial`; `-1` = không áp dụng, `0` = chưa xác định (2 dòng có sẵn ở mọi dimension); cột kỹ thuật `valid_from`, `valid_to`, `is_current`, `batch_id`.

| Dimension | Nguồn | Thuộc tính chính | Lịch sử |
|---|---|---|---|
| `dim_date` | Sinh 2025–2027 | date_key `yyyymmdd`, ngày, thứ, tuần, tháng, quý, năm, cờ cuối tuần, cờ ngày lễ VN, **cờ ngày đôi** (1/1…12/12) | Tĩnh |
| `dim_month` | Từ `dim_date` | month_key `yyyymm`, tháng, quý, năm | Tĩnh |
| `dim_product` | `products` + `map_sku_product` + cây danh mục | product_id, sku, tên, thương hiệu, category_key (lá), giá niêm yết (`price`), `original_price`, `unit_cost_est` | **SCD2**: giá niêm yết, danh mục, `is_active` · **SCD1**: tên, thương hiệu, mô tả. Lưu ý: nguồn mock hiện chỉ đổi `is_active` (khi seller bị khóa); logic SCD2 giá/danh mục vẫn cài và kiểm thử bằng ca có kiểm soát ở `stg` |
| `dim_category` | `primary_category_path` + `categories` | category_id, tên, parent_category_key, level, path, is_leaf | Phân cấp |
| `bridge_category_hierarchy` | Từ cây | ancestor_key, descendant_key, depth | Closure table |
| `dim_seller` | `sellers` | seller_id, shop_name, tỉnh, tier, status | **SCD2**: tier, tỉnh · **SCD1**: shop_name, email, phone |
| `dim_seller_tier_t3` | Từ `dim_seller` | seller_id, current_tier, previous_tier, tier_changed_on | **SCD3** (minh họa, bảng riêng) |
| `dim_customer` | `customers` | customer_id, tên, SĐT (che một phần), tỉnh, ngày đăng ký, giới tính | **SCD2**: tỉnh · **SCD1**: tên, SĐT, email |
| `dim_customer_profile` | Tính từ fact | membership_tier × spend_band_12m × frequency_band | **Mini-dimension** (tổ hợp bucket cố định) |
| `dim_channel` | `channels` + `map_channel` | channel_id, tên, mã marketing | Ít đổi |
| `dim_payment_method` | `payment_methods` | method, group (COD/E-Wallet/Card/Bank) | Ít đổi |
| `dim_promotion` | `promotions` | promo_code, loại (Platform/Seller/Freeship), apply_level, funded_by, hiệu lực | Ít đổi |
| `dim_warehouse` | `warehouses` | mã kho, tên, tỉnh | Ít đổi |
| `dim_campaign` | `marketing_campaigns` | mã, tên, loại, kênh đích, ngân sách, thời gian | Ít đổi |

### 4.3. Fact và Bridge

```sql
-- Fact_Order_Item (partition theo date_key / tháng)
dw.fact_order_item (
  order_item_sk      bigserial,
  source_system      text      not null default 'mock_oltp',
  order_id           bigint    not null,
  line_number        int       not null,
  order_code         text      not null,        -- degenerate
  date_key           int       not null,        -- ngày completed (FK dim_date)
  order_date_key     int       not null,        -- ngày đặt (role-playing)
  product_key        int       not null,        -- phiên bản tại thời điểm bán
  seller_key         int       not null,
  customer_key       int       not null,        -- -1: khách vãng lai
  customer_profile_key int     not null,
  channel_key        int       not null,
  payment_method_key int       not null,
  campaign_key       int       not null,        -- -1: không có chiến dịch
  promotion_group_key int      not null,        -- -1: không dùng voucher
  quantity           int       not null,
  list_price         numeric(18,2) not null, unit_price numeric(18,2) not null,
  list_amount        numeric(18,2) not null, gross_amount numeric(18,2) not null,
  list_discount_amount numeric(18,2) not null,
  discount_amount    numeric(18,2) not null,
  net_revenue        numeric(18,2) not null,
  commission_rate    numeric(6,4)  not null, commission_amount numeric(18,2) not null,
  is_returned        boolean   not null,
  batch_id           bigint    not null,
  primary key (date_key, order_item_sk),
  unique (source_system, order_id, line_number, date_key)
) partition by range (date_key);

-- Bridge khuyến mãi (nhóm = toàn bộ voucher của 1 dòng hàng)
dw.bridge_promotion_group (promotion_group_key, promotion_key, weighting_factor numeric(9,6))
-- Điều kiện: Σ weighting_factor = 1 mỗi group. Số tiền phân bổ = fact.discount_amount × weighting_factor
-- (không lưu ở bridge vì cùng một nhóm voucher dùng cho nhiều dòng có số tiền khác nhau — quyết định D4, M3).

-- Fact_Inventory_Snapshot (partition theo tháng)
dw.fact_inventory_snapshot (date_key, product_key, warehouse_key,
  quantity_on_hand int, quantity_reserved int, quantity_available int,
  qty_imported int, qty_sold int, qty_adjusted int,  -- từ inventory_movements
  stockout_flag smallint,
  inventory_value_est numeric(18,2),         -- on_hand × unit_cost_est (📝 G1)
  batch_id, primary key (date_key, product_key, warehouse_key)) partition by range (date_key);

-- Fact_Ad_Spend (tháng; nguồn ngày giữ ở stg)
dw.fact_ad_spend (month_key, campaign_key, channel_key,
  cost_amount numeric(18,2), impressions bigint, clicks bigint, active_days int,
  batch_id, primary key (month_key, campaign_key, channel_key));
```

Quy tắc tra phiên bản dimension cho fact: `valid_from ≤ thời điểm phát sinh < valid_to`, với thời điểm phát sinh = `orders.completed_at` (Product, Seller, Customer); `customer_profile_key` dùng **trạng thái trước giao dịch**.

### 4.4. Ma trận Bus

| Dimension | Fact_Order_Item | Fact_Inventory_Snapshot | Fact_Ad_Spend |
|---|---|---|---|
| Date | ✔ (2 vai trò) | ✔ | — |
| Month | ✔ (qua Date) | ✔ (qua Date) | ✔ |
| Product (+ Category) | ✔ | ✔ | — |
| Seller | ✔ | (qua Product) | — |
| Customer + Profile | ✔ | — | — |
| Channel | ✔ | — | ✔ |
| Payment_Method | ✔ | — | — |
| Promotion (Bridge) | ✔ | — | — |
| Warehouse | — | ✔ | — |
| Campaign | ✔ | — | ✔ |

### 4.5. Giả định giá vốn (G1)

`unit_cost_est = round_1000(price × cost_ratio(nhóm danh mục))`, với `cost_ratio` lấy từ bảng nhóm danh mục trong [DATA_GENERATION_RULES.md](../oltp/DATA_GENERATION_RULES.md) (R-PRD-05). Lưu ở `stg.product_cost_assumption` có `valid_from` để theo SCD2 cùng giá. Mọi báo cáo dùng `inventory_value_est` ghi chú "giá trị ước tính theo giả định giá vốn".

### 4.6. Cây danh mục (G5)

1. Đọc `product_raw.primary_category_path` (SQLite, chế độ chỉ đọc) → tách nút, **bỏ 2 nút đầu `1/2`** (gốc hệ thống Tiki), **cắt tại `products.category_id` của OLTP** (IR-04).
2. Tên nút: lấy từ `categories` (gốc, lá) và `product_categories`; nút trung gian chưa có tên → crawl `/api/v2/categories/{id}` một lần (tùy chọn) hoặc hiển thị `Danh mục {id}`.
3. Sinh `dim_category` (một cha) và `bridge_category_hierarchy` (closure).
4. Kiểm tra: không chu trình; mỗi nút đúng một cha; tổng doanh thu cây con = tổng doanh thu các lá thuộc cây (không cộng lặp).

### 4.7. Từ điển dữ liệu (Sub-milestone 3.3)

Bảng `audit.data_dictionary` (và xuất Markdown): `schema, table, column, data_type, mô tả, nguồn (bảng.cột OLTP), quy tắc biến đổi, additive/semi/non, SCD type, ví dụ`. Sinh khung tự động từ `information_schema`, điền mô tả thủ công.

### 4.8. Đặc tả chi tiết measure

Quy ước:

- **Tính cộng:** **A** = additive (cộng được theo mọi dimension); **SA** = semi-additive (cộng được theo một số dimension, **không** cộng theo thời gian); **NA** = non-additive (không cộng; phải tính lại từ tử và mẫu đã tổng hợp).
- **Tiền:** VND, kiểu `numeric(18,2)`, không làm tròn trong DW (IR-06); chỉ làm tròn khi hiển thị.
- **NULL:** measure lưu trữ không được NULL. Nếu nguồn thiếu giá trị → cách ly (DQ-01/02), không tự điền 0.
- Ký hiệu nguồn: `oi` = `order_items`, `o` = `orders`, `idb` = `inventory_daily_balance`, `im` = `inventory_movements`, `asl` = `ad_spend_logs`.

#### 4.8.1. `Fact_Order_Item` — measure lưu trữ

Grain: 1 dòng hàng của 1 đơn `Completed`, `oi.item_status ∈ {Fulfilled, Returned}`.

| Measure | Ý nghĩa | Công thức / nguồn | Kiểu | Cộng | Ràng buộc kiểm tra |
|---|---|---|---|---|---|
| `quantity` | Số món bán trên dòng | `oi.quantity` | `int` | A | `> 0` (hiện 1–2 món/dòng, TB 1,18) |
| `list_price` | Giá niêm yết tại lúc đặt | `oi.list_price` | `numeric` | **NA** (đơn giá) | `≥ unit_price` (300/1.474 dòng có giá niêm yết cao hơn giá bán) |
| `unit_price` | Giá bán thực tế / 1 món, trước voucher | `oi.unit_price` | `numeric` | **NA** (đơn giá) | `> 0`; ngoài flash sale `≥ cost × 1,02` (R-PRC-04, chỉ kiểm khi có giá vốn) |
| `list_amount` | Thành tiền theo giá niêm yết | `quantity × list_price` | `numeric` | A | `≥ gross_amount` |
| `gross_amount` | Doanh thu gộp trước voucher | `quantity × unit_price` | `numeric` | A | `> 0` |
| `list_discount_amount` | Giảm giá niêm yết của seller (markdown) | `list_amount − gross_amount` | `numeric` | A | `≥ 0` |
| `discount_amount` | Giảm giá voucher phân bổ vào dòng (sàn + seller; **không** gồm freeship) | `oi.discount_amount` | `numeric` | A | `0 ≤ discount ≤ gross`; `= Σ order_item_promotions.applied_discount_amount` ở stg (DQ-16); `Σ weight = 1` (RC-03) |
| `net_revenue` | **Doanh thu thuần** của dòng | `gross_amount − discount_amount` (= `oi.net_amount`) | `numeric` | A | `= oi.net_amount` từng dòng (DQ-03) |
| `commission_rate` | Tỷ lệ hoa hồng sàn áp lúc bán | `oi.commission_rate` (snapshot từ `seller_commission_rates` theo danh mục × hạng seller) | `numeric(6,4)` | **NA** | `0 ≤ rate ≤ 1` (hiện 4–6%) |
| `commission_amount` | Hoa hồng sàn thu trên dòng | `net_revenue × commission_rate` | `numeric` | A | `≤ net_revenue` |
| `seller_net_amount` | Phần seller được nhận trước hoàn | `net_revenue − commission_amount` | `numeric` | A | Đối chiếu `seller_payout_items` (mở rộng) |
| `cost_amount_est` 📝 | Giá vốn ước tính | `quantity × unit_cost_est` (4.5, phiên bản giá vốn tại `completed_at`) | `numeric` | A | Ghi chú "ước tính" |
| `gross_margin_est` 📝 | Lãi gộp ước tính | `net_revenue − cost_amount_est` | `numeric` | A | Có thể âm (flash sale, S-PRC-05) |
| `is_returned` | Cờ dòng đã trả hàng | `oi.item_status = 'Returned'` | `boolean` | — (dùng `COUNT FILTER`) | Không trừ khỏi `net_revenue` (3.1) |
| `line_count` | Đếm dòng (factless) | hằng `1` | `smallint` | A | Tiện cho số món/số dòng |

Không lưu ở dòng (cấp đơn, không chia được an toàn): `shipping_fee`, `shipping_discount_amount`, `final_amount` → để ở `mart.order_summary` (grain đơn) cho báo cáo phí ship; **không** cộng vào `net_revenue`.

#### 4.8.2. `Fact_Order_Item` — measure dẫn xuất (tính ở `mart`, không lưu)

| KPI | Công thức đúng | Sai thường gặp cần tránh |
|---|---|---|
| Doanh thu thuần | `SUM(net_revenue)` | Cộng `o.final_amount` (lẫn phí ship, nhân bản khi join dòng) |
| Doanh thu gộp | `SUM(gross_amount)` | — |
| Số đơn | `COUNT(DISTINCT (source_system, order_id))` | `COUNT(*)` (đếm dòng) |
| Số món | `SUM(quantity)` | — |
| AOV | `SUM(net_revenue) / COUNT(DISTINCT order_id)` tại đúng grain đang xem | Trung bình của AOV theo ngày |
| Giá bán bình quân | `SUM(gross_amount) / SUM(quantity)` | `AVG(unit_price)` |
| Tỷ lệ giảm giá voucher | `SUM(discount_amount) / SUM(gross_amount)` | Trung bình tỷ lệ từng dòng |
| Tỷ lệ giảm giá niêm yết | `SUM(list_discount_amount) / SUM(list_amount)` | — |
| Tỷ lệ hoa hồng hiệu dụng | `SUM(commission_amount) / SUM(net_revenue)` | `AVG(commission_rate)` |
| Tỷ lệ trả hàng (theo món) | `SUM(quantity) FILTER (WHERE is_returned) / SUM(quantity)` | — |
| Số khách mua | `COUNT(DISTINCT customer_key) FILTER (WHERE customer_key > 0)` | Đếm cả `-1` (khách vãng lai) |
| Tỷ trọng đơn khách vãng lai | `COUNT(DISTINCT order_id) FILTER (WHERE customer_key = -1) / số đơn` | — |
| Biên lãi gộp ước tính 📝 | `SUM(gross_margin_est) / SUM(net_revenue)` | — |
| Doanh thu theo voucher (qua bridge) | `SUM(f.discount_amount × b.weighting_factor)` theo `promotion_key`; doanh thu có voucher: `SUM(net_revenue)` trên các group có voucher | `SUM(net_revenue)` sau khi join bridge **không** nhân weight (nhân bản khi dòng có 2 voucher) |

#### 4.8.3. `Fact_Inventory_Snapshot` — measure lưu trữ

Grain: 1 sản phẩm × 1 kho × cuối 1 ngày. Nguồn `idb` (đã khớp 100% với replay `im`).

| Measure | Ý nghĩa | Công thức / nguồn | Kiểu | Cộng | Ràng buộc |
|---|---|---|---|---|---|
| `quantity_on_hand` | Tồn vật lý cuối ngày | `idb.quantity_on_hand` | `int` | **SA**: cộng theo kho, sản phẩm, danh mục; **không** cộng theo ngày | `≥ 0`; = tồn hôm trước + Σ `im.quantity_change` trong ngày (RC-04) |
| `quantity_reserved` | Đã giữ cho đơn chưa xuất | `idb.quantity_reserved` | `int` | **SA** | `0 ≤ reserved ≤ on_hand` (hiện ~150/18.256 dòng có giữ hàng) |
| `quantity_available` | Có thể bán | `on_hand − reserved` | `int` | **SA** | `≥ 0` |
| `qty_imported` | Nhập trong ngày | `Σ im.quantity_change` với `movement_type='Import'` (dương) | `int` | **A** (dòng chảy, cộng theo ngày được) | `≥ 0` |
| `qty_sold` | Xuất bán trong ngày | `−Σ im.quantity_change` với `movement_type='Sale'` (nguồn âm → lưu dương) | `int` | **A** | `≥ 0` |
| `qty_adjusted` | Điều chỉnh (hỏng, kiểm kê) | `Σ im.quantity_change` với `movement_type='Adjustment'` (giữ dấu) | `int` | **A** | Có thể âm |
| `stockout_flag` | Hết hàng cuối ngày | `1` nếu `quantity_available = 0` | `smallint` | A (đếm ngày hết hàng) | — |
| `inventory_value_est` 📝 | Giá trị tồn ước tính | `quantity_on_hand × unit_cost_est` (giá vốn có hiệu lực tại ngày snapshot) | `numeric` | **SA** | Ghi chú "ước tính" |

Dẫn xuất (ở `mart`):

| KPI | Công thức | Ghi chú |
|---|---|---|
| Tồn cuối kỳ (tháng/quý) | `quantity_on_hand` tại `MAX(date_key)` của kỳ, rồi cộng theo kho/sản phẩm | Không `SUM` qua ngày |
| Tồn bình quân kỳ | `AVG` theo ngày của `SUM(on_hand)` mỗi ngày | Tính trên tổng từng ngày, không trung bình từng dòng |
| Số ngày hết hàng | `SUM(stockout_flag)` theo sản phẩm–kho | — |
| Vòng quay tồn kho | `SUM(qty_sold kỳ) / tồn bình quân kỳ` | Hoặc dùng `Fact_Order_Item.quantity` theo cùng sản phẩm–kỳ (drill-across) |
| Số ngày tồn (days of supply) | `tồn cuối kỳ / (SUM(qty_sold kỳ) / số ngày kỳ)` | `NULL` nếu không bán |
| Tỷ lệ đáp ứng | `1 − SUM(stockout_flag) / số dòng` | — |

Đối chiếu hai nguồn bán hàng: `SUM(qty_sold)` theo ngày xuất kho **khác** `SUM(Fact_Order_Item.quantity)` theo ngày hoàn tất (lệch thời gian + đơn hủy sau xuất). Báo cáo đối soát doanh thu–tồn kho phải ghi rõ hai mốc thời gian.

#### 4.8.4. `Fact_Ad_Spend` — measure lưu trữ

Grain: 1 chiến dịch × 1 kênh × 1 tháng (gộp từ `asl` theo ngày).

| Measure | Ý nghĩa | Công thức / nguồn | Kiểu | Cộng | Ràng buộc |
|---|---|---|---|---|---|
| `cost_amount` | Chi phí quảng cáo | `Σ asl.cost_amount` | `numeric` | A | `≥ 0`; `= Σ` nguồn (RC-05) |
| `impressions` | Lượt hiển thị | `Σ asl.impressions` | `bigint` | A | `≥ clicks` (ràng buộc nguồn) |
| `clicks` | Lượt nhấp | `Σ asl.clicks` | `bigint` | A | `≥ 0` |
| `active_days` | Số ngày có chi phí trong tháng | `COUNT(DISTINCT asl.log_date)` | `int` | A theo chiến dịch/kênh; **không** cộng chéo chiến dịch để ra "số ngày chạy" | `≤` số ngày của tháng |
| `budget_amount` | Ngân sách chiến dịch | **Không lưu ở fact** — thuộc tính `dim_campaign` | — | — | Tránh nhân bản ngân sách theo tháng |

Dẫn xuất (ở `mart`):

| KPI | Công thức | Ghi chú |
|---|---|---|
| CTR | `SUM(clicks) / SUM(impressions)` | NA, tính lại từ tổng |
| CPC | `SUM(cost_amount) / SUM(clicks)` | NA |
| CPM | `SUM(cost_amount) / SUM(impressions) × 1000` | NA |
| Doanh thu / chi phí QC (tháng–kênh) | `SUM(net_revenue)` (Fact_Order_Item gộp tháng–kênh) / `SUM(cost_amount)` | Drill-across bằng FULL OUTER JOIN (6.2); chỉ là tỷ số tham khảo, không chứng minh nhân quả |
| ROAS theo chiến dịch (mở rộng) | `SUM(net_revenue) FILTER (WHERE campaign_key = c) / cost chiến dịch c` | Dùng `o.campaign_id`; ghi rõ là attribution theo đơn |
| Tỷ lệ dùng ngân sách | `SUM(cost_amount) / dim_campaign.budget_amount` | Tính theo chiến dịch, trên toàn thời gian chạy |

#### 4.8.5. Bridge khuyến mãi — measure phân bổ

| Cột | Công thức | Kiểm tra |
|---|---|---|
| `weighting_factor` | `oip.applied_discount_amount / Σ applied_discount_amount` trong cùng `order_item_id` | `Σ weight = 1` mỗi group (sai số ≤ 1e-6) |
| Tiền phân bổ (khi truy vấn) | `fact.discount_amount × weighting_factor` | `Σ` theo nhóm `= fact.discount_amount` (RC-03); đối chiếu `oip.applied_discount_amount` ở stg (DQ-16) |
| Dòng không voucher | `promotion_group_key = -1`, không có dòng bridge | Không bị loại khi báo cáo "có/không voucher" |

#### 4.8.6. Measure của các fact mở rộng (vòng xoắn 2–4, tóm tắt)

| Fact | Measure | Công thức | Cộng |
|---|---|---|---|
| `Fact_Order_Fulfillment` | `hours_to_pay`, `hours_to_ship`, `hours_to_deliver`, `hours_order_to_complete` | Hiệu các mốc (`payments.transaction_time`, `shipments.picked_at`, `delivered_at`, `o.completed_at` − `o.created_at`) | NA (dùng AVG/percentile) |
| | `delivery_attempt_count`, `is_failed_delivery`, `is_cancelled` | `COUNT(delivery_attempts)`, cờ | A |
| | `shipping_cost`, `shipping_fee`, `final_amount` | từ `shipments`, `orders` | A |
| `Fact_Return` | `return_quantity`, `refund_amount`, `days_to_request`, `days_to_refund` | `returns.quantity`, `returns.refund_amount`, hiệu ngày | A / A / NA / NA |
| `Fact_Seller_Settlement` | `gross_amount`, `refund_amount`, `commission_amount`, `net_payout` | `seller_payout_items.*` | A |

#### 4.8.7. Kiểm thử measure (bổ sung vào `sql/90_tests`)

1. Từng dòng: `net_revenue = gross_amount − discount_amount`, `gross_amount = quantity × unit_price`, `list_amount ≥ gross_amount`.
2. Tổng: Σ `net_revenue` fact = Σ `oi.net_amount` hợp lệ (RC-01); Σ `cost_amount` = Σ `asl.cost_amount` (RC-05).
3. Semi-additive: báo cáo tồn quý = tồn ngày cuối quý (so với truy vấn độc lập), khác `SUM` qua ngày.
4. Non-additive: AOV, CTR, tỷ lệ giảm giá ở cấp tháng tính lại từ tử/mẫu bằng đúng giá trị khi tính trực tiếp từ fact atomic.
5. Bridge: tổng doanh thu theo voucher có nhân weight = tổng doanh thu các dòng có voucher.

**Sản phẩm M3:** DDL `sql/30_dw`, sơ đồ Galaxy (vẽ lại Hình 2 với đủ key), bus matrix, từ điển dữ liệu.

---

## 5. Milestone 4 — ETL và SCD

### 5.1. Luồng tổng thể của một batch

```
run_etl.py --until <last_day>
 ├─ B0  Mở batch: audit.batch_log(status=RUNNING, watermark_from, watermark_to)
 ├─ B1  Extract  OLTP/SQLite → raw.*      (incremental theo watermark; checksum từng bảng)
 ├─ B2  Transform raw → stg.*             (T1–T10: ép kiểu, ánh xạ IR-01..07, DQ-01..20 — mục 5.3)
 │       └─ bản ghi lỗi → audit.quarantine(batch_id, table, key, rule, reason, payload)
 ├─ B3  Load dimension                    (SCD1 → SCD2 → SCD3 → mini-dim → category)
 ├─ B4  Load fact + bridge                (tra key theo thời điểm; -1/0; upsert theo khóa nghiệp vụ)
 ├─ B5  Đối soát                          (audit.reconciliation: nguồn hợp lệ = stg = fact)
 ├─ B6  Refresh mart (MV)                 (chỉ khi B5 đạt)
 └─ B7  Đóng batch: status=SUCCESS / FAILED; dữ liệu dở dang không công bố
```

Toàn bộ B3–B4 chạy trong một transaction; lỗi → rollback, `mart` giữ bản cũ và hiển thị "dữ liệu cũ" (đề xuất mục 3).

### 5.2. Extract (B1)

> ✅ Đã làm 07/11/2026 — [dw/etl/extract.py](../../../dw/etl/extract.py); ghi chép [06_buoc-5.2_extract.md](../../implementation/06_buoc-5.2_extract.md). Đọc mọi bảng trong 1 snapshot `REPEATABLE READ READ ONLY`; `raw` bất biến bằng trigger; nạp lại cùng mốc cho checksum trùng 19/19 bảng.

- Watermark = `last_day` đã hoàn tất của mock (đọc API `/api/overview`); **không** đọc ngày đang chạy.
- Bảng giao dịch: lấy theo cửa sổ thời gian (`created_at`, `updated_at`, `completed_at`, `balance_date`, `log_date`) trong `(watermark_from, watermark_to]`.
- Bảng con không có cột thời gian (`order_items`, `order_item_promotions`, `checkout_lines`) được trích **theo khóa cha**: mọi dòng thuộc các `order_id` đã trích trong batch (đơn có `created_at`/`updated_at`/`completed_at` trong cửa sổ). `payments` trích theo `order_id` tương tự, để có đủ payment của đơn hoàn tất muộn.
- Bảng dimension: **full snapshot** mỗi batch (bảng nhỏ: sellers 481, customers ~10–30 nghìn, products 3.532) để so sánh SCD.
- `raw.<bảng>` có thêm `batch_id`, `extracted_at`, `row_hash` (md5 nội dung); `audit.batch_log` ghi số dòng và checksum từng bảng.
- Kết nối bằng `dw_reader` (chỉ đọc), truy vấn ngoài giờ cao điểm hoặc mỗi vài giờ để không làm chậm mock.

### 5.3. Transform (B2): `raw` → `stg`, kiểm tra và cách ly

> ✅ Đã làm 07/11/2026 — [dw/etl/transform.py](../../../dw/etl/transform.py), [dw/sql/20_stg/201_stg.sql](../../../dw/sql/20_stg/201_stg.sql), ánh xạ [dw/etl/mappings/](../../../dw/etl/mappings/); ghi chép [07_buoc-5.3_transform.md](../../implementation/07_buoc-5.3_transform.md). Điều chỉnh khi làm: DQ-06 (ngoài cửa sổ) xử lý bằng **hoãn sang batch sau** thay vì cách ly; thêm DQ-21, DQ-22; thêm measure `qty_returned`; Extract trích thêm đơn có payment đến muộn.

Transform chạy **sau** Extract của cùng `batch_id`, đọc **chỉ** `raw.*` của batch đó (không đọc lại OLTP), ghi `stg.*`, `audit.quarantine`, `audit.dq_result`. Toàn bộ là SQL set-based (một câu `INSERT … SELECT` cho mỗi bước), Python chỉ điều phối và ghi audit. Mỗi bảng `stg` có cột kỹ thuật: `batch_id`, `source_system` (`mock_oltp` | `tiki_crawl`), `source_pk`, `row_hash`, `dq_status` (`VALID` | `WARN`), `transformed_at`.

#### 5.3.1. Các bước của Transform (áp dụng cho mọi bảng)

| Bước | Tên | Việc làm | Kết quả |
|---|---|---|---|
| T1 | Profiling batch | Đếm dòng, NULL theo cột, min/max ngày, số khóa trùng trong `raw` của batch | `audit.dq_result` (mức batch) |
| T2 | Ép kiểu & làm sạch cú pháp | `decimal(24,6)` → `numeric(18,2)` (tiền), `int`; `trim()`, chuẩn hóa khoảng trắng, chuỗi rỗng `''` → `NULL`; Unicode NFC cho tiếng Việt; timestamp giữ `without time zone` (UTC+7, IR-07) | Cột đã đúng kiểu |
| T3 | Chuẩn hóa giá trị | Ánh xạ danh mục giá trị (kênh, phương thức thanh toán, tỉnh, giới tính, trạng thái…) qua bảng `stg.map_*` | Mã chuẩn duy nhất |
| T4 | Tích hợp khóa | Áp IR-01..IR-05: `sku → product_id`, `order_code → order_id`, `channel_code → channel_id`, danh mục lá, khách vãng lai | Khóa nghiệp vụ chuẩn |
| T5 | Dẫn xuất cột | Tính measure dẫn xuất ở 4.8 (gross, list_amount, list_discount, commission_amount, qty_sold…), khóa ngày `yyyymmdd` | Cột sẵn để nạp |
| T6 | Kiểm tra quy tắc DQ | Chạy các quy tắc DQ-xx (5.3.4) | Cờ lỗi theo dòng |
| T7 | Cách ly | Dòng vi phạm quy tắc mức **ERROR** → `audit.quarantine` (kèm `rule_code`, `reason`, `payload jsonb`); mức **WARN** → vẫn vào `stg`, `dq_status='WARN'` | Chỉ dòng hợp lệ vào `stg` |
| T8 | Khử trùng lặp | Theo khóa nghiệp vụ trong batch: giữ bản `updated_at` mới nhất (`row_number() over (partition by key order by updated_at desc, source_pk desc)`), bản bị loại ghi `WARN DQ-07` | Mỗi khóa 1 dòng |
| T9 | Chuẩn bị SCD | Với dimension: tính `scd1_hash` (cột SCD1) và `scd2_hash` (cột SCD2), `effective_date = date(updated_at)` | Dùng ở B3 |
| T10 | Kiểm đếm | `đọc = hợp lệ + WARN + cách ly + trùng bị loại` (RC-07); ghi số liệu vào `audit.batch_log` | Batch đủ điều kiện sang B3 |

Nếu T10 lệch, hoặc tỷ lệ cách ly của một bảng vượt ngưỡng (`> 5%` dòng, cấu hình được) → batch `FAILED`, không nạp `dw`, `mart` giữ bản cũ.

#### 5.3.2. Bảng ánh xạ (`stg.map_*`) dùng ở T3–T4

| Bảng ánh xạ | Nguồn → Chuẩn | Ghi chú |
|---|---|---|
| `map_channel` | `asl.channel_code`, `marketing_campaigns.target_channel_code`: `WEB→1 Web`, `APP`/`MOBILE_APP→2 App`, `LIVESTREAM`/`LIVE→3 Livestream`; `channels.channel_name` → cùng `channel_id` | Mã ngoài bảng → cách ly DQ-04 |
| `map_payment_method` | `payment_methods.method_name` → `method_group` (`COD`, `E-Wallet`, `Card`, `Bank Transfer`) | 5 phương thức hiện có |
| `map_province` | Tên tỉnh nguồn (`TP. Hồ Chí Minh`, `Hà Nội`, `Đà Nẵng`, `Cần Thơ`…) → `province_code` + `region` (Bắc/Trung/Nam) theo mô hình 34 tỉnh `new_34` | Dùng chung cho khách, seller, kho, địa chỉ; biến thể chính tả (`TPHCM`, `Ho Chi Minh`) map về cùng mã |
| `map_gender` | `Male→M`, `Female→F`, `NULL→U` (Unknown) | Hiện 15% khách không có giới tính |
| `map_order_status` | `Pending`, `Processing`, `Completed`, `Cancelled` → nhóm `OPEN` / `DONE` / `CANCELLED` | Dùng ở lọc fact |
| `map_sku_product` | `products.sku → products.id` (duy nhất) | 3.532/3.532 SKU hiện map được |
| `map_category_path` | `product_raw.primary_category_path` (bỏ `1/2`, cắt tại `products.category_id`) → danh sách tổ tiên | Từ SQLite crawler (4.6, IR-04) |
| `map_cost_ratio` 📝 | nhóm danh mục gốc → `cost_ratio` (R-PRD-05) | Cho `unit_cost_est` (4.5) |

Các bảng ánh xạ có `valid_from` và được quản lý bằng file CSV trong repo (`etl/mappings/*.csv`) → thay đổi ánh xạ có lịch sử git, tái lập được (T7).

#### 5.3.3. Transform theo từng bảng `stg`

**(a) `stg.product` — nguồn `raw.products` + `raw.tiki_product_raw` + `raw.tiki_product_categories`**

| Cột `stg` | Nguồn & biến đổi |
|---|---|
| `product_id`, `sku` | `products.id`, `trim(sku)` |
| `product_name` | `trim`, gộp khoảng trắng; giữ nguyên chữ hoa/thường |
| `brand_name` | `trim`; rỗng → `'Không rõ thương hiệu'` (WARN) |
| `list_price` | `products.price` → `numeric(18,2)` |
| `original_price` | `coalesce(original_price, price)` |
| `discount_rate` | Nguồn ở **phần trăm** (`44.0`) → chuẩn về **tỷ lệ** `0.44` |
| `seller_id` | `products.seller_id` |
| `leaf_category_id` | `products.category_id` (IR-04: lá cấp 2 của OLTP, cũng là danh mục tính hoa hồng) |
| `root_category_id`, `category_path` | `categories.parent_id` của lá; chuỗi nút từ `map_category_path` |
| `unit_cost_est` 📝 | `round(list_price × cost_ratio / 1000) × 1000` (theo `map_cost_ratio`) |
| `is_active` | `coalesce(is_active, false)` (là cờ hiển thị, không phải tồn kho) |
| `updated_at`, `effective_date` | `updated_at`; `date(updated_at)` |
| `scd1_hash` | `md5(product_name ‖ brand_name ‖ short_description)` |
| `scd2_hash` | `md5(list_price ‖ leaf_category_id)` |

Bỏ qua (không đưa vào DW): `thumbnail_url`, `url_*`, `stock_item`, `type`, `inventory_status` (rỗng hoặc ngoài phạm vi phân tích).

**(b) `stg.category` — nguồn `raw.categories` + `map_category_path`**

1. Tách mọi đường dẫn thành cặp `(parent_id, child_id)`; hợp với `categories.parent_id`.
2. Tên: `categories.category_name` nếu có; nếu không → tên từ API Tiki (nếu đã crawl) hoặc `'Danh mục ' ‖ id` (WARN DQ-12).
3. Kiểm tra mỗi nút đúng một cha (DQ-13) và không có chu trình (DQ-14, CTE đệ quy với giới hạn độ sâu 10).
4. Sinh `level`, `is_leaf`, `path_text` (`Nhà Cửa > Nội thất > …`).

**(c) `stg.seller` — nguồn `raw.sellers`**

| Cột | Biến đổi |
|---|---|
| `seller_id`, `shop_name`, `seller_name` | `trim`, NFC |
| `tier` | Chuẩn hóa `{Mall, Preferred, Normal}`; giá trị khác → cách ly DQ-04 |
| `province_code`, `region` | `map_province(province)` |
| `status` | `{Active, Suspended…}`; dùng làm thuộc tính SCD2 |
| `email`, `phone` | Kiểm định dạng (DQ-08, WARN); không dùng làm khóa |
| `scd1_hash` | `md5(shop_name ‖ seller_name ‖ email ‖ phone)` |
| `scd2_hash` | `md5(tier ‖ province_code ‖ status)` |

**(d) `stg.customer` — nguồn `raw.customers`**

| Cột | Biến đổi |
|---|---|
| `customer_id` | `customers.id` (khách vãng lai không có dòng — xử lý ở fact bằng key `-1`) |
| `full_name` | `trim`, NFC |
| `phone_masked` | Giữ 3 số đầu + 3 số cuối (`035****266`); số gốc chỉ dùng tính `scd1_hash`, không lưu DW (bảo vệ dữ liệu cá nhân) |
| `email_domain` | Phần sau `@` (phân tích), email gốc không lưu |
| `gender` | `map_gender` (`U` khi NULL) |
| `birth_year`, `age_band` | `extract(year from date_of_birth)`; nhóm `18–24 / 25–34 / 35–44 / 45+ / Không rõ` (26% NULL → `Không rõ`) |
| `province_code`, `region` | `map_province(province)` |
| `membership_tier` | `{Member, Silver, Gold…}` — dùng cho **mini-dimension**, không SCD2 trong `dim_customer` |
| `registration_date` | `date(registration_date)` |
| `scd1_hash` | `md5(full_name ‖ phone_number ‖ email)` |
| `scd2_hash` | `md5(province_code)` |

**(e) `stg.order_item_sales` — nguồn `raw.order_items` ⋈ `raw.orders` ⋈ `raw.payments`** (nguồn của `Fact_Order_Item`)

Lọc: `o.order_status = 'Completed'` **và** `oi.item_status ∈ ('Fulfilled','Returned')` **và** `o.completed_at` thuộc cửa sổ batch (hoặc dòng đã có ở fact nhưng `item_status` đổi — late-arriving change).

| Cột | Biến đổi |
|---|---|
| `source_system, order_id, line_number` | Khóa nghiệp vụ |
| `order_code` | Degenerate dimension |
| `completed_at`, `date_key` | `o.completed_at`; `to_char(completed_at,'YYYYMMDD')::int` |
| `ordered_at`, `order_date_key` | `o.created_at`; tương tự |
| `product_id`, `seller_id` | `oi.product_id`, `o.seller_id` |
| `customer_id` | `o.customer_id` (NULL = khách vãng lai → `-1` ở B4) |
| `channel_id`, `campaign_id` | `o.channel_id`; `o.campaign_id` (NULL → `-1`) |
| `payment_method_id` | Payment `Success` của đơn; COD đã giao nhưng chưa thu (chưa có `Success`) → lấy payment mới nhất bất kỳ trạng thái; không có payment → `0` (WARN DQ-15) |
| `quantity, list_price, unit_price, discount_amount` | Ép kiểu |
| `list_amount, gross_amount, list_discount_amount` | Công thức 4.8.1 |
| `net_revenue` | `oi.net_amount`; **kiểm** `= gross − discount` (DQ-03) |
| `commission_rate, commission_amount` | `oi.commission_rate`; `net_revenue × rate` |
| `is_returned` | `oi.item_status = 'Returned'` |

Lưu ý không nhân dòng: `payments` được gộp về **1 dòng/đơn** (CTE chọn payment) trước khi join; không join trực tiếp `order_item_promotions` ở bảng này.

**(f) `stg.order_item_promotion` — nguồn `raw.order_item_promotions` ⋈ `raw.promotions`** (nguồn của bridge)

1. Giữ các dòng có `order_item_id` thuộc `stg.order_item_sales` của batch.
2. `weighting_factor = applied_discount_amount / sum(applied_discount_amount) over (partition by order_item_id)`.
3. `group_signature = string_agg(promotion_id ‖ ':' ‖ round(weight,6), ',' order by promotion_id)` → tra/tạo `promotion_group_key` ở B4.
4. Kiểm `Σ applied_discount_amount = order_items.discount_amount` (DQ-16); lệch → cách ly **cả dòng hàng** (fact và bridge) để tổng tiền không lệch.
5. `funded_by` (`Platform` | `Seller`), `promo_type` chuẩn hóa từ `promotions`.

**(g) `stg.inventory_daily` — nguồn `raw.inventory_daily_balance` + `raw.inventory_movements`**

| Cột | Biến đổi |
|---|---|
| `date_key` | `balance_date` |
| `product_id` | `map_sku_product(sku)` — không map được → cách ly DQ-04 |
| `warehouse_id` | `idb.warehouse_id` |
| `quantity_on_hand, quantity_reserved` | Ép kiểu; kiểm `0 ≤ reserved ≤ on_hand` (DQ-17) |
| `quantity_available` | `on_hand − reserved` |
| `qty_imported / qty_sold / qty_adjusted` | Gộp `im` theo `(date(movement_date), warehouse_id, sku, movement_type)`; `qty_sold = −Σ` (nguồn âm) |
| `stockout_flag` | `quantity_available = 0` |
| `inventory_value_est` 📝 | `on_hand × unit_cost_est` (phiên bản giá vốn tại ngày) |

Kiểm liên tục (DQ-18): `on_hand(d) = on_hand(d−1) + Σ quantity_change(d)` cho mọi (kho, SKU) — đã khớp 100% trên dữ liệu hiện có.

**(h) `stg.ad_spend_daily` và `stg.ad_spend_monthly` — nguồn `raw.ad_spend_logs` ⋈ `raw.marketing_campaigns`**

1. `channel_id = map_channel(asl.channel_code)` (IR-03).
2. Kiểm `impressions ≥ clicks ≥ 0`, `cost ≥ 0` (DQ-19); `log_date` nằm trong `[start_date, end_date]` của chiến dịch (DQ-20, WARN — chi phí ngoài thời gian chạy).
3. `stg.ad_spend_monthly`: gộp theo `(campaign_id, channel_id, month_key)`: `sum(cost)`, `sum(impressions)`, `sum(clicks)`, `count(distinct log_date)`. Tháng chưa kết thúc được tính lại ở batch sau.

**(i) Dimension nhỏ** — `channels`, `payment_methods`, `warehouses`, `promotions`, `marketing_campaigns`: ép kiểu, chuẩn hóa tỉnh (kho), `promo_type`/`funded_by`, ngày hiệu lực; không cần SCD2 (SCD1 ghi đè).

#### 5.3.4. Danh mục quy tắc chất lượng dữ liệu

| Mã | Áp cho | Quy tắc | Mức | Xử lý |
|---|---|---|---|---|
| DQ-01 | Mọi bảng | Khóa bắt buộc không NULL | ERROR | Cách ly |
| DQ-02 | Fact nguồn | `quantity > 0`, tiền `≥ 0` | ERROR | Cách ly |
| DQ-03 | order_item_sales | `net = quantity × unit_price − discount` (sai số ≤ 0,01) | ERROR | Cách ly |
| DQ-04 | Mọi ánh xạ | Mã không có trong `map_*` (SKU, kênh, tỉnh, tier…) | ERROR | Cách ly |
| DQ-05 | order_item_sales | Đơn `Completed` thiếu `completed_at` | ERROR | Cách ly |
| DQ-06 | Bảng giao dịch | Thời điểm ngoài cửa sổ watermark và không phải late-arriving hợp lệ | ERROR | Cách ly |
| DQ-07 | Mọi bảng | Trùng khóa nghiệp vụ trong batch | WARN | Giữ bản mới nhất |
| DQ-08 | customer, seller | Email/SĐT sai định dạng (`^0\d{9}$`, regex email) | WARN | Giữ, gắn cờ |
| DQ-09 | product | `list_price ≤ 0` | ERROR | Cách ly |
| DQ-10 | product | `unit_cost_est > list_price × 0,98` (vi phạm R-PRD-05) | WARN | Giữ |
| DQ-11 | order_item_sales | `list_price < unit_price` | WARN | Giữ (giá niêm yết thấp hơn giá bán là bất thường) |
| DQ-12 | category | Nút không có tên | WARN | Tên tạm |
| DQ-13 | category | Một nút nhiều cha | ERROR | Cách ly nút |
| DQ-14 | category | Có chu trình | ERROR | Dừng batch |
| DQ-15 | order_item_sales | Không xác định được phương thức thanh toán | WARN | Key `0` |
| DQ-16 | order_item_promotion | Σ phân bổ ≠ `discount_amount` | ERROR | Cách ly dòng hàng + bridge |
| DQ-17 | inventory_daily | `reserved > on_hand` hoặc âm | ERROR | Cách ly |
| DQ-18 | inventory_daily | Tồn không liên tục với sổ cái | WARN | Ghi cảnh báo, vẫn nạp snapshot nguồn |
| DQ-19 | ad_spend | `impressions < clicks` hoặc giá trị âm | ERROR | Cách ly |
| DQ-20 | ad_spend | Chi phí ngoài thời gian chạy chiến dịch | WARN | Giữ |
| DQ-21 | product | Thiếu thương hiệu (bổ sung khi triển khai) | WARN | Gán 'Không rõ thương hiệu' |
| DQ-22 | inventory_daily | Loại biến động kho ngoài Import/Sale/Return/Adjustment (bổ sung khi phát hiện loại `Return`) | WARN | Giữ |

`audit.quarantine(quarantine_id, batch_id, source_table, source_pk, rule_code, severity, reason, payload jsonb, quarantined_at, resolved_batch_id)`. Dòng cách ly **không bị xóa**; khi nguồn sửa, batch sau nạp lại và ghi `resolved_batch_id`.

#### 5.3.5. Kịch bản lỗi kiểm thử (G4)

OLTP hiện không có lỗi (0 email sai, 0 trùng, số học khớp 100%), nên chứng minh cơ chế cách ly bằng `etl/inject_test_errors.py --batch <id> --seed 42`, **chỉ ghi vào `raw`** của một batch kiểm thử riêng:

| Ca | Lỗi chèn | Quy tắc phải bắt |
|---|---|---|
| E1 | 5 dòng hàng `quantity = -1` | DQ-02 |
| E2 | 3 dòng `net_amount` lệch 1.000đ | DQ-03 |
| E3 | 4 bản ghi chi phí QC `channel_code = 'TIKTOK'` | DQ-04 |
| E4 | 3 dòng tồn kho SKU không tồn tại | DQ-04 |
| E5 | 2 đơn `Completed` thiếu `completed_at` | DQ-05 |
| E6 | 5 khách trùng `customer_id`, khác `updated_at` | DQ-07 |
| E7 | 3 email sai định dạng | DQ-08 |

Tiêu chí: 100% dòng lỗi vào đúng `rule_code`; Σ tiền của dòng hợp lệ ở `stg` = Σ ở fact (RC-01); chạy lại batch không nhân đôi cách ly (T3). Báo cáo ghi rõ đây là **dữ liệu kiểm thử**, không phải lỗi phát sinh từ nguồn.

#### 5.3.6. Ví dụ SQL (bước T4–T7 cho `stg.order_item_sales`)

```sql
with pay as (                       -- 1 payment / đơn, tránh nhân dòng
  select distinct on (order_id) order_id, payment_method_id
  from raw.payments where batch_id = :b
  order by order_id, (payment_status = 'Success') desc, transaction_time desc
), src as (
  select oi.*, o.order_code, o.seller_id, o.customer_id, o.channel_id, o.campaign_id,
         o.created_at, o.completed_at, p.payment_method_id,
         oi.quantity * oi.unit_price                    as gross_amount,
         oi.quantity * oi.list_price                    as list_amount
  from raw.order_items oi
  join raw.orders o on o.id = oi.order_id and o.batch_id = :b
  left join pay p on p.order_id = o.id
  where oi.batch_id = :b and o.order_status = 'Completed'
    and oi.item_status in ('Fulfilled','Returned')
), checked as (
  select s.*,
    case when s.completed_at is null                                   then 'DQ-05'
         when s.quantity <= 0 or s.unit_price < 0 or s.discount_amount < 0 then 'DQ-02'
         when abs(s.net_amount - (s.gross_amount - s.discount_amount)) > 0.01 then 'DQ-03'
         when not exists (select 1 from stg.product p where p.product_id = s.product_id) then 'DQ-04'
    end as err
  from src s
)
insert into audit.quarantine (batch_id, source_table, source_pk, rule_code, severity, reason, payload)
select :b, 'order_items', id::text, err, 'ERROR', 'xem rule_code', to_jsonb(checked)
from checked where err is not null;
-- dòng err IS NULL được INSERT vào stg.order_item_sales (cùng CTE) với dq_status 'VALID'/'WARN'
```

#### 5.3.7. Đầu ra của Transform

| Bảng `stg` | Sang bước | Dùng cho |
|---|---|---|
| `stg.product`, `stg.category`, `stg.seller`, `stg.customer` | B3 (SCD) | `dim_product`, `dim_category` + closure, `dim_seller` + SCD3, `dim_customer` |
| `stg.channel`, `stg.payment_method`, `stg.warehouse`, `stg.promotion`, `stg.campaign` | B3 (SCD1) | Dimension nhỏ |
| `stg.order_item_sales`, `stg.order_item_promotion` | B4 | `fact_order_item`, `bridge_promotion_group`, mini-dimension profile |
| `stg.inventory_daily` | B4 | `fact_inventory_snapshot` |
| `stg.ad_spend_monthly` (+ `daily`) | B4 | `fact_ad_spend` |
| `audit.quarantine`, `audit.dq_result`, `audit.batch_log` | Dashboard Chất lượng dữ liệu | M5, T2 |

### 5.4. Nạp dimension và SCD (B3)

Thuật toán snapshot-diff cho mỗi dimension SCD2 (Product, Seller, Customer):

1. So `stg.<dim>_snapshot` (batch hiện tại) với phiên bản `is_current` trong `dw`, theo khóa nghiệp vụ.
2. Thay đổi ở **cột SCD1** → `UPDATE` tại chỗ mọi phiên bản (hoặc chỉ current — chốt: **mọi phiên bản**, để sửa lỗi nhập sai lan toàn lịch sử), không tạo phiên bản mới.
3. Thay đổi ở **cột SCD2** → đóng phiên bản cũ `valid_to = effective_date`, mở phiên bản mới `valid_from = effective_date`, với `effective_date = date_trunc('day', updated_at nguồn)`.
4. Bản ghi mới → phiên bản đầu `valid_from = '1900-01-01'` (hoặc ngày tạo).
5. Thay đổi đến muộn (effective_date < valid_from của current) → **cách ly**, không sửa hồi tố (đề xuất mục 5).
6. SCD3 `dim_seller_tier_t3`: khi `tier` đổi → `previous_tier = current_tier`, `current_tier = mới`, `tier_changed_on`.
7. Mini-dimension: tính bucket cho mỗi khách từ fact đến **trước** ngày giao dịch (`spend_band_12m`: <1tr / 1–5tr / 5–20tr / >20tr; `frequency_band`: 1 / 2–3 / 4–9 / ≥10 đơn) × `membership_tier`; tra `customer_profile_key` khi nạp fact.

Kiểm tra sau nạp: không chồng lấn khoảng hiệu lực; mỗi khóa nghiệp vụ đúng 1 current; SCD1 không tăng số phiên bản (T4).

### 5.5. Nạp fact (B4)

**Fact_Order_Item**

1. Chọn dòng `stg.order_items` của đơn `Completed` có `completed_at` trong cửa sổ batch, `item_status ∈ {Fulfilled, Returned}`.
2. Tra key: product/seller/customer theo `completed_at` (SCD2); customer NULL → `-1`; không tra được → `0` (đếm trên báo cáo).
3. Bridge: nhóm voucher theo `order_item_id`; `weighting_factor = applied_discount_amount / Σ applied_discount_amount`; tái sử dụng `promotion_group_key` nếu tổ hợp voucher+weight đã có.
4. Upsert theo `(source_system, order_id, line_number)` → chạy lại batch không nhân đôi (T3).
5. Đơn chuyển trạng thái sau (ví dụ dòng thành `Returned`) → cập nhật cờ `is_returned` ở batch sau (late-arriving change).

**Fact_Inventory_Snapshot**: từ `stg.inventory_daily_balance` của các ngày trong cửa sổ, map SKU → product, cộng `qty_imported`/`qty_sold`/`qty_adjusted` từ `inventory_movements` theo ngày và `movement_type` (4.8.3); `inventory_value_est` theo giá vốn có hiệu lực tại ngày.

**Fact_Ad_Spend**: gộp `stg.ad_spend_logs` theo `(campaign, channel đã map, tháng)`; tháng chưa kết thúc được cập nhật lại ở batch sau (upsert theo khóa tháng).

### 5.6. Đối soát (B5)

| Mã | Kiểm tra | Điều kiện đạt |
|---|---|---|
| RC-01 | Σ `net_amount` dòng hợp lệ ở `stg` = Σ `net_revenue` fact (cùng cửa sổ) | Bằng tuyệt đối |
| RC-02 | Số dòng hợp lệ = số dòng fact mới/cập nhật | Bằng |
| RC-03 | Mỗi `promotion_group_key`: Σ `weighting_factor` = 1; Σ (`discount_amount × weight`) = Σ `discount_amount` fact; khớp Σ `applied_discount_amount` nguồn | Bằng (sai số ≤ 0,01) |
| RC-04 | Tồn kho fact = `inventory_daily_balance` hợp lệ | Bằng từng (sku, kho, ngày) |
| RC-05 | Σ chi phí quảng cáo fact = Σ `ad_spend_logs` hợp lệ | Bằng |
| RC-06 | Không có FK mồ côi trong fact | 0 dòng |
| RC-07 | Số dòng đọc = hợp lệ + cách ly | Bằng |

### 5.7. Điều phối và vận hành

- `run_etl.py --until 2026-01-31` (nạp lần đầu), rồi chạy định kỳ mỗi khi `last_day` tăng (ví dụ mỗi 6 giờ) → minh họa **incremental + late-arriving** trên dữ liệu đến dần thật.
- `run_etl.py --rerun <batch_id>` → chứng minh idempotent (T3).
- Log JSON từng bước; màn hình "Chất lượng dữ liệu" đọc `audit.*`.

**Sản phẩm M4:** sơ đồ luồng ETL (5.1), bảng chiến lược SCD theo dimension (4.2 + 5.4), mã ETL chạy được, log batch mẫu.

---

## 6. Lớp báo cáo và dashboard

### 6.1. Mart và KPI dùng chung

- `mart.v_kpi_definitions`: một nơi định nghĩa doanh thu thuần, số đơn, AOV, giá bán bình quân, tỷ lệ giảm giá, CTR, doanh thu/chi phí QC (Bảng 11 đề xuất).
- MV: `mv_sales_day_product`, `mv_sales_month_category`, `mv_sales_month_seller_tier`, `mv_inventory_month_product`, `mv_ads_month_channel`.
- `mart.refresh_status` (thời điểm refresh thành công gần nhất) — dashboard hiển thị.

### 6.2. Drill-across (đúng mục 6 đề xuất)

```sql
with s as (select month_key, channel_key, sum(net_revenue) revenue from dw.fact_order_item f
           join dw.dim_date d using (date_key) group by 1,2),
     a as (select month_key, channel_key, sum(cost_amount) cost from dw.fact_ad_spend group by 1,2)
select coalesce(s.month_key,a.month_key) month_key, coalesce(s.channel_key,a.channel_key) channel_key,
       s.revenue, a.cost, s.revenue/nullif(a.cost,0) revenue_per_ad_cost,
       (s.month_key is null) missing_sales, (a.month_key is null) missing_ads
from s full outer join a on s.month_key=a.month_key and s.channel_key=a.channel_key;
```

Tương tự doanh thu–tồn kho theo `(product_id, month)` — ghép bằng **mã nghiệp vụ** `product_id`, không bằng surrogate key.

### 6.3. Dashboard (Streamlit + Plotly)

| Màn hình | Nội dung | Bộ lọc | Kỹ năng |
|---|---|---|---|
| Tổng quan bán hàng | Doanh thu, số đơn, số món, AOV; xu hướng tháng; theo danh mục/seller/kênh; top sản phẩm | Ngày, danh mục (cây), seller, kênh, khuyến mãi | Drill-down năm→quý→tháng→ngày, danh mục gốc→lá |
| Lịch sử thuộc tính | Doanh thu theo hạng seller **tại thời điểm bán** vs hạng hiện tại; theo tỉnh khách | Tháng, hạng | SCD2 vs SCD1 |
| Đối soát vận hành | Doanh thu–tồn kho; doanh thu–quảng cáo tháng–kênh; cờ thiếu nguồn | Tháng, sản phẩm, kênh | Drill-across |
| Chất lượng dữ liệu | Batch, số dòng đọc/hợp lệ/lỗi, lý do cách ly, lần cập nhật gần nhất | Nguồn, ngày nạp | Audit |
| Hiệu năng | Median, p95, speedup, buffers, dung lượng, plan | Thí nghiệm, query | Bench |

Mọi màn hình có nút **xuất CSV** và hiển thị đơn vị tiền, khoảng thời gian, thời điểm dữ liệu.

---

## 7. Milestone 5.1 — Thí nghiệm hiệu năng

### 7.1. Chuẩn bị dữ liệu thí nghiệm

- `Fact_Inventory_Snapshot`: ~18.256 dòng/ngày → ~1,6 triệu dòng/quý, ~6,7 triệu dòng/năm (đạt mốc 2 triệu ở T6 sau ~4 tháng mô phỏng; mốc 5 triệu của phần mở rộng ở ~9 tháng).
- `Fact_Order_Item` nhỏ (~40 nghìn dòng/năm) → cho BM01/BM03 dùng thêm **`bench.fact_order_item_x50`** (nhân bản có seed, đổi `order_id` và dịch ngày trong cùng năm) — ghi rõ là dữ liệu nhân bản cho thí nghiệm, không phục vụ báo cáo.

### 7.2. Thí nghiệm

| Mã | Query | Đối chứng | Chỉ số |
|---|---|---|---|
| BM01 MV | Doanh thu tháng × danh mục | Tổng hợp trực tiếp fact vs đọc `mv_sales_month_category` | Thời gian, kích thước MV, thời gian tạo/refresh |
| BM02 Partition | Doanh thu/tồn kho trong 1 tháng | Bảng thường vs bảng partition theo tháng (cùng dữ liệu, cùng index) | Số partition truy cập, rows ở scan node, buffers |
| BM03 Index | Lọc theo seller + khoảng ngày | Không index vs B-tree đơn `(seller_key)` vs ghép `(seller_key, date_key)` (mở rộng: so với `(date_key, seller_key)`) | Plan, selectivity, kích thước & thời gian tạo index |

### 7.3. Quy trình đo (đề xuất mục 7)

1. Kiểm tra **kết quả tương đương** giữa hai phía (so hash kết quả) trước khi đo.
2. Cùng máy, cấu hình ghi lại (`SHOW ALL` rút gọn, phiên bản PG, RAM), concurrency 1.
3. 3 lượt warm-up + 15 lượt đo, xáo thứ tự cấu hình.
4. `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` lưu vào `bench/results/*.json`; lượt đo thô vào CSV.
5. Báo cáo median, p95, speedup = median baseline / median biến thể; ghi trung thực trường hợp không nhanh hơn.
6. **Tạm dừng mock khi đo** (`scripts/mock_runner/stop_all.sh`) để mock không chiếm tài nguyên; chạy lại sau khi đo.

### 7.4. Mở rộng

- Lattice MV: dựng lattice (tháng, danh mục, seller_tier, kênh), chọn 3 MV theo lợi ích/chi phí, so với MV đơn.

**Sản phẩm 5.1:** `bench/run_bench.py`, kết quả CSV/JSON, màn hình Hiệu năng, báo cáo ngắn.

---

## 8. Kiểm thử theo tiêu chí T1–T7

| Mã | Kiểm thử cụ thể (`sql/90_tests`) |
|---|---|
| T1 Mô hình | Mọi fact có PK, FK tới dimension; grain đúng: `count(*) = count(distinct khóa nghiệp vụ)`; từ điển phủ 100% cột |
| T2 Dữ liệu | RC-01..07 đạt; mọi dòng cách ly có `reason`; 0 FK mồ côi; key `0` được đếm và hiển thị |
| T3 Cập nhật | Chạy `--rerun` 2 lần: số dòng và Σ tiền không đổi; giả lập lỗi giữa batch → `mart` không đổi |
| T4 Lịch sử | Không chồng lấn `[valid_from, valid_to)`; 1 current/khóa; SCD1 không tăng phiên bản; fact trước/sau ngày đổi hạng gắn đúng phiên bản (ca kiểm thử cụ thể với seller đã `MGR-01`) |
| T5 Báo cáo | KPI dashboard = truy vấn SQL độc lập; CSV = bảng hiển thị; drill-across giữ nhóm một phía (Livestream có đơn nhưng chưa có QC hoặc ngược lại) |
| T6 Hiệu năng | BM01–03 có kết quả tương đương, plan, lượt đo thô, kích thước; p95 ≤ 3 s ở 2 triệu dòng (xác nhận trên máy thực tế) |
| T7 Tái lập | README: seed 42, phiên bản cấu hình mock, settings, lệnh chạy mock, lệnh `run_etl.py`, log batch |

Thêm kiểm thử đặc thù kỹ năng nâng cao:

- Bridge: `Σ weight = 1` từng group; Σ phân bổ = `discount_amount`.
- Cây danh mục: không chu trình; doanh thu cây con không cộng lặp.
- Mini-dimension: profile dùng trạng thái **trước** giao dịch (đơn đầu tiên của khách → bucket "chưa mua").
- Semi-additive: báo cáo tồn kho theo quý = tồn ngày cuối quý, không phải tổng.

---

## 9. Milestone 5.2 — Master Blueprint và mở rộng vòng xoắn ốc

### 9.1. Nội dung Blueprint

1. Bối cảnh, mục tiêu M1–M5, phạm vi.
2. Kiến trúc tầng (raw → stg → dw → mart, audit, bench) và luồng dữ liệu từ Mock Studio/crawler.
3. Bản đồ nguồn, chủ đề, quy tắc tích hợp IR-01..07.
4. Grain, tháp phân tầng.
5. Galaxy schema, bus matrix, từ điển dữ liệu.
6. ETL, DQ, cách ly, đối soát, SCD 1/2/3, mini-dimension, bridge, cây danh mục.
7. Dashboard và định nghĩa KPI.
8. Kết quả thí nghiệm hiệu năng.
9. Kết quả kiểm thử T1–T7.
10. Giới hạn và giả định (giá vốn ước tính, dữ liệu mô phỏng, clickstream rút gọn, lỗi kiểm thử chèn ở raw).
11. Lộ trình mở rộng.

### 9.2. Vòng xoắn mở rộng (Spiral + Bus)

Mỗi vòng thêm 1 quy trình, tái dùng dimension chung, không phá fact cũ:

| Vòng | Fact mới | Nguồn OLTP | Dimension mới | Kỹ năng |
|---|---|---|---|---|
| 2 | `Fact_Order_Fulfillment` | `orders`, `payments`, `shipments`, `delivery_attempts` | `dim_carrier` | **Accumulating snapshot**, lead time |
| 3 | `Fact_Return` | `returns`, `refunds`, `order_items` | `dim_return_reason` | Doanh thu thuần sau hoàn (drill-across) |
| 4 | `Fact_Seller_Settlement` | `seller_payouts`, `seller_payout_items`, `seller_commission_rates` | — | Đối soát tài chính sàn đa người bán |
| 5 | `Fact_Customer_Activity` | `sessions`, `page_events`, `cart_items` | `dim_device`, `dim_traffic_source` | Phễu chuyển đổi (factless/event fact) |

---

## 10. Lịch thực hiện (07/11 → 17/11/2026)

| Ngày | Việc | Sản phẩm | Người phụ trách (gợi ý) |
|---|---|---|---|
| **07/11 (tối)** | ✅ Bước 1.0: phiên bản cấu hình mock có SCD + QC đa kênh | Config + [ghi chép triển khai](../../implementation/) | — |
| **08/11** | M1: bản đồ nguồn, chủ đề, IR-01..07, quy tắc lưu vết. Tạo `dwh`, role, schema | Tài liệu M1, `sql/00_init` | Cả nhóm |
| **08/11** | M2: chốt grain, tháp phân tầng | Tài liệu M2 | 1 người |
| **09/11** | M3: DDL dimension/fact/bridge, `dim_date`, cây danh mục, từ điển khung | `sql/30_dw`, sơ đồ Galaxy | 2 người |
| **09/11** | ETL B1–B2: extract incremental, stg, DQ, quarantine, inject lỗi | `etl/extract.py`, `transform.py` | 2 người |
| **10/11** | ETL B3–B5: SCD1/2/3, mini-dim, fact, bridge, đối soát; nạp đến `last_day` | `load_*.py`, `reconcile.py` | 2 người |
| **10/11** | **Nộp 5.1**: BM01–BM03 trên dữ liệu hiện có (+ `bench` nhân bản) | Kết quả bench | 2 người |
| **11–12/11** | Mart, MV, dashboard 5 màn hình, xuất CSV | `dashboard/app.py` | 2 người |
| **13/11** | Chạy ETL incremental nhiều lần khi mock tiến; kiểm thử T1–T5, T7 | Báo cáo kiểm thử | 2 người |
| **14/11** | Đo lại T6 với dữ liệu lớn hơn (≥ 2 triệu dòng tồn kho) | Kết quả cuối | 1 người |
| **15–16/11** | Viết Master Blueprint, slide, demo | Blueprint, slide | Cả nhóm |
| **17/11** | **Nộp 5.2**, bảo vệ | — | Cả nhóm |

Dữ liệu dự kiến có tại các mốc (nếu máy chạy liên tục, ~15 phút/ngày mô phỏng): 10/11 ≈ đến tháng 3–4/2026; 14/11 ≈ tháng 8; 17/11 ≈ tháng 11. ETL và dashboard thiết kế để chạy trên bất kỳ khoảng dữ liệu nào đã hoàn tất.

---

## 11. Rủi ro và biện pháp

| Rủi ro | Biện pháp |
|---|---|
| Máy tắt làm dừng mock | Giữ máy cắm sạc; khởi động lại bằng `start_all.sh` (tự nối tiếp); ETL không phụ thuộc dữ liệu đủ năm |
| Không có thay đổi dimension đủ cho SCD | Bước 1.0; nếu vẫn ít, thêm ca kiểm thử có kiểm soát ở `stg`, ghi rõ |
| ETL đọc OLTP làm chậm mock | Role chỉ đọc, chạy định kỳ, chỉ đọc ngày đã hoàn tất |
| Nhân đôi doanh thu khi ghép fact | Chỉ drill-across sau khi tổng hợp cùng grain; RC-01 |
| Bench không nhanh hơn | Báo cáo trung thực bằng plan; tăng quy mô bằng `bench` |
| Phạm vi rộng so với 10 ngày | Làm phần bắt buộc trước (mục 2–8); vòng xoắn 2–5 chỉ đưa vào Blueprint |

---

## 12. Danh sách kỹ năng nâng cao và nơi thể hiện

| Kỹ năng | Mục | Bằng chứng khi bảo vệ |
|---|---|---|
| Galaxy schema, 3 loại grain | 4.3 | Sơ đồ + DDL |
| Conformed dimension, bus matrix | 4.4 | Ma trận + drill-across |
| Role-playing date, degenerate dimension | 4.3 | Cột `date_key`/`order_date_key`, `order_code` |
| Additive / semi-additive / non-additive | 3.2, 6.1 | KPI tồn kho cuối kỳ, CTR tính lại |
| Tích hợp, xung đột mã | 2.3 | IR-01..07, bảng ánh xạ |
| Khóa −1 / 0 | 4.2, 5.5 | Đếm key 0 trên dashboard |
| SCD1, SCD2 (snapshot-diff CDC), SCD3 | 5.4 | T4, màn hình Lịch sử thuộc tính |
| Mini-dimension | 4.2, 5.4 | `customer_profile_key` tại thời điểm mua |
| Bridge khuyến mãi có weight | 4.3, 5.5 | RC-03 |
| Cây danh mục (closure table) | 4.6 | Drill-down cây con |
| Incremental load, watermark, late-arriving | 5.2, 5.5 | Log nhiều batch |
| Idempotent reload | 5.5, 8 | T3 |
| Audit, DQ, cách ly có lý do | 5.3 | Màn hình Chất lượng dữ liệu |
| Đối soát tổng tiền | 5.6 | RC-01..07 |
| Materialized View, Partition, Index | 7 | BM01–BM03 |
| Lattice MV, thứ tự cột index ghép (mở rộng) | 7.4 | Kết quả bổ sung |
| Accumulating snapshot (vòng 2) | 9.2 | Blueprint |
