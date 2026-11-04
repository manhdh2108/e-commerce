# Bộ luật sinh dữ liệu OLTP — Sàn TMĐT đa người bán

Đặc tả cho bộ sinh dữ liệu (generator) ghi vào CSDL OLTP mô tả trong
[OLTP_SCHEMA.md](OLTP_SCHEMA.md) và [OLTP_ERD.md](OLTP_ERD.md). Bộ sinh mô
phỏng hoạt động của sàn **từng ngày**: khách vào xem, đặt hàng, dùng voucher,
thanh toán, giao hàng, hoàn hàng, nhập kho, chạy quảng cáo, đối soát người bán.

---

## 0. Cách đọc

- Luật có mã `R-<nhóm>-<số>`, tình huống có mã `S-<nhóm>-<số>`, bất biến kiểm
  tra có mã `V-<số>`.
- **PHẢI** = bắt buộc, vi phạm là lỗi của bộ sinh. **NÊN** = khuyến nghị.
- `{tham_so}` = tham số cấu hình ở mục 2.
- Khi các luật xung đột, thứ tự ưu tiên: **toàn vẹn dữ liệu > logic nghiệp vụ >
  phân bố thống kê**.
- Mọi tỷ lệ, giá, phí, ngưỡng trong tài liệu là **giả định mô phỏng**, không
  phải số liệu thật của sàn nào.
- Tài liệu **không giả định trước giá trị ID** của sản phẩm, người bán hay danh
  mục lá. Bộ sinh phải đọc dữ liệu crawl thực tế rồi áp luật ở mục 1. Ngoại lệ
  duy nhất: 26 ID danh mục gốc đã cố định trong `scripts/crawl_tiki.py`.
- Tiền tệ: VND, số nguyên. Thời gian: giờ Việt Nam (UTC+7), lưu `timestamp`
  không múi giờ.
- **Phạm vi**: tài liệu chỉ mô tả cách sàn vận hành và dữ liệu mà các hệ thống
  nguồn ghi ra. Mọi xử lý của kho dữ liệu (lịch sử SCD, bridge, mini-dimension,
  ánh xạ mã giữa các hệ thống, cách ly và chuẩn hóa dữ liệu lỗi) thuộc quy trình
  ETL, nằm ngoài tài liệu này. Bộ sinh **không** được bẻ logic nghiệp vụ để tạo
  sẵn tình huống cho một kỹ thuật DW cụ thể.

---

## 1. Hợp đồng dữ liệu đầu vào (từ crawler)

### 1.1 Nguồn đọc

| Bảng trong `data/tiki_crawl.db` (SQLite) | Dùng để |
|---|---|
| `products` | Sản phẩm, `seller_id`, giá, tín hiệu độ phổ biến |
| `product_categories` (`product_id`, `root_category_id`, `leaf_category_id`) | Danh mục lá của sản phẩm |
| `product_raw` (`raw_json`) | Tùy chọn: tên và đường dẫn danh mục nếu JSON có |
| `product_checkpoints` | Không dùng |

- **R-IN-01** PHẢI chỉ đọc crawl DB, không sửa. Bảng `products` trong OLTP là
  bản sao đã lọc và chuẩn hóa.
- **R-IN-02** Kiểu dữ liệu theo crawler: `id` INTEGER > 0; `price`,
  `original_price`, `discount`, `discount_rate` INTEGER; `seller_id`,
  `seller_product_id` INTEGER; `sku`, `name`, `brand_name`, `type` TEXT;
  `rating_average` REAL; `quantity_sold`, `review_count` INTEGER. Mọi cột trừ
  `id` có thể NULL.
- **R-IN-03** Trong crawl DB, `products.category_id` là **danh mục gốc**, không
  phải danh mục lá. Danh mục lá nằm ở `product_categories`. Một sản phẩm có thể
  thuộc nhiều cặp gốc/lá.

### 1.2 Quy tắc định danh (ID)

- **R-ID-01** `products.id` = ID crawl, giữ nguyên. Không đánh số lại, không giả
  định độ dài, khoảng giá trị, thứ tự hay tính liên tục.
- **R-ID-02** `sellers.id` = `products.seller_id`, giữ nguyên.
- **R-ID-03** `categories.id`: nút gốc và nút lá dùng ID Tiki. Nút trung gian do
  bộ sinh tạo thêm (R-CTG-04) lấy ID = `max(mọi ID danh mục thật) + 1, + 2, ...`
  tính lúc chạy, nên không bao giờ trùng ID thật.
- **R-ID-04** Mọi bảng còn lại: ID tuần tự từ 1, **tăng theo thời điểm ghi bản
  ghi vào OLTP** (ID lớn hơn nghĩa là ghi sau), giống sequence của CSDL thật.
- **R-ID-05** Mọi tham chiếu tới sản phẩm, seller, danh mục PHẢI tra từ bảng đã
  nạp. Không hardcode ID trong code bộ sinh.
- **R-ID-06** Tái lập độc lập với giá trị ID: trước mỗi lần chọn ngẫu nhiên trên
  một tập thực thể, PHẢI sắp tập theo ID tăng dần rồi mới lấy mẫu bằng RNG đã
  seed. Cùng dữ liệu crawl và cùng `{seed}` thì ra cùng kết quả.

**R-ID-07** Định dạng mã nghiệp vụ:

| Mã | Định dạng | Ví dụ |
|---|---|---|
| `orders.order_code` | `OD` + `YYMMDD` + số thứ tự trong ngày 6 chữ số | `OD251111000123` |
| `shipments.tracking_code` | `carrier_code` + `YYMMDD` + 8 chữ số | `GHN25111100004521` |
| `promotions.promo_code` (sàn) | `SAN` + `YYMMDD` + loại + số | `SAN251111FS01` |
| `promotions.promo_code` (shop) | `SHOP` + `seller_id` + `-` + số | `SHOP<seller_id>-07` |
| `marketing_campaigns.campaign_code` | `CMP-` + `YYYY` + `-` + tên ngắn | `CMP-2025-1111` |
| `warehouses.warehouse_code` | `WH-` + vùng + `-` + số | `WH-HCM-01` |
| `products.sku` khi thiếu | `SKU-` + `product_id` | `SKU-<product_id>` |
| `customers.email` | tên không dấu + số + `@example.com` | `nguyenvana123@example.com` |

Dùng tên miền `example.com` (dành riêng cho thử nghiệm) để không trùng email thật.

### 1.3 Lọc sản phẩm đủ điều kiện

| Điều kiện trên bản ghi crawl | Xử lý | Mã lý do loại |
|---|---|---|
| `seller_id` NULL | Loại | `NO_SELLER` |
| `price` NULL hoặc ≤ 0 | Loại | `NO_PRICE` |
| `price` < 1.000 hoặc > `{max_price}` | Loại | `PRICE_OUTLIER` |
| `name` NULL hoặc rỗng | Loại | `NO_NAME` |
| `is_active` = 0 | Loại | `INACTIVE` |
| `is_active` NULL | Giữ, coi là đang bán | |
| `original_price` NULL hoặc < `price` | Giữ, đặt `original_price = price` | |
| `sku` NULL, rỗng hoặc trùng sản phẩm khác | Giữ, đặt `sku = 'SKU-' + id` | |

- **R-IN-04** Bộ sinh PHẢI in **báo cáo hồ sơ đầu vào** trước khi sinh: tổng số
  sản phẩm, số bị loại theo từng mã lý do, số đủ điều kiện theo từng danh mục
  gốc, số seller, tỷ lệ NULL của từng cột.

### 1.4 Chuẩn hóa giá trị

- `base_list_price = original_price`, `base_price = price`.
- `base_markdown = 1 − price / original_price`, kẹp trong `[0; 0,7]`. Cột
  `discount_rate` của crawl chỉ dùng để đối chiếu.
- `quantity_sold`, `review_count` NULL thì coi là 0. `rating_average` NULL thì
  coi là "chưa có đánh giá".
- `brand_name`: cắt khoảng trắng. Giá trị rỗng, `OEM`, `No Brand` coi là không
  có thương hiệu.
- **R-IN-05** Các cột tín hiệu của Tiki (`rating_average`, `review_count`,
  `quantity_sold`, `inventory_status`, `stock_item`) là dữ liệu tham khảo chỉ
  đọc. Bộ sinh KHÔNG cập nhật chúng theo đơn hàng mô phỏng, và không dùng chúng
  để đối soát với `product_reviews` hay `order_items`.

### 1.5 Phân loại cách hoàn tất đơn (fulfillment class)

| Lớp | Điều kiện | Hệ quả |
|---|---|---|
| `DIGITAL` | Danh mục gốc 11312 (Voucher - Dịch vụ) hoặc `type = 'virtual'` | Không tồn kho, không giao vận, không COD, không hoàn hàng |
| `CROSS_BORDER` | Danh mục gốc 17166 (Hàng Quốc Tế) | Chỉ tồn ở kho quốc tế `WH-CB-01`, nhập hàng chậm, giao 7–14 ngày |
| `PHYSICAL` | Còn lại | Luật kho vận đầy đủ |

Danh mục gốc không nằm trong 26 ID của crawler (khi chạy `--category-ids` tùy
chỉnh) được xếp vào nhóm "Khác" với tham số mặc định.

### 1.6 Chọn danh mục mô phỏng (simulation catalog)

- **R-CAT-01** Số sản phẩm mô phỏng = `min({catalog_size}, số đủ điều kiện)`.
- **R-CAT-02** Chia quota theo danh mục gốc, tỷ lệ với `sqrt(số đủ điều kiện của
  gốc)`, mỗi gốc tối thiểu `min(20, số đủ điều kiện của gốc)`. Căn bậc hai giúp
  gốc nhỏ không bị lấn át.
- **R-CAT-03** Trong mỗi gốc, lấy mẫu không hoàn lại với trọng số
  `w = (quantity_sold + 1) ^ {alpha_pop}` (sắp theo ID trước, R-ID-06). Sản phẩm
  bán chạy trên Tiki có nhiều khả năng vào catalog hơn.
- **R-CAT-04** Bảng `products` trong OLTP **chỉ chứa catalog mô phỏng**. Nhờ vậy
  mọi sản phẩm trong OLTP đều bán được và có tồn kho (trừ `DIGITAL`).
- **R-CAT-05** Trọng số `w` được giữ lại làm **độ phổ biến gốc** của sản phẩm khi
  chọn sản phẩm cho đơn hàng (mục 7).

### 1.7 Dựng cây danh mục

- **R-CTG-01** Cấp 1 = 26 danh mục gốc, tên lấy từ hằng `CATEGORIES` trong
  crawler. `parent_id = NULL`, `level = 1`.
- **R-CTG-02** Danh mục lá chính của mỗi sản phẩm:
  1. Nếu `raw_json` có đường dẫn danh mục (ví dụ trường `primary_category_path`
     dạng `"1/2/<gốc>/.../<lá>"`), dùng đường dẫn đó và tạo đủ các cấp giữa gốc
     và lá.
  2. Nếu không: lấy `leaf_category_id` **nhỏ nhất** trong `product_categories`
     có `root_category_id = products.category_id` (gốc của crawl).
  3. Nếu không có dòng nào: lá = chính danh mục gốc.
- **R-CTG-03** Tên danh mục lá: lấy từ `raw_json` nếu có (ví dụ trường
  `primary_category_name`). Nếu không có: `"<tên gốc> - Nhóm <leaf_id>"`.
- **R-CTG-04** Cây danh mục của sàn thật có **độ sâu không đều** giữa các ngành
  hàng. Nếu dữ liệu crawl không có đường dẫn đầy đủ (cây bị dẹt còn 2 cấp), chọn khoảng 1/3 số danh mục gốc (theo seed) và chèn
  một cấp trung gian tổng hợp, gom các lá của gốc đó thành 2–4 nhóm. Các gốc còn
  lại giữ 2 cấp.
- **R-CTG-05** Mỗi nút có đúng một cha, không có chu trình, `level` = độ sâu.
- **R-CTG-06** `products.category_id` trong OLTP = **danh mục lá** (khác crawl).
  `slug` = tên không dấu, chữ thường, nối bằng `-`.
- **R-CTG-07** Cây danh mục cố định trong suốt mô phỏng. Chỉ có sản phẩm được
  chuyển sang lá khác (mục 15).

---

## 2. Tham số cấu hình

Có 2 hồ sơ: `dev` để kiểm thử nhanh toàn bộ luồng, `full` để chạy thật.

| Tham số | `dev` | `full` | Ghi chú |
|---|---|---|---|
| `{seed}` | 42 | 42 | RNG duy nhất cho toàn bộ bộ sinh |
| `{sim_start}` – `{sim_end}` | 2025-11-01 – 2025-11-30 | 2024-01-01 – 2025-12-31 | Bản `dev` vẫn chứa 11.11 và Black Friday |
| `{catalog_size}` | 500 | 5.000 | R-CAT-01 |
| `{target_order_lines}` | 7.500 | 2.000.000 | Tổng `order_items`, sai số cho phép ±5% |
| `{customers_at_end}` | 3.000 | 250.000 | Số khách đã đăng ký cuối kỳ |
| `{customers_existing_share}` | 40% | 40% | Khách đã đăng ký trước `{sim_start}` |
| `{guest_order_share}` | 4% | 4% | Đơn của khách vãng lai |
| `{alpha_pop}` | 0,7 | 0,7 | Độ lệch phân bố độ phổ biến |
| `{max_price}` | 500.000.000 | 500.000.000 | Ngưỡng giá ngoại lai |
| `{yoy_growth}` | 25% | 25% | Tăng trưởng số đơn theo năm |
| `{pause_points}` | Cuối mỗi tháng | Cuối mỗi tháng | Các điểm bộ sinh tạm dừng để quy trình ETL đọc dữ liệu; do phía ETL quyết định (mục 4.3) |
| `{clickstream_window}` | Toàn kỳ | 2025-11-01 – 2025-11-30 | Chỉ sinh clickstream trong cửa sổ này |
| `{livestream_launch}` | 2024-04-01 | 2024-04-01 | Kênh Livestream bắt đầu có đơn |
| `{commission_change_date}` | 2025-01-01 | 2025-01-01 | Ngày đổi chính sách hoa hồng |
| `{return_window}` | 7 ngày (Mall 15) | 7 ngày (Mall 15) | Hạn yêu cầu hoàn hàng |
| `{reorder_days}` / `{target_cover_days}` | 7 / 30 | 7 / 30 | Điểm đặt hàng lại / mức tồn mục tiêu, tính theo số ngày bán |
| `{lead_time}` | 2–7 ngày | 2–7 ngày | Kho quốc tế: 10–20 ngày |
| `{inject_errors}` | Bật | Bật | Mục 17 |
| `{admin_division_mode}` | `new_34` | `new_34` | Mục 5.4 |

---

## 3. Lịch và mô hình nhu cầu

### 3.1 Ngày Tết Nguyên đán (mùng 1)

| Năm | Ngày dương lịch |
|---|---|
| 2024 | 2024-02-10 |
| 2025 | 2025-01-29 |
| 2026 | 2026-02-17 |

Các khoảng Tết tính theo độ lệch ngày so với mùng 1 (ký hiệu `T`).

### 3.2 Hệ số số đơn theo sự kiện

| Sự kiện | Ngày | Hệ số |
|---|---|---|
| 11.11 | 11/11 | ×5,0 |
| 12.12 | 12/12 | ×4,0 |
| 9.9, 10.10 | 9/9, 10/10 | ×3,0 |
| Ngày đôi khác | 1/1 … 8/8 | ×2,0 |
| Black Friday | Thứ Sáu cuối cùng của tháng 11 | ×3,0 |
| Cyber Monday | Thứ Hai sau Black Friday | ×1,8 |
| Các ngày khác trong tuần Black Friday | | ×1,3 |
| Sale giữa tháng | Ngày 15 | ×1,3 |
| Kỳ nhận lương | Ngày 25 đến ngày 5 tháng sau | ×1,1 |
| Mua sắm trước Tết | `[T−21; T−4]` | ×1,3 |
| Nghỉ Tết | `[T−3; T+5]` | ×0,4 (ghi đè mọi sự kiện khác) |
| Trước các ngày tặng quà | 5 ngày trước 14/2, 8/3, 20/10, 20/11 | ×1,1 |

### 3.3 Cách kết hợp hệ số

- **R-DEM-01** Số đơn kỳ vọng của ngày `d`:
  `orders(d) = base × growth(d) × weekday(d) × event(d)`, trong đó:
  - `growth(d) = (1 + {yoy_growth}) ^ (số ngày từ {sim_start} / 365)`
  - `weekday(d)`: T2 0,95; T3 0,95; T4 1,0; T5 1,0; T6 1,0; T7 1,1; CN 1,15
  - `event(d)` = **giá trị lớn nhất** trong các sự kiện áp dụng (không nhân các
    sự kiện với nhau), mặc định 1,0. Trong khoảng nghỉ Tết, `event(d) = 0,4`.
- **R-DEM-02** `base` được hiệu chỉnh một lần trước khi chạy sao cho tổng số dòng
  hàng ≈ `{target_order_lines}`. Số đơn thực tế mỗi ngày lấy theo phân phối
  Poisson quanh `orders(d)`.

### 3.4 Phân bố theo giờ trong ngày

| Khung giờ | Ngày thường | Ngày sale lớn (ngày đôi, Black Friday) |
|---|---|---|
| 0–1h | 3% (gộp 0–5h) | 15% |
| 2–5h | | 3% |
| 6–8h | 6% | 5% |
| 9–11h | 17% | 14% |
| 12–13h | 13% | 11% |
| 14–17h | 20% | 16% |
| 18–19h | 11% | 9% |
| 20–23h | 30% | 27% |

Đơn kênh Livestream: 70% rơi vào 19–22h (giờ phát live).

### 3.5 Mùa vụ theo danh mục

Hệ số nhân vào trọng số chọn sản phẩm của danh mục gốc. Nếu nhiều giai đoạn
trùng nhau, lấy hệ số lớn nhất.

| Giai đoạn | Danh mục gốc (ID) | Hệ số |
|---|---|---|
| Trước Tết `[T−21; T−4]` | Bách Hóa Online (4384), NGON (44792) | ×1,8 |
| | Nhà Cửa - Đời Sống (1883), Chăm sóc nhà cửa (15078) | ×1,4 |
| | Thời trang nữ (931), Thời trang nam (915), Giày dép nam/nữ (1686, 1703) | ×1,5 |
| Tựu trường 1/8 – 5/9 | Nhà Sách Tiki (8322) | ×1,6 |
| | Balo và Vali (6000) | ×1,4 |
| | Laptop - Máy Vi Tính (1846) | ×1,3 |
| Mùa hè 1/4 – 31/7 | Điện Gia Dụng (1882), Điện Tử - Điện Lạnh (4221) | ×1,4 |
| | Thể Thao - Dã Ngoại (1975) | ×1,2 |
| Cuối năm 1/11 – 31/12 | Điện thoại (1789), Thiết bị số (1815), Laptop (1846), Máy ảnh (1801) | ×1,4 |
| 5 ngày trước 14/2, 8/3, 20/10, 20/11 | Làm Đẹp (1520), Đồng hồ và Trang sức (8371), Túi nữ (976) | ×1,5 |

### 3.6 Vận hành giao nhận theo lịch

- **R-DEM-03** Trong khoảng `[T−3; T+5]` không có lấy hàng và không có giao hàng.
  Đơn vẫn được đặt (hệ số 0,4) và nằm chờ. Từ `T+6`, lượng đơn tồn được lấy hàng
  rải đều trong 3 ngày.
- **R-DEM-04** Ngày sale lớn và 2 ngày sau đó: thời gian chờ lấy hàng cộng thêm
  24 giờ do quá tải.
- **R-DEM-05** Trước `{livestream_launch}` không có đơn, phiên hay voucher nào
  thuộc kênh Livestream. Chi phí quảng cáo kênh `LIVE` được phép bắt đầu sớm hơn
  1 tháng (quảng bá trước khi ra mắt, xem S-MKT-03).

---

## 4. Thứ tự sinh và vòng lặp mô phỏng

### 4.1 Khởi tạo (trạng thái tại `{sim_start}` 00:00)

Thứ tự bắt buộc, bảng cha trước bảng con:

1. `categories` (mục 1.7)
2. `sellers` (5.2), rồi `products` của catalog (5.1)
3. `warehouses`, `carriers`, `channels`, `payment_methods` (5.5)
4. `seller_commission_rates` (5.6)
5. Khách đã đăng ký trước kỳ: `customers`, `customer_addresses` (5.3, 5.4)
6. Tồn kho ban đầu: các dòng `inventory_movements` loại `Import` (mục 10)

Promotion và chiến dịch **không** tạo sẵn cho cả kỳ. Chúng được ghi vào OLTP
đúng ngày được tạo trong vòng lặp (R-ID-04).

### 4.2 Vòng lặp theo ngày

- **R-SIM-01** Bộ sinh là mô phỏng theo sự kiện với một đồng hồ chung. Trong mỗi
  ngày, mọi sự kiện được xử lý theo thứ tự thời gian. Nhờ vậy tồn kho, lượt dùng
  voucher và trạng thái đơn luôn nhất quán tại mọi thời điểm.
- **R-SIM-02** Các bước trong ngày `d`:

| Bước | Việc | Mục |
|---|---|---|
| 1 | 00:00 ngày 1 hằng tháng: tính lại `membership_tier`. Ngày 1 hằng quý: xét lại hạng seller | 5.3, 15 |
| 2 | Áp thay đổi dữ liệu chủ đã lên lịch: khách mới, seller mới, sản phẩm mới, đổi giá, đổi danh mục, chuyển tỉnh, ngừng bán, khóa shop | 5, 15 |
| 3 | Tạo promotion và chiến dịch có ngày tạo = `d` | 6, 12 |
| 4 | Ghi chi phí quảng cáo (có độ trễ, R-MKT-07) | 12 |
| 5 | Clickstream nếu `d` nằm trong `{clickstream_window}` | 13 |
| 6 | Tạo đơn mới theo giờ: chọn sản phẩm, tính giá, áp voucher, giữ hàng, tạo payment | 7, 6, 8 |
| 7 | Đẩy tiến trình đơn cũ: thanh toán, xác nhận, lấy hàng, vận chuyển, giao hoặc thất bại, hủy | 7, 8, 9 |
| 8 | Sau bán: yêu cầu hoàn, duyệt, hoàn tiền, đánh giá | 11 |
| 9 | Kho: hàng nhập về, đặt hàng bổ sung, kiểm kê (ngày cuối tháng), ghi tồn cuối ngày | 10 |
| 10 | Ngày 1 hằng tháng: lập `seller_payouts` tháng trước; chi trả các kỳ đến hạn | 14 |
| 11 | Nếu `d` là một điểm dừng trong `{pause_points}`: dừng ghi, chờ được gọi chạy tiếp | 4.3 |

### 4.3 Giao diện với quy trình ETL

Bộ sinh đóng vai các hệ thống nguồn. Nó không cần biết DW xử lý dữ liệu thế nào,
chỉ cần bảo đảm dữ liệu nguồn hành xử như hệ thống thật.

- **R-SIM-03** Bộ sinh chạy được theo từng đoạn thời gian (ví dụ `--until
  <ngày>`) và tiếp tục từ trạng thái đã lưu. Tại mỗi điểm dừng, mọi sự kiện đến
  23:59:59 của ngày đó đã được ghi xong. Trong lúc dừng, bộ sinh không ghi gì.
- **R-SIM-04** Thay đổi dữ liệu chủ xảy ra theo logic nghiệp vụ (mục 15), không
  điều chỉnh theo lịch đọc của ETL. Nếu ETL đọc thưa, một thực thể có thể đã đổi
  hai lần giữa hai lần đọc; đó là đặc tính thật của nguồn chỉ lưu trạng thái hiện
  tại.
- **R-SIM-05** Mọi UPDATE PHẢI đặt `updated_at` = thời điểm thay đổi, như cột kiểm
  toán của hệ thống thật.
- **R-SIM-06** Không DELETE bất kỳ bản ghi nào. Ngừng hoạt động thể hiện bằng
  `status`, `is_active` hoặc trạng thái đơn.
- **R-SIM-07** Hết kỳ mô phỏng thì dừng, không ép các đơn đang dở hoàn tất.

---

## 5. Dữ liệu chủ

### 5.1 Sản phẩm (`products`)

- **R-PRD-01** `created_at` (ngày lên sàn): 80% catalog rơi ngẫu nhiên trong 2 năm
  trước `{sim_start}`; 20% là **sản phẩm mới**, lên sàn trong khoảng
  `[{sim_start}; {sim_end} − 30 ngày]`. Luôn có
  `created_at ≥ sellers.created_at + 1 ngày`. Ban đầu `updated_at = created_at`.
- **R-PRD-02** Giá niêm yết đầu kỳ:
  `original_price = round_1000(base_list_price × U(0,92; 1,00))`.
  `price = round_1000(original_price × (1 − base_markdown))`.
- **R-PRD-03** Đổi giá niêm yết: mỗi quý 10% catalog đổi một lần, vào ngày ngẫu
  nhiên không phải ngày sale lớn. 70% tăng 3–15%, 30% giảm 5–20%. `price` đổi
  theo cùng tỷ lệ trong cùng sự kiện.
- **R-PRD-04** `products.price` chỉ thay đổi trong sự kiện R-PRD-03. Giá flash
  sale và giá ngày sale **không ghi vào `products`**; chúng chỉ xuất hiện ở
  `order_items.unit_price` (R-PRC-01). Giống sàn thật: giá khuyến mãi theo khung
  giờ do hệ thống khuyến mãi quản lý, không ghi đè giá gốc của sản phẩm.
- **R-PRD-05** Giá vốn: `cost_price = round_1000(price đầu kỳ × tỷ lệ giá vốn của
  nhóm)` (bảng 5.6). Tỷ lệ tính trên **giá bán**, không phải giá niêm yết, để giá
  bán thường ngày luôn cao hơn giá vốn. Mỗi nửa năm 5% catalog đổi giá vốn ±3–10%.
  Sau mọi thay đổi vẫn phải có `cost_price ≤ price × 0,98`.
- **R-PRD-06** Ngừng kinh doanh: mỗi năm 2% catalog chuyển `is_active = false`
  tại một ngày ngẫu nhiên. Sau thời điểm đó không có đơn mới.
- **R-PRD-07** Seller nhập sai tên: 0,5% catalog có tên lỗi lúc đăng bán (bỏ dấu,
  lặp khoảng trắng, sai một ký tự). Seller sửa lại đúng tên crawl gốc sau 1–6
  tháng.

### 5.2 Người bán (`sellers`)

- **R-SEL-01** `sellers` = tập `seller_id` khác nhau trong catalog.
- **R-SEL-02** Hạng ban đầu:
  - `Mall`: seller có nhiều sản phẩm nhất trong catalog (thường là nhà bán của
    chính sàn), cộng các seller có ≥ 10 sản phẩm mà ≥ 80% cùng một
    `brand_name`. Giới hạn tối đa 8% số seller.
  - `Preferred`: 25% seller còn lại có tổng độ phổ biến `w` cao nhất.
  - `Normal`: còn lại.
- **R-SEL-03** Tên: seller `Mall` có thương hiệu chủ đạo thì `shop_name` =
  `"<brand> Official Store"`, `seller_name` = `"Công ty TNHH <brand> Việt Nam"`.
  Các seller khác: `shop_name` = từ khóa danh mục chính + tên sinh bằng Faker
  (ví dụ "Thời Trang Minh Anh"); `seller_name` = `"Hộ kinh doanh <họ tên>"` hoặc
  `"Công ty TNHH <tên>"`.
- **R-SEL-04** Tỉnh: `Mall` gồm TP.HCM 50%, Hà Nội 40%, tỉnh khác 10%. Hạng khác
  gồm TP.HCM 45%, Hà Nội 30%, tỉnh khác 25% theo trọng số ở 5.4.
- **R-SEL-05** `created_at`: 85% seller tham gia trong 4 năm trước
  `{sim_start}`; 15% tham gia trong kỳ, và toàn bộ sản phẩm của họ là sản phẩm
  mới (R-PRD-01). `email`, `phone` duy nhất; `status = 'Active'`.

### 5.3 Khách hàng (`customers`)

- **R-CUS-01** Sinh bằng `Faker('vi_VN')`. Giới tính: nữ 58%, nam 40%, NULL 2%; tên
  khớp giới tính. Tuổi: 18–24 chiếm 30%, 25–34 chiếm 40%, 35–44 chiếm 20%, 45–60
  chiếm 10%.
- **R-CUS-02** `registration_date`: `{customers_existing_share}` khách đăng ký
  trước kỳ; số còn lại đăng ký trong kỳ, số lượng mỗi ngày tỷ lệ với hệ số nhu cầu
  (ngày sale có nhiều khách mới).
- **R-CUS-03** Số điện thoại 10 chữ số, đầu số 03, 05, 07, 08, 09, duy nhất.
  `email` duy nhất theo R-ID-07.
- **R-CUS-04** 35% khách đã đăng ký không bao giờ mua. Với khách còn lại, mỗi
  người có độ năng động `λ ~ Gamma(0,6)` dùng làm trọng số khi chọn khách mua
  lại. Phần lớn chỉ mua 1–2 lần, một nhóm nhỏ mua rất thường xuyên.
- **R-CUS-05** Hạng thành viên tính lúc 00:00 ngày 1 hằng tháng từ chi tiêu 365
  ngày gần nhất (tổng `final_amount` của đơn `Completed`, trừ tiền đã hoàn):

| Hạng | Chi tiêu 365 ngày |
|---|---|
| `Member` | < 2.000.000 |
| `Silver` | 2.000.000 – < 6.000.000 |
| `Gold` | 6.000.000 – < 15.000.000 |
| `Platinum` | ≥ 15.000.000 |

  Khách có từ trước kỳ được gán một khoản **chi tiêu trước kỳ** lúc khởi tạo (để
  có đủ các hạng ngay từ đầu). Khoản này giảm tuyến tính về 0 trong 12 tháng đầu.
  Chỉ UPDATE (và đổi `updated_at`) khi hạng thực sự thay đổi.

### 5.4 Địa chỉ và đơn vị hành chính

- **R-ADR-01** Chế độ `new_34` (mặc định): toàn bộ dữ liệu dùng danh mục **34 đơn
  vị cấp tỉnh** hiện hành (sau sắp xếp có hiệu lực 01/07/2025) và mô hình 2 cấp:
  `ward` = phường/xã, `district` = NULL. Danh mục đặt trong file cấu hình
  `provinces.csv` (`province_name`, `region` Bắc/Trung/Nam, `weight`).
- **R-ADR-02** Trọng số tỉnh của khách: TP.HCM 28%, Hà Nội 22%, Hải Phòng 4%, Đồng
  Nai 3,5%, Đà Nẵng 3,5%, Cần Thơ 3%, Bắc Ninh 3%, Khánh Hòa 2%; phần còn lại chia
  theo dân số.
- **R-ADR-03** Chế độ `transition` (sát thực tế hơn): địa chỉ tạo trước 01/07/2025
  dùng 63 tỉnh cũ và có `district`; địa chỉ tạo từ 01/07/2025 dùng 34 tỉnh mới.
  Như hệ thống thật, địa chỉ cũ không được tự động sửa. Chế độ `new_34` là cách
  đơn giản hóa, coi như mọi địa chỉ đã theo danh mục mới.
- **R-ADR-04** Mỗi khách có một địa chỉ mặc định tạo cùng lúc đăng ký, cùng tỉnh
  với hồ sơ. 20% khách có thêm địa chỉ thứ hai (trong đó 30% ở tỉnh khác). Người
  nhận là chính khách (85%) hoặc người khác (15%).
- **R-ADR-05** Mỗi khách luôn có đúng một địa chỉ `is_default = true`.
- **R-ADR-06** Đơn của khách vãng lai tạo một dòng địa chỉ mới với
  `customer_id = NULL`, `is_default = false`, dùng một lần.

### 5.5 Bảng tĩnh

| Bảng | Giá trị |
|---|---|
| `warehouses` | `WH-HN-01` Hà Nội, `WH-HN-02` Bắc Ninh (vùng Bắc); `WH-DN-01` Đà Nẵng (Trung); `WH-HCM-01` TP.HCM, `WH-HCM-02` Đồng Nai, `WH-CT-01` Cần Thơ (Nam); `WH-CB-01` kho hàng quốc tế đặt tại TP.HCM, chỉ chứa hàng `CROSS_BORDER` |
| `carriers` | `GHN` 30%, `GHTK` 30%, `VTP` 20%, `JNT` 15%, `NJV` 5%. Giao hỏa tốc chỉ qua `GHN` |
| `channels` | `Web` và `App` (`channel_type = 'Online Owned'`), `Livestream` (`'Social Commerce'`) |
| `payment_methods` | `COD` (nhóm COD), `Momo`, `ZaloPay` (E-Wallet), `Credit Card` (Card), `Bank Transfer` (Bank Transfer) |
| Mã kênh marketing | `Web` ↔ `WEB`, `App` ↔ `MOBILE_APP`, `Livestream` ↔ `LIVE` |

### 5.6 Tham số theo nhóm danh mục

Dùng chung cho giá vốn, hoa hồng, tỷ lệ hoàn và số lượng mua.

| Nhóm | Danh mục gốc (ID) | Tỷ lệ giá vốn | Hoa hồng cơ sở | Tỷ lệ hoàn | Số lượng mỗi dòng |
|---|---|---|---|---|---|
| G1 Công nghệ giá trị cao | 1789, 1801, 1846 | 0,82–0,92 | 2,5% | 2% | Đơn chiếc |
| G2 Điện tử, gia dụng | 1815, 1882, 4221 | 0,70–0,85 | 4% | 3% | Đơn chiếc |
| G3 Thời trang, phụ kiện | 915, 931, 976, 1686, 1703, 27498, 27616 | 0,40–0,60 | 8% | 6% | Thường |
| G4 Làm đẹp, sức khỏe | 1520 | 0,45–0,65 | 7% | 2% | Thường |
| G5 Đồng hồ, balo vali | 6000, 8371 | 0,50–0,65 | 7% | 3% | Đơn chiếc |
| G6 Nhà cửa, mẹ bé, thể thao, xe | 1883, 1975, 2549, 8594, 15078 | 0,55–0,72 | 6% | 2% | Thường |
| G7 Sách | 8322 | 0,60–0,75 | 5% | 1% | Sách |
| G8 Bách hóa | 4384, 44792 | 0,75–0,88 | 4% | 0,5% | Số lượng lớn |
| G9 Voucher, dịch vụ | 11312 | 0,85–0,95 | 3% | 0% | Sách |
| G10 Hàng quốc tế | 17166 | 0,65–0,80 | 6% | 3% | Thường |
| G0 Khác | Gốc ngoài 26 ID | 0,60–0,75 | 6% | 2% | Thường |

Phân phối số lượng mỗi dòng: **Đơn chiếc** 1 (97%), 2 (3%). **Thường** 1 (75%),
2 (18%), 3–5 (7%). **Sách** 1 (70%), 2–3 (25%), 4–10 (5%). **Số lượng lớn**
1 (50%), 2–3 (30%), 4–12 (20%).

- **R-FIN-01** `seller_commission_rates` khai báo ở **cấp danh mục gốc**: 26 gốc ×
  3 hạng × 2 giai đoạn. Danh mục lá dùng tỷ lệ của gốc. Tỷ lệ = hoa hồng cơ sở +
  điều chỉnh theo hạng (`Normal` +0, `Preferred` +0,5 điểm %, `Mall` +2 điểm %).
- **R-FIN-02** Giai đoạn 1: `effective_from = 2019-01-01`,
  `effective_to = {commission_change_date} − 1 ngày`. Giai đoạn 2: từ
  `{commission_change_date}`, `effective_to = NULL`, nhóm G3 và G4 tăng thêm 1
  điểm %.
- **R-FIN-03** Một dòng hàng dùng tỷ lệ có hiệu lực vào **ngày đặt hàng**
  (`orders.created_at`), theo danh mục gốc của sản phẩm tại thời điểm đó và hạng
  của seller tại thời điểm đó.

---

## 6. Giá bán và khuyến mãi

### 6.1 Giá tại thời điểm mua

- **R-PRC-01** Với mỗi dòng hàng tạo lúc `t`:
  - `order_items.list_price` = `products.original_price` có hiệu lực tại `t`.
  - `unit_price = round_1000(list_price × (1 − m))`, với
    `m = base_markdown + extra(t)`, kẹp `m ≤ 0,8`.
  - Luôn có `1.000 ≤ unit_price ≤ list_price`.
- **R-PRC-02** `extra(t)` theo loại ngày:

| Trường hợp | `extra` |
|---|---|
| Ngày thường | Nhiễu `U(0; 0,03)`, cố định theo cặp (sản phẩm, tuần ISO) |
| Sản phẩm tham gia ngày sale lớn (30% catalog, seller `Mall` 50%) | `U(0,05; 0,30)` trong cả ngày đó |
| Khung flash sale | `U(0,30; 0,50)` |

- **R-PRC-03** Flash sale: ngày sale lớn có 3 khung (0–2h, 12–14h, 21–23h); ngày
  của chiến dịch Flash Sale hằng tuần có 1 khung (12–14h). Mỗi khung chọn 1%
  catalog (ưu tiên sản phẩm phổ biến), mỗi sản phẩm có hạn mức 20–200 đơn vị ở
  giá flash. Hết hạn mức thì quay về giá thường cho phần còn lại của khung.
- **R-PRC-04** Ngoài flash sale, PHẢI có `unit_price ≥ cost_price × 1,02`. Nếu
  công thức cho giá thấp hơn, nâng lên mức này (làm tròn lên 1.000). Chỉ dòng
  flash sale được phép bán dưới giá vốn (S-PRC-05).

### 6.2 Danh mục voucher

| Mã | Loại | `promo_type` / `apply_level` | `eligibility` | Mức giảm | Đơn tối thiểu | Hiệu lực | `usage_limit` / `per_customer_limit` |
|---|---|---|---|---|---|---|---|
| V1 | Voucher sàn ngày sale lớn | Platform Voucher / Order | All | 3 mức mỗi ngày: giảm 30.000; giảm 100.000; giảm 10% tối đa 50.000 | 300.000; 1.000.000; 200.000 | Trọn ngày sale | 30–60% số đơn dự kiến đủ điều kiện / 1 |
| V2 | Voucher sàn ngày lương | Platform Voucher / Order | All | 8%, tối đa 40.000 | 150.000 | Ngày 25 | Như V1 / 1 |
| V3 | Voucher khách mới | Platform Voucher / Order | New Customer | 50.000 | 99.000 | Cả kỳ | Không giới hạn / 1 |
| V4 | Voucher thành viên | Platform Voucher / Order | Gold+ hoặc Platinum | Gold+: 50.000; Platinum: 100.000 | 500.000; 800.000 | Trọn tháng, tạo ngày 1 | Không giới hạn / 2 |
| V5 | Voucher Livestream | Platform Voucher / Order | Livestream Only | 15%, tối đa 100.000 | 200.000 | 19:00–22:00 ngày có live | 500–5.000 / 1 |
| V6 | Freeship | Freeship Voucher / Shipping | All | Hằng tuần: 15.000 phí ship; ngày sale lớn: 30.000 | 99.000; 199.000 | Theo tuần / trọn ngày sale | Không giới hạn / 3 mỗi tuần; 1 mỗi ngày sale |
| V7 | Voucher toàn shop | Seller Voucher / Order | All | Cố định 10.000 / 20.000 / 50.000, hoặc 5–15% tối đa 20.000–100.000 | 99.000 / 199.000 / 499.000; loại %: 150.000 | 7–30 ngày | 100–2.000 / 1 |
| V8 | Voucher sản phẩm | Seller Voucher / Item (`product_id` = 1 trong 3 sản phẩm bán chạy của shop) | All | 10–20% giá sản phẩm, làm tròn 1.000, ghi dạng cố định | 0 | 7–14 ngày | 50–500 / 1 |
| V9 | Voucher shop ngày sale lớn | Seller Voucher / Order | All | 20.000–100.000 | 2–5 lần mức giảm | Trọn ngày sale | 200–3.000 / 1 |

- **R-PRM-01** Số voucher shop hoạt động đồng thời: `Mall` 2–3, `Preferred` 1–2,
  `Normal` 0–1 (50% có). V8 chỉ dành cho `Mall` và `Preferred`. V9 chỉ cho seller
  có sản phẩm tham gia ngày sale đó.
- **R-PRM-02** Voucher được ghi vào OLTP trước ngày hiệu lực 1–3 ngày (V1, V5,
  V6, V9), hoặc đúng ngày bắt đầu (V2, V4, V7, V8). V3 ghi lúc khởi tạo.
- **R-PRM-03** Voucher **không bị UPDATE** sau khi tạo. Lượt đã dùng được bộ sinh
  theo dõi trong bộ nhớ, không lưu thành cột.

### 6.3 Điều kiện được dùng voucher

Một voucher dùng được cho đơn tạo lúc `t` khi thỏa **tất cả**:

- **R-PRM-04** `start_date ≤ t ≤ end_date`.
- **R-PRM-05** Còn lượt: số lượt đã dùng < `usage_limit` (nếu có), và số lần khách
  này đã dùng < `per_customer_limit`.
- **R-PRM-06** **Khách vãng lai không dùng được voucher nào** (phải đăng nhập).
- **R-PRM-07** Voucher shop: `promotions.seller_id = orders.seller_id`. Voucher
  sản phẩm: đơn có dòng chứa đúng `product_id` đó.
- **R-PRM-08** `eligibility`:
  - `New Customer`: đây là đơn đầu tiên không bị hủy của khách, và đặt trong vòng
    30 ngày từ ngày đăng ký.
  - `Gold+`: hạng thành viên tại `t` là `Gold` hoặc `Platinum`. `Platinum`: chỉ
    hạng `Platinum`.
  - `Livestream Only`: đơn thuộc kênh Livestream.
- **R-PRM-09** Đạt `min_order_value` theo đúng cơ sở tính ở R-PRM-11.
- **R-PRM-10** Đơn chỉ gồm hàng `DIGITAL` không dùng freeship (không có phí ship).

### 6.4 Cộng dồn và thứ tự áp

- **R-PRM-11** Mỗi đơn dùng tối đa **1 voucher shop** (V7, V8 hoặc V9), **1 voucher
  sàn** (V1–V5) và **1 freeship** (V6). Áp theo thứ tự:
  1. Voucher shop. Cơ sở: `G` = tổng `quantity × unit_price` của đơn (voucher
     toàn shop), hoặc giá trị dòng của sản phẩm đó (voucher sản phẩm).
  2. Voucher sàn. Cơ sở: `G − giảm giá của voucher shop`.
  3. Freeship. Điều kiện tối thiểu xét trên `G − tổng giảm giá hàng`; số tiền giảm
     trừ vào `shipping_fee`.
- **R-PRM-12** Số tiền giảm:
  - Loại cố định: `min(discount_value, cơ sở)`.
  - Loại %: `min(floor(tỷ lệ × cơ sở), max_discount_amount)`.
  - Freeship: `min(discount_value, shipping_fee)`.
- **R-PRM-13** Khách chọn voucher cho giảm nhiều nhất trong số voucher hợp lệ cùng
  loại; bằng nhau thì chọn `promotions.id` nhỏ hơn. Xác suất khách có dùng (khi có
  voucher hợp lệ):

| Loại | Ngày thường | Ngày sale lớn |
|---|---|---|
| Voucher shop | 55% | 80% |
| Voucher sàn | 50% | 85% |
| Freeship | 70% | 90% |

- **R-PRM-14** Gom đơn: ngày sale lớn, nếu `G` thấp hơn ngưỡng của voucher sàn tốt
  nhất không quá 15%, có 40% khả năng khách thêm một sản phẩm khác của cùng shop
  để đạt ngưỡng (S-PRM-08).
- **R-PRM-15** Checkout nhiều shop (tách thành nhiều đơn, R-ORD-04): voucher sàn có
  `per_customer_limit = 1` chỉ áp cho **một** đơn, là đơn có cơ sở lớn nhất đạt
  ngưỡng.

### 6.5 Phân bổ giảm giá xuống từng dòng

- **R-PRM-16** Voucher cấp đơn được chia cho các dòng **tỷ lệ với cơ sở của từng
  dòng**: voucher shop theo `quantity × unit_price` của dòng; voucher sàn theo
  `quantity × unit_price − phần giảm của voucher shop trên dòng đó`.
- **R-PRM-17** Làm tròn theo **phương pháp phần dư lớn nhất**: lấy phần nguyên của
  mỗi phần chia, rồi cộng từng đồng còn thiếu cho các dòng có phần thập phân lớn
  nhất (bằng nhau thì ưu tiên `line_number` nhỏ hơn). Tổng phần chia PHẢI bằng
  đúng số tiền giảm của voucher.
- **R-PRM-18** Voucher sản phẩm: toàn bộ số tiền giảm nằm trên dòng của sản phẩm đó.
- **R-PRM-19** Ghi kết quả:
  - `order_item_promotions`: mỗi cặp (dòng, voucher) có số tiền > 0 là một dòng.
    Không ghi dòng 0 đồng. Mỗi dòng hàng có 0, 1 hoặc 2 bản ghi.
  - `order_items.discount_amount` = tổng `applied_discount_amount` của dòng.
  - `order_items.net_amount = quantity × unit_price − discount_amount ≥ 0`.
  - Freeship **không** ghi vào `order_item_promotions`; ghi vào
    `orders.shipping_promotion_id` và `orders.shipping_discount_amount`.
  - `orders.total_gross_amount = G`; `orders.total_discount_amount` = tổng giảm
    giá hàng (không gồm freeship).
  - `orders.final_amount = total_gross_amount − total_discount_amount +
    shipping_fee − shipping_discount_amount`.

### 6.6 Lượt dùng và bên chịu chi phí

- **R-PRM-20** Lượt dùng được tính lúc tạo đơn, theo thứ tự thời gian (R-SIM-01).
  Khi đạt `usage_limit`, các đơn sau không dùng được nữa (S-PRM-06).
- **R-PRM-21** Đơn bị hủy **trước khi lấy hàng** (khách hủy, shop hủy, hệ thống tự
  hủy): hoàn lại lượt dùng cho cả giới hạn chung và giới hạn theo khách. Các dòng
  `order_item_promotions` vẫn giữ làm lịch sử. Đơn giao thất bại thì không hoàn
  lượt.
- **R-PRM-22** Voucher sàn và freeship do **sàn chịu**; voucher shop do **seller
  chịu**. Điều này quyết định tiền seller được nhận (mục 14).

### 6.7 Ví dụ tính toán đầy đủ

Đơn của một shop vào ngày 11.11, khách đăng nhập, giao liên vùng.

| Dòng | Sản phẩm | `list_price` | `unit_price` | `quantity` | Giá trị dòng |
|---|---|---|---|---|---|
| 1 | X | 350.000 | 299.000 | 1 | 299.000 |
| 2 | Y | 120.000 | 99.000 | 2 | 198.000 |
| | | | | **G** | **497.000** |

**Bước 1 — voucher shop V7**: giảm 10% tối đa 40.000, đơn tối thiểu 300.000.
10% × 497.000 = 49.700, vượt trần nên giảm 40.000. Chia theo giá trị dòng:

| Dòng | Phần chia chính xác | Phần nguyên | Sau khi cộng phần dư |
|---|---|---|---|
| 1 | 40.000 × 299.000 / 497.000 = 24.064,39 | 24.064 | 24.064 |
| 2 | 40.000 × 198.000 / 497.000 = 15.935,61 | 15.935 | **15.936** (phần thập phân lớn hơn) |

**Bước 2 — voucher sàn V1**: giảm 50.000, đơn tối thiểu 400.000. Cơ sở =
497.000 − 40.000 = 457.000, đạt ngưỡng. Cơ sở từng dòng: 274.936 và 182.064.

| Dòng | Phần chia chính xác | Phần nguyên | Sau khi cộng phần dư |
|---|---|---|---|
| 1 | 50.000 × 274.936 / 457.000 = 30.080,53 | 30.080 | **30.081** |
| 2 | 50.000 × 182.064 / 457.000 = 19.919,47 | 19.919 | 19.919 |

**Bước 3 — freeship V6 ngày sale**: giảm 30.000 phí ship, đơn tối thiểu 199.000.
Cơ sở 407.000 đạt. Phí ship liên vùng 35.000, nên giảm 30.000.

**Kết quả ghi vào OLTP**

| Bảng | Giá trị |
|---|---|
| `order_items` dòng 1 | `discount_amount` = 24.064 + 30.081 = 54.145; `net_amount` = 244.855 |
| `order_items` dòng 2 | `discount_amount` = 15.936 + 19.919 = 35.855; `net_amount` = 162.145 |
| `order_item_promotions` | 4 dòng: (1, V7, 24.064), (1, V1, 30.081), (2, V7, 15.936), (2, V1, 19.919) |
| `orders` | `total_gross_amount` 497.000; `total_discount_amount` 90.000; `shipping_fee` 35.000; `shipping_discount_amount` 30.000; `final_amount` **412.000** |
| `payments` | 1 dòng `Success`, `paid_amount` 412.000 |

Kiểm tra: 244.855 + 162.145 = 407.000 = 497.000 − 90.000.

Phần seller được ghi nhận (mục 14) = giá trị dòng − voucher shop: dòng 1 là
274.936, dòng 2 là 182.064, tổng 457.000. Voucher sàn 50.000 và freeship 30.000
do sàn chịu.

---

## 7. Đơn hàng

### 7.1 Tạo đơn mới

- **R-ORD-01** Số đơn trong ngày theo R-DEM-01 và R-DEM-02; giờ đặt theo 3.4.
- **R-ORD-02** Người mua:

| Loại | Tỷ lệ | Cách chọn |
|---|---|---|
| Khách vãng lai | `{guest_order_share}` | `customer_id = NULL`, chỉ kênh Web, địa chỉ theo R-ADR-06 |
| Khách mua lần đầu | 25% năm đầu, 15% năm sau | Khách đã đăng ký chưa từng mua, đăng ký trong 30 ngày gần nhất được ưu tiên |
| Khách mua lại | Phần còn lại | Theo trọng số `λ` (R-CUS-04) |

  Khách phải có `registration_date < created_at` của đơn.
- **R-ORD-03** Kênh: App 60%, Web 30%, Livestream 10% (sau `{livestream_launch}`;
  trước đó chia lại cho App và Web). Đơn Livestream nghiêng về G3, G4 và seller
  `Mall`. Nếu đơn có phiên (`session_id`) thì kênh của đơn = kênh của phiên.
- **R-ORD-04** Chọn hàng:
  1. Chọn sản phẩm đầu tiên theo trọng số = `w` (R-CAT-05) × mùa vụ (3.5) × hệ số
     hạng seller (`Mall` 1,5; `Preferred` 1,2; `Normal` 1,0).
  2. Shop của đơn = seller của sản phẩm đó.
  3. Số dòng: 1 (60%), 2 (25%), 3 (10%), 4–6 (5%); ngày sale lớn dịch lên một bậc
     với xác suất 30%. Các dòng sau chọn trong sản phẩm của **cùng shop**. Shop có
     ít sản phẩm hơn số dòng thì giảm số dòng.
  4. Không có hai dòng cùng `product_id` trong một đơn. Số lượng mỗi dòng theo
     nhóm danh mục (5.6).
  5. Checkout nhiều shop: 10% số lần checkout (ngày sale lớn 18%) gồm 2–3 shop,
     tách thành 2–3 đơn có cùng `created_at`, cùng khách, cùng phiên.
- **R-ORD-05** Chỉ được chọn sản phẩm thỏa tại thời điểm đặt: `is_active = true`,
  `created_at` ≤ thời điểm đặt, seller `Active`, và (với hàng không phải
  `DIGITAL`) còn hàng khả dụng (`quantity_on_hand − quantity_reserved`) đủ số
  lượng ở ít nhất một kho. Hết hàng thì khách không mua được (mất doanh số,
  S-INV-03).
- **R-ORD-06** Giá từng dòng theo 6.1; voucher theo 6.3–6.5.
- **R-ORD-07** Phí ship trước giảm (`shipping_fee`) theo vùng giữa kho xuất và địa
  chỉ nhận: cùng tỉnh 15.000; cùng vùng 25.000; khác vùng 35.000. Cộng 10.000 nếu
  đơn có hàng G2 thuộc 1882 hoặc 4221 (hàng cồng kềnh). Giao hỏa tốc: 50.000. Đơn
  chỉ có hàng `DIGITAL`: 0.
- **R-ORD-08** Địa chỉ nhận: địa chỉ mặc định 90%; địa chỉ khác của khách 8%; với
  khách có địa chỉ ở tỉnh khác thì đó là đơn gửi tặng (S-ORD-13). `shipping_address_id`
  PHẢI thuộc đúng khách của đơn (trừ khách vãng lai).
- **R-ORD-09** `line_number` đánh 1, 2, 3… theo thứ tự thêm vào đơn.
- **R-ORD-10** Gán chiến dịch (`campaign_id`) theo R-MKT-08.

### 7.2 Vòng đời đơn

```text
Pending ──(thanh toán thành công / COD được xác nhận)──> Processing
Pending ──(khách hủy / hết hạn thanh toán / shop không xác nhận)──> Cancelled
Processing ──(giao thành công)──> Completed
Processing ──(khách hủy hoặc shop hủy trước khi lấy hàng)──> Cancelled
Processing ──(giao thất bại)──> Cancelled
```

- **R-ORD-11** Mốc thời gian (giờ tính từ `created_at`; seller `Mall` dùng nửa dưới
  của khoảng):

| Mốc | Thời gian | Ghi chú |
|---|---|---|
| Thanh toán ví, thẻ | 0,5–10 phút | Thất bại theo R-PAY-03 |
| Chuyển khoản | 0–24 giờ (trung vị 30 phút) | Quá 24 giờ chưa trả thì hệ thống hủy |
| COD | Không có bước trả trước | Chuyển `Processing` khi shop xác nhận |
| Shop xác nhận, tạo vận đơn | 1–12 giờ sau khi `Processing` | |
| Lấy hàng (`picked_at`) | 2–36 giờ sau khi tạo vận đơn | Cộng R-DEM-03, R-DEM-04 |
| Giao (`delivered_at`) | Cùng tỉnh 1–2 ngày; cùng vùng 2–3; khác vùng 3–5; hàng quốc tế 7–14 | Chỉ giao 8:00–20:00 |
| Giao hỏa tốc | 2–4 giờ sau khi đặt | 3% đơn đủ điều kiện: shop `Mall` hoặc `Preferred`, kho cùng tỉnh với khách, đặt trước 18:00 |

- **R-ORD-12** `completed_at = delivered_at`. `cancelled_at` = thời điểm hủy hoặc
  `failed_at`. Mỗi đơn chỉ có một trong hai mốc.
- **R-ORD-13** Hủy đơn:

| Nguyên nhân | Xác suất | Thời điểm |
|---|---|---|
| Khách hủy | COD 4%, trả trước 2% | Trước `picked_at` |
| Shop hủy (hết hàng, không xác nhận trong 48 giờ) | `Normal` 1%, `Preferred` 0,5%, `Mall` 0,2% | 2–48 giờ sau khi đặt |
| Hệ thống hủy (không thanh toán) | Theo R-PAY-03, R-PAY-04 | Hết hạn thanh toán |
| Giao thất bại | COD 7%, trả trước 1,5% | `failed_at` |
| Shop bị khóa | Mọi đơn chưa lấy hàng của shop | Lúc khóa (R-SEL-06) |

- **R-ORD-14** Trạng thái dòng:
  - Đơn `Pending` hoặc `Processing`: dòng ở trạng thái `Pending`.
  - Đơn `Completed`: dòng chuyển `Fulfilled` lúc giao, rồi `Returned` nếu sau đó
    được hoàn tiền (mục 11).
  - Đơn `Cancelled`: mọi dòng `Cancelled`.
- **R-ORD-15** Hủy một phần: 0,5% đơn nhiều dòng có **một dòng hết hàng** lúc shop
  xác nhận. Dòng đó thành `Cancelled`, các dòng khác giao bình thường. Các tổng
  tiền của `orders` giữ nguyên như lúc đặt (không tính lại). Phần tiền của dòng bị
  hủy được hoàn theo R-PAY-06 và không thu khi giao COD. Voucher cấp đơn vẫn giữ
  nguyên dù phần còn lại thấp hơn ngưỡng (sàn không thu hồi).
- **R-ORD-16** Đơn có hàng `DIGITAL`: không có vận đơn, không có COD;
  `completed_at` = thời điểm thanh toán thành công + 1–30 phút. Đơn không trộn
  hàng `DIGITAL` với hàng vật lý.
- **R-ORD-17** `orders.updated_at` = thời điểm thay đổi gần nhất của chính đơn hoặc
  của bất kỳ dòng, thanh toán, vận đơn, hoàn hàng nào thuộc đơn.

---

## 8. Thanh toán (`payments`)

- **R-PAY-01** Chọn phương thức:

| Phương thức | Tỷ lệ cơ sở |
|---|---|
| COD | 50% (giảm 2 điểm % mỗi năm, chuyển sang ví điện tử) |
| Momo | 15% |
| ZaloPay | 10% |
| Credit Card | 12% |
| Bank Transfer | 13% |

  Điều chỉnh rồi chuẩn hóa lại tổng về 100%:
  - `final_amount` > 5.000.000: tỷ lệ COD giảm một nửa, thẻ và chuyển khoản tăng gấp đôi.
  - `final_amount` > 20.000.000: không cho COD.
  - Khách vãng lai: COD 70%, chuyển khoản 30%.
  - Kênh Livestream: COD 60%.
  - Hàng `DIGITAL`: không COD.
- **R-PAY-02** `payments` là **sổ giao dịch**: mỗi lần thử thanh toán hoặc mỗi lần
  hoàn tiền là một dòng mới. Chỉ được UPDATE `Pending → Success` hoặc
  `Pending → Failed`. Không xóa dòng nào.
- **R-PAY-03** Ví điện tử và thẻ: mỗi lần thử thành công 93%. Thất bại thì ghi dòng
  `Failed` với `paid_amount = 0`. 60% khách thử lại trong 15 phút (dòng mới, cùng
  hoặc khác phương thức trả trước, thành công 90%). Không thanh toán được thì đơn
  giữ `Pending` và bị hệ thống hủy sau 24 giờ.
- **R-PAY-04** Chuyển khoản: tạo dòng `Pending` lúc đặt. 95% chuyển thành `Success`
  trong 24 giờ; còn lại thành `Failed` và đơn bị hủy lúc hết 24 giờ.
- **R-PAY-05** COD: tạo dòng `Pending` (`paid_amount = 0`) lúc đặt. Giao thành công
  thì chuyển `Success`, `transaction_time = delivered_at`,
  `paid_amount = final_amount − tổng net_amount các dòng bị hủy một phần`. Đơn hủy
  hoặc giao thất bại thì chuyển `Failed`.
- **R-PAY-06** Hoàn tiền: ghi **dòng mới** `Refunded` với `paid_amount` **âm**:

| Trường hợp | Số tiền | Thời điểm |
|---|---|---|
| Đơn trả trước bị hủy sau khi đã thanh toán | −`final_amount` | Ví: 1–3 ngày sau hủy; thẻ, chuyển khoản: 3–7 ngày |
| Hủy một phần đơn trả trước | −`net_amount` của dòng bị hủy | Như trên |
| Hoàn hàng | −`returns.refund_amount` | `returns.refunded_at` |

  Phương thức của dòng hoàn = phương thức của dòng `Success`; đơn COD thì hoàn qua
  `Bank Transfer`.
- **R-PAY-07** Mỗi đơn có tối đa một dòng `Success`. Phương thức thanh toán của
  đơn (dùng cho `Dim_Payment_Method`) là phương thức của dòng `Success` này.
- **R-PAY-08** Tổng tiền thực thu của một đơn:
  - Đơn `Completed`: `Σ paid_amount = final_amount − Σ net_amount dòng hủy một
    phần − Σ refund_amount đã hoàn`.
  - Đơn `Cancelled`: `Σ paid_amount = 0`.

---

## 9. Giao vận (`shipments`)

- **R-SHP-01** Mỗi đơn có **tối đa một vận đơn**. Không tạo vận đơn cho đơn
  `DIGITAL` và đơn bị hủy trước khi shop xác nhận.
- **R-SHP-02** Kho xuất được chọn **lúc tạo đơn** để giữ hàng (R-INV-03): ưu tiên kho
  cùng vùng với địa chỉ nhận còn đủ hàng cho mọi dòng; nếu không có thì kho bất kỳ
  còn đủ hàng; nếu không kho nào đủ thì áp R-ORD-15 hoặc shop hủy đơn. Hàng
  `CROSS_BORDER` luôn xuất từ `WH-CB-01`.
- **R-SHP-03** Đơn vị vận chuyển theo tỷ trọng ở 5.5. Đơn hỏa tốc luôn dùng `GHN`.
- **R-SHP-04** Trạng thái và mốc thời gian:
  `Created` (`created_at`, lúc shop xác nhận) → `Picked` (`picked_at`) →
  `In Transit` → `Delivered` (`delivered_at`) hoặc `Failed` (`failed_at`).
  `shipment_status` = trạng thái cuối cùng đã đạt. Luôn có
  `created_at ≤ picked_at < delivered_at` (hoặc `< failed_at`).
- **R-SHP-05** Không có `picked_at`, `delivered_at`, `failed_at` nào nằm trong
  khoảng nghỉ Tết (R-DEM-03).
- **R-SHP-06** `shipping_cost` (sàn trả cho đơn vị vận chuyển) = cước theo vùng của
  R-ORD-07 × hệ số hãng (`GHN` 1,05; `GHTK` 0,95; `VTP` 1,0; `JNT` 0,90; `NJV`
  0,92), làm tròn 1.000. Cước này **không phụ thuộc** freeship hay phí khách trả.
- **R-SHP-07** `shipments.order_code` = `orders.order_code` (hệ thống kho không biết
  `orders.id`). `tracking_code` duy nhất theo R-ID-07.
- **R-SHP-08** Giao thất bại: `failed_at` = thời điểm giao dự kiến + 1–2 ngày (các
  lần giao lại). Hàng quay về kho xuất sau 3–7 ngày (R-INV-06).

---

## 10. Tồn kho

Hệ thống kho định danh sản phẩm bằng `sku` (= `products.sku`), không dùng
`product_id`.

- **R-INV-01** Cặp (kho, SKU) được kích hoạt:
  - Hàng `PHYSICAL`: một **kho chính** thuộc vùng của tỉnh seller (Bắc:
    `WH-HN-01`/`WH-HN-02`; Trung: `WH-DN-01`; Nam: `WH-HCM-01`/`WH-HCM-02`/
    `WH-CT-01`, chọn theo seed). 20% sản phẩm phổ biến nhất có thêm **kho phụ**:
    `WH-HCM-01` nếu kho chính ở Bắc hoặc Trung, `WH-HN-01` nếu kho chính ở Nam.
  - Hàng `CROSS_BORDER`: chỉ `WH-CB-01`.
  - Hàng `DIGITAL`: không có cặp nào, không có tồn kho.
- **R-INV-02** Tồn đầu: một dòng `Import` tại `max({sim_start}, products.created_at)`
  với số lượng = `{target_cover_days}` × nhu cầu ngày ước tính của cặp (tối thiểu 5).
- **R-INV-03** Giữ hàng: lúc tạo đơn, `quantity_reserved += quantity` ở kho đã chọn
  (R-SHP-02). Hàng khả dụng = `quantity_on_hand − quantity_reserved`, luôn ≥ 0.
- **R-INV-04** Lấy hàng: tại `picked_at`, `quantity_on_hand −= q` và
  `quantity_reserved −= q`. Ghi một dòng `Sale` cho mỗi dòng hàng:
  `quantity_change = −q`, `reference_code = order_code`, `movement_date = picked_at`.
- **R-INV-05** Hủy trước khi lấy hàng (kể cả hủy một phần): `quantity_reserved −= q`,
  không ghi movement.
- **R-INV-06** Giao thất bại: hàng về kho sau 3–7 ngày, ghi `Return` với
  `quantity_change = +q`, `reference_code = order_code`.
- **R-INV-07** Khách hoàn hàng: lý do khác `Damaged` thì ghi `Return` (+ số lượng
  hoàn) lúc kho nhận hàng, tức 2–5 ngày sau `requested_at` và trước `refunded_at`.
  Lý do `Damaged` thì không nhập lại kho (hàng tiêu hủy).
- **R-INV-08** Nhập bổ sung: 23:00 mỗi ngày, nếu `hàng khả dụng + hàng đang về` <
  `{reorder_days}` × nhu cầu trung bình 14 ngày gần nhất (tối thiểu 2), thì đặt
  hàng. Hàng về sau `{lead_time}`, ghi `Import` với số lượng đưa tồn lên
  `{target_cover_days}` × nhu cầu trung bình (tối thiểu 5).
- **R-INV-09** Trữ hàng trước sale: 7–10 ngày trước 11.11 và 12.12, sản phẩm tham gia
  sale nhập thêm 2–3 lần mức mục tiêu.
- **R-INV-10** Hàng bán chậm: 10% catalog (theo seed) có mức tồn mục tiêu 120 ngày,
  tạo nhóm "tồn nhiều, bán ít" (S-INV-04).
- **R-INV-11** Hàng hay hết: 5% catalog có thời gian nhập hàng gấp 3 lần, tạo các giai
  đoạn hết hàng (S-INV-03).
- **R-INV-12** Kiểm kê ngày cuối tháng: 5% số cặp có một dòng `Adjustment` ±1–3 đơn
  vị (80% là âm, do hao hụt). Không được làm tồn âm hoặc thấp hơn lượng đang giữ.
- **R-INV-13** Sản phẩm ngừng kinh doanh: sau khi các đơn đang giữ hàng xử lý xong,
  phần tồn còn lại trả về seller bằng một dòng `Adjustment` (−toàn bộ tồn) trong
  vòng 7 ngày. Sau đó không nhập thêm.
- **R-INV-14** `inventory_daily_balance`: lúc 23:59:59 mỗi ngày, ghi một dòng cho
  **mỗi cặp đã kích hoạt** (`balance_date`, `warehouse_id`, `sku`,
  `quantity_on_hand`, `quantity_reserved`). Ghi cả khi tồn bằng 0, vì "hết hàng"
  khác "không có dữ liệu". Cặp của sản phẩm ngừng bán dừng ghi sau 30 ngày kể từ
  khi tồn về 0.
- **R-INV-15** `inventory_levels`: mỗi cặp một dòng, luôn bằng trạng thái hiện tại.
  Cuối kỳ phải trùng với `inventory_daily_balance` của ngày cuối. `updated_at` =
  lần thay đổi tồn hoặc lượng giữ gần nhất.
- **R-INV-16** Bất biến, với mỗi cặp và mỗi ngày `d`:
  - `on_hand(d) = on_hand(d − 1) + Σ quantity_change` của các movement có ngày
    `movement_date = d`.
  - `on_hand ≥ 0` và `0 ≤ reserved ≤ on_hand`.
  - `reserved` = tổng số lượng của các dòng đã giữ ở kho đó, chưa lấy hàng, chưa hủy.

---

## 11. Sau bán

### 11.1 Hoàn hàng (`returns`)

- **R-RET-01** Chỉ dòng `Fulfilled` của đơn `Completed`, không phải hàng `DIGITAL`.
  `requested_at` nằm trong `(completed_at; completed_at + {return_window}]`, 60%
  trong 3 ngày đầu. Khách vãng lai vẫn được hoàn.
- **R-RET-02** Xác suất hoàn của một dòng = tỷ lệ hoàn của nhóm (5.6), nhân thêm:
  dòng flash sale ×1,3; seller `Normal` ×1,2; seller `Mall` ×0,8; giao trễ hơn dự
  kiến trên 2 ngày ×1,5.
- **R-RET-03** Lý do hoàn:

| Nhóm | `Changed Mind` | `Not As Described` | `Wrong Item` | `Damaged` |
|---|---|---|---|---|
| G3 | 45% | 30% | 15% | 10% |
| G1, G2, G5 | 10% | 30% | 15% | 45% |
| Nhóm khác | 25% | 25% | 25% | 25% |

- **R-RET-04** Mỗi dòng có tối đa một yêu cầu hoàn. Hoàn toàn bộ dòng 85%; hoàn một
  phần 15% (chỉ khi `quantity ≥ 2`, số lượng hoàn từ 1 đến `quantity − 1`).
- **R-RET-05** `refund_amount = round(net_amount × số lượng hoàn / quantity)`, làm
  tròn nửa lên. Hoàn toàn bộ thì đúng bằng `net_amount`. Không hoàn phí ship.
- **R-RET-06** Trạng thái: `Requested` → `Approved` (85%, sau 1–2 ngày) →
  `Refunded` (`refunded_at` = `requested_at` + 3–10 ngày); hoặc `Requested` →
  `Rejected` (15%, sau 1–3 ngày, `refund_amount` đặt về 0, `refunded_at` NULL).
- **R-RET-07** Khi `Refunded`: dòng hàng chuyển `item_status = 'Returned'` (kể cả
  hoàn một phần), ghi dòng hoàn tiền theo R-PAY-06, nhập kho theo R-INV-07.

### 11.2 Đánh giá (`product_reviews`)

- **R-REV-01** Chỉ khách đăng nhập, chỉ dòng `Fulfilled` hoặc `Returned` của đơn
  `Completed`. Mỗi dòng tối đa một đánh giá. `customer_id = orders.customer_id`,
  `product_id = order_items.product_id`.
- **R-REV-02** Xác suất đánh giá 25% mỗi dòng (seller `Mall` 30%).
  `created_at` = `completed_at` + 1–14 ngày, 60% trong 3 ngày đầu.
- **R-REV-03** Phân bố sao cơ sở: 5★ 62%, 4★ 20%, 3★ 7%, 2★ 3%, 1★ 8%. Dòng hoàn
  vì `Damaged` hoặc `Not As Described`: 1★ 60%, 2★ 25%, 3★ 15%. Giao trễ: 30% khả
  năng bị trừ 1 sao.
- **R-REV-04** `comment` lấy từ mẫu câu tiếng Việt theo số sao; 30% để NULL.

---

## 12. Marketing và chi phí quảng cáo

- **R-MKT-01** Lịch chiến dịch:

| `campaign_type` | Khi nào | Thời gian chạy | Mã kênh |
|---|---|---|---|
| Mega Sale | Mỗi ngày đôi `D` | `[D−5; D]`; riêng 11.11 và 12.12 là `[D−10; D]` | `WEB`, `MOBILE_APP`, thêm `LIVE` sau ra mắt |
| Mega Sale | Black Friday | `[BF−3; Cyber Monday]` | Như trên |
| Mega Sale | Tết | `[T−28; T−4]` | `WEB`, `MOBILE_APP` |
| Mega Sale | Tựu trường | 1/8 – 5/9 | `WEB`, `MOBILE_APP` |
| Flash Sale | Mỗi thứ Sáu | 1 ngày | `MOBILE_APP` |
| Brand Awareness | Mỗi quý | 30–60 ngày | `WEB` |
| Retargeting | Mỗi tháng | Trọn tháng, 1 chiến dịch cho mỗi kênh | `WEB`, `MOBILE_APP` |
| Livestream Show | Mỗi tháng sau ra mắt | Tối thứ Sáu, thứ Bảy và các ngày sale lớn | `LIVE` |
| Brand Awareness | Trước ra mắt Livestream | `[{livestream_launch} − 30; {livestream_launch} − 1]` | `LIVE` |

- **R-MKT-02** Chỉ chiến dịch Mega Sale chi trên nhiều kênh (`MOBILE_APP` 55%, `WEB`
  30%, `LIVE` 15% ngân sách). `target_channel_code` = kênh có tỷ trọng ngân sách
  lớn nhất. Các loại khác chỉ chi trên đúng `target_channel_code`.
- **R-MKT-03** Chiến dịch được ghi vào OLTP 14–30 ngày trước `start_date`.
  `budget_amount` = tỷ lệ quảng cáo `U(2%; 6%)` × GMV dự kiến của các kênh trong
  thời gian chạy, làm tròn đến 1.000.000.
- **R-MKT-04** Chi thực tế: 90% chiến dịch chi `U(80%; 100%)` ngân sách; 10% chi
  vượt `U(100%; 110%)` (S-MKT-01).
- **R-MKT-05** Phân bổ theo ngày: Mega Sale tăng dần về ngày `D`, ngày `D` chiếm
  30–40% tổng chi; loại khác chia đều ±20%.
- **R-MKT-06** Mỗi dòng `ad_spend_logs` ứng với một bộ (chiến dịch, `channel_code`,
  `log_date`), không trùng:
  - `impressions = round(cost_amount / CPM × 1.000)`, CPM `U(15.000; 40.000)`,
    ngày cao điểm ×1,5.
  - `clicks = round(impressions × CTR)`, CTR: Retargeting 2–4%; Mega Sale, Flash
    Sale 1–3%; Livestream Show 1,5–3%; Brand Awareness 0,5–1,5%.
  - Luôn có `clicks ≤ impressions`.
- **R-MKT-07** Số liệu quảng cáo về trễ: dòng của ngày `d` được ghi vào OLTP lúc
  23:00 ngày `d` (5%), ngày `d+1` (60%), `d+2` (25%) hoặc `d+3` (10%), vì nền tảng
  quảng cáo chốt số liệu chậm 1–3 ngày (S-MKT-04).
- **R-MKT-08** Gán chiến dịch cho đơn (`orders.campaign_id`):
  - Trong `{clickstream_window}`: bằng `sessions.campaign_id` nếu phiên của đơn có
    `traffic_source = 'Paid Ads'`, ngược lại NULL.
  - Ngoài cửa sổ: với mỗi (chiến dịch, kênh, ngày), số đơn được gán =
    `round(clicks × CVR)`, CVR `U(2%; 4%)`. Chọn ngẫu nhiên trong các đơn cùng
    ngày, cùng kênh chưa được gán. Tổng số đơn được gán của một kênh trong ngày
    không quá 60% số đơn của kênh đó.
  - Chiến dịch được gán phải đang chạy lúc đặt đơn và có chi tiêu trên kênh của
    đơn trong ngày đó.
  - 5% chiến dịch Brand Awareness có CVR = 0 (S-MKT-02).

---

## 13. Clickstream

- **R-CLK-01** Chỉ sinh trong `{clickstream_window}`. Ngoài cửa sổ không có
  `sessions`, `page_events`, `cart_items`, và `orders.session_id = NULL`.
- **R-CLK-02** Trong cửa sổ, mọi đơn có đúng một phiên. Các đơn tách từ cùng một lần
  checkout dùng chung phiên.
- **R-CLK-03** Tổng số phiên mỗi ngày = số đơn / tỷ lệ chuyển đổi `U(2,5%; 3,5%)`.
  Phần lớn phiên không mua.
- **R-CLK-04** Nguồn truy cập: số phiên `Paid Ads` của mỗi (chiến dịch, kênh, ngày) =
  `round(clicks × U(70%; 90%))`, luôn ≤ `clicks`. Số phiên còn lại chia `Organic`
  47%, `Direct` 29%, `Social` 18%, `Email` 6%.
- **R-CLK-05** Thiết bị: App gồm `Mobile` 95%, `Tablet` 5%; Web gồm `Desktop` 55%,
  `Mobile` 40%, `Tablet` 5%; Livestream gồm `Mobile` 90%, `Tablet` 10%.
- **R-CLK-06** Tỷ lệ phiên đã đăng nhập: App 90%, Livestream 85%, Web 70%. Khách
  phải có `registration_date ≤ started_at`. Đơn của khách vãng lai chỉ đến từ phiên
  Web chưa đăng nhập.
- **R-CLK-07** Thời lượng phiên theo phân phối log-normal, trung vị 6 phút; phiên
  thoát ngay dưới 1 phút. `ended_at > started_at`, mọi sự kiện nằm trong
  `[started_at; ended_at]` và theo đúng thứ tự thời gian.
- **R-CLK-08** Phễu cho phiên không thoát ngay: `search` 0–3 lần; `view_product` 2–15
  lần (sản phẩm chọn như R-ORD-04, có thể đang hết hàng); `add_to_cart` ở khoảng 10%
  phiên (chỉ sản phẩm còn hàng); `remove_from_cart` với 20% món đã thêm;
  `begin_checkout` ở 50% phiên có giỏ; `purchase` ở 80% phiên đã checkout. Phiên
  thoát ngay (35%) có đúng 1 sự kiện `view_product` hoặc `search`.
- **R-CLK-09** Phiên có mua PHẢI có `view_product` và `add_to_cart` cho mỗi sản phẩm
  được mua (trừ sản phẩm đã nằm sẵn trong giỏ từ phiên trước, S-CLK-03), một
  `begin_checkout` trước 1–5 phút, và một sự kiện `purchase` cho mỗi đơn với
  `event_time = orders.created_at`, `order_id` = đơn đó.
- **R-CLK-10** `cart_items`:
  - `add_to_cart` tạo dòng `Active` (`added_at` = thời điểm sự kiện).
  - Được mua: `Ordered`, `closed_at = orders.created_at`.
  - Bị bỏ khỏi giỏ: `Removed`, `closed_at` = thời điểm bỏ.
  - Không mua, khách vãng lai: `Abandoned` lúc kết thúc phiên.
  - Không mua, khách đăng nhập: giữ `Active` tối đa 7 ngày. 15% trong số này được
    mua ở một phiên sau (S-CLK-03); số còn lại thành `Abandoned` lúc
    `added_at + 7 ngày`.
- **R-CLK-11** `page_events.product_id` NULL với sự kiện `search`. `order_id` chỉ có
  ở sự kiện `purchase`.

---

## 14. Đối soát người bán

- **R-FIN-04** Với mỗi dòng hàng:
  - `seller_funded` = tổng giảm giá từ voucher shop trên dòng.
  - `platform_funded` = tổng giảm giá từ voucher sàn trên dòng.
  - **Khoản ghi có cho seller** `credit = quantity × unit_price − seller_funded`
    `= net_amount + platform_funded`. Seller không chịu voucher sàn.
- **R-FIN-05** Hoa hồng của dòng = `round(credit × tỷ lệ)`, tỷ lệ theo R-FIN-03,
  làm tròn nửa lên.
- **R-FIN-06** Kỳ đối soát = tháng dương lịch. Mỗi (seller, tháng) có ít nhất một
  dòng giao thành công hoặc một khoản hoàn tạo một bản ghi `seller_payouts`, lập
  lúc 02:00 ngày 1 tháng sau với `payout_status = 'Pending'`, chuyển `Paid` vào ngày
  5–10 (`paid_at`). Kỳ cuối có thể còn `Pending` nếu hết kỳ mô phỏng.
- **R-FIN-07** `gross_sales` = Σ `credit` của các dòng `Fulfilled` hoặc `Returned`
  thuộc đơn có `completed_at` trong kỳ. Dòng hủy một phần không tính.
- **R-FIN-08** `refund_amount` = khoản **trừ của seller do hoàn hàng** =
  Σ `round(credit × số lượng hoàn / quantity)` của các yêu cầu có `refunded_at`
  trong kỳ. Khoản này tính theo `credit`, khác số tiền hoàn cho khách (tính theo
  `net_amount`); phần chênh là trợ giá voucher sàn được thu lại.
- **R-FIN-09** `commission_amount` = Σ hoa hồng các dòng ở R-FIN-07 − Σ
  `round(hoa hồng của dòng × số lượng hoàn / quantity)` của các khoản hoàn trong kỳ.
- **R-FIN-10** `payout_amount = gross_sales − refund_amount − commission_amount`.
  Có thể âm khi kỳ đó hoàn nhiều hơn bán (S-FIN-03).
- **R-FIN-11** Phí ship và cước vận chuyển không nằm trong đối soát người bán (sàn
  thu phí của khách và trả cước cho đơn vị vận chuyển).

---

## 15. Thay đổi dữ liệu chủ theo thời gian

Các thông tin chủ dưới đây thay đổi trong vận hành hằng ngày của sàn. Mọi thay
đổi đều cập nhật `updated_at` (R-SIM-05).

| Mã | Thực thể | Sự kiện | Tần suất | Cột thay đổi |
|---|---|---|---|---|
| R-CHG-01 | Seller | Sàn xét lại hạng (bên dưới) | Ngày 1 hằng quý | `tier` |
| R-CHG-02 | Seller | Chuyển địa điểm kinh doanh | 1% seller mỗi năm | `province`, `city` |
| R-CHG-03 | Seller | Đổi tên shop | 1% seller mỗi năm | `shop_name` |
| R-SEL-06 | Seller | Bị khóa do vi phạm (bên dưới) | 0,5% seller mỗi quý | `status` |
| R-CHG-04 | Khách | Chuyển nơi ở | 2% khách mỗi năm | `province`, `city` + địa chỉ mặc định mới |
| R-CHG-05 | Khách | Đổi số điện thoại | 1% khách mỗi năm | `phone_number` |
| R-CUS-05 | Khách | Sàn tính lại hạng thành viên | Ngày 1 hằng tháng | `membership_tier` |
| R-PRD-03 | Sản phẩm | Seller đổi giá niêm yết | 10% catalog mỗi quý | `original_price`, `price` |
| R-CHG-06 | Sản phẩm | Seller chuyển sản phẩm sang danh mục khác | 0,5% catalog mỗi quý | `category_id` |
| R-PRD-05 | Sản phẩm | Giá nhập thay đổi | 5% catalog mỗi nửa năm | `cost_price` |
| R-PRD-07 | Sản phẩm | Seller sửa tên nhập sai | Một lần cho 0,5% catalog | `name` |
| R-PRD-06 | Sản phẩm | Ngừng kinh doanh | 2% catalog mỗi năm | `is_active` |

- **R-CHG-01** Xét hạng seller lúc 00:00 ngày 1 hằng quý, theo 90 ngày trước đó:
  - `Normal` → `Preferred`: thuộc top 20% số đơn `Completed`, tỷ lệ shop hủy < 3%,
    điểm đánh giá trung bình (từ `product_reviews`) ≥ 4,3.
  - `Preferred` → `Normal`: tỷ lệ shop hủy > 6%, hoặc ra khỏi top 40% số đơn.
  - `Preferred` → `Mall`: 1–3 seller mỗi quý có ≥ 80% sản phẩm cùng thương hiệu
    (ký hợp đồng thương hiệu).
  - `Mall` không bị hạ hạng theo chỉ số.
- **R-SEL-06** Khóa shop: mỗi quý chọn 0,5% seller `Normal` thuộc nhóm 10% có tỷ lệ
  shop hủy cao nhất, khóa vào một ngày ngẫu nhiên. Cùng thời điểm, toàn bộ sản
  phẩm của shop chuyển `is_active = false`. Đơn chưa lấy hàng bị shop hủy; đơn đã
  lấy hàng vẫn giao. Shop không mở lại trong kỳ mô phỏng.
- **R-CHG-04** Khách chuyển nơi ở: tạo địa chỉ mới ở tỉnh mới, chuyển
  `is_default` sang địa chỉ mới, cập nhật `customers.province`, `city`,
  `updated_at`. Đơn sau đó giao tới địa chỉ mới theo R-ORD-08.
- **R-CHG-06** Đổi danh mục: 80% sang lá khác cùng gốc, 20% sang gốc khác.
- **R-CHG-07** Giờ xảy ra thay đổi: thay đổi do sàn thực hiện (xét hạng, khóa
  shop) chạy theo lịch đã nêu; thay đổi do seller thực hiện rơi vào 8:00–22:00;
  thay đổi do khách tự cập nhật rơi vào 7:00–23:00. Đơn hàng vẫn phát sinh bình
  thường trước và sau thời điểm thay đổi trong cùng ngày.

---

## 16. Danh mục tình huống

Đây là các tình huống vận hành mà dữ liệu nguồn PHẢI chứa (ở `full`, và nên có ở
`dev`). Cột "Dấu hiệu" cho biết cách kiểm tra bộ sinh đã thực sự tạo ra tình huống.

### 16.1 Giá bán

| Mã | Tình huống | Dấu hiệu trong dữ liệu |
|---|---|---|
| S-PRC-01 | Mua giá thường | `unit_price` ≈ `products.price`, không dùng voucher |
| S-PRC-02 | Seller đổi giá niêm yết giữa hai lần bán cùng sản phẩm (R-PRD-03) | Cùng `product_id`, `order_items.list_price` khác nhau theo thời gian |
| S-PRC-03 | Sản phẩm tham gia ngày sale lớn | `unit_price` thấp hơn ngày thường 5–30% |
| S-PRC-04 | Flash sale hết suất giữa khung giờ (R-PRC-03) | Cùng sản phẩm, cùng ngày, hai mức `unit_price` |
| S-PRC-05 | Bán dưới giá vốn trong flash sale | `unit_price < cost_price` |
| S-PRC-06 | Giá nhập thay đổi (R-PRD-05) | `cost_price` của sản phẩm thay đổi theo thời gian |

### 16.2 Khuyến mãi

| Mã | Tình huống | Dấu hiệu trong dữ liệu |
|---|---|---|
| S-PRM-01 | Đơn không dùng voucher (luôn đúng với khách vãng lai) | Không có dòng `order_item_promotions` |
| S-PRM-02 | Chỉ dùng voucher shop | Mỗi dòng hàng có 1 dòng `order_item_promotions`, voucher loại Seller |
| S-PRM-03 | Chỉ dùng voucher sàn | Mỗi dòng hàng có 1 dòng `order_item_promotions`, voucher loại Platform |
| S-PRM-04 | Dùng cả voucher sàn và voucher shop (ví dụ 6.7) | Mỗi dòng hàng có 2 dòng `order_item_promotions` |
| S-PRM-05 | Voucher sản phẩm | Chỉ dòng của sản phẩm đó có `order_item_promotions` |
| S-PRM-06 | Voucher hết lượt giữa ngày sale | Sau một thời điểm, đơn đủ điều kiện không còn dùng được voucher đó |
| S-PRM-07 | Voucher % chạm trần | Tổng giảm của voucher = `max_discount_amount` |
| S-PRM-08 | Gom đơn để đạt ngưỡng (R-PRM-14) | Ngày sale có nhiều đơn sát trên `min_order_value` |
| S-PRM-09 | Không đạt đơn tối thiểu | Có voucher đang chạy nhưng `G` < ngưỡng nên đơn không có voucher |
| S-PRM-10 | Voucher khách mới | Đơn đầu tiên trong 30 ngày từ ngày đăng ký |
| S-PRM-11 | Voucher hạng thành viên | Chỉ khách `Gold`/`Platinum` tại thời điểm đặt |
| S-PRM-12 | Voucher Livestream | Chỉ đơn kênh Livestream, 19–22h |
| S-PRM-13 | Freeship | `shipping_discount_amount > 0`, voucher không nằm trong `order_item_promotions` |
| S-PRM-14 | Đơn dùng voucher rồi bị hủy (R-PRM-21) | `order_item_promotions` còn nhưng đơn `Cancelled`; lượt dùng được hoàn |
| S-PRM-15 | Checkout nhiều shop (R-PRM-15) | Các đơn cùng phiên, cùng giờ; chỉ một đơn có voucher sàn |
| S-PRM-16 | Chia voucher lệch 1 đồng do làm tròn (R-PRM-17) | Các phần chia chênh nhau 1 đồng, tổng vẫn khớp |

### 16.3 Vòng đời đơn

| Mã | Tình huống | Dấu hiệu trong dữ liệu |
|---|---|---|
| S-ORD-01 | Giao thành công bình thường | `Completed`, vận đơn `Delivered` |
| S-ORD-02 | Giao hỏa tốc | `completed_at − created_at` < 4 giờ, hãng `GHN` |
| S-ORD-03 | Khách hủy trước khi lấy hàng | `Cancelled`, không có `picked_at` |
| S-ORD-04 | Shop hủy (hết hàng, không xác nhận) | `Cancelled` 2–48 giờ sau khi đặt, không có vận đơn |
| S-ORD-05 | Hệ thống hủy vì không thanh toán | Chỉ có payment `Failed`, hủy sau 24 giờ |
| S-ORD-06 | Thanh toán thất bại rồi thử lại thành công | 2 dòng payment: `Failed` rồi `Success` |
| S-ORD-07 | Giao thất bại, bom hàng COD | Vận đơn `Failed`, đơn `Cancelled`, có movement `Return` |
| S-ORD-08 | Hủy một phần (R-ORD-15) | Đơn `Completed` có một dòng `Cancelled` |
| S-ORD-09 | Đặt trong Tết, giao sau Tết | `created_at` trong `[T−3; T+5]`, `picked_at` ≥ `T+6` |
| S-ORD-10 | Đặt cuối tháng, giao tháng sau | Tháng của `created_at` ≠ tháng của `completed_at` |
| S-ORD-11 | Đơn còn dở dang khi kết thúc mô phỏng (R-SIM-07) | `Pending`/`Processing` ở ngày cuối |
| S-ORD-12 | Khách vãng lai | `customer_id` NULL |
| S-ORD-13 | Gửi tặng tỉnh khác | Tỉnh của `shipping_address_id` ≠ `customers.province` |
| S-ORD-14 | Đơn giá trị lớn | `final_amount` > 20.000.000, không có COD |
| S-ORD-15 | Hàng số (`DIGITAL`) | Không có vận đơn, không có movement |
| S-ORD-16 | Hàng quốc tế | Kho `WH-CB-01`, giao 7–14 ngày |
| S-ORD-17 | Shop bị khóa khi còn đơn (R-SEL-06) | Đơn chưa lấy hàng bị hủy cùng thời điểm khóa |
| S-ORD-18 | Khách mua lại nhiều lần | Một khách có nhiều đơn trong kỳ |

### 16.4 Sau bán

| Mã | Tình huống | Dấu hiệu trong dữ liệu |
|---|---|---|
| S-RET-01 | Hoàn toàn bộ dòng | `returns.quantity = order_items.quantity` |
| S-RET-02 | Hoàn một phần số lượng | `returns.quantity < order_items.quantity` |
| S-RET-03 | Yêu cầu hoàn bị từ chối | `status = 'Rejected'`, dòng vẫn `Fulfilled` |
| S-RET-04 | Hàng hoàn bị hỏng | Lý do `Damaged`, không có movement `Return` |
| S-RET-05 | Đánh giá thấp gắn với hoàn hàng | Review 1–2★ trên dòng có hoàn vì `Damaged`/`Not As Described` |
| S-RET-06 | Hoàn tiền đơn trả trước bị hủy | Payment `Refunded` với số tiền âm |

### 16.5 Tồn kho

| Mã | Tình huống | Dấu hiệu trong dữ liệu |
|---|---|---|
| S-INV-01 | Nhập bổ sung theo điểm đặt hàng (R-INV-08) | `Import` sau khi tồn khả dụng xuống thấp |
| S-INV-02 | Trữ hàng trước 11.11/12.12 (R-INV-09) | `Import` lớn 7–10 ngày trước ngày sale |
| S-INV-03 | Hết hàng, mất doanh số (R-INV-11) | Tồn = 0 nhiều ngày, không có đơn; trong cửa sổ clickstream vẫn có lượt xem |
| S-INV-04 | Tồn nhiều, bán ít (R-INV-10) | Tồn cao, rất ít `Sale` |
| S-INV-05 | Kiểm kê hao hụt (R-INV-12) | `Adjustment` âm ngày cuối tháng |
| S-INV-06 | Ngừng kinh doanh, trả hàng seller (R-INV-13) | `Adjustment` âm bằng toàn bộ tồn |
| S-INV-07 | Có tồn nhưng không bán trong tháng | Có dòng `inventory_daily_balance`, không có `order_items` trong tháng |
| S-INV-08 | SKU hết hàng vẫn có trong báo cáo tồn cuối ngày (R-INV-14) | `inventory_daily_balance.quantity_on_hand = 0` |

### 16.6 Thay đổi thông tin chủ

| Mã | Tình huống | Dấu hiệu trong dữ liệu |
|---|---|---|
| S-CHG-01 | Seller `Normal` lên `Preferred` | `tier` đổi, `updated_at` = ngày 1 của quý |
| S-CHG-02 | Seller `Preferred` lên `Mall` | Như trên |
| S-CHG-03 | Seller bị hạ hạng | `Preferred` → `Normal` |
| S-CHG-04 | Seller chuyển địa điểm kinh doanh | `province` đổi |
| S-CHG-05 | Seller sửa tên shop hoặc tên sản phẩm nhập sai | `shop_name` / `name` đổi |
| S-CHG-06 | Khách chuyển nơi ở | `province` đổi, có địa chỉ mặc định mới |
| S-CHG-07 | Sản phẩm đổi danh mục | `category_id` đổi |
| S-CHG-08 | Khách đổi số điện thoại | `phone_number` đổi |
| S-CHG-09 | Khách lên hoặc xuống hạng thành viên | `membership_tier` đổi vào ngày 1 hằng tháng |
| S-CHG-10 | Sàn đổi chính sách hoa hồng | Hai dòng tỷ lệ có `effective_from`/`effective_to` nối tiếp |

### 16.7 Marketing và clickstream

| Mã | Tình huống | Dấu hiệu trong dữ liệu |
|---|---|---|
| S-MKT-01 | Chiến dịch chi vượt ngân sách (R-MKT-04) | Σ `cost_amount` > `budget_amount` |
| S-MKT-02 | Chiến dịch không tạo ra đơn | Có chi phí, không có đơn được gán |
| S-MKT-03 | Quảng bá Livestream trước khi ra mắt | Có chi phí `LIVE` trước `{livestream_launch}`, chưa có đơn Livestream |
| S-MKT-04 | Số liệu quảng cáo về trễ (R-MKT-07) | Dòng `ad_spend_logs` được ghi vào OLTP 1–3 ngày sau `log_date` |
| S-MKT-05 | Chiến dịch đa kênh (R-MKT-02) | Một chiến dịch có nhiều `channel_code` |
| S-CLK-01 | Phiên thoát ngay | Phiên có đúng 1 sự kiện |
| S-CLK-02 | Bỏ giỏ hàng | `cart_status = 'Abandoned'` |
| S-CLK-03 | Thêm giỏ hôm trước, mua ở phiên sau | `cart_items.session_id` ≠ `orders.session_id` |
| S-CLK-04 | Xem sản phẩm đang hết hàng | `view_product` không có `add_to_cart` lúc tồn = 0 |
| S-CLK-05 | Khách vãng lai mua hàng | Phiên Web không đăng nhập có `purchase` |

### 16.8 Đối soát người bán

| Mã | Tình huống | Dấu hiệu trong dữ liệu |
|---|---|---|
| S-FIN-01 | Đơn có cả voucher sàn và voucher shop | `gross_sales` gồm phần voucher sàn, không gồm voucher shop |
| S-FIN-02 | Hoàn hàng ở tháng sau tháng bán | Khoản trừ nằm ở kỳ sau |
| S-FIN-03 | Kỳ đối soát âm | `payout_amount < 0` |
| S-FIN-04 | Đặt trước ngày đổi chính sách, giao sau ngày đó | Dùng tỷ lệ cũ theo ngày đặt (R-FIN-03) |

---

## 17. Dữ liệu lỗi của hệ thống nguồn

Hệ thống nguồn thật luôn có một tỷ lệ nhỏ dữ liệu bẩn: nhập tay sai, đồng bộ giữa
các hệ thống bị lệch, file của đối tác sai định dạng. Bộ sinh tái hiện điều đó.
Phát hiện và xử lý các lỗi này là việc của ETL.

- **R-ERR-01** Chỉ tạo lỗi khi `{inject_errors}` bật, và chỉ sau khi dữ liệu sạch đã
  qua toàn bộ kiểm tra ở mục 18.
- **R-ERR-02** Mọi lỗi được ghi vào file `generation_manifest.json` nằm ngoài OLTP
  (bảng, ID bản ghi, cột, mã lỗi, giá trị gốc), để đối chiếu khi kiểm thử.
- **R-ERR-03** Không tạo lỗi trên các bản ghi thuộc tình huống ở mục 16, để mỗi
  tình huống vẫn còn bản ghi sạch.
- **R-ERR-04** DDL của OLTP giữ PK, FK, NOT NULL, UNIQUE, nhưng **không đặt CHECK**
  trên các cột có trong bảng dưới (hệ thống nguồn kiểm tra lỏng).

| Mã | Bảng | Lỗi | Tỷ lệ | Nguyên nhân thường gặp ngoài thực tế |
|---|---|---|---|---|
| E-01 | `inventory_movements` | `sku` không có trong `products` | 0,05% | Nhân viên kho nhập tay sai mã, hoặc dùng mã cũ chưa đồng bộ |
| E-02 | `shipments` | `order_code` không tồn tại | 0,02% | Vận đơn tạo trên hệ thống hãng vận chuyển với mã đơn gõ sai |
| E-03 | `ad_spend_logs` | `channel_code` sai định dạng (`web`, ` MOBILE_APP`, `Live`) | 0,1% | File báo cáo của nền tảng quảng cáo dùng định dạng khác |
| E-04 | `ad_spend_logs` | Dòng trùng: cùng chiến dịch, kênh, ngày và số liệu, khác ID | 0,1% | Cùng một file báo cáo bị nhập hai lần |
| E-05 | `order_items` | `quantity ≤ 0` | 0,01% | Lỗi của hệ thống cũ khi sửa đơn |
| E-06 | `orders` | `completed_at < created_at` | 0,01% | Lệch đồng hồ giữa các máy chủ |
| E-07 | `customers` | Số điện thoại sai định dạng (thiếu số, có ký tự lạ) | 0,1% | Khách tự nhập, form không kiểm tra |
| E-08 | `order_items` | `net_amount ≠ quantity × unit_price − discount_amount` | 0,01% | Sửa giá thủ công sau khi đơn đã tạo |

---

## 18. Bất biến kiểm tra sau khi sinh

Chạy bằng một bộ câu SQL trên OLTP **trước khi chèn lỗi**. Vi phạm bất kỳ bất biến
nào từ V-01 đến V-22 là lỗi của bộ sinh: sửa bộ sinh, không sửa tay dữ liệu.

**Toàn vẹn**

- **V-01** Không trùng PK và các cột duy nhất: `order_code`, `tracking_code`, `sku`,
  `email`, `phone_number`.
- **V-02** Mọi FK trỏ tới bản ghi tồn tại. Mọi `sku`, `order_code`, `channel_code`
  của hệ thống kho và marketing ánh xạ được.
- **V-03** Mọi cột dạng danh mục chỉ chứa giá trị nằm trong schema.

**Tiền**

- **V-04** `net_amount = quantity × unit_price − discount_amount` và
  `discount_amount = Σ applied_discount_amount` của dòng.
- **V-05** Các tổng của `orders` đúng theo R-PRM-19.
- **V-06** Trong mỗi đơn, tổng phần chia của một voucher = số tiền giảm của voucher
  đó, không vượt `max_discount_amount`, và đơn đạt `min_order_value`.
- **V-07** Mỗi đơn có tối đa một payment `Success`; tổng tiền thực thu đúng R-PAY-08.
- **V-08** `refund_amount ≤ net_amount`; `returns.quantity ≤ order_items.quantity`.
- **V-09** `seller_payouts` tính lại từ dòng hàng và hoàn hàng khớp R-FIN-07 đến
  R-FIN-10.
- **V-10** `clicks ≤ impressions`; số phiên `Paid Ads` ≤ `clicks`; số đơn được gán
  chiến dịch ≤ `clicks` của cùng (chiến dịch, kênh, ngày).

**Thời gian**

- **V-11** `sellers.created_at < products.created_at <` thời điểm đơn đầu tiên của sản
  phẩm; `registration_date <` đơn và phiên của khách.
- **V-12** Đặt hàng ≤ thanh toán thành công ≤ tạo vận đơn ≤ lấy hàng < giao =
  `completed_at`; hoàn hàng và đánh giá sau `completed_at`;
  `refunded_at > requested_at`.
- **V-13** Voucher được dùng trong thời gian hiệu lực; đơn được gán chiến dịch nằm
  trong thời gian chạy; `ad_spend_logs.log_date` nằm trong thời gian chạy.
- **V-14** Không có lấy hàng, giao hàng trong khoảng nghỉ Tết.

**Trạng thái**

- **V-15** Mọi sản phẩm trong đơn thuộc `orders.seller_id`; voucher shop thuộc đúng
  seller của đơn; voucher sản phẩm có sản phẩm nằm trong đơn.
- **V-16** Trạng thái đơn, trạng thái dòng, các mốc thời gian và trạng thái vận đơn
  nhất quán theo R-ORD-12, R-ORD-14, R-SHP-04.
- **V-17** Không có đơn sau khi sản phẩm ngừng bán hoặc shop bị khóa; không có đơn
  Livestream trước `{livestream_launch}`.
- **V-18** Khách vãng lai không có voucher và không có đánh giá; địa chỉ giao thuộc
  đúng khách của đơn.
- **V-19** Mỗi khách có đúng một địa chỉ mặc định.

**Tồn kho và lịch sử**

- **V-20** R-INV-16 đúng với mọi cặp và mọi ngày; `inventory_daily_balance` ngày
  cuối trùng `inventory_levels`.
- **V-21** Mỗi dòng hàng đã lấy hàng có đúng một movement `Sale` với
  `−quantity_change = quantity`.
- **V-22** `updated_at` của mỗi bản ghi dữ liệu chủ trùng thời điểm thay đổi gần
  nhất của bản ghi đó (R-SIM-05), và giờ thay đổi đúng R-CHG-07.

**Phân bố (chỉ cảnh báo, không chặn)**

- **V-23** Tổng số dòng hàng nằm trong ±5% `{target_order_lines}`. Các tỷ lệ hủy,
  hoàn, COD, dùng voucher lệch không quá 30% so với mức đặt trong tài liệu. Mỗi
  tình huống ở mục 16 xuất hiện ít nhất 1 lần ở `dev` và ít nhất 20 lần ở `full`
  (trừ tình huống chỉ xảy ra theo lịch như S-MKT-03, S-CHG-10).

---

## 19. Thay đổi schema do bộ luật này yêu cầu

Đã cập nhật vào [OLTP_SCHEMA.md](OLTP_SCHEMA.md) và [OLTP_ERD.md](OLTP_ERD.md).

| Bảng | Thay đổi | Luật liên quan |
|---|---|---|
| `products` | Thêm `created_at`, `updated_at`; `category_id` là danh mục lá | R-PRD-01, R-SIM-05, R-CTG-06 |
| `order_items` | Thêm `list_price`; `item_status` thêm giá trị `Pending` | R-PRC-01, R-ORD-14 |
| `orders` | Thêm `shipping_discount_amount`, `shipping_promotion_id` | R-PRM-19 |
| `promotions` | Thêm `max_discount_amount`, `usage_limit`, `per_customer_limit`, `eligibility`, `product_id`; `promo_type` thêm `Freeship Voucher`; `apply_level` thêm `Shipping` | Mục 6 |
| `customer_addresses` | `customer_id` cho phép NULL (khách vãng lai); `district` cho phép NULL | R-ADR-01, R-ADR-06 |
| `customers` | `province` là tỉnh cư trú trong hồ sơ | R-CHG-04 |
| `payments` | Dòng `Refunded` là dòng mới, số tiền âm | R-PAY-06 |
| `marketing_campaigns` | `campaign_type` thêm `Livestream Show` | R-MKT-01 |
| `seller_payouts` | `gross_sales`, `refund_amount` tính theo khoản ghi có cho seller | R-FIN-07, R-FIN-08 |
| `inventory_daily_balance` | **Bảng mới**: tồn cuối ngày theo kho và SKU | R-INV-14 |
