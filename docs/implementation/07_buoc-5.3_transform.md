# 07 — PLAN 5.3: Transform (B2) — `raw` → `stg`, kiểm tra chất lượng, cách ly lỗi

| | |
|---|---|
| Ngày thực hiện | 07/11/2026, 22:50–23:10 |
| Trạng thái | ✅ Xong. Batch 1 (dữ liệu thật) và batch 3 (kiểm thử lỗi) ở trạng thái `TRANSFORMED` |
| Liên quan PLAN | Mục 5.3.1–5.3.7; quy tắc IR-01..10 (M1); RC-07 |
| Liên quan đề xuất | Mục 5 "Tích hợp và kiểm soát chất lượng": bản ghi sai kiểu, thiếu khóa, không ánh xạ được hoặc vi phạm quy tắc → bảng cách ly kèm lý do, không loại bỏ âm thầm; M5 (Chất lượng dữ liệu); T2, T3 |
| Liên quan lộ trình | Milestone 4.1 (Cleanse + Transform) |

## 1. Mục tiêu

Biến dữ liệu nguyên trạng của một batch (`raw`) thành dữ liệu **đã chuẩn hóa, đã tích hợp mã, đã kiểm tra** (`stg`), sẵn sàng nạp vào kho:
- áp đủ các quy tắc tích hợp IR-01..10;
- chạy các quy tắc chất lượng DQ;
- dòng lỗi được **cách ly kèm lý do**;
- kiểm đếm "đọc = ghi + cách ly + trùng";
- chứng minh cơ chế cách ly bằng một batch có lỗi cài sẵn, vì OLTP quá sạch (G4).

## 2. Đầu vào

- Batch 1 (`EXTRACTED`, 01/01–13/01/2026): 253.303 dòng `raw` cần xử lý.
- Thiết kế PLAN 5.3, các bảng `stg` theo PLAN 5.3.3.
- R-PRD-05 (bảng tỷ lệ giá vốn 5.6) và mô hình 34 tỉnh (R-ADR-01) trong [DATA_GENERATION_RULES.md](../data-model/oltp/DATA_GENERATION_RULES.md).

## 3. Phân tích trước khi làm

Truy vấn giá trị thực trong `raw` cho ra 3 phát hiện mới so với PLAN:

| Phát hiện | Xử lý |
|---|---|
| `inventory_movements` có thêm loại **`Return`** (hàng trả nhập lại kho) | Thêm measure `qty_returned` vào `stg` và `dw.fact_inventory_snapshot` (ALTER, cập nhật từ điển); thêm DQ-22 (WARN) cho loại lạ |
| R-PRD-05 cho tỷ lệ giá vốn theo **khoảng** | Dùng **trung điểm** khoảng, ghi rõ là giả định trong `map_cost_ratio.csv` |
| Mô hình địa giới mặc định là **34 tỉnh** | `map_province.csv` đủ 34 tỉnh, 57 cách viết, kèm vùng Bắc/Trung/Nam |

Thiết kế bộ máy: **một bộ máy dùng chung** cho mọi thực thể, gồm câu SELECT chuẩn hóa → bảng tạm → các quy tắc (biểu thức boolean) → cách ly → khử trùng → ghi `stg` → kiểm đếm. Mỗi thực thể chỉ khai báo câu SELECT và danh sách quy tắc. Nhờ vậy thêm quy tắc mới chỉ cần thêm một dòng, và mọi thực thể được kiểm đếm theo cùng một cách.

## 4. Cách thực hiện

### 4.1. File

| File | Nội dung |
|---|---|
| [dw/etl/mappings/](../../dw/etl/mappings/) | `map_channel.csv` (8 dòng, nhận cả mã engine `WEB/APP/LIVESTREAM` lẫn mã tài liệu `MOBILE_APP/LIVE`), `map_province.csv` (34 tỉnh / 57 biến thể), `map_gender.csv`, `map_cost_ratio.csv` (27 danh mục gốc + mặc định G0) |
| [dw/sql/20_stg/201_stg.sql](../../dw/sql/20_stg/201_stg.sql) | 4 bảng `stg.map_*` + 13 bảng `stg` (đều có `batch_id`, `dq_status`) |
| [dw/etl/transform.py](../../dw/etl/transform.py) | Bộ máy T1–T10 + đặc tả 13 thực thể + kiểm tra mức bảng DQ-13/14/18 |
| [dw/etl/inject_test_errors.py](../../dw/etl/inject_test_errors.py) | Tạo batch `TEST_ERRORS` từ batch nguồn, cài 7 ca lỗi E1–E7 (chỉ INSERT vào `raw`, không đụng OLTP) |
| `303_facts.sql`, `502_dictionary_metadata.sql` | Thêm `qty_returned` |

### 4.2. Bộ máy cho mỗi thực thể (`run_entity`)

1. `CREATE TEMP TABLE tmp_<x> AS SELECT …, row_number() OVER (PARTITION BY <khóa> ORDER BY <mới nhất>)`, sau đó `ANALYZE`.
2. Với từng quy tắc: đếm số dòng vi phạm, ghi `audit.dq_result`. Nếu có vi phạm, ghi `audit.quarantine` (mã quy tắc, mức, lý do, `payload` JSON của cả dòng).
3. Dòng có lỗi ERROR bị loại. Dòng trùng khóa (không lỗi, `rn > 1`) bị loại và ghi cảnh báo DQ-07.
4. Ghi `stg.<x>` các dòng còn lại; `dq_status = WARN` nếu dính quy tắc WARN, ngược lại `VALID`. Sau đó `ANALYZE stg.<x>`.
5. Kiểm đếm `đọc = ghi + cách ly + trùng`, ghi `audit.batch_table_log` (stage `TRANSFORM`). Lệch thì dừng batch.
6. Nếu **tỷ lệ cách ly > 5%** (tham số `--max-quarantine-ratio`) thì dừng batch: nguồn có vấn đề hệ thống, không nạp tiếp.

Cả lượt chạy nằm trong **một transaction**: lỗi thì rollback, `stg` của batch giữ nguyên bản trước đó và batch chuyển `FAILED`. Chạy lại cùng batch sẽ xóa kết quả TRANSFORM cũ của batch đó rồi làm lại.

### 4.3. Thực thể và quy tắc

| Thực thể (`stg`) | Chuẩn hóa chính | Quy tắc |
|---|---|---|
| `category` | Path Tiki bỏ `1/2`, cắt tại danh mục OLTP (IR-04); tên ưu tiên `categories` → tên crawler (chỉ khi nút cuối của path chính là danh mục OLTP) → `Danh mục <id>`; sau đó điền gốc, đường dẫn, `is_leaf` bằng CTE đệ quy | DQ-01, DQ-13 (nhiều cha), DQ-12 WARN (chưa tên), DQ-14 (chu trình, mức bảng) |
| `product` | Gộp khoảng trắng; `discount_rate / 100` (IR-10); giá vốn = `round_1000(price × tỷ lệ)` theo gốc; hash SCD1/SCD2; `effective_date` | DQ-01, DQ-09, DQ-04 (danh mục ngoài cây), DQ-10 WARN, DQ-21 WARN |
| `seller` | Tỉnh → mã + vùng (IR-08); SĐT che; tên miền email | DQ-01, DQ-04, DQ-08 WARN |
| `customer` | Giới tính M/F/U (IR-09); năm sinh, nhóm tuổi (tính tại 01/01/2026); tỉnh | DQ-01, DQ-04 (tỉnh, hạng), DQ-08 WARN |
| `channel`, `payment_method`, `warehouse`, `promotion`, `campaign` | Mã marketing (IR-03); nhóm thanh toán; tỉnh kho; bên tài trợ voucher | DQ-01, DQ-04 |
| `order_item_promotion` | `weighting_factor = applied / Σ applied` theo dòng hàng; chữ ký nhóm | DQ-01, DQ-16 |
| `order_item_sales` | Lọc đơn `Completed` và dòng `Fulfilled/Returned`; **hoãn** dòng hoàn tất trong ngày chưa chốt; gộp 1 payment/đơn (ưu tiên `Success`); tính các measure 4.8.1 | DQ-05, DQ-01, DQ-02, DQ-03, DQ-04, DQ-16, DQ-11 WARN, DQ-15 WARN |
| `inventory_daily` | SKU → sản phẩm (IR-01); gộp biến động theo loại (Import, Sale đảo dấu, Return, Adjustment) | DQ-01, DQ-04, DQ-17, DQ-22 WARN, DQ-18 WARN (mức bảng) |
| `ad_spend_daily` | Mã kênh → kênh (IR-03); `month_key` | DQ-01, DQ-04, DQ-19, DQ-20 WARN |

```bash
bash dw/etl/run.sh transform                    # batch EXTRACTED mới nhất
bash dw/etl/run.sh transform --batch 1          # chỉ định batch (chạy lại an toàn)
bash dw/etl/run.sh inject_test_errors --source-batch 1
bash dw/etl/run.sh transform --batch 3 --max-quarantine-ratio 1.0
```

## 5. Quá trình thực hiện (diễn biến thật)

| Giờ | Diễn biến | Xử lý |
|---|---|---|
| 22:52 | Lần 1: 10/13 thực thể xong, lỗi ở `order_item_sales`: `syntax error at end of input`. Dòng chú thích `-- …` cuối câu SELECT đã nuốt dấu `)` mà bộ máy bọc thêm. Batch 1 → `FAILED`, rollback | Xuống dòng trước `)`; cho phép chạy lại batch `FAILED` khi chỉ định `--batch` |
| 22:53 | Lần 2: **batch 1 xong trong 5,8 s**, 253.303 đọc = 253.303 ghi, 0 cách ly, 28 WARN danh mục chưa tên, 9 WARN DQ-15 | Điều tra 9 WARN DQ-15 (mục 7) |
| 22:54 | Tạo batch 3 (`TEST_ERRORS`): E1 5, E2 3, E3 4, E4 3, E5 2, E6 5, E7 3 dòng | — |
| 22:54–23:04 | Transform batch 3 **treo gần 10 phút** ở bảng tạm tồn kho. `pg_stat_activity` cho thấy truy vấn đang chạy; thống kê `raw` cũ (autoanalyze chạy lúc 22:55:24, sau khi truy vấn đã lên kế hoạch) | Hủy (`pg_cancel_backend`). Thêm `ANALYZE` cuối Extract, cuối script tạo lỗi, sau mỗi bảng tạm và sau mỗi lần ghi `stg` |
| 23:05 | Lượt chạy bằng code cũ lại chậm ở DQ-18 (self-join `stg.inventory_daily` chưa có thống kê) | Hủy, chạy lại bằng code mới: **batch 3 xong trong 8,9 s** |
| 23:06 | Chạy batch 3 với ngưỡng mặc định 5%: **bị chặn**: `Tỷ lệ cách ly ad_spend_daily = 50.0% vượt ngưỡng 5%`. `stg` giữ nguyên 1.285 dòng của lượt trước | Đúng thiết kế. Chạy lại với ngưỡng 100% để xem chi tiết |
| 23:07 | Chạy lại batch 1 để kiểm chứng idempotent và xóa thông báo lỗi cũ trong `batch_log` | md5 `stg` trước = sau |

## 6. Kiểm tra kết quả

Output đầy đủ: [evidence/07_transform_check.txt](evidence/07_transform_check.txt).

**Batch 1, dữ liệu thật:**

| Thực thể | Đọc | VALID | WARN | Cách ly | Trùng | Ghi | Cân bằng |
|---|---:|---:|---:|---:|---:|---:|---|
| category | 77 | 49 | 28 | 0 | 0 | 77 | ✅ |
| product | 3.532 | 3.532 | 0 | 0 | 0 | 3.532 | ✅ |
| seller / customer | 481 / 10.380 | 481 / 10.380 | 0 | 0 | 0 | 481 / 10.380 | ✅ |
| channel / payment_method / warehouse / promotion / campaign | 3/5/6/3/1 | = | 0 | 0 | 0 | = | ✅ |
| order_item_promotion | 188 | 188 | 0 | 0 | 0 | 188 | ✅ |
| order_item_sales | 1.295 | 1.286 | 9 | 0 | 0 | 1.295 | ✅ |
| inventory_daily | 237.324 | 237.324 | 0 | 0 | 0 | 237.324 | ✅ |
| ad_spend_daily | 8 | 8 | 0 | 0 | 0 | 8 | ✅ |
| **RC-07 toàn batch** | **253.303** | | | | | **253.303** | ✅ |

Kiểm tra mức bảng: DQ-14 0 chu trình; DQ-18 **219.067 cặp ngày liên tiếp, 0 lệch** giữa tồn kho và sổ cái.

**Batch 3, kiểm thử cách ly:**

| Ca | Lỗi cài | Quy tắc bắt được | Kết quả |
|---|---|---|---|
| E1 | 5 dòng `quantity = -1` | DQ-02 (5 dòng; cùng lúc DQ-03 vì gross âm) | ✅ cách ly |
| E2 | 3 dòng `net_amount + 1.000đ` | DQ-03: khóa (7,1) (8,1) (11,1) | ✅ cách ly |
| E3 | 4 chi phí QC kênh `TIKTOK` | DQ-04: id 1–4 | ✅ cách ly (50% → chặn batch nếu ngưỡng 5%) |
| E4 | 3 tồn kho SKU không tồn tại | DQ-04: `SKU-KHONG-TON-TAI-1..3` | ✅ cách ly |
| E5 | 2 đơn `Completed` thiếu `completed_at` | DQ-05: (2,1) (9,1) | ✅ cách ly |
| E6 | 5 khách trùng khóa | DQ-07: 1–5, **giữ bản `updated_at` mới nhất** (5/5) | ✅ khử trùng |
| E7 | 3 email sai định dạng | DQ-08 WARN: 6, 7, 8 | ✅ vẫn nạp, `dq_status = WARN` |

Đối soát tiền: batch 3 có 1.285 dòng hợp lệ so với 1.295 của batch 1. Doanh thu thuần bị loại = **3.772.100đ** = 922.400.105 − 918.628.005, tức **chỉ đúng các dòng lỗi bị loại**, không mất dòng hợp lệ nào. RC-07 của batch 3: 253.311 = 253.311.

**Idempotent:** chạy lại batch 1 cho md5 `stg.order_item_sales` (`ab0e1164…`) và `stg.inventory_daily` (`7317a9b9…`) trùng trước/sau; số dòng cách ly không bị nhân đôi (37).

**Mẫu chuẩn hóa:**
- Cây `Làm Đẹp - Sức Khỏe > Danh mục 1582 > Sữa rửa mặt`. Cây có 4 cấp: 5 / 22 / 32 / 18 nút; 44 lá; 28 nút chưa tên.
- Sản phẩm 484392: `discount_rate` 44 → 0,4400; giá vốn 25.000đ (gốc Bách hóa, tỷ lệ 0,815).
- Seller: `095****524`, `example.com`, `can-tho`, vùng Nam.
- Khách: giới tính F 4.638 / M 4.198 / U 1.544; vùng Nam 5.192 / Bắc 3.101 / Trung 2.087.
- Tồn kho 13 ngày: nhập 5.671.400, bán 1.699, trả 6, điều chỉnh −21.

## 7. Vấn đề & cách xử lý

| Vấn đề | Xử lý |
|---|---|
| **9 dòng DQ-15** (7 đơn COD) hoàn tất ngày 13/01 nhưng chưa có payment lúc trích. Kiểm tra lại nguồn sau đó: cả 7 đơn đều đã có payment, tạo trong ngày 14/01 khi thu tiền COD. Đây là **dữ liệu đến muộn thật** | Batch này gán khóa thanh toán `0` + WARN (đúng thiết kế). Đã sửa **Extract**: đơn có `payments.transaction_time` trong cửa sổ cũng được trích lại, vì thêm payment không cập nhật `orders.updated_at`. Nếu không sửa, khóa `0` sẽ nằm mãi trong fact. Batch sau sẽ cập nhật khóa đúng |
| Truy vấn chậm do thiếu thống kê sau khi nạp lớn | `ANALYZE` chủ động (bài học về hiệu năng, dùng lại ở BM02/BM03) |
| DQ-06 (dữ liệu ngoài cửa sổ) trong PLAN là "cách ly" | Đổi thành **hoãn**: dòng hoàn tất trong ngày chưa chốt không được đọc ở batch này và sẽ được trích ở batch sau. Cách ly sẽ biến dữ liệu hợp lệ thành "lỗi" |
| Lượt chạy hỏng đầu tiên làm mất phần thông báo "extract 20.2 s" của batch 1 | Không ảnh hưởng dữ liệu; thời gian Extract vẫn còn ở log và `batch_table_log` |
| Batch 2 (`RERUN`) vẫn ở `EXTRACTED` | Giữ làm bằng chứng nạp lại ở bước 06; không transform (cùng dữ liệu với batch 1) |

## 8. Ảnh hưởng & bước tiếp theo

- Mới:
  - `dw/etl/transform.py`, `dw/etl/inject_test_errors.py`, `dw/etl/mappings/*.csv`;
  - `dw/sql/20_stg/201_stg.sql` (đã thêm vào `run_ddl.sh`);
  - `evidence/07_transform_check.txt`.
- Sửa:
  - `dw/etl/extract.py` (đơn có payment đến muộn; `ANALYZE`);
  - `303_facts.sql` và `502_dictionary_metadata.sql` (`qty_returned`);
  - `run_ddl.sh` (bỏ NOTICE);
  - PLAN (DQ-21/22, DQ-06, trạng thái 5.3).
- Database `dwh`: 13 bảng `stg` có dữ liệu batch 1 và 3; `audit.quarantine` 37 dòng (batch 1) và 59 dòng (batch 3); `audit.dq_result`, `batch_table_log`, `reconciliation` đầy đủ.
- Bước tiếp theo: **08 — PLAN 5.4–5.6 Load**:
  - nạp dimension (SCD1/2/3, mini-dimension, cây danh mục + closure);
  - nạp fact và bridge (tra khóa theo thời điểm, −1/0, upsert theo khóa nghiệp vụ);
  - đối soát RC-01..07;
  - batch 1 → `SUCCESS`.
