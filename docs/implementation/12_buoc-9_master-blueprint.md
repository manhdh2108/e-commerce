# Bước 12 — PLAN 9: Master Blueprint

> Ngày thực hiện: 09/11/2026 · Sản phẩm: [docs/MASTER_BLUEPRINT.md](../MASTER_BLUEPRINT.md) (12 mục + 2 phụ lục) · Hình: [docs/images/etl_architecture.png](../images/etl_architecture.png) (+ [SVG](../images/etl_architecture.svg))
> Nguồn dữ liệu của tài liệu: các tài liệu M1–M3, ghi chép bước 01–11, kết quả kiểm thử bước 11, truy vấn trực tiếp `dwh`

## 1. Mục tiêu

Hoàn thành sản phẩm Milestone 5.2 theo [PLAN mục 9](../DW_BUILD_PLAN.md): một tài liệu **Master Blueprint** gồm 11 nội dung (bối cảnh–mục tiêu–phạm vi; kiến trúc tầng và luồng dữ liệu; bản đồ nguồn–chủ đề–quy tắc tích hợp; grain và tháp phân tầng; galaxy schema, bus matrix, từ điển; ETL–DQ–SCD; dashboard và KPI; kết quả hiệu năng; kết quả kiểm thử; giới hạn và giả định; lộ trình mở rộng), cộng bảng kỹ năng nâng cao của PLAN mục 12. Người đọc dự kiến: giảng viên chấm bài 5.2 và các thành viên nhóm chuẩn bị slide, demo.

## 2. Đầu vào

| Thành phần | Nguồn |
|---|---|
| Thiết kế | [M1](../M1_KHAO_SAT_NGUON_CHU_DE_TICH_HOP.md), [M2](../M2_GRAIN_PHAN_TANG.md), [M3](../M3_THIET_KE_VAT_LY_STAR_SCHEMA.md), [từ điển](../M3_TU_DIEN_DU_LIEU.md) |
| Triển khai | Ghi chép bước 01–10, [08a SCD](08a_tong-hop-scd.md), [08b](08b_mini-dimension_bridge_cay-danh-muc.md) |
| Kết quả | Hiệu năng ở bước 10; kiểm thử ở [bước 11](11_buoc-8_kiem-thu.md) |
| Số liệu hiện hành | Truy vấn trực tiếp `dwh` ngày 09/11: batch 4–7 SUCCESS, `fact_order_item` 3.419 dòng / 2.996 đơn, Σ net 2.590.938.257 VND, `fact_inventory_snapshot` 565.982 dòng, 8 seller / 14 khách / 8 sản phẩm có phiên bản SCD2, 24 KPI (6 A, 2 SA, 16 NA), 200 cột có mô tả |
| Hình kiến trúc | `docs/images/etl_architecture.png` (vẽ lại bằng SVG ở bước trước) |

## 3. Phân tích trước khi làm

- **Blueprint là bản tổng hợp có tham chiếu, không chép lại.** Các tài liệu M1–M3 và ghi chép bước đã có chi tiết; Blueprint tóm tắt quyết định và số liệu rồi liên kết tới nguồn, để một người đọc nắm được toàn bộ thiết kế trong một tài liệu mà không có hai bản chi tiết lệch nhau.
- **Số liệu phải là số hiện hành, không phải số cũ trong các tài liệu trước.** Nhiều ghi chép được viết khi kho mới có batch 4 (12 ngày, 1.195 dòng bán hàng): M1 ghi "quảng cáo đa kênh từ 30/01", 08a mục 7 ghi "chưa có phiên bản SCD2 thật". Với mỗi con số đưa vào Blueprint, đã đối chiếu lại bằng truy vấn trên kho hiện tại hoặc ghi rõ là số đo ở bước tương ứng (ví dụ số liệu bench là của lần đo 08/11).
- **Hai chỗ tài liệu cũ chưa khớp với thực tế, Blueprint dùng giá trị mới:** ngày bắt đầu kịch bản SCD là **25/01** (đã chuyển sớm, [bước 01 §10](01_buoc-1.0_cau-hinh-mock-scd.md)), không phải 30/01 như PLAN gốc; số bảng OLTP là **33** (không phải 27 như tài liệu cấu trúc ban đầu của repo).
- **Phải nói rõ giới hạn, đặc biệt những điểm dễ bị hỏi khi bảo vệ:** giao dịch là dữ liệu mô phỏng; giá vốn là giả định; không có đổi giá/danh mục thật; lỗi cách ly là lỗi chèn; kho mới có 4 batch; payment đến muộn gây khóa 0 tạm thời. Mục 10 liệt kê từng điểm kèm hệ quả.
- **Lộ trình mở rộng không cần code.** PLAN mục 11 đã chốt: vòng xoắn ốc 2–5 chỉ đưa vào Blueprint. Mỗi vòng ghi fact mới, nguồn OLTP, dimension mới và kỹ năng thể hiện, cùng quy trình áp dụng lại.

## 4. Cách thực hiện

1. Đọc M1, M2, M3, ghi chép bước 06–10 và 08a/08b (số liệu, quyết định, hạn chế).
2. Truy vấn `dwh` lấy số liệu hiện hành (số dòng fact/dimension, KPI, quy tắc DQ, ca SCD thật).
3. Viết theo thứ tự 11 nội dung của PLAN mục 9.1, mỗi mục: kết luận/quyết định → bảng hoặc sơ đồ → liên kết tới tài liệu chi tiết.
4. Ba sơ đồ Mermaid mới (tháp phân tầng, galaxy schema rút gọn, luồng một batch) cộng hình kiến trúc PNG ở mục 2; bảng kỹ năng nâng cao (mục 12) trỏ tới kiểm thử cụ thể (T1.x–T7.x).
5. Chạy kiểm thử cuối để mục 9 của Blueprint lấy số liệu từ lần chạy thật ([bước 11](11_buoc-8_kiem-thu.md)).

Cấu trúc [MASTER_BLUEPRINT.md](../MASTER_BLUEPRINT.md):

| Mục | Nội dung |
|---|---|
| 1 | Bối cảnh, mục tiêu theo milestone (kèm trạng thái), phạm vi trong/ngoài |
| 2 | Kiến trúc tổng thể: hình, các lớp schema và quyền truy cập, công nghệ, lý do thiết kế |
| 3 | Bản đồ nguồn S1–S7, chủ đề C1–C4, IR-01..10, quy tắc lưu vết NV/TV |
| 4 | Ba grain atomic, tháp phân tầng |
| 5 | Galaxy schema, bus matrix, dimension và chiến lược lịch sử, quyết định D1–D8, từ điển |
| 6 | ETL từng bước, DQ, cách ly, thuật toán SCD, fact, bridge, mini-dim, cây danh mục, đối soát, dữ liệu thay đổi thật |
| 7 | Mart, 24 KPI, drill-across, dashboard 5 màn hình |
| 8 | Kết quả BM01–BM03 |
| 9 | Kết quả T1–T7 |
| 10 | Giới hạn và giả định |
| 11 | Vòng xoắn ốc 2–5, cải tiến kỹ thuật |
| 12 | Kỹ năng nâng cao và bằng chứng |
| Phụ lục | Cấu trúc kho mã, lệnh tái lập nhanh |

## 5. Quá trình thực hiện (diễn biến thật)

| Giờ (09/11) | Việc | Kết quả |
|---|---|---|
| ~14:50 | Đọc M1–M3, ghi chép 08a/08b/09/10, PLAN §5.3 (DQ), §9, §12 | Nắm số liệu và các hạn chế đã ghi |
| ~14:55 | Truy vấn `dwh`: số dòng, danh sách 24 KPI (6 A, 2 SA, 16 NA), 22 DQ + kết quả batch 7, danh mục (77 nút, `path_ids`), ca SCD | Số liệu hiện hành để thay số cũ |
| ~15:05 | Viết Blueprint mục 1–8, 10–12; để chỗ trống mục 9 | Tài liệu đầy đủ trừ kết quả kiểm thử |
| ~15:10 | Điền mục 9 từ lần chạy kiểm thử cuối | 58/58 PASS, kèm phát hiện test lỗi và khóa 0 |

## 6. Kiểm tra kết quả

- **Đủ 11 nội dung của PLAN mục 9.1** (mục 1–11 của Blueprint) và bảng kỹ năng PLAN mục 12 (mục 12 của Blueprint, có cột bằng chứng trỏ tới mã kiểm thử).
- **Số liệu** trong mục 2, 4, 5, 6.6, 7, 8, 9 đối chiếu được: mục hiện hành ↔ truy vấn ngày 09/11; hiệu năng ↔ `bench.bm_result`; kiểm thử ↔ [evidence/11_kiem_thu_T1-T7.txt](evidence/11_kiem_thu_T1-T7.txt).
- **Liên kết tương đối** tới tài liệu và mã đều dùng đường dẫn trong repo; README ở gốc repo (kiểm thử T7.2) nêu `docs/MASTER_BLUEPRINT.md` và `docs/BAO_CAO_KIEM_THU_T1_T7.md`.
- **Sơ đồ Mermaid** dùng cú pháp `flowchart`/`erDiagram` chuẩn; hình PNG kiến trúc đã được mở xem ở bước vẽ.

Chưa làm (và không thuộc phạm vi tài liệu này): slide và demo (15–16/11), kiểm tra bằng mắt việc Mermaid hiển thị trên công cụ xem cuối cùng (GitHub/VS Code/Markdown viewer của giảng viên).

## 7. Vấn đề & cách xử lý

| Vấn đề | Xử lý |
|---|---|
| Tài liệu gốc còn số cũ (batch 4, 1.195 dòng; "SCD từ 30/01"; "27 bảng") | Dùng số hiện hành đo lại hoặc ghi rõ mốc đo; ghi chú sai khác ở mục 3 ghi chép này |
| Không muốn Blueprint hứa hẹn quá mức với dữ liệu mới có 4 batch | Mục 10 ghi rõ khối lượng nhỏ, những gì chưa kiểm chứng (cập nhật payment đến muộn, đường `FAILED`, khách ở hai phiên bản) và mục 11 ghi việc cần làm khi mô phỏng tiến xa |
| Kết quả kiểm thử phụ thuộc lần chạy cuối | Viết mục 9 sau khi có bằng chứng chạy; số liệu lấy nguyên từ file bằng chứng |
| Nhánh `quybruno` không chứa engine mock và settings (chỉ có ở worktree `D:/PTIT/mock_run`) | README và Blueprint nêu rõ nguồn của settings/engine thay vì trỏ vào đường dẫn không có trong repo |

## 8. Ảnh hưởng & bước tiếp theo

- **File mới:** `docs/MASTER_BLUEPRINT.md`. Không sửa mã, schema hay dữ liệu.
- **Giữ cho khớp:** khi nạp thêm batch hoặc thay đổi thiết kế, cập nhật các số liệu hiện hành ở mục 1.2 (trạng thái dữ liệu), 6.6, 9, 10 của Blueprint và chạy lại `bash dw/tests/run_tests.sh`.
- **Tiếp theo (theo lịch PLAN mục 10):** 13/11 chạy ETL incremental nhiều lần khi mock tiến (cập nhật 08a/08b, kiểm chứng payment đến muộn, chạy lại kiểm thử); 14/11 đo lại T6 với dữ liệu thật lớn hơn; 15–16/11 làm slide và demo từ Blueprint; 17/11 nộp 5.2.
