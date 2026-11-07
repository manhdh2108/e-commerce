# 05 — PLAN 4 (Milestone 3): Thiết kế vật lý, Galaxy schema, từ điển dữ liệu

| | |
|---|---|
| Ngày thực hiện | 07/11/2026, 22:45–23:15 |
| Trạng thái | ✅ Xong (cấu trúc đã tạo; dữ liệu sẽ nạp ở bước ETL) |
| Liên quan PLAN | Mục 4.1–4.8 |
| Liên quan lộ trình | Milestone 3 (Sub 3.1, 3.2, 3.3); Kimball – Dimensional Modeling |
| Sản phẩm | [M3_THIET_KE_VAT_LY_STAR_SCHEMA.md](../data-model/warehouse/M3_THIET_KE_VAT_LY_STAR_SCHEMA.md), [M3_TU_DIEN_DU_LIEU.md](../data-model/warehouse/M3_TU_DIEN_DU_LIEU.md) |

## 1. Mục tiêu

Chuyển mô hình logic (grain M2, quy tắc M1) thành **cấu trúc bảng thật** trong `dwh.dw`:
- 3 fact, 14 dimension và 2 bridge, có PK, FK, CHECK, partition;
- thành viên đặc biệt `-1`/`0`;
- `dim_date` và `dim_month` được nạp sẵn;
- từ điển dữ liệu sinh tự động từ catalog, kèm lineage về nguồn OLTP.

## 2. Đầu vào

- Database `dwh`, role `dw_etl`, 6 schema (bước 02).
- Thiết kế PLAN 4.2 (dimension), 4.3 (DDL nháp), 4.8 (measure); grain M2; IR-01..10 (M1).
- Postgres 15.19.

## 3. Phân tích trước khi làm

Có 4 điểm trong bản nháp PLAN cần kiểm tra trước khi viết DDL:
1. **Kiểu tiền:** `numeric(18,2)` có đủ chính xác không, khi nguồn có `discount_amount` lẻ? Đã kiểm tra trên OLTP: engine làm tròn 2 chữ số, `quantity × unit_price − round(discount,2) = round(net,2)` lệch **0 dòng**. Giữ `numeric(18,2)`.
2. **PK của bảng partition:** PostgreSQL bắt buộc khóa partition (`date_key`) nằm trong mọi PK/UNIQUE. Vì vậy PK = `(date_key, source_system, order_id, line_number)`. Khóa vẫn duy nhất theo nghiệp vụ vì `completed_at` không đổi.
3. **Bridge khuyến mãi:** bản nháp có `allocated_discount` trong bridge theo nhóm. Đây là lỗi grain, vì cùng một nhóm voucher được dùng cho nhiều dòng có số tiền giảm khác nhau. Bỏ cột này; số tiền tính bằng `discount_amount × weighting_factor`.
4. **Từ điển dữ liệu:** muốn từ điển không lệch với DDL thì phải sinh từ catalog. Mô tả nằm trong `COMMENT ON`, còn lineage nằm trong bảng `audit.column_lineage`, cả hai cùng sinh từ một danh sách duy nhất.

## 4. Cách thực hiện

| File | Nội dung |
|---|---|
| [30_dw/301_dim_date.sql](../../dw/sql/30_dw/301_dim_date.sql) | `dim_month` (36 tháng), `dim_date` (1.095 ngày, 2025–2027): thứ ISO, tuần ISO, quý, cuối tuần, ngày lễ VN (2026 có ngày âm lịch đã quy đổi), ngày đôi, cuối tháng |
| [30_dw/302_dimensions.sql](../../dw/sql/30_dw/302_dimensions.sql) | 14 dimension + 2 bridge; cột SCD2 (`valid_from`, `valid_to`, `is_current`, `scd1_hash`, `scd2_hash`); index unique một phần "1 bản hiện hành / khóa"; thành viên `-1`/`0`; mini-dimension sinh sẵn 125 tổ hợp; đặt lại sequence |
| [30_dw/303_facts.sql](../../dw/sql/30_dw/303_facts.sql) | 3 fact, 18 FK, CHECK cho measure; partition RANGE theo tháng (36 partition + `default`) tạo bằng vòng lặp `DO`; index FK |
| [50_audit/501_audit.sql](../../dw/sql/50_audit/501_audit.sql) | `batch_log`, `batch_table_log`, `quarantine`, `dq_result`, `reconciliation`, `column_lineage`; view `audit.data_dictionary` |
| [50_audit/502_dictionary_metadata.sql](../../dw/sql/50_audit/502_dictionary_metadata.sql) | Danh sách duy nhất (bảng, cột, mô tả, nguồn, quy tắc, tính cộng, SCD) → `COMMENT ON COLUMN` + upsert `audit.column_lineage`; `COMMENT ON TABLE` |
| [run_ddl.sh](../../dw/sql/run_ddl.sh) | Chạy 5 file theo thứ tự bằng `dw_etl`, `ON_ERROR_STOP=1` |
| [dw/tools/export_dictionary.py](../../dw/tools/export_dictionary.py) | Xuất `audit.data_dictionary` → `M3_TU_DIEN_DU_LIEU.md` |

```bash
bash dw/sql/run_ddl.sh                      # tạo / cập nhật cấu trúc (idempotent)
python dw/tools/export_dictionary.py        # sinh lại từ điển dữ liệu
```

## 5. Quá trình thực hiện (output thật)

1. Lần chạy đầu dừng ở `301_dim_date.sql`:
   ```
   ERROR:  column reference "d" is ambiguous
   ```
   Nguyên nhân: CTE ngày lễ có cột `d` trùng tên với cột ngày của bảng sinh. Sửa: đổi tên cột của CTE thành `hd`.
2. Lần chạy thứ hai: 5/5 file thành công (`ddl done`). Chạy thêm lần ba để kiểm tra idempotent: `rerun OK (idempotent)`.
3. Kiểm tra lần đầu cho thấy `dim_date`/`dim_month` mới có mô tả 7/17 và 1/9 cột. Đã bổ sung 22 dòng metadata, chạy lại: đủ **199/199**.
4. Câu kiểm tra FK đầu tiên trả rỗng. Lý do: so `conrelid::regclass::text` với `'dw.fact_…'`, trong khi `search_path` đã bỏ tiền tố schema. Viết lại bằng so sánh `regclass`.

Kết quả kiểm tra đầy đủ: [evidence/05_m3_ddl_check.txt](evidence/05_m3_ddl_check.txt).

## 6. Kiểm tra kết quả

| # | Kiểm tra | Kết quả thật | Đạt |
|---|---|---|---|
| K1 | Số bảng trong `dw` (không tính partition) | 19 bảng (3 fact, 14 dim, 2 bridge), tất cả có `COMMENT` | ✅ |
| K2 | Partition | `fact_order_item`: 37, `fact_inventory_snapshot`: 37 (36 tháng + default) | ✅ |
| K3 | `dim_date` | 1.095 ngày, 2025-01-01..2027-12-31, 17 ngày lễ, 36 ngày đôi; 2026: Tết 16–19/02, Giỗ Tổ 26/04 (Chủ Nhật) | ✅ |
| K4 | Thành viên đặc biệt | `-1=Không áp dụng/Khách vãng lai/Không có chiến dịch/NONE`, `0=Chưa xác định`; profile 127 = 125 + 2 | ✅ |
| K5 | FK | `fact_order_item` 11, `fact_inventory_snapshot` 4, `fact_ad_spend` 3 | ✅ |
| K6 | Định tuyến partition | Insert thử ngày 20260115 → `fact_inventory_snapshot_202601` (rollback) | ✅ |
| K7 | CHECK chặn dữ liệu sai | `reserved = 9 > on_hand = 5` → `violates check constraint` | ✅ |
| K8 | Từ điển dữ liệu | 199 cột, 199 có mô tả, 199 có lineage; xuất Markdown 19 bảng | ✅ |
| K9 | Idempotent | Chạy `run_ddl.sh` lần 3 không lỗi, không nhân đôi dòng đặc biệt | ✅ |

Đối chiếu tiêu chí T1 của đề xuất ("ba fact đúng grain; có PK/FK, dimension dùng chung và từ điển dữ liệu"): đạt về cấu trúc. Phần "đúng grain trên dữ liệu" sẽ được kiểm khi nạp ETL (bước 08).

## 7. Vấn đề & cách xử lý

| Vấn đề | Xử lý |
|---|---|
| `allocated_discount` trong bridge sai grain (bản nháp PLAN) | Bỏ; sửa PLAN 4.3, 4.8.1, 4.8.5, RC-03 (quyết định D4) |
| PK của bảng partition phải chứa `date_key` | PK = khóa nghiệp vụ + `date_key` (D2) |
| Ngày âm lịch chỉ quy đổi cho năm 2026 | Dữ liệu chỉ có 2026; 2025 và 2027 chỉ có ngày lễ dương lịch (ghi trong `COMMENT`) |
| Cột `dim_date` thiếu mô tả ở lần đầu | Bổ sung metadata (22 dòng), từ điển đạt 100% |

## 8. Ảnh hưởng & bước tiếp theo

- Mới: `dw/sql/30_dw/{301,302,303}*.sql`, `dw/sql/50_audit/{501,502}*.sql`, `dw/sql/run_ddl.sh`, `dw/tools/export_dictionary.py`, `docs/data-model/warehouse/M3_*.md`, `evidence/05_m3_ddl_check.txt`.
- Database `dwh`: 19 bảng `dw` (+74 partition), 7 đối tượng `audit`; `dim_date`/`dim_month` đã có dữ liệu; các dimension khác mới có `-1`/`0`.
- Sửa PLAN: thiết kế bridge, RC-03, trạng thái mục 4.
- Bước tiếp theo: **06 — PLAN 5.2 Extract**: viết `dw/etl/extract.py` (đọc `last_day`, trích incremental bảng giao dịch, trích bảng con theo khóa cha, full snapshot dimension, checksum, ghi `raw.*` và `audit.batch_log`).
