# Nhật ký triển khai kho dữ liệu

Thư mục này ghi lại **chi tiết từng bước đã thực hiện** khi xây dựng kho dữ liệu theo
[DW_BUILD_PLAN.md](../data-model/warehouse/DW_BUILD_PLAN.md): làm gì, bằng lệnh/mã nào, kết quả thực tế ra sao, kiểm tra thế nào và gặp vấn đề gì.

## Quy ước

- Mỗi bước là một file `NN_buoc-<mã bước trong PLAN>_<tên ngắn>.md`. Số `NN` tăng theo thứ tự thực hiện.
- Mỗi file có đủ 8 mục:
  1. **Mục tiêu**: bước này giải quyết gì, gắn với mục nào của PLAN và đề xuất.
  2. **Đầu vào**: dữ liệu, file, trạng thái hệ thống trước khi làm.
  3. **Phân tích trước khi làm**: những gì phải kiểm tra, phát hiện quan trọng.
  4. **Cách thực hiện**: các bước, lệnh, mã, SQL đúng như đã chạy.
  5. **Quá trình thực hiện**: diễn biến thực tế, output thật, số liệu thật (không ghi số dự kiến).
  6. **Kiểm tra kết quả**: tiêu chí đạt và bằng chứng.
  7. **Vấn đề & cách xử lý**: lỗi, giới hạn, quyết định đổi hướng.
  8. **Ảnh hưởng & bước tiếp theo**: thay đổi ở file nào, việc tiếp theo.
- Mọi thời gian ghi theo giờ máy (UTC+7). Ngày mô phỏng là ngày trong năm 2026 của dữ liệu OLTP.
- Ghi chép được viết ngay khi làm xong bước, không viết bù sau.

## Mục lục và trạng thái

| # | Bước | File | Trạng thái | Ngày làm |
|---|---|---|---|---|
| 00 | Sinh dữ liệu OLTP bằng Mock Studio (tiền đề) | [00_sinh-du-lieu-oltp.md](00_sinh-du-lieu-oltp.md) | 🔄 Đang chạy nền | 07/11/2026 |
| 01 | PLAN 1.0 — Cấu hình mock cho SCD và quảng cáo đa kênh | [01_buoc-1.0_cau-hinh-mock-scd.md](01_buoc-1.0_cau-hinh-mock-scd.md) | ✅ Xong (chờ áp dụng từ ngày mô phỏng 30/01) | 07/11/2026 |
| 02 | PLAN 1.1 — Khởi tạo database `dwh`, role, schema | [02_buoc-1.1_khoi-tao-dwh.md](02_buoc-1.1_khoi-tao-dwh.md) | ✅ Xong | 07/11/2026 |
| 03 | PLAN 2 — M1: bản đồ nguồn, chủ đề, quy tắc tích hợp | [03_buoc-2_m1-khao-sat-nguon.md](03_buoc-2_m1-khao-sat-nguon.md) → sản phẩm [M1](../data-model/warehouse/M1_KHAO_SAT_NGUON_CHU_DE_TICH_HOP.md) | ✅ Xong | 07/11/2026 |
| 04 | PLAN 3 — M2: grain, tháp phân tầng | [04_buoc-3_m2-grain-phan-tang.md](04_buoc-3_m2-grain-phan-tang.md) → sản phẩm [M2](../data-model/warehouse/M2_GRAIN_PHAN_TANG.md) | ✅ Xong | 07/11/2026 |
| 05 | PLAN 4 — M3: DDL dimension/fact/bridge, từ điển dữ liệu | [05_buoc-4_m3-thiet-ke-vat-ly.md](05_buoc-4_m3-thiet-ke-vat-ly.md) → [M3 schema](../data-model/warehouse/M3_THIET_KE_VAT_LY_STAR_SCHEMA.md), [M3 từ điển](../data-model/warehouse/M3_TU_DIEN_DU_LIEU.md) | ✅ Xong | 07/11/2026 |
| 06 | PLAN 5.2 — Extract | [06_buoc-5.2_extract.md](06_buoc-5.2_extract.md) | ✅ Xong | 07/11/2026 |
| 07 | PLAN 5.3 — Transform | [07_buoc-5.3_transform.md](07_buoc-5.3_transform.md) | ✅ Xong | 07/11/2026 |
| 08 | PLAN 5.4–5.6 — Load dimension/SCD, fact, đối soát | — | ⏳ | |
| 09 | PLAN 6 — Mart, dashboard | — | ⏳ | |
| 10 | PLAN 7 — Thí nghiệm hiệu năng BM01–BM03 | — | ⏳ | |
| 11 | PLAN 8 — Kiểm thử T1–T7 | — | ⏳ | |
| 12 | PLAN 9 — Master Blueprint | — | ⏳ | |
