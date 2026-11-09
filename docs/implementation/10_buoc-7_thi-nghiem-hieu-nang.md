# Bước 10 — PLAN 7: Thí nghiệm hiệu năng BM01 (MV), BM02 (Partition), BM03 (Index)

> Ngày thực hiện: 08/11/2026 · Lần đo: `20261108_123944` · Kết quả: 10 truy vấn × 2–4 biến thể, **390 lượt đo, 100% kết quả trùng hash với baseline**
> Mã: [bench/run_bench.py](../../bench/run_bench.py), [bench/run.sh](../../bench/run.sh) · Kết quả thô: [bench/results/](../../bench/results/) (CSV lượt đo, JSON môi trường, 26 plan `EXPLAIN ANALYZE BUFFERS`)
> Bằng chứng: [evidence/10_bench_result.txt](evidence/10_bench_result.txt) · Màn hình: dashboard → **Hiệu năng**

## 1. Mục tiêu

Đo bằng số liệu, theo đúng quy trình đề xuất mục 7, lợi ích **và chi phí** của ba kỹ thuật vật lý:

- **BM01:** materialized view so với tổng hợp trực tiếp trên fact.
- **BM02:** partition theo tháng so với bảng thường (cùng dữ liệu, cùng index).
- **BM03:** không index / B-tree đơn `(seller_key)` / ghép `(seller_key, date_key)` / ghép đảo `(date_key, seller_key)` (mở rộng 7.4 — thứ tự cột).

Phải ghi trung thực cả trường hợp **không nhanh hơn**.

## 2. Đầu vào

| Thành phần | Giá trị |
|---|---|
| Dữ liệu thật | `dw.fact_order_item` 1.195 dòng, `dw.fact_inventory_snapshot` 219.067 dòng (12 ngày, batch 4) — quá nhỏ để đo có ý nghĩa |
| Môi trường | PostgreSQL 15.19 (Docker, WSL2) · 16 CPU · RAM 7,8 GB · `shared_buffers` 128 MB · `work_mem` 4 MB · JIT on · 2 worker/gather · `random_page_cost` 4 |
| Lưu trữ | Toàn bộ dữ liệu bench nằm trong `D:\WSL\DockerDesktopWSL\disk\docker_data.vhdx` (**ổ D**, theo yêu cầu không ghi lên ổ C); kết quả CSV/JSON trong repo (ổ D, 212 KB) |

## 3. Phân tích trước khi làm

- **Dữ liệu nhân bản (PLAN 7.1)**, chỉ phục vụ thí nghiệm, nằm riêng trong schema `bench`:
  - `bench.foi_*` = `fact_order_item` × **1.680 bản** = **2.007.600 dòng** (431 MB). Bản k dịch ngày `(k mod 36) × 10` ngày (phủ 03/01–28/12/2026), `order_id += k × 10⁷`, `seller_key` hoán vị tất định `((seller_key × 31 + k × 17) mod 481) + 1` → mỗi seller ~4.000 dòng (độ chọn lọc ~0,2%). Ghi vật lý theo `date_key` như fact nạp tăng dần theo ngày.
  - `bench.inv_*` = `fact_inventory_snapshot` × **30 bản** dịch 12 ngày → 360 ngày, **6.572.010 dòng** (826 MB) — đúng cỡ dự kiến ~6,7 triệu dòng/năm (M2).
- **Một bảng riêng cho mỗi biến thể index** (`foi_noidx`, `foi_idx_seller`, `foi_idx_seller_date`, `foi_idx_date_seller` — cùng nội dung, cùng thứ tự vật lý) để xáo thứ tự biến thể trong từng lượt mà không phải dựng lại index; planner không thể "chọn nhầm" index của biến thể khác.
- **Partition:** `foi_part`, `inv_part` — 12 partition tháng + `default`; `inv_plain` và `inv_part` có cùng PK `(date_key, product_key, warehouse_key)` + index `product_key`; `foi_noidx` và `foi_part` cùng **không** index.
- **Tạm dừng mock khi đo (7.3 bước 6):** `bench/run.sh` đóng băng worker bằng `SIGSTOP` và `trap … SIGCONT` khi kết thúc (kể cả khi lỗi). Đã kiểm tra engine không có watchdog heartbeat → job giữ `RUNNING` và chạy tiếp đúng chỗ.
- **Đo thời gian phía client** (execute + fetch hết kết quả) — gần với trải nghiệm dashboard; `EXPLAIN (ANALYZE, BUFFERS)` chạy riêng sau khi đo để lấy plan, buffers, số partition.

## 4. Cách thực hiện

```bash
bash bench/run.sh            # tạm dừng mock → setup + run → mock chạy lại
bash bench/run.sh setup      # chỉ dựng dữ liệu (≈ 10 phút)
bash bench/run.sh run        # chỉ đo (≈ 5 phút)
.venv/bin/python -m bench.run_bench clean     # xóa ~4,3 GB dữ liệu nhân bản, GIỮ kết quả bm_*
```

Quy trình đo cho mỗi truy vấn:

1. Chạy mọi biến thể một lần, so **md5 của toàn bộ kết quả** với baseline (`hash_match`).
2. **3 lượt warm-up + 15 lượt đo**; mỗi lượt **xáo thứ tự biến thể** (`random.Random(42)`), concurrency 1.
3. Median, p95, min, max, mean; **speedup = median baseline / median biến thể**.
4. `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` → `bench/results/plans/<run>_<query>_<biến thể>.json`. Trích: node gốc, các nút scan, số relation/partition bị quét, `shared hit/read`, index dùng.
5. Lưu `bench.bm_run` (môi trường + tham số), `bench.bm_object` (kích thước, thời gian dựng), `bench.bm_result`; lượt đo thô `bench/results/raw_<run>.csv`.

## 5. Quá trình thực hiện (diễn biến thật)

| Giờ | Việc | Kết quả |
|---|---|---|
| 12:20 | `run.sh setup` lần 1 | Lỗi `column "?column?" specified more than once` — biểu thức trong `CREATE TABLE AS` chưa đặt alias. Mock tự chạy lại (trap) |
| 12:21 | Lần 2 | Dựng 9 đối tượng; **lỗi** `could not resize shared memory segment … No space left on device` khi VACUUM MV |
| — | Phân tích | **Không phải hết đĩa**: `/dev/shm` của container chỉ 64 MB, VACUUM song song với `maintenance_work_mem` 512 MB xin vùng nhớ chia sẻ lớn hơn → tắt song song cho bước dựng (`max_parallel_maintenance_workers = 0`, `VACUUM (PARALLEL 0)`); lúc đo vẫn giữ cấu hình mặc định |
| 12:29–12:39 | Lần 3 (chạy nền) | Dựng xong 12 đối tượng (~4,3 GB) |
| 12:39–12:44 | `run.sh run` | 390 lượt đo; mock tạm dừng 12:39:38 → chạy lại 12:44 |
| 12:44 | Kiểm tra mock | heartbeat mới, số hành động tăng 72.928 → 73.339 — mock chạy tiếp bình thường |

## 6. Kết quả

Median (ms) của 15 lượt; speedup so với biến thể đầu (baseline). Mọi dòng `hash_match = true`.

### BM01 — Materialized View

| Truy vấn | Trực tiếp fact | Đọc MV | Speedup | Chi phí MV |
|---|---:|---:|---:|---|
| Q1a Doanh thu tháng × danh mục (2 triệu dòng, có `COUNT(DISTINCT order_id)`) | 6.170,0 | **2,49** | **×2.481** | MV 516 dòng, 0,11 MB; **REFRESH 10,0 s** |
| Q1b Cùng truy vấn trên dữ liệu **thật** (1.195 dòng) | 4,42 | 1,05 | ×4,2 | Lợi tuyệt đối ~3 ms — không đáng kể khi fact còn nhỏ |
| Q1c Tồn cuối tháng & bình quân × danh mục (6,6 triệu dòng) | 2.011,6 | **2,54** | **×793** | MV 528 dòng, 0,10 MB; **REFRESH 2,7 s** |

Diễn giải: MV dời chi phí `GROUP BY` sang lúc refresh. Điểm hòa vốn của Q1a ≈ 10,0 s / 6,17 s ≈ **2 lần truy vấn cho mỗi lần refresh** — dashboard đọc nhiều lần sau mỗi batch nên có lợi rõ. Q1b cho thấy với dữ liệu nhỏ MV không cần thiết. Lưu ý MV của mart có grain tháng × danh mục × **kênh**: gộp lên tháng × danh mục chỉ đúng với measure cộng được (Σ net, Σ món), **không** đúng với số đơn distinct.

### BM02 — Partition theo tháng

| Truy vấn | Bảng thường | Partition | Speedup | Plan (EXPLAIN) |
|---|---:|---:|---:|---|
| Q2a Tồn kho theo ngày trong 06/2026 | 208,3 | 154,5 | ×1,35 | Thường: index range scan PK (8.340 buffer). Partition: pruning còn **1 partition**, seq scan (6.238 buffer) |
| Q2b Tồn kho 1 ngày theo kho | 10,6 | 11,2 | **×0,95** | Cả hai dùng PK index, cùng 281 buffer → **không có lợi** |
| Q2c Doanh thu 1 tháng, **không index** | 315,5 | 106,6 | **×2,96** | Thường: seq scan cả năm (~55.200 buffer). Partition: 1 partition (~4.600 buffer, ≈ 1/12) |
| Q2d Quét cả năm, không lọc ngày | 700,6 | 836,5 | **×0,84 (chậm hơn)** | Partition: Append **13 relation**, không cắt tỉa được |

Diễn giải: partition có lợi khi điều kiện theo khóa partition loại được phần lớn dữ liệu và **không có index tốt** (Q2c), hoặc khi đọc trọn một tháng (Q2a — seq scan 1 partition rẻ hơn index scan rải rác). Với truy vấn rất chọn lọc đã có index (Q2b) không khác biệt; quét toàn bộ (Q2d) **chậm hơn ~16%** do chi phí Append nhiều partition. Q2c chỉ nhanh ×3 (không phải ×12) vì bảng thường được quét song song và phần lớn trang đã nằm trong cache hệ điều hành. Lợi ích chính khác của partition (không đo ở đây): xóa/lưu trữ dữ liệu cũ theo tháng bằng `DETACH`, `VACUUM`/`ANALYZE` theo partition.

### BM03 — Index (lọc seller + khoảng ngày)

Seller được chọn: `seller_key = 129` (số dòng trung vị, ~4.000 dòng / 2 triệu ≈ 0,2%).

| Truy vấn | Không index | `(seller_key)` | `(seller_key, date_key)` | `(date_key, seller_key)` |
|---|---:|---:|---:|---:|
| Q3a 1 seller, 1 tháng | 286,2 | 8,11 (×35) | **1,51 (×189)** — 244 buffer | 2,61 (×110) — 421 buffer |
| Q3b 1 seller, cả năm | 276,1 | **9,45 (×29)** | **9,34 (×30)** | 14,02 (×20) — quét cả index, 5.075 buffer |
| Q3c Toàn sàn 1 tuần (không lọc seller) | 259,4 | 269,8 (×0,96, seq scan) | 276,5 (×0,94, seq scan) | **40,5 (×6,4)** |

Chi phí index: 13,5 MB `(seller_key)` / 16,9 MB mỗi index ghép (≈ 3–4% bảng 431 MB); thời gian `CREATE INDEX` 6–17 s.

Diễn giải:

- Cột so sánh bằng (`seller_key =`) **đứng trước** cột khoảng (`date_key BETWEEN`) cho phạm vi quét hẹp nhất (Q3a: 244 buffer, nhanh nhất).
- `(date_key, seller_key)` vẫn dùng được cho Q3a/Q3b nhưng phải lướt nhiều mục hơn; chỉ index này phục vụ được lọc **theo ngày** (Q3c). Hai index có `seller_key` đứng đầu không giúp gì cho Q3c (planner chọn seq scan — ghi trung thực ×0,94–0,96).
- Kết luận thiết kế: fact giữ index FK đơn (bước 05); nếu dashboard lọc seller + ngày thường xuyên → `(seller_key, date_key)`; lọc theo ngày toàn sàn đã có partition pruning nên không cần thêm `(date_key, …)`.

## 7. Vấn đề, giới hạn & cách xử lý

| Vấn đề / giới hạn | Xử lý / ghi chú |
|---|---|
| Alias thiếu trong `CREATE TABLE AS` | Đặt alias cho mọi cột biểu thức |
| `/dev/shm` 64 MB của container | Tắt song song **chỉ trong bước dựng** dữ liệu; nếu muốn bảo trì song song cần tăng `shm_size` trong `scripts/compose.mock.yaml` (phải tạo lại container — không làm khi mock đang chạy) |
| Dữ liệu nhân bản lặp mẫu của 12 ngày thật | Phân phối theo ngày/seller đều hơn thực tế; số tuyệt đối mang tính minh họa, **tỷ lệ và hướng** của kết quả mới là điều cần đọc |
| `shared_buffers` 128 MB, máy 7,8 GB | Phần lớn "read" là từ cache hệ điều hành, không phải đĩa vật lý; kết quả là trạng thái **ấm** (sau warm-up) |
| Thời gian dựng bảng dao động (6,9 s vs 58 s cho cùng `CREATE TABLE AS`) | Do cache/ghi WAL ở thời điểm khác nhau — không dùng để so sánh; chỉ thời gian `CREATE INDEX` và `REFRESH` được báo cáo |
| Chi phí ghi của index / partition khi nạp | Chưa đo (mở rộng: đo thời gian `load` batch với/không index ghép) |
| Dung lượng | ~4,3 GB trong `docker_data.vhdx` trên ổ D; xóa bằng `python -m bench.run_bench clean` khi không cần (file vhdx không tự co lại) |

## 8. Ảnh hưởng & bước tiếp theo

- Dashboard → **Hiệu năng** hiển thị lần đo, môi trường, median (thang log), speedup, cảnh báo các ca chậm hơn, chi phí đối tượng.
- Đề xuất cho thiết kế cuối: giữ MV ở mart (refresh ở B6), partition tháng cho 2 fact lớn, thêm index `(seller_key, date_key)` nếu màn hình theo seller được dùng nhiều.
- Có thể đo lại khi dữ liệu thật lớn hơn (sau vài tháng mô phỏng): `bash bench/run.sh` (setup dựng lại từ fact mới nhất).
- **Tiếp theo:** bước 11 — kiểm thử T1–T7 (PLAN 8); bước 12 — Master Blueprint (hạn 17/11).
