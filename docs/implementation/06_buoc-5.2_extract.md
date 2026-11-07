# 06 — PLAN 5.2: Extract (B1) — OLTP + crawler → `raw`

| | |
|---|---|
| Ngày thực hiện | 07/11/2026, 22:35–22:50 |
| Trạng thái | ✅ Xong. Batch 1 (INCREMENTAL) và batch 2 (RERUN) ở trạng thái `EXTRACTED`, chờ Transform |
| Liên quan PLAN | Mục 5.1 (B0, B1), 5.2; quy tắc NV-01, TV-05 (M1 §1.4) |
| Liên quan đề xuất | Mục 5 "Tích hợp và kiểm soát chất lượng": mỗi batch có mã nguồn, checksum, số dòng, thời điểm, trạng thái; nạp lại không nhân đôi |
| Liên quan lộ trình | Milestone 4.1 (luồng ETL — Extract) |

## 1. Mục tiêu

Đưa dữ liệu nguồn vào tầng `raw` của kho theo từng **batch**, đúng nguyên tắc đã chốt:
- chỉ lấy các ngày mô phỏng **đã hoàn tất**;
- mọi bảng đọc từ **cùng một snapshot** nhất quán;
- trích incremental với bảng giao dịch, theo khóa cha với bảng con, full snapshot với dimension;
- `raw` **bất biến**;
- mỗi bảng có số dòng và checksum để chứng minh nạp lại cho cùng dữ liệu.

## 2. Đầu vào

- `mock_oltp`, đọc bằng `dw_reader` (chỉ đọc, bước 02). Mock Studio `last_day = 2026-01-13`.
- SQLite crawler `data/tiki_crawl_share.db`, đọc ở chế độ `mode=ro`.
- Bảng `audit.batch_log` và `audit.batch_table_log` (bước 05).
- Môi trường chạy: WSL, `.venv` (Python 3.12.14, psycopg 3.3.8, requests 2.34.2).

## 3. Phân tích trước khi làm

| Vấn đề | Quyết định |
|---|---|
| Engine đang ghi trong lúc trích xuất; đọc từng bảng riêng lẻ có thể không nhất quán (đơn có nhưng dòng hàng chưa có) | Đọc **mọi bảng OLTP trong một transaction `REPEATABLE READ READ ONLY`**: một snapshot duy nhất |
| Ngày đang chạy dở (`next_day`) có dữ liệu chưa chốt | Cửa sổ `(watermark_from, watermark_to]` với `watermark_to = last_day` (TV-05). Không cho `--until` vượt `last_day` |
| 9 bảng không có cột thời gian (M1, P2) | `order_items`, `payments`, `order_item_promotions`: trích **theo khóa cha** (đơn trong cửa sổ). Bảng danh mục và dimension: **full snapshot** (cần cho so sánh SCD) |
| Đơn hoàn tất hoặc trả hàng muộn 2–6 ngày (M2, G5) | Đơn "trong cửa sổ" = được tạo **hoặc** cập nhật **hoặc** hoàn tất **hoặc** hủy trong cửa sổ, **hoặc** có dòng trả hàng phát sinh trong cửa sổ |
| Quy tắc `raw` bất biến (NV-01) chỉ được viết trên giấy | Thực thi bằng **trigger** chặn UPDATE/DELETE/TRUNCATE, áp cả với chủ sở hữu bảng |
| Một batch có thể lỗi giữa chừng | `batch_log` được commit trước (để ghi được `FAILED`); toàn bộ `raw` của batch nằm trong **một transaction** (all-or-nothing) |
| Hiệu năng | Stream bằng `COPY (SELECT …) TO STDOUT` → `COPY … FROM STDIN`, không đưa dữ liệu qua Python từng dòng |

## 4. Cách thực hiện

### 4.1. File

| File | Vai trò |
|---|---|
| [dw/etl/config.py](../../dw/etl/config.py) | URL nguồn (`dw_reader`), URL đích (`dw_etl`), API mock, đường dẫn SQLite, mốc đầu `2025-12-31`; ghi đè được bằng biến môi trường |
| [dw/etl/extract.py](../../dw/etl/extract.py) | Module Extract (đặc tả `SPEC`, tạo bảng `raw` động, COPY, checksum, audit, trigger bất biến, crawler) |
| [dw/etl/run.sh](../../dw/etl/run.sh) | Chạy module trong WSL, ghi thêm log JSON vào `data/logs/etl.log` |
| [dw/sql/50_audit/503_batch_status.sql](../../dw/sql/50_audit/503_batch_status.sql) | Trạng thái batch `RUNNING → EXTRACTED → TRANSFORMED → SUCCESS / FAILED`; cột `source_snapshot` |

### 4.2. Đặc tả trích xuất (`SPEC`)

`F`/`T` = `watermark_from + 1 ngày 00:00` (gồm) / `watermark_to + 1 ngày 00:00` (không gồm).

| Bảng | Chế độ | Điều kiện | Phục vụ |
|---|---|---|---|
| `products`, `categories`, `sellers`, `customers`, `channels`, `payment_methods`, `warehouses`, `marketing_campaigns`, `promotions`, `seller_commission_rates` | FULL | — | Dimension, SCD |
| `orders` | WINDOW | tạo / cập nhật / hoàn tất / hủy ∈ [F, T) hoặc có `returns` phát sinh trong [F, T) | Fact_Order_Item |
| `order_items`, `payments` | PARENT | `order_id` ∈ đơn ở trên | Grain fact, phương thức thanh toán |
| `order_item_promotions` | PARENT | `order_item_id` thuộc các đơn ở trên | Bridge khuyến mãi |
| `returns` | WINDOW | `requested/approved/received/refunded_at` ∈ [F, T) | `is_returned` |
| `inventory_daily_balance` | WINDOW | `balance_date` ∈ (watermark_from, watermark_to] | Fact_Inventory_Snapshot |
| `inventory_movements` | WINDOW | `movement_date` ∈ [F, T) | Nhập/bán/điều chỉnh |
| `ad_spend_logs` | WINDOW | `log_date` ∈ (watermark_from, watermark_to] | Fact_Ad_Spend |
| `tiki_product_category` (SQLite) | FULL | `product_raw` ⋈ `product_categories` ⋈ `products`: `primary_category_path`, gốc, lá, tên | Cây danh mục (IR-04) |

### 4.3. Luồng một lần chạy

1. Đọc `last_day` từ `GET /api/overview`. `watermark_to = --until` hoặc `last_day`. `watermark_from = --from` hoặc `max(watermark_to)` của batch `SUCCESS` (lần đầu: `2025-12-31`).
2. Ghi `audit.batch_log(status='RUNNING')` và **commit ngay**.
3. Mở `dw_reader` với `REPEATABLE READ` + `read_only`. Lấy `extracted_at = now()` của snapshot.
4. Với mỗi bảng trong `SPEC`:
   - đọc cột nguồn từ `information_schema`;
   - `CREATE TABLE IF NOT EXISTS raw.<bảng>` gồm 3 cột kỹ thuật (`batch_id`, `extracted_at`, `row_hash`) và đúng kiểu cột nguồn;
   - gắn trigger bất biến;
   - `COPY (SELECT batch_id, extracted_at, md5(t::text), cột… FROM t WHERE …)` stream sang `raw`;
   - tính số dòng và `checksum = md5(string_agg(row_hash ORDER BY id))`;
   - ghi `audit.batch_table_log` (stage `EXTRACT`).
5. Kết thúc snapshot nguồn. Đọc crawler SQLite, ghi `raw.tiki_product_category`.
6. `status = 'EXTRACTED'`, commit toàn bộ `raw` của batch. Nếu có lỗi: rollback `raw` và ghi `status='FAILED'` kèm thông báo.

```bash
# trong WSL, từ thư mục repo
bash dw/etl/run.sh extract                                  # incremental tới last_day
bash dw/etl/run.sh extract --until 2026-01-13 --type RERUN  # nạp lại cùng mốc (kiểm chứng)
```

## 5. Quá trình thực hiện (output thật)

**Batch 1** (INCREMENTAL, 2025-12-31 → 2026-01-13), 20,2 giây:

| Bảng | Chế độ | Dòng | Thời gian |
|---|---|---:|---:|
| products | FULL | 3.532 | 0,34 s |
| categories / sellers / customers | FULL | 49 / 481 / 10.380 | 0,03 / 0,06 / 0,54 s |
| channels / payment_methods / warehouses | FULL | 3 / 5 / 6 | ~0,03 s |
| marketing_campaigns / promotions / seller_commission_rates | FULL | 1 / 3 / 132 | ~0,04 s |
| orders | WINDOW | 1.511 | 0,13 s |
| order_items / payments / order_item_promotions | PARENT | 1.737 / 1.362 / 188 | 0,13 / 0,09 / 0,04 s |
| returns | WINDOW | 6 | 0,03 s |
| inventory_daily_balance | WINDOW | **237.324** | 14,44 s |
| inventory_movements | WINDOW | 19.765 | 1,12 s |
| ad_spend_logs | WINDOW | 8 | 0,03 s |
| tiki_product_category | FULL (SQLite) | 3.532 | ~3 s |

**Batch 2** (RERUN, cùng mốc), 18,1 giây, cùng số dòng.

Không phát sinh lỗi khi chạy. Lỗi duy nhất được phát hiện **trước khi chạy** là xung đột giữa lệnh `BEGIN` viết tay và cơ chế tự mở transaction của psycopg3; đã sửa bằng `isolation_level` và `read_only` của connection.

## 6. Kiểm tra kết quả

Output đầy đủ: [evidence/06_extract_check.txt](evidence/06_extract_check.txt).

| # | Kiểm tra | Kết quả thật | Đạt |
|---|---|---|---|
| E1 | Batch có đủ mã, cửa sổ, nguồn, thời gian, trạng thái | 2 batch, `EXTRACTED`, `source_snapshot = mock last_day=2026-01-13`, `extract 20.2 s` / `18.1 s` | ✅ |
| E2 | Nạp lại cùng mốc cho cùng dữ liệu | **19/19 bảng có checksum trùng** giữa batch 1 và 2 | ✅ |
| E3 | Không lọt dữ liệu của ngày chưa hoàn tất | Đơn có created/updated/completed ≥ 14/01: **0**; `max(created_at)` = 13/01 23:01:08; tồn kho 01/01–13/01 (13 ngày) | ✅ |
| E4 | `raw` bất biến | UPDATE, DELETE, TRUNCATE đều bị chặn: `raw.<bảng> là bất biến (NV-01)` | ✅ |
| E5 | Đủ dòng so với nguồn | orders 1.511 = 1.511; order_items 1.737 = 1.737; inventory_daily_balance 237.324 = 237.324; ad_spend_logs 8 = 8 | ✅ |
| E6 | `row_hash` = md5 dòng nguồn | 3/3 sản phẩm mẫu trùng hash | ✅ |
| E7 | Dung lượng | `raw.inventory_daily_balance` 60 MB cho 13 ngày (bảng lớn nhất) | ✅ (ghi nhận) |

## 7. Vấn đề & cách xử lý

| Vấn đề | Xử lý |
|---|---|
| Snapshot dimension đọc lúc chạy có thể chứa thay đổi của ngày đang chạy (vd. khách đổi hạng lúc 10:00 của `next_day`) | Không sai lịch sử: thay đổi được gán `valid_from = date(updated_at)` = `next_day`, nên mọi fact ≤ `last_day` vẫn tra về phiên bản cũ. Xử lý ở Transform/Load (TV-03) |
| Đơn có thể đổi trạng thái sau khi đã trích (hoàn tất, trả hàng) | Batch sau sẽ trích lại đơn đó (cửa sổ dựa trên `updated_at`, `completed_at`, `returns`), Load upsert theo khóa nghiệp vụ |
| `raw` lớn dần vì dimension là full snapshot mỗi batch | Chấp nhận (≈ 20 nghìn dòng dimension/batch). Bảng lớn (tồn kho) chỉ trích phần ngày mới |
| Batch 2 (RERUN) để lại thêm một bộ `raw` | Đúng theo NV-01 (không xóa). Transform xử lý batch được chỉ định (mặc định là batch `EXTRACTED` mới nhất) |
| Chưa có batch `SUCCESS`, nên chưa thử được nhánh incremental "từ batch thành công gần nhất" | Thử ở bước 08, khi batch đầu được nạp đến `SUCCESS` |

## 8. Ảnh hưởng & bước tiếp theo

- Mới:
  - `dw/__init__.py`, `dw/etl/{__init__,config,extract}.py`, `dw/etl/run.sh`;
  - `dw/sql/50_audit/503_batch_status.sql` (đã thêm vào `run_ddl.sh`);
  - `evidence/06_extract_check.txt`.
- Database `dwh`:
  - 19 bảng `raw.*` (có trigger bất biến), hàm `raw.forbid_mutation()`;
  - 2 batch trong `audit.batch_log`, 38 dòng `audit.batch_table_log`.
- Không ghi gì vào `mock_oltp`; engine mock vẫn chạy (đang ở ngày 14/01).
- Bước tiếp theo: **07 — PLAN 5.3 Transform**: tạo các bảng ánh xạ `stg.map_*` (CSV), các bảng `stg.*` theo 5.3.3, các quy tắc DQ-01..20, cách ly vào `audit.quarantine`, kiểm đếm RC-07; chạy trên batch 1.
