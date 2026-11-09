# Bước 08 — PLAN 5.4–5.6: Load (dimension + SCD, fact + bridge, đối soát)

> Ngày thực hiện: 08/11/2026 · Batch: **4** (INCREMENTAL, cửa sổ 2025-12-31 → 2026-01-12) · Kết quả: **SUCCESS**
> Mã: [dw/etl/load.py](../../dw/etl/load.py), kiểm thử SCD [dw/tests/test_scd_load.py](../../dw/tests/test_scd_load.py)
> Bằng chứng: [evidence/08_load_check.txt](evidence/08_load_check.txt), [evidence/08_scd_test.txt](evidence/08_scd_test.txt)

## 1. Mục tiêu

Nạp `stg.*` của một batch đã TRANSFORMED vào tầng `dw` (star/galaxy schema đã tạo ở bước 05), gồm:

- **B3:** dimension với SCD1 / SCD2 / SCD3, cây danh mục + closure table, các dimension nhỏ.
- **B4:** 3 fact (`fact_order_item`, `fact_inventory_snapshot`, `fact_ad_spend`) + bridge khuyến mãi + mini-dimension hồ sơ khách.
- **B5:** đối soát RC-01..06 và kiểm tra SCD (T4). Đạt hết thì batch → `SUCCESS` (mốc watermark cho batch kế tiếp).

## 2. Đầu vào

| Nguồn | Nội dung (batch 4) |
|---|---|
| `stg.category` / `product` / `seller` / `customer` | 77 / 3.532 / 481 / 10.361 dòng |
| `stg.channel`, `payment_method`, `warehouse`, `promotion`, `campaign` | 3, 5, 6, 3, 1 |
| `stg.order_item_sales` | 1.195 dòng hàng của đơn Completed (645 dòng khách vãng lai) |
| `stg.order_item_promotion` | 188 dòng hàng có voucher, 1 tổ hợp voucher |
| `stg.inventory_daily` | 219.067 dòng (3.532 SKU × kho × 12 ngày, thưa) |
| `stg.ad_spend_daily` | 8 ngày có chi phí, 1 chiến dịch, kênh WEB |
| DDL đích | [302_dimensions.sql](../../dw/sql/30_dw/302_dimensions.sql), [303_facts.sql](../../dw/sql/30_dw/303_facts.sql) (đã có 2 thành viên đặc biệt −1/0 mỗi dimension, 125 tổ hợp mini-dimension) |

## 3. Phân tích trước khi làm

- **Thứ tự batch:** batch 1–3 được trích từ bộ OLTP *trước khi sinh lại* (xem [00 §9](00_sinh-du-lieu-oltp.md)). Nếu lỡ nạp, kho sẽ trộn hai bộ dữ liệu. Vì vậy Load chỉ nhận batch có `watermark_from` = `watermark_to` của batch SUCCESS gần nhất (lần đầu = `INITIAL_WATERMARK` 2025-12-31). Batch 1–3 có cùng mốc đầu nhưng mặc định chọn batch TRANSFORMED **mới nhất** nối tiếp mốc, tức batch 4. Sau khi batch 4 SUCCESS, mốc thành 2026-01-12 nên batch 1–3 không bao giờ còn được nhận.
- **Dữ liệu thật chưa có thay đổi SCD:** kịch bản đổi tỉnh / hạng / trạng thái chỉ chạy từ ngày mô phỏng 30/01 ([01](01_buoc-1.0_cau-hinh-mock-scd.md)). Logic SCD vẫn phải cài đủ và được chứng minh bằng **ca có kiểm soát** (PLAN 4.2) → viết `test_scd_load.py` chạy trong transaction rồi rollback.
- **Phiên bản đầu `valid_from = 1900-01-01`:** để mọi giao dịch trước lần thay đổi đầu tiên đều tra được phiên bản (nguồn không lưu lịch sử trước khi kho bắt đầu).
- **Snapshot FULL có dòng của ngày đang sinh:** customers trích lúc Mock đang chạy ngày 13/01 có `effective_date` = 2026-01-13 > watermark. Không ảnh hưởng: phiên bản đầu vẫn là 1900-01-01; thay đổi SCD2 thật sẽ lấy đúng ngày `updated_at`.
- **Partition không cho `RETURNING xmax`** (lỗi gặp khi chạy, §7) → đếm số khóa đã tồn tại trước khi upsert để tách *mới* / *cập nhật*.

## 4. Cách thực hiện

Lệnh (trong WSL, từ thư mục repo):

```bash
bash dw/etl/run.sh load                # nạp batch TRANSFORMED nối tiếp mốc SUCCESS
bash dw/etl/run.sh load --batch 4      # chỉ định batch (cho phép batch FAILED ở bước Load)
bash dw/etl/run.sh load --reload       # nạp lại batch SUCCESS mới nhất — kiểm thử idempotent T3
.venv/bin/python -m dw.tests.test_scd_load   # kiểm thử SCD có kiểm soát (rollback)
```

Toàn bộ B3 → B4 → B5 chạy trong **một transaction**. Nếu một kiểm tra không đạt: rollback, kết quả đối soát vẫn được ghi (transaction riêng), batch → `FAILED` (riêng `--reload` thất bại thì giữ nguyên SUCCESS).

### 4.1. B3 — Dimension

| Dimension | Cách nạp | Khóa thay thế |
|---|---|---|
| `dim_category` + `bridge_category_hierarchy` | Upsert SCD1 theo `category_id`; sau đó gán cha/gốc (FK tự tham chiếu); dựng lại closure bằng CTE đệ quy (gồm cặp tự thân depth 0, có cả −1/0) | `category_key = category_id` |
| `dim_channel`, `dim_payment_method`, `dim_warehouse`, `dim_promotion`, `dim_campaign` | SCD1: `INSERT … ON CONFLICT DO UPDATE … WHERE (cột) IS DISTINCT FROM (mới)` (không ghi khi không đổi) | = id nguồn |
| `dim_product`, `dim_seller`, `dim_customer` | Snapshot-diff SCD1 + SCD2 (bảng dưới) | `serial` |
| `dim_seller_tier_t3` | SCD3: `previous_tier ← current_tier`, `current_tier ← tier`, `tier_changed_on` | `seller_id` |

Cột SCD theo dimension (so bằng `scd1_hash` / `scd2_hash` tính ở Transform):

| Dimension | SCD1 (ghi đè mọi phiên bản) | SCD2 (phiên bản mới) |
|---|---|---|
| `dim_product` | sku, product_name, brand_name, seller_id, original_price, discount_rate | list_price, category_key, is_active, unit_cost_est |
| `dim_seller` | shop_name, seller_name, email_domain, phone_masked | province, region, tier, status |
| `dim_customer` | full_name, phone_masked, email_domain, gender, birth_year, age_band, registration_date | province, region |

Thuật toán `load_scd` (cho mỗi dimension SCD2):

1. Khóa mới → chèn phiên bản đầu `valid_from = 1900-01-01`, `valid_to = 9999-12-31`, `is_current`.
2. `scd1_hash` khác → `UPDATE` mọi phiên bản của khóa (sửa lỗi nhập lan toàn lịch sử, không thêm phiên bản).
3. `scd2_hash` khác so với phiên bản current → bảng tạm `tmp_chg`, phân loại theo `effective_date` (= ngày `updated_at` nguồn):
   - `<` `valid_from` của current → **đến muộn**: ghi `audit.quarantine` mã **DQ-23** (ERROR), không sửa hồi tố;
   - `=` → cùng ngày hiệu lực: sửa tại chỗ phiên bản current;
   - `>` → đóng current (`valid_to = effective_date`, `is_current = false`), mở phiên bản mới `valid_from = effective_date`.
4. Bảo đảm số phiên bản đóng = số phiên bản mở; `ANALYZE` dimension.

### 4.2. B4 — Fact và bridge

**`fact_order_item`** (grain: dòng hàng của đơn Completed):

1. Nhóm voucher: mỗi `order_item_id` → `group_signature` (`promotion_id:weight,…`). Chữ ký mới → `dim_promotion_group` (khóa = max + row_number); dòng bridge `(group, promotion_key, weighting_factor)`; chữ ký đã có thì **tái dùng**.
2. Tra khóa theo **ngày hoàn tất** (SCD2: `valid_from ≤ ngày < valid_to`) cho product (lấy luôn `category_key`, `unit_cost_est` của đúng phiên bản), seller, customer.
3. Quy ước khóa đặc biệt: `customer_id` NULL → −1 (khách vãng lai); không có chiến dịch → −1; không voucher → −1; tra không được → 0.
4. Measure: lấy nguyên từ stg; thêm `seller_net_amount = net − commission`, `cost_amount_est = quantity × unit_cost_est`, `gross_margin_est = net − cost_est` (📝 ước tính, PLAN 4.5).
5. Upsert theo `(date_key, source_system, order_id, line_number)` → chạy lại không nhân đôi; bản cập nhật ghi `updated_batch_id` (dòng chuyển *Returned* ở batch sau được cập nhật cờ).
6. **Mini-dimension** `customer_profile_key`: với mỗi dòng của khách có tài khoản, tính lịch sử **trước ngày giao dịch** trong 365 ngày (Σ net_revenue, số đơn distinct, gộp theo `customer_id` qua mọi phiên bản) → bucket chi tiêu (`Chưa mua`, `< 1 triệu`, `1–5`, `5–20`, `> 20 triệu`) × tần suất (`0`, `1`, `2–3`, `4–9`, `≥ 10 đơn`) × hạng thành viên (snapshot của batch) → tra 125 tổ hợp dựng sẵn. Khách vãng lai → −1.

**`fact_inventory_snapshot`**: từ `stg.inventory_daily`, tra product theo `balance_date`, `inventory_value_est = on_hand × unit_cost_est` (📝); upsert theo `(date_key, product_key, warehouse_key)`.

**`fact_ad_spend`**: dòng ngày hợp lệ của batch này + các batch SUCCESS (khử trùng theo `ad_spend_log_id`, giữ batch mới nhất); với các tháng batch chạm tới thì **xóa và tính lại trọn tháng** (tháng chưa kết thúc được cập nhật ở batch sau).

### 4.3. B5 — Đối soát (ghi `audit.reconciliation`)

| Mã | Kiểm tra |
|---|---|
| RC-01 | Σ `net_revenue` stg = Σ fact (cùng các dòng của batch) — bằng tuyệt đối |
| RC-02 | Số dòng stg = số dòng fact tương ứng |
| RC-03a / b | Mọi nhóm voucher có Σ weight = 1 (±1e-6); Σ `applied_discount` nguồn = Σ `discount_amount × weight` qua bridge (±0,01) |
| RC-04 | Mỗi (sku, kho, ngày) của stg khớp fact về on_hand, reserved, sold, imported |
| RC-05 | Σ chi phí QC ngày (các tháng của batch) = Σ `fact_ad_spend` |
| RC-06 / RC-06i | Không có khóa ngoại mồ côi; (thông tin) số dòng dùng khóa 0 |
| SCD-01 / SCD-02 | Mỗi dimension SCD2: không có hai phiên bản chồng lấn khoảng hiệu lực; mỗi khóa nghiệp vụ đúng 1 current |

RC-07 (đọc = ghi + cách ly) đã ghi ở Transform.

## 5. Quá trình thực hiện (diễn biến thật)

| Giờ | Việc | Kết quả |
|---|---|---|
| 10:53:09 | `load` lần 1 | Dimension xong; **lỗi** `cannot retrieve a system column in this context` khi upsert fact (partition) → rollback, batch 4 FAILED |
| 10:53:25 | Sửa `upsert` (đếm khóa có sẵn), `load --batch 4` | **SUCCESS**, 73,6 s (fact tồn kho 70 s cho 219.067 dòng) |
| 10:54:50 | `load --reload` (T3) | SUCCESS, 31,7 s: 0 dòng mới, 0 phiên bản mới, fact chỉ cập nhật |
| ~10:56 | `test_scd_load` | **10/10 PASS**, rollback |
| 10:57:37 | Sửa phần ghép `message` của batch, `--reload` lần nữa | SUCCESS 37,1 s; khôi phục message thời gian cho batch 4 |

Thống kê lần nạp thật (batch 4):

| Bảng | Đọc | Ghi |
|---|---:|---:|
| `dim_category` / closure | 77 | 77 nút (+ cha/gốc), 219 cặp tổ tiên–hậu duệ |
| `dim_product` / `dim_seller` / `dim_customer` | 3.532 / 481 / 10.361 | 3.532 / 481 / 10.361 khóa mới (phiên bản 1900-01-01) |
| `dim_seller_tier_t3` | 481 | 481 |
| Dimension nhỏ | 3 + 5 + 6 + 3 + 1 | toàn bộ |
| `dim_promotion_group` / bridge | 188 dòng có voucher | 1 nhóm mới / 1 dòng bridge |
| `fact_order_item` | 1.195 | 1.195 mới; 550 dòng có hồ sơ khách (còn lại −1) |
| `fact_inventory_snapshot` | 219.067 | 219.067 mới (partition `_202601`) |
| `fact_ad_spend` | 8 dòng ngày | 1 dòng tháng 202601 |

## 6. Kiểm tra kết quả

**Đối soát batch 4 — đạt 15/15** (trích [evidence/08_load_check.txt](evidence/08_load_check.txt)):

| Mã | Nguồn | Đích |
|---|---:|---:|
| RC-01 | 858.670.245,00 | 858.670.245,00 |
| RC-02 | 1.195 | 1.195 |
| RC-03a / RC-03b | 0 / 3.040.000,00 | 0 / 3.040.000,00 |
| RC-04 | 219.067 | 219.067 |
| RC-05 | 2.932.996,00 | 2.932.996,00 |
| RC-06 / RC-06i | 0 | 0 / 0 dòng khóa 0 |
| RC-07 (Transform) | 234.927 | 234.927 |
| SCD-01, SCD-02 × 3 dimension | 0 | 0 |

**Kiểm tra bổ sung:**

- *Không cộng lặp qua cây danh mục:* Σ doanh thu qua các nút gốc (closure) = 858.670.245 = Σ fact.
- *Khóa đặc biệt:* 0 dòng khóa 0 ở product/seller/customer/payment; 932 dòng không có chiến dịch (−1), 1.015 dòng không voucher (−1).
- *Partition:* 100% dòng nằm ở `fact_order_item_202601`, `fact_inventory_snapshot_202601`.
- *Mini-dimension:* đa số "Chưa mua · 0 đơn" (lịch sử mới 12 ngày) — hợp lý; khách mua lần 2 đã sang "< 1 triệu · 1 đơn" / "2–3 đơn".
- **T3 — idempotent:** `--reload` không thêm dòng/phiên bản nào; đối soát vẫn 15/15.
- **T4 — SCD có kiểm soát** ([evidence/08_scd_test.txt](evidence/08_scd_test.txt)), 10/10 PASS:

| Ca | Kết quả |
|---|---|
| Khách A đổi tỉnh ngày 01/02 | 2 phiên bản, bản cũ `valid_to` = 2026-02-01, 1 current |
| Khách B đổi tên | SCD1: vẫn 1 phiên bản, tên mới |
| Seller S Normal → Mall | SCD2 2 phiên bản + SCD3 (current Mall, previous Normal, 2026-02-01) |
| Sản phẩm P giá +10% + đổi tên | 2 phiên bản giá; tên mới ghi đè **cả hai** phiên bản |
| Tra theo thời điểm | 15/01 → key 3533 (135.000 đ); 05/02 → key 7065 (148.500 đ) |
| Seller S đổi hạng lần 2 cùng ngày | Sửa tại chỗ, vẫn 2 phiên bản |
| Khách A đổi tỉnh với ngày 20/01 (< 01/02) | Cách ly DQ-23, không sửa hồi tố |
| SCD-01/02 sau kịch bản | 0 chồng lấn, đúng 1 current |

## 7. Vấn đề & cách xử lý

| Vấn đề | Nguyên nhân | Xử lý |
|---|---|---|
| `cannot retrieve a system column in this context` | Bảng partition không hỗ trợ `RETURNING xmax` để phân biệt insert/update | Đếm số khóa đã tồn tại trong bảng tạm trước khi upsert: mới = rowcount − đã có |
| Lần nạp đầu FAILED để lại `message` lỗi | Ghép message bằng cách cắt chuỗi `; load` | Ghép lại từ phần `extract … s`, `transform … s` bằng regex; đã khôi phục message batch 4 |
| Nạp fact tồn kho chậm (70 s / 219 nghìn dòng) | 4 FK + kiểm tra CHECK trên từng dòng, partition | Chấp nhận cho batch đầu; lần nạp lại 28 s. Là dữ liệu đầu vào cho thí nghiệm BM02/BM03 (bước 10) |
| Batch 1–3 cũ có thể bị nạp nhầm | Cùng `watermark_from` với batch 4 | Quy tắc nối tiếp mốc SUCCESS + mặc định chọn batch mới nhất; sau batch 4 các batch cũ không còn hợp lệ |
| Sequence bị "tiêu" khi chạy test rollback | Sequence PostgreSQL không rollback | Chỉ tạo khoảng trống trong surrogate key (vô hại, đúng bản chất khóa thay thế) |

## 8. Ảnh hưởng & bước tiếp theo

- Kho đã có dữ liệu thật đầu tiên (SUCCESS): mốc watermark = **2026-01-12**. Batch kế tiếp: `extract` → `transform` → `load` sẽ lấy (2026-01-12, last_day].
- Khi Mock sinh qua 30/01 (kịch bản SCD), các batch sau sẽ có thay đổi SCD2/SCD3 **thật**. Cần chạy lại `test_scd_load` và kiểm tra `dim_*` có phiên bản mới.
- **Tiếp theo:** bước 09 — `mart` (MV dùng chung, drill-across 6.2) và dashboard. Sau đó bước 10 thí nghiệm BM01–03 (hạn 10/11), bước 11 kiểm thử T1–T7.

## 9. Kiểm thử measure độc lập với ETL (PLAN 4.8.7) — 08/11/2026

**Mục đích:** RC-01..06 chỉ so kho với `stg`; lỗi nằm ở Extract/Transform sẽ không bị phát hiện. Bước này **tính lại measure trực tiếp từ OLTP gốc** (`mock_oltp`) và so với fact (đọc ngược qua dimension về mã nguồn).

**Lệnh:** `bash dw/tests/run_measure_tests.sh` ([measure_src.sql](../../dw/tests/measure_src.sql), [measure_dw.sql](../../dw/tests/measure_dw.sql), [measure_rules.sql](../../dw/tests/measure_rules.sql)). Bằng chứng: [evidence/08_measure_test.txt](evidence/08_measure_test.txt).

**A. OLTP gốc vs kho: 20/20 dòng khớp, 0 khác biệt.** Gồm:
- md5 từng dòng của 1.195 dòng hàng × 20 cột (khóa, ngày, mã sản phẩm/seller/khách/kênh/chiến dịch, 10 measure, cờ trả hàng);
- tổng các measure và doanh thu thuần theo từng ngày;
- giảm giá theo voucher;
- md5 của 219.067 dòng tồn kho × 6 measure; 0 biến động kho bị rơi khỏi snapshot;
- chi phí, impressions, clicks, số ngày chạy quảng cáo theo tháng.

**B. Quy tắc trên kho: mọi kiểm tra vi phạm = 0.**

| Nhóm | Kết quả |
|---|---|
| Công thức Fact_Order_Item (gross, list_amount, list_discount, net, commission, seller_net, margin, miền giá trị) | 0 / 1.195 dòng vi phạm |
| `cost_amount_est` dùng đúng phiên bản sản phẩm tại ngày hoàn tất; `unit_cost_est = round_1000(giá × cost_ratio)` | 0 vi phạm |
| Bridge: Σ phân bổ = Σ discount dòng có voucher (3.040.000); dòng không voucher có discount 0; Σ weight = 1 | Đạt |
| Tồn kho: available, stockout, dòng chảy không âm, `inventory_value_est`; tính liên tục tồn(d) = tồn(d−1) + nhập − bán + trả + điều chỉnh | 0 vi phạm; liên tục 200.810 / 200.810 |
| Semi-additive | Tồn cuối kỳ (12/01) = 5.669.671; SUM qua ngày = 68.038.406 (sai — minh họa vì sao không cộng theo thời gian) |
| Non-additive | AOV tính lại từ tổng ngày = AOV atomic = 828.033,02; trung bình AOV các ngày = 784.419,96 (sai). Hoa hồng hiệu dụng 5,8622% ≠ AVG(rate) 5,6946% |
| Quảng cáo | impressions ≥ clicks; CTR 1,13%, CPC 915 đ, CPM 10.311 đ |
| Hai mốc thời gian bán | Xuất kho 1.589 món ≠ hoàn tất 1.400 món (đúng kỳ vọng: lệch thời gian và đơn chưa hoàn tất) |

**Giới hạn còn lại:**
- `cost_amount_est`, `gross_margin_est`, `inventory_value_est` đúng **theo giả định giá vốn G1**, không phải giá vốn thật (nguồn không có).
- `commission_amount = round(net × rate, 2)` là định nghĩa của kho; nguồn không lưu hoa hồng theo dòng. `seller_payout_items` tính trên `seller_gross` (gồm trợ giá sàn) nên phải đối chiếu riêng ở fact mở rộng.
- Chưa có dòng *Returned* và chưa có thay đổi SCD trong cửa sổ, nên cập nhật `is_returned` (late-arriving) và tra phiên bản SCD2 chỉ mới kiểm bằng ca có kiểm soát. Cần chạy lại kiểm thử này sau mỗi batch mới, nhất là sau 30/01.
