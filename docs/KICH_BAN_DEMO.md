# Kịch bản demo trực tiếp (khoảng 26 phút)

Số liệu đo trên `dwh` ngày 09/11/2026 (batch 7, dữ liệu đến 31/01/2026). Xưng hô thống nhất là "Thầy/Cô". Riêng số đo thời gian: luôn đọc số trên màn hình, không đọc số thuộc lòng.

| # | Phần | Nội dung | Phút |
|---|---|---|---|
| 0 | Mở đầu | Dashboard Tổng quan, sơ đồ kiến trúc | 1,5 |
| 1 | Tích hợp và ETL | Nhật ký batch, IR-03, từ điển dữ liệu, đối soát | 3 |
| 2 | Mô hình, OLAP và SCD | Galaxy schema, roll-up, drill-down, slice, dice (đề cương mục 4.2), SCD2, SCD3, bridge, semi-additive, drill-across | 7,5 |
| 3 | Chất lượng dữ liệu | Cơ chế cách ly lỗi | 2 |
| 4 | Tốc độ | Summary (MV) so với Atomic (fact), index, partition | 6 |
| 5 | Nhất quán | Fact và Dimension, view 21 kiểm tra | 4 |
| 6 | Kiểm thử và kết luận | T1–T7, giới hạn, vòng xoắn ốc | 2,5 |

Nếu thiếu thời gian: bỏ phần 3, rút phần 4 còn một so sánh (tab `[P2b]`), rồi trong phần OLAP chỉ chạy roll-up và drill-down (bỏ slice, dice, còn khoảng 1 phút).

---

## Chuẩn bị (xong trước giờ demo 15 phút)

1. **Dừng mock** để số đo không bị nhiễu (chạy lại sau demo bằng `start_all.sh`):
   `wsl -d Ubuntu-20.04 -- bash /mnt/d/PTIT/mock_run/scripts/mock_runner/stop_all.sh`
2. **Không nạp batch mới trước demo**, vì hầu hết số trong kịch bản sẽ đổi.
3. **Mở dashboard trước:** `wsl -d Ubuntu-20.04 -- bash "/mnt/d/PTIT/KÌ 1 năm 4/DATA WAREHOUSE/e-commerce/dashboard/run.sh"`, rồi mở http://localhost:8501. Lần mở đầu mất khoảng 38 giây, sau đó chuyển màn hình chỉ 0,5–2 giây. Bấm qua màn hình "3 bảng Fact và kỹ thuật (SCD, bridge)" một lần để nạp sẵn, rồi quay lại "Tổng quan".
4. **DBeaver:** host `127.0.0.1`, cổng `55432`, database `dwh`, user `dw_analyst`, mật khẩu `dw_analyst_local` (chỉ đọc). Mở các file trong [dw/demo_sql/](../dw/demo_sql/) thành tab. Con trỏ đặt vào câu lệnh rồi nhấn `Ctrl + Enter`.

   | Tab | File | Phần |
   |---|---|---|
   | `[P1a]` | `P1a_batch_log.sql` | 1 |
   | `[P1b]` | `P1b_tich_hop_ma_kenh.sql` | 1 |
   | `[P1c]` | `P1c_tu_dien_du_lieu.sql` | 1 |
   | `[P3]` | `P3_olap.sql` | 2 |
   | `[P4]` | `P4_cach_ly.sql` | 3 |
   | `[P2a]` | `P2a_gioi_thieu_mv.sql` | 4 |
   | `[P2b]` | `P2b_drill_across.sql` | 4 |
   | `[P2c]` | `P2c_index.sql` | 4 |
   | `[P2d]` | `P2d_partition.sql` | 4 |
   | `[P2e]` | `P2e_summary_vs_atomic_bo_sung.sql` | 4 (tuỳ chọn, khi được hỏi thêm) |
   | `[P5]` | `P5_consistency_check.sql` | 5 |

   Dự phòng nếu DBeaver lỗi: `docker exec -it scripts-mock-postgres-1 psql -U dw_analyst -d dwh`, gõ `\pset pager off` (lệnh này chỉ dùng trong `psql`), rồi dán từng câu từ file.
5. **Chạy thử mỗi tab một lần** để làm nóng cache. Nhớ chạy hai lệnh `RESET` cuối tab `[P2c]`. Thử xem lệnh `SET` ở tab này có chỉ áp dụng cho tab đó không; nếu không chắc, luôn `RESET` xong mới sang tab khác.
6. **Mở sẵn:** `docs/images/etl_architecture.png`; `docs/MASTER_BLUEPRINT.html` ở mục 5 (Galaxy schema, Bus matrix); file bằng chứng `docs/implementation/evidence/11_kiem_thu_T1-T7.txt`.
7. **Chạy lại bộ kiểm thử đầy đủ một lần** để file bằng chứng phản ánh dashboard mới (khoảng 3 phút, có nạp lại batch mới nhất, số liệu không đổi):
   `bash dw/tests/run_tests.sh | tee docs/implementation/evidence/11_kiem_thu_T1-T7.txt` (chạy trong WSL). Kết quả phải đọc lại trước khi nói "58/58".
8. **Quay video dự phòng 30–45 giây** cảnh dashboard mới, lưu ở màn hình nền.
9. **Không làm trong lúc demo:** `UPDATE` để thử view, `inject_test_errors`, `bench clean`.

---

## Phần 0. Mở đầu (1,5 phút)

**Thao tác:** dashboard, chế độ "Thống kê", màn hình "Tổng quan", chọn "7 ngày gần nhất".

**Lời thoại:** "Thưa Thầy/Cô, đây là giao diện thống kê của kho dữ liệu sàn thương mại điện tử nhiều người bán. Bảy ngày gần nhất doanh thu 521,6 triệu, giảm 21,7% so với kỳ trước, từ 745 đơn. Dashboard có 9 màn hình, chia hai chế độ: Thống kê cho người dùng nghiệp vụ, Kỹ thuật để kiểm tra kho."

**Thao tác:** chuyển sang `etl_architecture.png`.

**Lời thoại:** "Dữ liệu sản phẩm là thật, crawl từ Tiki; đơn hàng, tồn kho, quảng cáo là mô phỏng với 33 bảng OLTP. Nhóm tách kho khỏi OLTP vì OLTP chỉ giữ trạng thái hiện tại nên mất lịch sử, các hệ thống dùng mã khác nhau, và truy vấn phân tích tranh tài nguyên với giao dịch. Dữ liệu đi qua bốn lớp: `raw` chỉ ghi thêm, `stg` làm sạch, `dw` là lõi chiều, `mart` là tầng tổng hợp."

---

## Phần 1. Tích hợp và ETL (3 phút)

**Tab `[P1a]`.** Kỳ vọng: batch 4–7 đều `SUCCESS`, mốc dữ liệu nối tiếp nhau đến 31/01; câu thứ hai ra 15 dòng, `passed` đều `t`.

**Lời thoại:** "Mỗi lần nạp là một batch. Cuối batch, ETL tự đối soát 15 điều kiện, ví dụ tổng tiền ở `stg` bằng tổng ở fact, số dòng đọc bằng số ghi cộng cách ly. Một điều kiện sai thì cả batch rollback."

**Tab `[P1b]`.** Kỳ vọng: `WEB → Web`, `APP → App`, `LIVESTREAM → Livestream`; Web có doanh thu 2,07 tỷ và chi phí quảng cáo 2,9 triệu; App có 519,9 triệu, chưa có quảng cáo.

**Lời thoại:** "Đây là quy tắc tích hợp IR-03: marketing gọi kênh là `WEB`, hệ đơn hàng gọi là `Web`. Kho chuẩn hóa về một khóa kênh, nên hai fact từ hai hệ nguồn nối được với nhau. Nhóm có 10 quy tắc như vậy, ví dụ kho dùng `sku` còn đơn hàng dùng `product_id`."

**Tab `[P1c]`.** Kỳ vọng: 200 cột có mô tả.

**Lời thoại:** "Đây là từ điển dữ liệu: mỗi cột có kiểu, mô tả và tính cộng được, phủ 200 cột của kho."

---

## Phần 2. Mô hình và SCD (5 phút)

**Thao tác:** `MASTER_BLUEPRINT.html`, mục 5 (Galaxy schema và Bus matrix). *(45 giây)*

**Lời thoại:** "Mô hình là Galaxy schema: 3 bảng fact dùng chung các dimension, tổng cộng 14 dimension và 2 bridge. Bus matrix cho thấy fact nào dùng dimension nào. Mọi cột khóa của fact đều có khóa ngoại, đã kiểm thử ở T1.2."

**Tab `[P3]`: các phép OLAP trên Fact_Order_Item** *(2 phút; đề cương mục 4.2)*. Mọi câu đọc fact atomic nối dimension, mỗi câu chạy 6–89 ms. Chạy lần lượt, đặt con trỏ vào câu rồi `Ctrl + Enter`.

| Phép | Câu chạy | Kỳ vọng (đọc số trên màn hình) |
|---|---|---|
| **Roll-up** | Câu 1: `ROLLUP(tháng, tuần)` | 5 dòng tuần, dòng tháng và dòng TỔNG CỘNG cùng 2.590.938.257 đ; AOV mỗi cấp 725.040 đến 1.038.571, tổng 864.799 |
| **Roll-up** | Câu 1 (phần danh mục): lên danh mục gốc | Điện Thoại - Máy Tính Bảng 1.437.851.000 (55,5%), Làm Đẹp - Sức Khỏe 375.178.713, Thời trang nữ 365.579.269, Bách Hóa Online 325.230.921, Chăm sóc nhà cửa 87.098.354 |
| **Drill-down** | 2a: gốc "Làm Đẹp - Sức Khỏe" xuống cấp 2 | 3 nút: 208.517.163, 106.464.750, 60.196.800; `tong_cac_con` = 375.178.713 = số của gốc |
| **Drill-down** | 2b: xuống cấp 3 của "Danh mục 1582" | 1 dòng "Sữa rửa mặt" 208.517.163, 640 món, bằng đúng nút cha |
| **Drill-down** | 2c: tuần 4 xuống ngày | 7 ngày, tổng 674.212.704; ngày cao nhất 20/01 (176.651.347) |
| **Slice** | Cố định `kênh = App` | Các tuần cộng lại 519.946.374 |
| **Dice** | Kênh App, hạng seller lúc bán Mall hoặc Preferred, 12–25/01 | 7 dòng; đầu bảng "Làm Đẹp - Sức Khỏe, Preferred, 39 dòng, 13.253.400" |

**Lời thoại:** "Thưa Thầy/Cô, đây là bốn phép OLAP cơ bản trên bảng fact bán hàng. Roll-up là gộp lên cấp cao hơn: một câu `ROLLUP` cho doanh thu từng tuần, tổng tháng và tổng cộng 2,59 tỷ. Chú ý AOV được tính lại ở mỗi cấp chứ không cộng AOV của các tuần, vì AOV là chỉ số non-additive. Ở cấp danh mục, điện thoại chiếm hơn một nửa doanh thu. Drill-down là khoan ngược lại: từ danh mục gốc Làm Đẹp 375 triệu xuống ba nút cấp 2, cộng các nút con đúng bằng số của nút cha, rồi xuống cấp 3. Fact chỉ gắn vào danh mục lá nên câu này đi qua bảng bridge. Slice cố định một chiều, ở đây là kênh App. Dice lọc đồng thời nhiều chiều: kênh, hạng seller và khoảng ngày; hạng seller lấy từ SCD2 nên là hạng đúng tại ngày bán."

Lưu ý khi nói: tên "Danh mục 1582" là tên tạm của nút trung gian chưa có tên trong dữ liệu nguồn (hạn chế đã ghi ở Blueprint mục 10).

**Thao tác tiếp (30–45 giây):** dashboard, chế độ **Thống kê**, màn hình **Bán hàng chi tiết**: đổi "Mức thời gian" Năm, Quý, Tháng, Ngày (roll-up và drill-down theo thời gian), chọn "Danh mục gốc" rồi "Danh mục con" ở thanh bên (drill-down theo danh mục), chọn một "Kênh" (slice), thêm "Hạng seller" và khoảng ngày (dice), cuối cùng bấm một nút xuất CSV. **Lời thoại:** "Cùng các phép đó, người dùng nghiệp vụ làm trực tiếp trên dashboard mà không cần viết SQL."

**Thao tác:** dashboard, chuyển "Chế độ xem" sang **Kỹ thuật kho dữ liệu**, màn hình **3 bảng Fact và kỹ thuật (SCD, bridge)**.

**Tab `Fact_Order_Item`** *(2,5 phút, cuộn xuống phần B)*
- **SCD2 khách (khách 7944):** "Khách này mua ngày 08/01 lúc còn ở Hà Nội, 270.000 đồng, rồi chuyển vào TP. Hồ Chí Minh ngày 29/01. Nếu ghi đè như OLTP, số tiền bị tính cho TP. Hồ Chí Minh; với SCD2 vẫn thuộc Hà Nội."
- **SCD2 và SCD3 seller (332670):** "Seller lên hạng Mall ngày 28/01. 33 dòng trước đó, 20,4 triệu, thuộc hạng Normal; 2 dòng sau, 1,2 triệu, thuộc hạng Mall. Bảng SCD3 giữ hạng hiện tại và hạng liền trước."
- **Bridge danh mục ("Bách Hóa Online"):** "Fact chỉ gắn vào danh mục lá. Lọc đúng danh mục cha cho kết quả 0. Nối qua bridge cho 325,2 triệu, và tổng các con khớp, không cộng lặp."

**Tab `Fact_Inventory_Snapshot`** *(1 phút)*
- "Tồn kho là semi-additive: cộng qua 31 ngày ra 175 triệu món, gấp 31 lần tồn thật 5.669.223 món."
- "Đối soát dòng chảy: tồn đầu cộng nhập, trả, điều chỉnh, trừ bán, đúng bằng tồn cuối."

**Tab `Fact_Ad_Spend`** *(45 giây)*
- "Drill-across hai fact khác mức hạt qua dimension dùng chung. Kênh App có 519,9 triệu doanh thu nhưng chưa chạy quảng cáo; `INNER JOIN` sẽ làm mất 20,1% doanh thu, nên nhóm dùng `FULL OUTER JOIN`."

---

## Phần 3. Chất lượng dữ liệu (2 phút, tab `[P4]`)

Kỳ vọng: DQ-02 (5), DQ-03 (8), DQ-04 (7), DQ-05 (2) mức ERROR; DQ-07 (5), DQ-08 (3), DQ-12 (28), DQ-15 (9) mức WARN; tổng 67.

**Lời thoại:** "Dữ liệu mô phỏng quá sạch nên nhóm tạo một batch thử có lỗi cài sẵn: số lượng âm, tiền lệch 1.000 đồng, kênh `TIKTOK` không tồn tại, đơn thiếu ngày hoàn tất. Mức ERROR có 22 lượt ghi nhận, ứng với 17 dòng bị loại, vì có dòng vi phạm hai quy tắc. Mức WARN vẫn được giữ lại nhưng có ghi vết. Mỗi dòng lưu mã quy tắc, lý do và nội dung gốc, không xóa âm thầm. Ngoài ra, ETL có ngưỡng 5%: batch này có bảng quảng cáo bị cách ly 50% nên lần chạy với ngưỡng mặc định bị chặn; nhóm phải nới ngưỡng để xem chi tiết. Đây là batch thử nên không nạp vào kho."

---

## Phần 4. Tốc độ: Summary so với Atomic, index, partition (6 phút)

Chỉ dùng bảng thật. Chạy mỗi câu hai lần, đọc dòng `Execution Time` của lần hai.

**Tab `[P2a]`.** Kỳ vọng: 8 MV, cùng refresh ở batch 7.

**Lời thoại:** "Fact là tầng Atomic. Tầng Summary gồm 8 materialized view, mỗi cái là một câu `GROUP BY` được lưu sẵn kết quả. ETL tự làm mới cả 8 sau mỗi batch thành công."

**Tab `[P2b]`: ghép hai fact.** Lần đo gần nhất (mock đang chạy): khoảng 450 ms so với 18–33 ms, nhanh khoảng 13–25 lần. Hai câu không có `EXPLAIN` đều ra `3532 | 2590938257.00 | 4273`.

**Lời thoại:** "Cùng câu hỏi, cùng kết quả. Cách Atomic phải quét 566 nghìn dòng tồn kho mỗi lần hỏi, cách Summary đọc kết quả đã gom sẵn. Cái giá là MV chỉ cập nhật khi ETL chạy xong một batch."

**Tab `[P2c]`: index `product_key` trên fact tồn kho.** Lần đo gần nhất: khoảng 3–5 ms (Bitmap Index Scan) so với 44–46 ms (Parallel Seq Scan), nhanh khoảng 10–15 lần. **Chạy hai lệnh `RESET` ở cuối.**

**Lời thoại:** "Kho mới có khoảng một tháng dữ liệu nên số tuyệt đối còn là mili giây. Thí nghiệm riêng ở báo cáo bước 10, trên dữ liệu nhân bản 2 triệu dòng, cho MV nhanh gấp 2.481 lần và index ghép `(seller_key, date_key)` nhanh gấp 189 lần. Khoảng cách lớn hơn vì chi phí Atomic tăng theo số dòng, còn Summary chỉ phụ thuộc số nhóm."

**Tab `[P2d]`: partition theo tháng trên fact tồn kho** *(1 phút)*. Chạy bốn câu đầu của tab (phần "TUỲ CHỌN" ở dưới chỉ dùng khi được hỏi quy mô lớn). Kỳ vọng: câu 1 chỉ có `fact_inventory_snapshot_202601` chứa dữ liệu (565.982 dòng); câu 2 ra 37 partition cho mỗi fact (36 tháng và 1 partition default); câu 3 (có `date_key`) trong kế hoạch chỉ có đúng một partition `_202601`; câu 4 (không lọc ngày) liệt kê cả chuỗi partition, phần lớn `actual rows=0`. Lần đo trước: khoảng 9–10 ms so với 85–106 ms; đọc số trên màn hình.

**Lời thoại:** "Hai fact lớn được phân vùng theo tháng. Khi câu hỏi có điều kiện ngày, PostgreSQL chỉ mở đúng partition của tháng đó và bỏ qua các tháng còn lại, đó là partition pruning. Khi không có điều kiện ngày thì phải duyệt tất cả. Dữ liệu thật mới có một tháng nên chênh lệch thời gian còn nhỏ; điều Thầy/Cô thấy ở đây là kế hoạch thực thi. Báo cáo bước 10 có số đo trên bảng nhân bản: lọc theo tháng và không có index thì partition nhanh gấp 2,96 lần, nhưng quét cả năm thì partition chậm hơn (×0,84), nhóm ghi nhận trung thực cả hai trường hợp."

Nếu được hỏi thêm cặp Summary so với Atomic khác (tồn kho theo tháng × kho, hoặc SCD hạng seller), dùng tab `[P2e]`; mỗi cặp có câu chứng minh hai cách ra cùng kết quả.

---

## Phần 5. Tính nhất quán (4 phút, tab `[P5]`)

Câu đầu đọc view `mart.v_consistency_check`, mất khoảng 1–2 giây; câu hai tóm tắt `PASS | 21`; câu ba là ca seller cụ thể.

| Nhóm | Nói gì | Dòng |
|---|---|---|
| A. Khóa ngoại | 0 khóa ngoại mồ côi ở fact bán hàng và tồn kho | 2 |
| B. Mức hạt | Số dòng fact bằng số grain duy nhất, cả 3 fact | 3 |
| C. SCD2 | Khoảng hiệu lực không chồng, không hở, đúng một phiên bản hiện hành | 3 |
| D. Đúng phiên bản | Fact trỏ đúng phiên bản seller, khách, sản phẩm tại ngày giao dịch | 3 |
| E. Tiền giữa các tầng | Doanh thu ở fact bằng 4 MV (2.590.938.257 đồng); chi phí quảng cáo ở fact bằng MV | 5 |
| F. Đẳng thức tiền | gross − giảm giá = net; net − hoa hồng = phần seller nhận; không số âm; Σ trọng số bridge = 1 | 4 |
| G. Đối soát ETL | Batch mới nhất không có đối soát nào sai | 1 |

Ca cụ thể: seller 9455 có 13 dòng (3.108.000 đ) ở Normal và 3 dòng (511.000 đ) ở Mall; seller 332670 có 33 dòng (20.425.209 đ) ở Normal và 2 dòng (1.224.000 đ) ở Mall.

**Lời thoại:** "Đây là một view gom 21 kiểm tra, mỗi dòng là PASS hoặc FAIL. Các kiểm tra tính độc lập với mã ETL, nên ETL sai thì kiểm tra không sai theo cùng một cách. Nhóm đã thử cố ý làm lệch một đồng trong một transaction: view báo đúng một dòng FAIL, sau rollback lại 21/21."

---

## Phần 6. Kiểm thử và kết luận (2,5 phút)

**Thao tác:** mở `11_kiem_thu_T1-T7.txt`, kéo xuống dòng tổng kết. Chỉ nói "58/58" nếu lần chạy lại ở Chuẩn bị mục 7 cho đúng số đó.

**Lời thoại:** "Bộ kiểm thử tự động có 58 ca, từ khóa và mức hạt đến nạp lại không sinh thêm dòng. Có một chuyện đáng kể: bộ test từng báo lệch 11.688 món tồn. Nhóm điều tra và thấy chính công thức của test gom theo `product_key` nên đếm đôi, còn mart gom theo mã nghiệp vụ là đúng. Nhóm sửa test, không sửa dữ liệu."

**Giới hạn:** "Giao dịch là mô phỏng, giá vốn là giả định, kho mới có khoảng một tháng, 1 chiến dịch quảng cáo, 1 voucher mỗi dòng, và lỗi cách ly là lỗi chèn có chủ đích."

**Mở rộng:** "Theo mô hình xoắn ốc và Bus Architecture, các vòng tiếp theo thêm `Fact_Order_Fulfillment`, `Fact_Return`, `Fact_Seller_Settlement`, `Fact_Customer_Activity`, dùng lại dimension dùng chung. Em xin hết phần demo."

---

## Câu hỏi dự phòng

| Câu hỏi | Trả lời |
|---|---|
| Vì sao không báo cáo trên OLTP? | OLTP chỉ giữ trạng thái hiện tại nên mất lịch sử, không tích hợp được nhiều nguồn, tranh CPU và I/O với giao dịch. PostgreSQL dùng MVCC nên đọc không khóa ghi; vấn đề không phải locking. |
| Vì sao SCD2 mà không SCD1? | SCD1 ghi đè nên doanh thu quá khứ bị gán sai. Nhóm vẫn dùng SCD1 cho thuộc tính chỉ để hiển thị như tên, liên hệ. |
| Vì sao hạng khách dùng mini-dimension? | Hạng và nhóm chi tiêu đổi liên tục; cấu hình mock có thể tới ~8.500 lượt đổi hạng. Mini-dimension chỉ có 125 tổ hợp. |
| Sao số đo khác báo cáo bước 10? | Báo cáo đo trên dữ liệu nhân bản 2 triệu và 6,6 triệu dòng, demo đo trên dữ liệu thật. Số tuyệt đối và tỷ lệ đều khác: dữ liệu càng lớn, MV càng có lợi. |
| MV có nhược điểm gì? | Chỉ mới khi refresh sau batch (khoảng 10 giây ở quy mô 2 triệu dòng); chỉ cộng tiếp được measure cộng được, số đơn và số khách thì không (hậu tố `_na`). |
| Dòng RC-06i, "khóa 0" là gì? | 5 dòng đơn hoàn tất cuối ngày 31/01 có thanh toán ghi sang 01/02. Dự kiến cập nhật thành khóa thật ở batch sau, **chưa kiểm chứng** vì chưa nạp batch đó. |
| Sao không có dòng `is_returned`? | Fact có sẵn cờ này và ETL cập nhật lại được dòng đã nạp, nhưng đến 31/01 chưa dòng nào có cờ. Phân tích trả hàng thuộc vòng mở rộng `Fact_Return`. |
| Dữ liệu đến muộn thì sao? | Thay đổi SCD2 có ngày hiệu lực sớm hơn phiên bản hiện hành bị cách ly (DQ-23), không sửa hồi tố. |
| Vì sao 4.273 món xuất kho khác 4.048 món bán? | Tồn kho ghi lúc xuất kho, bán hàng ghi lúc hoàn tất đơn. |

---

## Nếu có sự cố

| Sự cố | Xử lý |
|---|---|
| Dashboard trắng khi mới mở | Đợi khoảng 40 giây. |
| Dashboard không lên | Chạy lại lệnh ở Chuẩn bị mục 3. Không được thì chiếu video dự phòng. |
| DBeaver hoặc `psql` không kết nối | Kiểm tra Docker Desktop và container `scripts-mock-postgres-1`. Sau khi khởi động lại máy: `docker compose -p scripts -f D:\PTIT\mock_run\scripts\compose.mock.yaml up -d` (giữ nguyên dữ liệu). |
| Số đo lệch nhiều | Chạy lại; kiểm tra mock đã dừng. Đọc đúng số trên màn hình. |
| Quên `RESET` sau `[P2c]` | `RESET enable_indexscan; RESET enable_bitmapscan;` hoặc kết nối lại. |
| View `mart.v_consistency_check` không tồn tại | `bash dw/sql/run_ddl.sh` trong WSL (idempotent). |
