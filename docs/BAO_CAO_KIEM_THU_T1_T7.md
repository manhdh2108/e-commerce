# Báo cáo kiểm thử T1–T7

| | |
|---|---|
| Thực hiện | 09/11/2026 · kho `dwh` ở batch 7 (dữ liệu nghiệp vụ 03/01 → 31/01/2026) |
| Bộ kiểm thử | [dw/tests/run_tests.py](../dw/tests/run_tests.py) — chạy một lệnh: `bash dw/tests/run_tests.sh` (đầy đủ, ~2,5 phút) hoặc `--quick` (chỉ đọc, ~20 giây) |
| Kết quả | **58 kiểm thử: 58 PASS, 0 FAIL** (T1 14 · T2 10 · T3 5 · T4 10 · T5 9 · T6 5 · T7 5) |
| Bằng chứng chạy thật | [implementation/evidence/11_kiem_thu_T1-T7.txt](implementation/evidence/11_kiem_thu_T1-T7.txt) |
| Ghi chép triển khai | [implementation/11_buoc-8_kiem-thu.md](implementation/11_buoc-8_kiem-thu.md) |

Báo cáo này đối chiếu từng tiêu chí T1–T7 của [DW_BUILD_PLAN.md §8](DW_BUILD_PLAN.md) với kiểm thử cụ thể, số liệu đo được và giới hạn. Mọi con số lấy từ lần chạy trên; mã kiểm thử là nguồn sự thật cho điều kiện đạt.

## 1. Cách tổ chức kiểm thử

- Bộ tổng hợp **gom lại** các kiểm thử đã có ở các bước trước và **bổ sung** phần còn thiếu: `test_scd_load.py` (SCD có kiểm soát, chạy trong transaction rồi rollback), `test_mart.sql` (mart = truy vấn độc lập), `dashboard/test_app.py` (5 màn hình, KPI = SQL), kết quả `bench.bm_result` (hiệu năng).
- **Nguyên tắc:** mỗi kiểm thử tự tính lại kết quả bằng truy vấn **độc lập với mã ETL** (không dùng lại câu SQL của `load.py`), rồi so với giá trị trong kho/mart.
- **Chỉ T3 ghi vào kho:** nạp lại batch SUCCESS mới nhất (idempotent, đúng điều T3 cần chứng minh) và giả lập lỗi trong một lần nạp lại rồi rollback. Mọi kiểm thử khác chỉ đọc hoặc rollback.
- Kết quả có ba mức: `PASS`, `FAIL`, `SKIP` (chỉ khi `--quick`); dòng *thông tin* (không phải lỗi) hiển thị `INFO` trong `test_mart.sql`. Mã thoát khác 0 nếu có FAIL.

## 2. Kết quả theo tiêu chí

### T1 — Mô hình (14/14 PASS)

| Mã | Kiểm thử | Kết quả đo |
|---|---|---|
| T1.1 | Mọi fact có khóa chính | `fact_order_item (date_key, source_system, order_id, line_number)`; `fact_inventory_snapshot (date_key, product_key, warehouse_key)`; `fact_ad_spend (month_key, campaign_key, channel_key)` |
| T1.2 | Mọi cột `*_key` của fact có FK tới `dim_*` | 11 / 4 / 3 cột `*_key` đều có FK (gồm hai vai trò `date_key` và `order_date_key` cùng tới `dim_date`) |
| T1.3 | Grain: `count(*) = count(distinct khóa nghiệp vụ)` | `fact_order_item` 3.419 = 3.419; `fact_inventory_snapshot` 565.982 = 565.982 (tính theo `product_id` nghiệp vụ, không theo phiên bản SCD); `fact_ad_spend` 1 = 1 |
| T1.4 | Từ điển phủ 100% cột | **200/200** cột của `dw` (không tính partition con) có mô tả |
| T1.5 | Mọi dimension và bridge có khóa chính | 0 bảng thiếu PK |
| T1.6 | Mọi FK trong `dw` đã validate | 0 FK chưa validate |
| T1.7 | Bridge: Σ `weighting_factor` = 1 từng nhóm; Σ phân bổ = Σ giảm giá của dòng có voucher | 0 nhóm sai; 3.040.000 = 3.040.000 |

### T2 — Dữ liệu (10/10 PASS)

| Mã | Kiểm thử | Kết quả đo |
|---|---|---|
| T2.1 | RC-01..07 (+SCD-01/02) có và đạt ở **mọi** batch SUCCESS | Batch 4, 5, 6, 7: 15/15 kiểm tra đạt mỗi batch |
| T2.2 | Mọi dòng cách ly có `reason`, `rule_code`, `source_table`, `payload` | 224 dòng cách ly, 0 dòng thiếu thông tin |
| T2.3 | 0 FK mồ côi (truy vấn độc lập với RC-06, phủ cả 9 khóa của `fact_order_item`) | 0 dòng |
| T2.4 | Khóa 0 được đếm và hiển thị | Đếm độc lập 5 = `mart.v_unknown_keys` 5; dashboard truy vấn view này |
| T2.5 | Tỷ lệ cách ly mọi bảng, mọi batch SUCCESS ≤ 5% | Cao nhất 0,00% |
| T2.6 | Lỗi chèn có chủ đích bị bắt | Batch 3 (dữ liệu batch 1 + lỗi chèn): 67 dòng cách ly so với 37 của batch 1 |
| T2.7 | RC-07 theo bảng: đọc = hợp lệ + cảnh báo + cách ly + trùng bị loại | 0 dòng log lệch |

### T3 — Cập nhật: idempotent và rollback (5/5 PASS)

| Mã | Kiểm thử | Kết quả đo |
|---|---|---|
| T3.1 | `load --reload` **hai lần**: số dòng, Σ tiền và **băm nội dung từng dòng** của fact không đổi | `fact_order_item` 3.419 dòng, Σ net 2.590.938.257, md5 `85eae95dbb24…` giống nhau trước và sau cả hai lần (14,0 s và 10,6 s); cùng kiểm tra cho tồn kho, quảng cáo, số phiên bản mọi dimension, khóa surrogate lớn nhất và các Σ của mart |
| T3.2 | Sau hai lần nạp lại batch vẫn SUCCESS, đối soát đạt | `SUCCESS`, đạt |
| T3.3 | Giả lập lỗi giữa batch (dimension và fact đã nạp xong, lỗi ở fact cuối) → rollback | Ngoại lệ được bắt; dấu vân tay `dw` trước = sau |
| T3.4 | Cùng ca đó: `mart` không refresh và không đổi, batch giữ SUCCESS | `mart_batch` và `mart_refreshed_at` không đổi; batch vẫn SUCCESS |

### T4 — Lịch sử (10/10 PASS)

| Mã | Kiểm thử | Kết quả đo |
|---|---|---|
| T4.1 | Mỗi dimension SCD2: không chồng lấn, **không hở**, đúng 1 phiên bản hiện hành/khóa | `dim_product` 3.542 phiên bản (8 thêm do SCD2); `dim_seller` 491 (8 thêm); `dim_customer` 10.860 (14 thêm) — 0 vi phạm |
| T4.2 | Mọi dòng fact gắn phiên bản có hiệu lực tại ngày hoàn tất / ngày snapshot | 0 dòng sai ở seller, product, customer (fact bán hàng) và product (fact tồn kho) |
| T4.3 | **Ca cụ thể** seller đã đổi hạng (MGR-01): fact trước ngày đổi gắn phiên bản cũ, từ ngày đổi gắn phiên bản mới | Seller **9455**: Normal (13 dòng, đến 24/01) → Mall từ 25/01 (3 dòng, từ 29/01). Seller **332670**: Normal (33 dòng, đến 26/01) → Mall từ 28/01 (2 dòng, từ 29/01) |
| T4.4 | SCD3 khớp lịch sử SCD2 | `current_tier` đúng với phiên bản hiện hành; `previous_tier` đúng với phiên bản kết thúc đúng ngày đổi hạng — 0 sai |
| T4.5 | Kịch bản có kiểm soát (SCD1 không tăng phiên bản; SCD2 đóng/mở; SCD1+SCD2 trên sản phẩm; SCD3; cùng ngày sửa tại chỗ; đến muộn → DQ-23) | 10/10 PASS, kho không đổi (rollback) |

### T5 — Báo cáo và kiểm thử đặc thù (9/9 PASS)

| Mã | Kiểm thử | Kết quả đo |
|---|---|---|
| T5.1 | Mart = truy vấn độc lập trên fact atomic | 20/20 PASS; 1 dòng thông tin: khóa 0 = 5 |
| T5.2 | Drill-across giữ nhóm một phía, không nhân đôi | 2 nhóm (tháng, kênh): 1 nhóm chỉ có bán hàng (kênh App chưa có chi phí quảng cáo), 0 nhóm chỉ có quảng cáo; Σ doanh thu 2.590.938.257 = fact, Σ chi phí 2.932.996 = fact |
| T5.3 | **Semi-additive**: tồn cuối kỳ = tồn ngày cuối kỳ | Ngày 31/01: 5.669.223 (mart = độc lập); SUM qua các ngày (sai) = 175.754.845 |
| T5.4 | **Non-additive**: AOV tính lại từ tử/mẫu | 864.799,15 (từ tổng) = 864.799,15 (atomic); trung bình các AOV ngày (sai) = 833.167,40 |
| T5.5 | Cây danh mục không chu trình | 0 nút tự làm cha, 0 chu trình |
| T5.6 | Doanh thu cây con qua bridge = tính độc lập theo `path_ids`; Σ các nút gốc = tổng | 77 nút, 0 lệch; Σ nút gốc 2.590.938.257 = tổng fact (không cộng lặp) |
| T5.7 | **Mini-dimension** tính theo trạng thái **trước** giao dịch (tính lại độc lập từng dòng) | 1.513 dòng khách có tài khoản, 0 lệch; 1.320/1.320 dòng của ngày mua đầu tiên ở bucket "Chưa mua / 0 đơn" |
| T5.8 | Dashboard: 5 màn hình không lỗi, KPI và bộ lọc = SQL độc lập | 9 kiểm tra PASS |
| T5.9 | **File CSV = bảng hiển thị** (chặn `st.dataframe` và `st.download_button`, so từng cặp) | 24/24 nút xuất CSV khớp cột và số dòng của bảng đang hiển thị |

### T6 — Hiệu năng (5/5 PASS)

| Mã | Kiểm thử | Kết quả đo |
|---|---|---|
| T6.1 | Đủ BM01, BM02, BM03 | 26 cấu hình đo, lần đo `20261108_123944` |
| T6.2 | Kết quả mọi biến thể trùng hash với baseline | 26/26 |
| T6.3 | Có plan EXPLAIN JSON, lượt đo thô, kích thước đối tượng | 26 plan JSON, 390 lượt đo thô, 12 đối tượng có kích thước |
| T6.4 | p95 ≤ 3 s ở ~2 triệu dòng, ở phương án tối ưu của **mọi** truy vấn | p95 tốt nhất theo truy vấn: Q1a 2,8 ms · Q1b 2,3 · Q1c 3,2 · Q2a 187 · Q2b 14,9 · Q2c 121 · Q2d 801 · Q3a 1,9 · Q3b 12,8 · Q3c 48,7 (ms). Baseline vượt 3 s chỉ có Q1a (6.949 ms) và được MV xử lý |
| T6.5 | Quy mô ≥ 2 triệu dòng | `bench.foi_noidx` = 2.007.600 dòng |

### T7 — Tái lập (5/5 PASS)

| Mã | Kiểm thử | Kết quả đo |
|---|---|---|
| T7.1 | [README.md](../README.md) nêu seed 42, phiên bản cấu hình mock, settings, lệnh chạy mock, lệnh ETL, lệnh kiểm thử, log batch | Đủ 11 mục |
| T7.2 | Mọi đường dẫn tệp nêu trong README đều tồn tại | 12 đường dẫn |
| T7.3 | Mỗi batch SUCCESS ghi mốc nguồn | `mock last_day` = 12/01, 25/01, 29/01, 31/01 cho batch 4–7 |
| T7.4 | Tái lập Extract: nạp lại cùng mốc cho checksum trùng | 19/19 bảng (batch 1 và batch 2) |
| T7.5 | Có ghi chép triển khai từng bước và bằng chứng chạy thật | Ghi chép trong `docs/implementation/` (kèm các tệp bằng chứng) |

## 3. Vấn đề phát hiện khi kiểm thử

| # | Phát hiện | Bản chất | Xử lý |
|---|---|---|---|
| 1 | Kiểm tra mart "Σ tồn cuối tháng" lệch **11.688** (mart 5.669.223, công thức độc lập 5.680.911) | **Lỗi của bài kiểm thử**, không phải của kho. Công thức độc lập cũ chọn "dòng snapshot cuối" theo `product_key` (phiên bản SCD). Từ 25/01 có 8 sản phẩm đổi phiên bản, mỗi phiên bản có "ngày cuối" riêng nên bị cộng hai lần. MV gom theo `product_id` nên đúng với semi-additive; T5.3 xác nhận 5.669.223 đúng bằng tổng tồn ngày cuối | Sửa công thức độc lập trong [test_mart.sql](../dw/tests/test_mart.sql) để lấy dòng cuối theo `(tháng, product_id, kho)` bằng `DISTINCT ON` |
| 2 | Dòng "Khóa 0 trên fact" = 5 bị tính là FAIL | 5 dòng `payment_method_key = 0` của đơn hoàn tất 23:2x–23:5x ngày 31/01, còn giao dịch thanh toán ghi sang 01/02 (payment đến muộn; cảnh báo DQ-15). Không phải lỗi | Đánh dấu dòng này là **INFO** trong `test_mart.sql` và trong bộ tổng hợp; fact sẽ được cập nhật ở batch sau theo thiết kế late-arriving |
| 3 | T7 lần chạy đầu thất bại hai kiểm tra | Do README chưa tồn tại lúc đó và kiểm thử phân biệt hoa/thường, không tìm tên tệp trần | Viết README; sửa kiểm thử cho phù hợp |

Phát hiện 1 là ví dụ cho giá trị của dữ liệu SCD thật: bản kiểm thử cũ đạt 21/21 ở batch 4 (khi chưa có phiên bản SCD2 nào) và chỉ lộ lỗi khi dữ liệu có đổi phiên bản.

## 4. Giới hạn của bộ kiểm thử

- **Khối lượng nhỏ:** kho mới có 3.419 dòng bán hàng và 1 dòng quảng cáo tháng; kết quả đúng nhưng chưa thử sức ở quy mô cả năm. Bench dùng dữ liệu nhân bản (ghi rõ) cho phần hiệu năng; việc đo lại trên dữ liệu thật lớn hơn nằm trong kế hoạch.
- **T4.3 chỉ có seller:** chưa có khách nào có đơn ở cả hai phiên bản tỉnh (mọi khách đã đổi tỉnh đều chưa mua ở một trong hai phiên bản). Khách, sản phẩm được phủ bởi T4.2 (kiểm tra tổng quát trên mọi dòng) và T4.5 (ca có kiểm soát).
- **Chưa kiểm chứng cập nhật payment đến muộn** (khóa 0 → khóa thật) vì cần chạy thêm một batch; mã đã có, sẽ kiểm khi nạp batch tiếp theo.
- **Đường lỗi `FAILED` của batch chưa nạp lần đầu:** T3.3/T3.4 chạy trên đường `--reload` (lỗi → rollback, batch SUCCESS giữ nguyên). Nhánh đánh dấu `FAILED` khi nạp batch mới lỗi có trong mã nhưng chưa có ca kiểm thử riêng.
- **Không kiểm thử đồng thời:** chưa chạy hai batch song song hay nạp trong lúc dashboard đang refresh nhiều người dùng.
- **T6.4 đo trên dữ liệu nhân bản**, trên một máy ở trạng thái ấm; "p95 ≤ 3 s" là điều kiện đạt ở phương án tối ưu, không phải với mọi cách viết truy vấn (baseline Q1a vượt ngưỡng và đó chính là lý do dùng MV).

## 5. Kết luận

Kho đáp ứng cả bảy tiêu chí T1–T7 ở quy mô dữ liệu hiện có: mô hình đúng grain và ràng buộc (T1); đối soát, cách ly và khóa đặc biệt đúng (T2); nạp lại không làm đổi dữ liệu và lỗi giữa batch không để lại dấu vết (T3); lịch sử SCD đúng cả ở mức tổng quát và ở ca thật của seller đổi hạng (T4); mart, KPI, drill-across, cây danh mục, mini-dimension và CSV khớp truy vấn độc lập (T5); thí nghiệm hiệu năng có kết quả tương đương, plan và số đo thô (T6); và một người khác có thể tái lập từ README (T7). Các giới hạn ở mục 4 là việc cần làm khi dữ liệu mô phỏng tiến xa hơn.
