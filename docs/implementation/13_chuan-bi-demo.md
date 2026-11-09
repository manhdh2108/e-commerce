# Bước 13 — Chuẩn bị demo: màn hình tổng duyệt, SQL cho DBeaver, kịch bản gọn

> Ngày thực hiện: 09/11/2026 · Dữ liệu: kho `dwh` ở batch 7 · Kết quả: view `mart.v_consistency_check` 21/21 PASS (~1,3 giây), 7 file SQL demo chạy không lỗi, kịch bản [KICH_BAN_DEMO.md](../KICH_BAN_DEMO.md) viết lại
> Mã: [dw/sql/40_mart/402_consistency.sql](../../dw/sql/40_mart/402_consistency.sql), [dw/demo_sql/](../../dw/demo_sql/), sửa [dw/sql/run_ddl.sh](../../dw/sql/run_ddl.sh)

## 1. Mục tiêu

Áp dụng góp ý của một lượt đánh giá kịch bản demo (đối chiếu với lộ trình 6 bước): (1) thêm phần chứng minh **tích hợp** (Bước 2); (2) chỉ giữ hai so sánh tốc độ mạnh nhất; (3) gộp phần nhất quán thành **một màn hình tổng duyệt**; (4) có sẵn SQL để chạy bằng `Ctrl + Enter` thay vì copy-paste; (5) có Plan B cho dashboard; (6) kể theo mạch 6 bước.

## 2. Đầu vào

- Kịch bản cũ: 8 phần, phần tốc độ có 5 so sánh (4a–4e), phần nhất quán có 6 nhóm câu SQL rời (5a–5f), tổng 23 phút.
- Kho batch 7; role chỉ đọc `dw_analyst` (dùng khi demo); mock đang chạy nền (làm số đo nhiễu).

## 3. Phân tích trước khi làm

- **Tích hợp (IR-03):** `dw.dim_channel` có sẵn cột `marketing_code` (`WEB`, `APP`, `LIVESTREAM`) cạnh `channel_name`, nên một câu `SELECT` đủ chứng minh ánh xạ; thêm một câu cho thấy hai fact của hai hệ nguồn nối được qua cùng `channel_key`.
- **View thay vì file script:** `psql` chạy trong container không `\i` được file ở máy chủ, và DBeaver thì chạy một câu thuận tiện hơn nhiều file; một view `mart.v_consistency_check` cho phép **một câu `SELECT`** ra toàn bộ kết quả, và `dw_analyst` đọc được.
- **Không viết lại logic ETL trong view:** mỗi kiểm tra tính độc lập (anti-join, `lag(valid_to)`, so tổng fact với từng MV), cùng tinh thần bộ T1–T7.
- **Chi phí chạy:** view nằm trong demo nên phải đủ nhanh; cần đo, không đoán.
- **Phần tốc độ:** giữ truy vấn ghép hai fact (kỹ thuật khó nhất, 531,9 ms so với 27,3 ms ở lần chạy thử) và index (4,5 ms so với 58,3 ms); chuyển ba so sánh còn lại (tồn kho theo tháng, SCD trên MV, partition) sang phụ lục dự phòng.

## 4. Cách thực hiện

```bash
docker exec -i scripts-mock-postgres-1 psql -q -U dw_etl -d dwh -v ON_ERROR_STOP=1 < dw/sql/40_mart/402_consistency.sql
docker exec -i scripts-mock-postgres-1 psql -U dw_analyst -d dwh -c "SELECT * FROM mart.v_consistency_check"
```

- [402_consistency.sql](../../dw/sql/40_mart/402_consistency.sql) (đã thêm vào danh sách của `run_ddl.sh`): view 21 dòng, nhóm A khóa ngoại (2), B mức hạt (3), C khoảng hiệu lực SCD2 (3), D fact trỏ đúng phiên bản (3), E tiền khớp giữa fact và MV (5), F đẳng thức tiền và bridge (4), G đối soát ETL ở batch mới nhất (1); `GRANT SELECT` cho `dw_analyst`.
- [dw/demo_sql/](../../dw/demo_sql/): `P1a_batch_log`, `P1b_tich_hop_ma_kenh`, `P2a_gioi_thieu_mv`, `P2b_drill_across`, `P2c_index`, `P4_cach_ly`, `P5_consistency_check`; mỗi file mở thành một tab DBeaver, dòng đầu ghi tên tab và kỳ vọng.
- Kịch bản [KICH_BAN_DEMO.md](../KICH_BAN_DEMO.md): đánh số lại theo thứ tự trình bày (Mở đầu, ETL và tích hợp, Tốc độ, Dashboard, Chất lượng, Nhất quán, Kiểm thử, Kết luận), có bảng "Bước lộ trình ↔ phần ↔ câu mở đầu", phần Chuẩn bị mới (DBeaver, view, Plan B), phụ lục dự phòng.

## 5. Quá trình thực hiện (diễn biến thật)

| Việc | Kết quả |
|---|---|
| Chạy thử câu tích hợp | `WEB → Web`, `APP → App`, `LIVESTREAM → Livestream`; Web: doanh thu 2.070.991.883, chi phí QC 2.932.996; App: doanh thu 519.946.374, chưa có QC |
| Tạo view bản 1, chạy bằng `dw_analyst` | Đúng (21/21 PASS) nhưng **36,5 giây** — quá chậm |
| `EXPLAIN (ANALYZE)` view | Nhánh kiểm tra khóa ngoại `fact_order_item` (9 điều kiện `NOT EXISTS … OR NOT EXISTS …`) mất **37,8 giây**: planner chạy từng dòng với subplan. Tách thành 9 anti-join riêng cộng lại; kiểm tra tồn kho (566 nghìn dòng) đếm khóa phân biệt thay vì từng dòng |
| Bản 2 | 8,4–10,0 giây; còn kiểm tra grain tồn kho mất ~4,5 s |
| Bản 3: chỉ kiểm nhóm sản phẩm có ≥ 2 phiên bản SCD2 (khóa chính đã đảm bảo duy nhất ở mức phiên bản) | **1,25–1,29 giây** (ba lần liên tiếp), vẫn 21/21 PASS |
| **Thử bắt lỗi:** trong transaction, làm lệch hoa hồng 1 đồng ở một dòng fact | Đúng một dòng `FAIL` ("doanh thu thuần − hoa hồng ≠ phần seller nhận" = 1); sau `ROLLBACK` view lại 21/21 PASS, kho không đổi |
| Chạy cả 7 file SQL qua `psql` với `ON_ERROR_STOP` | Không lỗi. Đo: ghép hai fact 531,9 ms (Atomic) so với 27,3 ms (Summary); index 4,5 ms so với 58,3 ms; `P4_cach_ly` ra DQ-02 (5), DQ-03 (8), DQ-04 (7), DQ-05 (2)… |
| Kiểm số liệu ca seller | 9455: Normal 13 dòng 3.108.000, Mall 3 dòng 511.000; 332670: Normal 33 dòng 20.425.209, Mall 2 dòng 1.224.000 — khớp kịch bản |

## 6. Kiểm tra kết quả

- View: 21 dòng, mọi dòng `PASS`; bắt được một lệch 1 đồng khi cố ý làm sai.
- File SQL: chạy được từ đầu đến cuối bằng `dw_analyst`; kỳ vọng ghi trong kịch bản khớp số đo.
- Số khẳng định trong kịch bản đối chiếu lại với kho trước khi viết (kênh, seller, thời gian).

**Không làm được / chưa làm:**
- **Quay video Plan B** — chỉ có thể do người trình bày thực hiện; kịch bản có hướng dẫn (Win + Alt + R hoặc OBS) và danh sách cảnh cần quay.
- **Sơ đồ kế hoạch dạng hình trong DBeaver** — chưa kiểm tra bản DBeaver của máy demo; kịch bản dặn thử trước và dùng bản chữ nếu không ổn.
- Số đo tốc độ khi mock đang chạy nền dao động (ví dụ ghép hai fact 27 ms thay vì 21–24 ms); dừng mock trước demo cho số ổn định.

## 7. Vấn đề & cách xử lý

| Vấn đề | Xử lý |
|---|---|
| View ban đầu 36,5 giây | Xem bảng ở mục 5. Bài học: nhiều `NOT EXISTS` nối bằng `OR` ngăn planner dùng hash anti-join; tách riêng từng điều kiện. Ghi chú giải thích trong chính file SQL |
| Kiểm tra grain tồn kho theo `product_id` tốn kém | Chỉ kiểm sản phẩm có ≥ 2 phiên bản SCD2, vì chỉ nhóm đó mới có thể trùng ở mức sản phẩm nghiệp vụ khi khóa chính đã chặn trùng ở mức phiên bản; ghi rõ trong comment |
| Số file SQL đặt tên theo số phần cũ | Đổi tên theo thứ tự trình bày mới (P1, P2, P4, P5) và sửa dòng đầu từng file |
| Gợi ý "dừng mock cho số ổn định" xung đột với việc mock đang chạy cho dữ liệu mới | Giữ như một bước chuẩn bị tùy chọn trong kịch bản; chạy lại `start_all.sh` sau demo |

## 7b. Bổ sung: tab `[P3] OLAP` (đề cương mục 4.2)

Đề cương bài tập lớn yêu cầu Chương IV.2 trình bày roll-up, drill-down, slice, dice và drill-across; kịch bản demo chưa có bốn phép đầu. Thêm [dw/demo_sql/P3_olap.sql](../../dw/demo_sql/P3_olap.sql) (7 câu, đo 6–89 ms mỗi câu bằng `dw_analyst`) và chèn vào Phần 2 của kịch bản, nối với màn hình dashboard "Bán hàng chi tiết" (đã có sẵn "Mức thời gian" Năm/Quý/Tháng/Ngày, bộ lọc danh mục gốc → con, kênh, hạng seller lúc bán, nút xuất CSV).

| Phép | Câu SQL | Số đo thật |
|---|---|---|
| Roll-up | `ROLLUP(tháng, tuần)`; lên danh mục gốc | 5 tuần (152,3 / 646,8 / 661,6 / 674,2 / 456,1 triệu), tháng và tổng đều 2.590.938.257; AOV tính lại mỗi cấp (725.040 đến 1.038.571, tổng 864.799). Danh mục: Điện thoại 1.437.851.000 (55,5%) |
| Drill-down | Gốc "Làm Đẹp - Sức Khỏe" → cấp 2 → cấp 3 qua bridge; tuần 4 → ngày | Ba nút cấp 2 cộng 375.178.713 = số của gốc; cấp 3 "Sữa rửa mặt" 208.517.163 (640 món) = số của nút cha; 7 ngày tổng 674.212.704 |
| Slice | `kênh = App` | 519.946.374 (cộng 5 tuần khớp) |
| Dice | Kênh App, hạng lúc bán Mall/Preferred, 12–25/01 | 7 dòng, đầu bảng 13.253.400 |

Vấn đề gặp khi làm: ví dụ drill-down đầu tiên chọn "Điện thoại Smartphone" (doanh thu lớn nhất, tên đầy đủ) nhưng đó là **danh mục lá ở cấp 2**, nên bước khoan xuống cấp 3 trả về 0 dòng. Đổi sang nhánh "Làm Đẹp - Sức Khỏe" (3 cấp có dữ liệu); đổi lại là các nút trung gian dùng tên tạm "Danh mục 1582" (28 nút chưa có tên ở nguồn, đã ghi ở hạn chế), kịch bản có dặn nói rõ khi gặp. Cũng sửa chú thích roll-up: `ROLLUP(tháng, tuần)` không chứa mức ngày, mức ngày xem ở câu drill-down 2c.

## 7c. Bổ sung: tab `[P2d]` partition và `[P2e]` cặp Summary/Atomic thêm

Rà soát độ phủ của SQL demo so với yêu cầu "chạy truy vấn mẫu kiểm tra tốc độ Summary và Atomic; kiểm tra nhất quán Fact/Dimension; kiểm tra tốc độ khi dùng index và partition": Summary so với Atomic (`P2a`, `P2b`), nhất quán (`P5`, `P1a`), index (`P2c`) đã có; **partition chưa có tab nào** (bản kịch bản cũ chỉ có SQL partition ở phụ lục, bị bỏ khi kịch bản được viết lại). Thêm [P2d_partition.sql](../../dw/demo_sql/P2d_partition.sql) (phân bố dòng theo partition, số partition, `EXPLAIN ANALYZE` có và không có điều kiện `date_key`, cùng phần tuỳ chọn so bảng thường với bảng phân vùng ở schema `bench`) và [P2e_summary_vs_atomic_bo_sung.sql](../../dw/demo_sql/P2e_summary_vs_atomic_bo_sung.sql) (tồn kho theo tháng × kho; hạng seller SCD; mỗi cặp kèm câu `EXCEPT` chứng minh cùng kết quả).

**Trạng thái kiểm chứng: CHƯA chạy thử hai file này.** Lúc viết, Docker Desktop đang trả lỗi 500 cho mọi lệnh `docker`, và kết nối trực tiếp tới cổng 55432 bị treo (cổng mở nhưng không có phản hồi). Các số "kỳ vọng" trong hai file lấy từ lần đo trước đó trong ngày (partition 9–10 ms so với 85–106 ms; hai cặp ở `P2e` 127–197 ms so với 8–14 ms và 8 ms so với 1,1 ms), cần chạy lại và đọc số thật khi Docker hoạt động trở lại.

## 8. Ảnh hưởng & bước tiếp theo

- **Schema:** thêm một view `mart.v_consistency_check` (chỉ đọc, không đổi dữ liệu); `run_ddl.sh` chạy lại idempotent. Không đổi bộ kiểm thử T1–T7 (vẫn 58 ca).
- **Tài liệu:** README, Blueprint (mục 7.1, phụ lục A) nhắc tới view và `dw/demo_sql/`; bản HTML của Blueprint dựng lại.
- **Trước buổi demo:** mở các tab DBeaver, chạy thử `[P2b]`, `[P2c]`, `[P5]` một lần; quay video Plan B; cân nhắc dừng mock.
