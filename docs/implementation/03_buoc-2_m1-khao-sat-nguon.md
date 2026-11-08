# 03 — PLAN 2 (Milestone 1): Khảo sát nguồn, chủ đề, quy tắc tích hợp

| | |
|---|---|
| Ngày thực hiện | 07/11/2026, 22:26–22:50 |
| Trạng thái | ✅ Xong |
| Liên quan PLAN | Mục 2.1–2.4 |
| Liên quan lộ trình | Milestone 1 (Sub 1.1, 1.2, 1.3), Inmon chương 1–2 |
| Sản phẩm | [M1_KHAO_SAT_NGUON_CHU_DE_TICH_HOP.md](../data-model/warehouse/M1_KHAO_SAT_NGUON_CHU_DE_TICH_HOP.md) |

## 1. Mục tiêu

Hoàn thành 3 output của Milestone 1. Tất cả phải dựa trên **dữ liệu thật**, không dựa vào tài liệu thiết kế:
1. Bản đồ hệ thống nguồn và lý do không chạy báo cáo trên OLTP (Sub 1.1).
2. 3–4 chủ đề cốt lõi (Sub 1.2).
3. Ít nhất 3 xung đột tích hợp kèm quy tắc chuẩn hóa, và quy tắc lưu vết (Sub 1.3).

## 2. Đầu vào

- `mock_oltp`: dữ liệu mô phỏng 01/01–12/01/2026 (1.382 đơn), đọc bằng `dw_reader` (bước 02).
- SQLite crawler `data/tiki_crawl.db`, đọc ở chế độ `mode=ro`.
- Kế hoạch M1 trong PLAN mục 2 (bản nháp quy tắc IR-01..07).

## 3. Phân tích trước khi làm

Bản nháp quy tắc trong PLAN được viết từ tài liệu ([OLTP_SCHEMA.md](../data-model/oltp/OLTP_SCHEMA.md), CLAUDE.md). Mỗi quy tắc cần được xác nhận hoặc bác bỏ bằng một câu SQL. Riêng câu hỏi danh mục cần đối chiếu chéo OLTP với SQLite crawler, nên viết thêm một đoạn Python.

## 4. Cách thực hiện

1. Viết script profiling [dw/sql/05_profiling/m1_source_profile.sql](../../dw/sql/05_profiling/m1_source_profile.sql), gồm 17 truy vấn:
   - **P0–P3:** mốc dữ liệu; số dòng 33 bảng theo 6 hệ thống (đếm động bằng `query_to_xml`); cột thời gian của từng bảng (để biết bảng nào trích incremental được); kiểu thời gian.
   - **IR-01..IR-10:** mỗi xung đột một truy vấn bằng chứng.
   - **T1–T2:** OLTP có lịch sử không; bảng nào không có cột thời gian.
   - **K:** kiểm tra mồ côi ở 7 quan hệ khóa quan trọng.
2. Chạy bằng role chỉ đọc và lưu toàn bộ output:
   ```bash
   docker exec -i scripts-mock-postgres-1 psql -h 127.0.0.1 -U dw_reader -d mock_oltp -v ON_ERROR_STOP=1 \
     < dw/sql/05_profiling/m1_source_profile.sql >> docs/implementation/evidence/03_m1_source_profile.txt
   ```
3. Đối chiếu danh mục OLTP với crawler (Python, SQLite `mode=ro`). Với mỗi sản phẩm, so `products.category_id` của OLTP với:
   - `products.category_id` của crawler (gốc);
   - `product_categories.leaf_category_id`;
   - nút cuối và vị trí trong `primary_category_path`;
   - cha của nó trong `categories` OLTP.
   
   Sau đó dựng thử cây đã cắt và đếm số nút, độ sâu, số nút có 2 cha. Đồng thời kiểm tra `order_items.commission_category_id`.
4. Đo truy vấn báo cáo điển hình trực tiếp trên OLTP bằng `EXPLAIN (ANALYZE, BUFFERS)`, trong lúc engine đang ghi, để làm bằng chứng cho lý do L4.
5. Viết sản phẩm M1, rồi sửa PLAN theo kết quả.

## 5. Quá trình thực hiện (kết quả thật)

**Profiling** (output đầy đủ: [evidence/03_m1_source_profile.txt](evidence/03_m1_source_profile.txt)):

| Truy vấn | Kết quả |
|---|---|
| P1 | 33 bảng; lớn nhất `inventory_daily_balance` 219.067 dòng / 12 ngày; `seller_payouts` và `seller_payout_items` = 0 |
| P2 | 9 bảng không có cột thời gian: `order_items`, `order_item_promotions`, `checkout_lines`, `customer_addresses`, `categories`, `channels`, `payment_methods`, `warehouses`, `carriers` |
| P3 | 39 cột `timestamp without time zone`, 10 cột `date` |
| IR-01 | 3.532 SKU ở kho, **0 không map**; SKU không trùng |
| IR-02 | 1.175/1.175 vận đơn map được về đơn, không trùng |
| IR-03 | Marketing chỉ có `WEB`; bảng kênh là `Web`/`App`/`Livestream` |
| IR-04 | **Mọi sản phẩm trỏ tới danh mục cấp 2**; 5 danh mục gốc, 44 lá |
| IR-05 | 733/1.382 đơn (53,0%) và 6.644/12.037 phiên là khách vãng lai |
| IR-06 | `discount_amount` và `net_amount` lẻ ở 26/1.586 dòng; `unit_price` không lẻ |
| IR-08 | 4 tỉnh, viết thống nhất ở cả 4 bảng |
| IR-09 | Thiếu giới tính 1.540 (14,9%), thiếu ngày sinh 2.655 (25,6%) |
| IR-10 | `discount_rate` max 62 (phần trăm), 720 dòng > 1 |
| T1 | Customers 0, sellers 1, products 0 dòng từng bị cập nhật (trước khi bước 01 có hiệu lực) |
| K | 0 dòng mồ côi ở cả 7 quan hệ |

**Đối chiếu danh mục:**

```
products 3532
oltp_cat==crawl products.category_id(root): 0
oltp_cat in product_categories leaf: 3532
oltp_cat == path last: 3308
oltp_cat in path: 3532
oltp parent == crawl root: 3532
multi root/leaf pairs: 0
index_in_path,path_len: [((3,4),113), ((4,5),1576), ((5,6),1619), ((5,7),200), ((5,8),24)]
commission_category_id = products.category_id: 1586/1586
truncated depth dist [(2,113), (3,1576), (4,1843)] nodes 77 edges 72 multi-parent conflicts 0
```

**Đo truy vấn báo cáo trên OLTP:**

| Truy vấn | Dữ liệu | Execution time |
|---|---|---|
| R1: doanh thu ngày × danh mục gốc × kênh (join 6 bảng, lọc trạng thái) | 1.586 dòng hàng | 12,6 ms |
| R2: tồn kho theo danh mục gốc × ngày | 219.067 dòng tồn | 176,1 ms |

## 6. Kiểm tra kết quả

| Tiêu chí Milestone 1 | Đạt |
|---|---|
| 1.1: Liệt kê mọi nguồn, có sơ đồ ranh giới OLTP ↔ DW | ✅ 6 hệ thống + crawler; sơ đồ Mermaid; ranh giới thực thi bằng quyền (bước 02) |
| 1.1: Phân tích vì sao OLTP không dùng cho báo cáo dài hạn | ✅ 5 lý do L1–L5, mỗi lý do có bằng chứng; có ghi chú trung thực về MVCC |
| 1.2: 3–4 chủ đề | ✅ 4 chủ đề + Khách hàng dùng chung, có sơ đồ thực thể |
| 1.3: ≥ 3 xung đột thực tế và quy tắc chuẩn hóa | ✅ 10 xung đột (IR-01..IR-10), đều có số đo |
| 1.3: Quy tắc cấm sửa/xóa lịch sử, lưu vết | ✅ NV-01..03, TV-01..06 |

## 7. Vấn đề & cách xử lý

| Vấn đề | Xử lý |
|---|---|
| **Giả định trong PLAN sai:** IR-04 viết `products.category_id` là danh mục gốc, theo mô tả crawler trong CLAUDE.md. Khi đồng bộ sang OLTP, Mock Studio lại ghi **danh mục lá** vào `products.category_id` và đặt gốc làm cha | Sửa IR-04 trong PLAN (mục 2.3, 4.6, 5.3.2, 5.3.3a). Danh mục chuẩn = danh mục lá OLTP (khớp hoa hồng); cây lấy từ path, cắt tại danh mục này |
| Path của 224 sản phẩm đi sâu hơn danh mục OLTP | Cắt tại danh mục OLTP để cây nhất quán với hoa hồng và báo cáo. Phần sâu hơn bỏ qua (ghi giới hạn) |
| 28 nút trung gian của cây chưa có tên | Tạm hiển thị `Danh mục <id>`; tùy chọn crawl tên một lần qua `/api/v2/categories` (bước M3) |
| Đề bài nói đến "nghẽn khóa bảng", nhưng PostgreSQL dùng MVCC nên đọc không khóa ghi | Ghi trung thực trong M1: vấn đề thật là thiếu lịch sử, thiếu tích hợp, tranh tài nguyên và dữ liệu dở dang |
| Ở mức 12 ngày dữ liệu, truy vấn OLTP còn nhanh (12–176 ms) | Nêu đúng số đo, kèm ước tính tăng trưởng (~6,7 triệu dòng tồn/năm); không phóng đại |
| Lỗi mã hóa khi in tiếng Việt trên console Windows | Đặt `PYTHONIOENCODING=utf-8` |

## 8. Ảnh hưởng & bước tiếp theo

- Mới:
  - `dw/sql/05_profiling/m1_source_profile.sql`;
  - `docs/implementation/evidence/03_m1_source_profile.txt`;
  - `docs/data-model/warehouse/M1_KHAO_SAT_NGUON_CHU_DE_TICH_HOP.md`.
- Sửa PLAN: IR-04 (danh mục), thêm IR-08..10, G5, mục 4.6 bước 1, `map_category_path`, `stg.product`.
- Bước tiếp theo: **04 — PLAN 3 (Milestone 2)**: đặc tả grain atomic cho 3 fact (kiểm tra tính duy nhất của khóa grain trên dữ liệu thật) và tháp phân tầng Atomic → Summary.
