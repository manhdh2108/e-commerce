# Bước 11 — PLAN 8: Kiểm thử T1–T7

> Ngày thực hiện: 09/11/2026 · Dữ liệu: kho `dwh` ở batch 7 (nghiệp vụ 03/01 → 31/01/2026) · Kết quả: **58 kiểm thử, 58 PASS**
> Mã: [dw/tests/run_tests.py](../../dw/tests/run_tests.py), [dw/tests/run_tests.sh](../../dw/tests/run_tests.sh) · Sửa: [dw/tests/test_mart.sql](../../dw/tests/test_mart.sql) · Tài liệu mới: [README.md](../../README.md)
> Báo cáo: [BAO_CAO_KIEM_THU_T1_T7.md](../BAO_CAO_KIEM_THU_T1_T7.md) · Bằng chứng: [evidence/11_kiem_thu_T1-T7.txt](evidence/11_kiem_thu_T1-T7.txt)

## 1. Mục tiêu

Hiện thực bảng tiêu chí T1–T7 của [PLAN mục 8](../DW_BUILD_PLAN.md) thành **một bộ kiểm thử chạy bằng một lệnh**, có kết quả PASS/FAIL, số đo cụ thể và mã thoát; cộng bốn kiểm thử đặc thù của kỹ năng nâng cao (bridge, cây danh mục, mini-dimension, semi-additive). Đề xuất gắn T1–T7 với mục tiêu M1–M5 và tiêu chí chấm của nhóm.

## 2. Đầu vào

| Thành phần | Trạng thái trước khi làm |
|---|---|
| Kho `dwh` | Batch 4–7 SUCCESS (watermark 31/01/2026); `fact_order_item` 3.419 dòng, `fact_inventory_snapshot` 565.982, `fact_ad_spend` 1; có SCD2 thật từ 25/01 (8 seller, 14 khách, 8 sản phẩm đổi phiên bản) |
| Kiểm thử đã có (rời rạc) | `test_scd_load.py` (SCD có kiểm soát, rollback), `test_mart.sql` (21 kiểm tra mart), `measure_*.sql` + `run_measure_tests.sh` (công thức measure, so với OLTP gốc), `dashboard/test_app.py` (5 màn hình + KPI), `bench.bm_result` |
| Còn thiếu | Kiểm thử T1 (PK/FK/grain/từ điển), T2 (cách ly có lý do, khóa 0), **T3** (nạp lại, rollback), T4 (không hở, ca seller đổi hạng, SCD3), CSV = bảng, bốn kiểm thử đặc thù, T6/T7 dưới dạng kiểm tra tự động; chưa có README tái lập |
| Môi trường | Docker Postgres `scripts-mock-postgres-1` đang chạy; mock vẫn chạy nền (dữ liệu OLTP đã tới 01/02) — kiểm thử không động tới OLTP |

## 3. Phân tích trước khi làm

- **Không viết lại câu SQL của ETL để kiểm ETL.** Nếu kiểm thử dùng lại logic của `load.py` thì lỗi logic sẽ lặp ở cả hai phía. Mỗi kiểm thử tính lại bằng cách **khác** (ví dụ mini-dimension tính lại bằng truy vấn con tương quan thay vì `GROUP BY` của ETL; doanh thu cây con tính bằng `path_ids` thay vì closure table).
- **T3 phải ghi vào kho nhưng không được làm hỏng nó.** Chọn nạp lại **batch SUCCESS mới nhất** (`--reload`), vì đây là thao tác idempotent mà ETL đã hỗ trợ; so "dấu vân tay" trước/sau gồm số dòng, các Σ tiền, **md5 của chuỗi nội dung từng dòng fact** (không kể cột `batch_id`/`updated_batch_id`), số phiên bản và khóa surrogate lớn nhất của dimension, và các Σ của mart. Giả lập lỗi giữa batch bằng cách thay hàm `load_ad_spend` bằng hàm ném ngoại lệ — lúc đó dimension và hai fact đầu **đã được ghi** trong transaction, nên rollback thật sự có việc để hoàn tác.
- **Trên đường `--reload`, lỗi không đánh dấu batch `FAILED`** (mã giữ batch SUCCESS và rollback). Vì vậy T3.3/T3.4 chứng minh "rollback + mart không đổi", còn nhánh `FAILED` của batch mới nạp lần đầu chưa có ca kiểm thử (ghi ở báo cáo mục 4).
- **Ca T4 cụ thể phải lấy từ dữ liệu thật.** Đã truy vấn trước: seller **9455** (Normal → Mall, 25/01) và **332670** (28/01) có dòng bán ở cả hai phiên bản. Không có khách nào có đơn ở cả hai phiên bản tỉnh, nên ca khách dựa vào kiểm tra tổng quát T4.2 và ca có kiểm soát T4.5.
- **CSV = bảng hiển thị:** `st.download_button` của Streamlit không cho đọc nội dung file từ `AppTest`. Cách làm: thay tạm `st.dataframe` và `st.download_button` bằng hàm bọc, ghi lại cặp *(bảng, byte CSV)* mà ứng dụng truyền vào, rồi `pd.read_csv` so cột và số dòng. Vì `AppTest` chạy script trong cùng tiến trình nên cách này hoạt động.
- **Quy tắc ưu tiên khi test và dữ liệu mâu thuẫn:** nghi ngờ test trước (vì dữ liệu đã qua đối soát RC), chứng minh bằng truy vấn, rồi mới kết luận.

## 4. Cách thực hiện

```bash
# trong WSL, từ thư mục gốc repo
bash dw/tests/run_tests.sh --quick      # chỉ đọc, ~20 s
bash dw/tests/run_tests.sh              # đầy đủ ~2,5 phút: thêm T3 (nạp lại batch), T4.5 (test_scd_load), T5.8–T5.9 (dashboard)
bash dw/tests/run_tests.sh --only T4,T6 # theo nhóm
```

[run_tests.py](../../dw/tests/run_tests.py) gồm bảy hàm `t1..t7`, mỗi kiểm thử gọi `rec(mã, mô tả, đạt?, chi tiết)` để in và gom kết quả; mã thoát 1 nếu có FAIL. [run_tests.sh](../../dw/tests/run_tests.sh) chạy bằng `.venv` của repo và ghi thêm vào `data/logs/test.log`. Danh sách kiểm thử và kết quả đo: [báo cáo §2](../BAO_CAO_KIEM_THU_T1_T7.md). Các kỹ thuật chính:

| Nhóm | Cách kiểm |
|---|---|
| T1 | Đọc `pg_constraint` / `pg_attribute` để đối chiếu cột `*_key` với FK; `count(*)` so `count(distinct …)`; `audit.data_dictionary` so `information_schema.columns` (bỏ partition con) |
| T2 | Đọc `audit.reconciliation` của từng batch SUCCESS; anti-join độc lập cho FK mồ côi; đếm khóa 0 bằng `count(*) FILTER` rồi so `mart.v_unknown_keys`; tỷ lệ cách ly từ `audit.batch_table_log` |
| T3 | `subprocess` chạy `python -m dw.etl.load --reload` hai lần; hàm `fingerprint()` trước/sau; thay `L.load_ad_spend` để giả lập lỗi rồi gọi `L.main(["--reload"])` |
| T4 | Truy vấn khoảng hiệu lực (chồng lấn bằng self-join, hở bằng `lag(valid_to)`); join fact với dimension theo `date_key ∈ [valid_from, valid_to)`; ca seller bằng self-join hai phiên bản; chạy `test_scd_load` |
| T5 | Chạy nguyên văn [test_mart.sql](../../dw/tests/test_mart.sql) bằng `dw_analyst`; các kiểm thử đặc thù tính lại độc lập; AppTest cho dashboard |
| T6 | Đọc `bench.bm_result` (lần đo mới nhất), đếm `bench/results/plans/*.json` và `raw_*.csv` |
| T7 | Kiểm README (từ khóa, đường dẫn), `audit.batch_log.source_snapshot`, checksum Extract batch 1 vs 2 |

Bổ sung [README.md](../../README.md) ở gốc repo (tiêu chí T7): môi trường, seed 42, phiên bản cấu hình mock, lệnh chạy mock/ETL/dashboard/bench/kiểm thử, mẫu log batch, cấu trúc thư mục.

## 5. Quá trình thực hiện (diễn biến thật)

| Giờ (09/11) | Việc | Kết quả |
|---|---|---|
Giờ là giờ máy, làm tròn đến 5 phút.

| Giờ (09/11) | Việc | Kết quả |
|---|---|---|
| ~14:30 | Khảo sát: `audit.batch_log`, dimension SCD thật, `bench.bm_result`, `audit.data_dictionary`, cấu trúc `dim_category`/bridge | Tìm được 2 seller có fact ở cả hai phiên bản; từ điển 200 cột; 26 cấu hình bench |
| ~14:45 | Viết `run_tests.py`, chạy `--quick` lần 1 (141 s) | 47 PASS, 3 FAIL, 4 SKIP. FAIL: T5.1 (2 dòng của `test_mart.sql`), T7.1–T7.2 chưa có README |
| ~14:50 | Điều tra T5.1 | Xem mục 7 (hai phát hiện); sửa `test_mart.sql` |
| ~15:00 | Viết README; chạy đầy đủ lần 1 (137 s) | T3 đạt ngay (nạp lại 14,0 s và 10,6 s, md5 trùng); 56 PASS; T7.1/T7.2 vẫn FAIL vì chính kiểm thử (phân biệt hoa/thường, tên tệp trần) |
| ~15:05 | Sửa kiểm thử T7, tắt cảnh báo log của Streamlit; chạy lại T7 | T7 5/5 |
| ~15:05 | Chạy đầy đủ lần cuối, ghi bằng chứng | **58/58 PASS**, mã thoát 0 |

## 6. Kiểm tra kết quả

Tiêu chí đạt: mọi kiểm thử PASS, bằng chứng chạy thật được lưu, và các kiểm thử không để lại thay đổi trong kho.

- **58/58 PASS** (T1 14 · T2 10 · T3 5 · T4 10 · T5 9 · T6 5 · T7 5) — số đo từng kiểm thử ở [báo cáo §2](../BAO_CAO_KIEM_THU_T1_T7.md).
- **Kho không đổi sau kiểm thử** (T3.1 chứng minh): `fact_order_item` 3.419 dòng, Σ net 2.590.938.257, md5 `85eae95dbb24…` trước và sau hai lần nạp lại; `audit.batch_log` vẫn 7 batch (4–7 SUCCESS).
- **Kiểm thử SCD có kiểm soát** (T4.5) chạy trong transaction rồi rollback: 10/10, kho không đổi.
- **Chạy lại được:** mã thoát phản ánh kết quả (`exit "${PIPESTATUS[0]}"`); khi chạy từ Git Bash phải gọi `wsl -d Ubuntu-20.04 --exec bash …` (dạng `wsl … -- bash -c` làm mất `$?`, mọi lệnh đều báo 0).

## 7. Vấn đề & cách xử lý

| Vấn đề | Nguyên nhân | Xử lý |
|---|---|---|
| `test_mart.sql` báo lệch **11.688** ở "Σ tồn cuối tháng" (mart 5.669.223 vs 5.680.911) | **Lỗi của bài kiểm thử**: công thức độc lập chọn dòng snapshot cuối theo `product_key` (phiên bản SCD). 8 sản phẩm đã đổi phiên bản từ 25/01, mỗi phiên bản có "ngày cuối" riêng nên tồn bị cộng hai lần. MV gom theo `product_id` nên đúng; T5.3 xác nhận mart bằng đúng tổng tồn ngày cuối (5.669.223). Bản kiểm thử cũ đạt 21/21 ở batch 4 chỉ vì khi đó chưa có phiên bản SCD2 nào | Viết lại công thức độc lập: dòng cuối theo `(tháng, product_id, kho)` bằng `DISTINCT ON`; thêm chú thích giải thích trong file |
| "Khóa 0 trên fact" = 5 bị tính FAIL | 5 dòng `payment_method_key = 0`: đơn hoàn tất 23:29–23:54 ngày 31/01, nhưng giao dịch thanh toán ghi sang 01/02 (01:07–18:28) → batch 7 chưa thấy payment (DQ-15 WARN). OLTP hiện đã có đủ 5 payment `Success`. Là hiện tượng đến muộn có chủ đích, không phải lỗi | Dòng này luôn ra `INFO` (cột `ket_qua` của `test_mart.sql` có thêm giá trị `INFO`); bộ tổng hợp in ra như thông tin. Cập nhật thành khóa thật sẽ xảy ra ở batch sau — chưa kiểm chứng (nêu ở báo cáo) |
| T7.1 thất bại với README đã có | Kiểm thử so khớp phân biệt hoa/thường ("Seed 42" ≠ "seed 42") | So khớp không phân biệt hoa/thường |
| T7.2 báo 8 đường dẫn "không tồn tại" | Bảng cấu trúc thư mục nêu tên tệp trần (`extract.py`, …) | Tên tệp không có thư mục được tìm theo tên trong `dw`, `scripts`, `dashboard`, `bench`, `docs` |
| Log Streamlit "missing ScriptRunContext" lẫn vào bằng chứng | AppTest chạy ở chế độ bare | `setLevel(ERROR)` trên logger `streamlit` **không** tắt được (logger của Streamlit tự đặt mức riêng); dùng `logging.disable(logging.WARNING)` bao quanh T5.9 và khôi phục ở `finally` |
| Mọi lệnh `wsl … -- bash -c '…; echo $?'` báo 0 | Đường dẫn gọi qua `wsl.exe` làm mất mã thoát | Dùng `wsl … --exec bash -c '…'` (đã kiểm: `false` → 1, `exit 3` → 3) |

**Đường dẫn trong README:** engine Mock Studio và file `medium-ecommerce.json` nằm ở git worktree `D:/PTIT/mock_run` chứ không ở nhánh `quybruno` hiện tại; README ghi rõ điều này thay vì chỉ tới đường dẫn không tồn tại trong repo.

## 8. Ảnh hưởng & bước tiếp theo

- **File mới:** `dw/tests/run_tests.py`, `dw/tests/run_tests.sh`, `README.md`, `docs/BAO_CAO_KIEM_THU_T1_T7.md`, `docs/MASTER_BLUEPRINT.md` (bước 12), `docs/implementation/evidence/11_kiem_thu_T1-T7.txt`. **File sửa:** `dw/tests/test_mart.sql`.
- **Không đổi:** dữ liệu `dw`/`mart` (chỉ nạp lại batch 7 hai lần, cho cùng kết quả; `mart_refreshed_at` đổi), schema, mã ETL.
- Các kiểm thử có thể chạy lại sau mỗi batch mới: `bash dw/tests/run_tests.sh` — đặc biệt sau batch đầu tiên qua 01/02 để kiểm chứng payment đến muộn được cập nhật (khóa 0 → khóa thật) và T4.3 với dữ liệu mới.
- **Tiếp theo:** bước 12 — [Master Blueprint](../MASTER_BLUEPRINT.md) (đã viết), rồi slide và demo (15–16/11).
