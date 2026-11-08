# 02 — PLAN 1.1: Khởi tạo database kho `dwh`, role và schema

| | |
|---|---|
| Ngày thực hiện | 07/11/2026, ~22:35 |
| Trạng thái | ✅ Xong |
| Liên quan PLAN | Mục 1.1 (Cơ sở dữ liệu kho), 1.2 (cấu trúc repo) |
| Liên quan đề xuất | Mục 3 (các schema logic `raw/stg/dw/mart/audit/bench`), Bảng 3 (nhà phân tích dùng tài khoản chỉ đọc), Bảng 5 |
| Liên quan lộ trình | Milestone 1.1 (ranh giới OLTP ↔ DW) |

## 1. Mục tiêu

Tạo nơi chứa kho dữ liệu **tách biệt** với OLTP. Đây là nguyên tắc Inmon "tách hệ thống vận hành và phân tích" (Bước 1 của lộ trình), gồm:
- database riêng `dwh`;
- 6 schema logic theo đề xuất;
- 3 role phân quyền tối thiểu: ETL đọc nguồn, ETL ghi kho, người phân tích chỉ đọc.

## 2. Đầu vào

- Postgres 15.19 trong container `scripts-mock-postgres-1`, cổng `127.0.0.1:55432`. Superuser là `mock`.
- Database sẵn có: `mock_oltp` (OLTP, engine đang ghi), `mock_control` (điều khiển mock).
- 10 database kiểm chứng tạm (`eqa…eqe_control/oltp`) còn lại từ bước 00.

## 3. Phân tích trước khi làm

- **Đặt kho ở đâu?** Đề xuất ghi "các lớp logic trên cùng một cơ sở dữ liệu PostgreSQL". Tôi chọn **cùng server Postgres nhưng khác database** (`dwh`):
  - ETL đọc được `mock_oltp` mà không cần cài thêm server;
  - đối tượng của kho không lẫn vào `mock_oltp`. Điều này bắt buộc, vì Mock Studio từ chối chạy nếu `mock_oltp` có bảng lạ ("DB nghiệp vụ có bảng ngoài mô hình").
- **Không ghi vào nguồn.** Engine đối chiếu ảnh trước/sau (manifest) để khôi phục, nên mọi thao tác ghi tay vào `mock_oltp` đều có thể làm hỏng lượt mô phỏng. Vì vậy `dw_reader` có 2 lớp bảo vệ: chỉ được cấp `SELECT`, và phiên luôn ở chế độ `read_only`.
- **Postgres 15:** đủ cho partition khai báo, materialized view và `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` mà BM01–BM03 cần. Đề xuất trích tài liệu PG 18, nhưng các tính năng dùng đến đều có từ PG 10–13.

## 4. Cách thực hiện

File trong [dw/sql/00_init/](../../dw/sql/00_init/):

| File | Chạy trên | Bằng role | Nội dung |
|---|---|---|---|
| [001_database_roles.sql](../../dw/sql/00_init/001_database_roles.sql) | `postgres` | `mock` | Tạo role `dw_reader`, `dw_etl`, `dw_analyst` (idempotent bằng `DO $$ … IF NOT EXISTS`); `GRANT dw_reader TO dw_etl`; tạo `dwh` (dùng `\gexec` vì `CREATE DATABASE` không chạy được trong transaction); chỉ role kho được `CONNECT`; `dw_analyst` luôn ở phiên chỉ đọc trong `dwh` |
| [002_source_grants.sql](../../dw/sql/00_init/002_source_grants.sql) | `mock_oltp` | `mock` | `SELECT` trên mọi bảng `public` cho `dw_reader` (kể cả bảng tạo sau); thu hồi mọi quyền ghi; `statement_timeout = 10min`; `default_transaction_read_only = on` |
| [003_schemas.sql](../../dw/sql/00_init/003_schemas.sql) | `dwh` | `dw_etl` | Tạo 6 schema kèm `COMMENT`; `dw_analyst` có `SELECT` trên `dw`, `mart`, `audit`, kể cả bảng tạo sau (`ALTER DEFAULT PRIVILEGES`); `search_path = dw, mart, public`; múi giờ `Asia/Ho_Chi_Minh` |
| [run_init.sh](../../dw/sql/00_init/run_init.sh) | — | — | Chạy 3 file theo thứ tự qua `docker exec … psql -v ON_ERROR_STOP=1` |

Ma trận quyền:

| Role | `mock_oltp` | `dwh.raw/stg/bench` | `dwh.dw/mart` | `dwh.audit` |
|---|---|---|---|---|
| `dw_reader` | Chỉ đọc | ❌ Không kết nối | ❌ | ❌ |
| `dw_etl` | Chỉ đọc (qua `dw_reader`) | Chủ sở hữu | Chủ sở hữu | Chủ sở hữu |
| `dw_analyst` | ❌ | ❌ | Chỉ đọc | Chỉ đọc |

Chuỗi kết nối (local, dùng cho ETL và dashboard ở các bước sau):

```
ETL ghi kho : postgresql://dw_etl:dw_etl_local@127.0.0.1:55432/dwh
ETL đọc nguồn: postgresql://dw_reader:dw_reader_local@127.0.0.1:55432/mock_oltp
Dashboard   : postgresql://dw_analyst:dw_analyst_local@127.0.0.1:55432/dwh
```

## 5. Quá trình thực hiện (output thật)

1. Dọn 10 database kiểm chứng tạm của bước 00 (`DROP DATABASE … WITH (FORCE)`). Còn lại `mock_control`, `mock_oltp`, `postgres`.
2. Lần chạy `run_init.sh` đầu tiên: file 001 và 002 thành công, file 003 dừng ở dòng cuối:
   ```
   ALTER DEFAULT PRIVILEGES
   ERROR:  permission denied
   ```
   Nguyên nhân: câu `ALTER ROLE dw_analyst IN DATABASE dwh SET …` cần superuser, mà file 003 chạy bằng `dw_etl`. Cách sửa: chuyển câu này sang file 001.
3. Lần chạy thứ hai (các script đều idempotent):
   ```
   GRANT
   GRANT
   ALTER DEFAULT PRIVILEGES
   ALTER DATABASE
   ALTER DATABASE
   init done
   ```

## 6. Kiểm tra kết quả

| # | Kiểm tra | Kết quả thật | Đạt |
|---|---|---|---|
| K1 | 6 schema tồn tại, chủ sở hữu `dw_etl`, có mô tả | `audit, bench, dw, mart, raw, stg \| dw_etl \| …` | ✅ |
| K2 | `dw_reader` đọc được OLTP | `select count(*) from orders` → `1382` | ✅ |
| K3 | `dw_reader` **không** ghi được OLTP | `ERROR: cannot execute UPDATE in a read-only transaction` | ✅ |
| K4 | `dw_reader` không vào được `dwh` | `User does not have CONNECT privilege` | ✅ |
| K5 | `dw_analyst` không ghi được `dwh` | `ERROR: cannot execute CREATE TABLE in a read-only transaction` | ✅ |
| K6 | `dw_etl` tạo bảng trong `dw`, `dw_analyst` đọc được bảng mới (default privileges) | `INSERT 0 1` → analyst `select count(*)` = `1` → `DROP TABLE` | ✅ |
| K7 | Thiết lập database/role | `dwh/dw_analyst: read_only=on`; `dw_reader: statement_timeout=10min, read_only=on`; `dwh: search_path=dw, mart, public, TimeZone=Asia/Ho_Chi_Minh` | ✅ |
| K8 | Kết nối bằng mật khẩu từ WSL (nơi ETL chạy) qua cổng 55432 | `dw_etl → dwh`, `dw_reader → mock_oltp`, `dw_analyst → dwh` đều kết nối được | ✅ |

Script kiểm tra dùng lại được: các lệnh K1–K7 nằm trong `verify_init.sh` (scratchpad), nội dung như trong bảng trên.

## 7. Vấn đề & cách xử lý

| Vấn đề | Xử lý |
|---|---|
| `ALTER ROLE … IN DATABASE` cần superuser | Chuyển sang file 001 (chạy bằng `mock`) |
| Mật khẩu ghi thẳng trong SQL | Chấp nhận cho môi trường local (giống `local_mock_only` của Mock Studio); không dùng cho môi trường công khai (ngoài phạm vi đề xuất) |
| Nếu tạo lại volume Docker thì mất `dwh` và role | Chạy lại `bash dw/sql/00_init/run_init.sh` |

## 8. Ảnh hưởng & bước tiếp theo

- Mới: `dw/sql/00_init/{001_database_roles.sql, 002_source_grants.sql, 003_schemas.sql, run_init.sh}`.
- Không thay đổi gì trong `mock_oltp` ngoài quyền (GRANT). Engine mock vẫn chạy bình thường.
- Bước tiếp theo: **03 — PLAN 2 (Milestone 1)**: bản đồ hệ thống nguồn (đếm dòng và kiểm tra khóa thật của 33 bảng), chủ đề cốt lõi, bảng quy tắc tích hợp IR-01..07 kèm bằng chứng từ dữ liệu.
