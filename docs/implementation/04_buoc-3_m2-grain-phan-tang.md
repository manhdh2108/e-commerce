# 04 — PLAN 3 (Milestone 2): Mức hạt và tháp phân tầng

| | |
|---|---|
| Ngày thực hiện | 07/11/2026, 22:30–22:45 |
| Trạng thái | ✅ Xong |
| Liên quan PLAN | Mục 3.1, 3.2 |
| Liên quan lộ trình | Milestone 2 (Sub 2.1, 2.2), Inmon chương 3, Kimball – grain |
| Sản phẩm | [M2_GRAIN_PHAN_TANG.md](../data-model/warehouse/M2_GRAIN_PHAN_TANG.md) |

## 1. Mục tiêu

Chốt grain atomic của 3 fact, có giải thích lý do (Sub 2.1), và thiết kế tháp phân tầng từ atomic lên các tầng tổng hợp ngày/tháng/quý (Sub 2.2). Các quyết định phải được kiểm chứng trên dữ liệu thật: khóa grain có duy nhất không, dữ liệu dày hay thưa, có dữ liệu đến muộn không, kích thước từng tầng.

## 2. Đầu vào

- Quyết định nháp ở PLAN 3.1 (đã chốt `Date_Key` = ngày hoàn tất, `gross_amount`, phí ship, dòng `Returned`).
- Nguồn `mock_oltp` 01/01–12/01/2026, đọc bằng `dw_reader`.
- Kết quả M1 (bước 03).

## 3. Phân tích trước khi làm

Có 5 câu hỏi cần dữ liệu trả lời trước khi chốt grain:
1. Khóa grain của mỗi fact có thật sự duy nhất trong nguồn?
2. Một đơn có thể có nhiều seller hoặc nhiều kênh không? Nếu có, gắn `seller_key` vào dòng hàng sẽ sai grain.
3. Đơn hoàn tất sau bao lâu? Câu trả lời quyết định cách nạp incremental khi `Date_Key` là ngày hoàn tất.
4. Snapshot tồn kho là dày (mọi cặp kho–SKU mỗi ngày) hay thưa?
5. Mỗi tầng tổng hợp lớn cỡ nào? Cần biết để chọn bảng cho thí nghiệm MV và partition.

## 4. Cách thực hiện

1. Viết [dw/sql/05_profiling/m2_grain_check.sql](../../dw/sql/05_profiling/m2_grain_check.sql) với 8 nhóm kiểm tra:
   - G1: tính duy nhất của `(order_id, line_number)`;
   - G2: ma trận trạng thái đơn × trạng thái dòng;
   - G3: số seller và kênh mỗi đơn, số checkout bị tách thành nhiều đơn;
   - G4: phân bố số dòng mỗi đơn;
   - G5: phân bố độ trễ từ lúc đặt tới lúc hoàn tất;
   - G6: tính duy nhất và độ dày của tồn kho;
   - G7: tính duy nhất của chi phí QC theo ngày;
   - G8: số nhóm của các tầng tổng hợp dự kiến.
2. Chạy bằng `dw_reader`, lưu output vào [evidence/04_m2_grain_check.txt](evidence/04_m2_grain_check.txt).
3. Ngoại suy khối lượng cả năm từ 12 ngày đã có. Chỉ dùng ngày thường; ngày 01/01 là ngày lễ.
4. Viết sản phẩm M2: câu grain, điều kiện đưa vào/loại ra, ngày của fact, quyết định thưa/dày, tháp 5 tầng kèm kích thước, quy tắc tổng hợp, lựa chọn tầng cho BM01–03.

## 5. Quá trình thực hiện (kết quả thật)

| Kiểm tra | Kết quả | Quyết định rút ra |
|---|---|---|
| G1 | 1.687 dòng, 1.687 khóa, **0 trùng** | Khóa nghiệp vụ `(source_system, order_id, line_number)` dùng được cho upsert / idempotent |
| G2 | `Completed/Fulfilled` 1.195 (đều có `completed_at`); `Cancelled` 78; `Pending`/`Processing` 414; **chưa có `Returned`** | Lọc theo cả hai trạng thái; xử lý `Returned` là thay đổi đến muộn của dòng đã có trong fact |
| G3 | 1.467/1.467 đơn có đúng 1 seller và 1 kênh; **149 checkout tách thành nhiều đơn** | Gắn seller/kênh vào dòng hàng là hợp lệ |
| G4 | 1 dòng: 1.276 đơn; 2 dòng: 167; 3 dòng: 19; 4 dòng: 5 | Lưu cấp dòng (11,6% đơn có nhiều dòng) |
| G5 | Trễ 2 ngày: 83; 3: 649; 4: 266; 5: 37; 6: 2 | Batch ngày D phải nạp đơn đặt từ D−6 hoàn tất trong ngày D |
| G6 | 219.067 dòng, 0 trùng; 12 ngày; **18.257/21.192 cặp** kho–SKU | Snapshot **thưa**; không sinh dòng 0 giả |
| G7 | 8 dòng, 0 trùng; gộp tháng còn 1 | Giữ ngày ở `stg`, fact ở tháng |
| G8 | ngày×sản phẩm×kênh: 1.021; ngày×danh mục lá×kênh: 404; ngày×seller: 607; tồn ngày×danh mục×kho: 3.168 | Tầng 2 cho bán hàng gần bằng atomic (ít lợi ích); tầng 2 cho tồn kho giảm ~70 lần → nên dùng cho thí nghiệm MV trên dữ liệu thật |

Ngoại suy khối lượng một năm: Fact 1 ~40.000 dòng; Fact 2 ~6,7 triệu; Fact 3 ~60 (từ 30/01).

## 6. Kiểm tra kết quả

| Tiêu chí Milestone 2 | Đạt |
|---|---|
| 2.1: Định nghĩa grain atomic cho từng fact, có giải thích lý do | ✅ 3 câu grain, khóa đã kiểm chứng duy nhất, lý do lấy từ số đo (G4, G6, G7) |
| 2.1: Grain khớp đề xuất Bảng 6 | ✅ Giữ nguyên cả 3. Bổ sung: ngày của fact, quyết định thưa, atomic ngày của QC ở `stg` |
| 2.2: Tháp phân tầng Atomic → Summary phục vụ các cấp quản lý | ✅ 5 tầng (0–4), mỗi đối tượng có grain, nguồn, cách làm mới, kích thước và người dùng |
| Quy tắc tổng hợp đúng loại measure | ✅ additive / semi-additive / non-additive / đếm phân biệt / theo cây |

## 7. Vấn đề & cách xử lý

| Vấn đề | Xử lý |
|---|---|
| Fact 1 quá nhỏ (~40.000 dòng/năm), MV khó thấy hiệu quả | Thí nghiệm dùng bản nhân `bench` x50 (PLAN 7.1); thêm thí nghiệm MV tồn kho trên dữ liệu thật |
| Grain tháng của Fact_Ad_Spend thô hơn nguồn (ngày) | Giữ atomic ngày ở `stg.ad_spend_daily`; fact tháng theo đúng đề xuất; ghi rõ là tổng hợp có chủ đích |
| Chưa có dòng `Returned` để kiểm thử | Thiết kế upsert cập nhật `is_returned`; kiểm thử khi engine sinh hàng trả (đã có 6 yêu cầu `Approved`) |
| Ngày 01/01 là ngày lễ (296 đơn) | Không dùng để ngoại suy khối lượng |

## 8. Ảnh hưởng & bước tiếp theo

- Mới: `dw/sql/05_profiling/m2_grain_check.sql`, `docs/implementation/evidence/04_m2_grain_check.txt`, `docs/data-model/warehouse/M2_GRAIN_PHAN_TANG.md`.
- PLAN mục 3 được đánh dấu đã làm, kèm link.
- Bước tiếp theo: **05 — PLAN 4 (Milestone 3)**: viết DDL cho dimension, fact và bridge (`dw/sql/30_dw`), sinh `dim_date`, dựng cây danh mục, từ điển dữ liệu, sơ đồ Galaxy schema.
