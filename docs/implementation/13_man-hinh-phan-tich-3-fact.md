# Bước 13 — Màn hình "Phân tích theo bảng Fact" (3 tab, mỗi tab một bảng fact)

> Ngày thực hiện: 09/11/2026 · Mã: [dashboard/fact_tabs.py](../../dashboard/fact_tabs.py), [dashboard/common.py](../../dashboard/common.py), sửa [dashboard/app.py](../../dashboard/app.py), [dashboard/test_app.py](../../dashboard/test_app.py)
> Dữ liệu: kho `dwh` ở batch 7 (nghiệp vụ 03/01 → 31/01/2026) · Kiểm thử: `dashboard/test_app.py` 6/6 màn hình, 0 lỗi

## 1. Mục tiêu

Dashboard cũ tổ chức theo kỹ thuật (SCD, drill-across) và chủ yếu thể hiện bài toán bán hàng; bài toán tồn kho và quảng cáo chưa có biểu đồ nói thẳng câu hỏi kinh doanh. Yêu cầu: **3 tab, mỗi tab một bảng fact**, trong mỗi tab vừa có biểu đồ cho bài toán nghiệp vụ mà fact được xây để trả lời, vừa thể hiện được các kỹ thuật kho dữ liệu (SCD, bridge...) bằng ví dụ cụ thể, ví dụ khách ở tỉnh này rồi chuyển sang tỉnh khác thì doanh số tính cho tỉnh nào.

## 2. Thiết kế

Mỗi tab có hai phần: **A. Bài toán kinh doanh** (biểu đồ kèm một dòng kết luận tính từ dữ liệu) và **B. Kỹ thuật kho dữ liệu** (chọn một đối tượng thật để xem trực tiếp).

| Tab | A. Bài toán kinh doanh | B. Kỹ thuật thể hiện |
|---|---|---|
| `Fact_Order_Item` (bán hàng) | Nhịp doanh thu theo ngày (cuối tuần tô màu riêng) + số đơn; thác nước giá niêm yết → giảm giá → voucher → doanh thu thuần → hoa hồng → seller nhận, và doanh thu → giá vốn → lãi gộp; treemap danh mục; kênh × phương thức thanh toán; top 10 seller tô theo hạng lúc bán; doanh thu theo tỉnh khách | (1) SCD2 khách: chọn một khách đã chuyển tỉnh, xem dòng thời gian phiên bản + các đơn, so doanh số theo tỉnh lúc mua và tỉnh hiện tại; (2) SCD2 + SCD3 seller: doanh thu theo ngày tô theo phiên bản, vạch ngày đổi; (3) mini-dimension hồ sơ khách; (4) bridge khuyến mãi (đối soát Σ phân bổ = Σ giảm giá); (5) bridge cây danh mục (closure) |
| `Fact_Inventory_Snapshot` (tồn kho) | Dòng nhập/trả/bán/điều chỉnh theo ngày + đường tồn; thác nước đối soát tồn đầu + nhập + trả − bán ± điều chỉnh = tồn cuối; lưới 2×2 (bán chạy/chậm × tồn cao/thấp) và hai danh sách "cần nhập", "tồn dư"; tồn và giá trị theo kho | (1) semi-additive: SUM qua ngày so với tồn cuối kỳ và bình quân; (2) SCD2 sản phẩm: tồn theo ngày tô theo phiên bản, so gom theo `product_key` và `product_id`; (3) bridge cây danh mục cho giá trị tồn |
| `Fact_Ad_Spend` (quảng cáo) | KPI chi phí, ngân sách dùng, CTR, CPC, ROAS; phễu hiển thị → click → đơn; ngân sách và chi tiêu; chi phí so doanh thu gắn chiến dịch; doanh thu theo ngày, đơn gắn và không gắn chiến dịch | (1) conformed dimension và drill-across `FULL OUTER JOIN`: kênh có bán nhưng chưa có quảng cáo, doanh thu sẽ mất nếu dùng `INNER JOIN` |

Tách hàm dùng chung (`q`, `num`, `vnd`, `pct`, `intf`, `table`) sang `common.py` để `app.py` và `fact_tabs.py` cùng dùng. Màn hình mới đứng đầu danh sách (`PAGES[0]`), các màn hình cũ giữ nguyên.

## 3. Kiểm tra kết quả

`bash`/WSL: `.venv/bin/python dashboard/test_app.py` → 6/6 PASS. Với màn hình mới: 3 tab, 39 chỉ số, 30 biểu đồ; KPI so với SQL độc lập: Doanh thu thuần 2,59 tỷ, tồn cuối kỳ 5.669.223 món, chi phí quảng cáo 2,9 tr đều khớp.

Số liệu hiển thị đối chiếu với các bước trước:

| Nội dung | Giá trị trên màn hình | Nguồn đối chiếu |
|---|---|---|
| Khách 7944 | 270.000 đ, Hà Nội (lúc mua) → TP. Hồ Chí Minh (hiện tại, đổi 29/01) | duy nhất khách có đơn ở phiên bản cũ; 08a §7 |
| Seller 332670 | 20.425.209 đ (33 dòng) hạng Normal + 1.224.000 đ (2 dòng) hạng Mall, đổi 28/01 | 08a §7.2 |
| Đối soát tồn | 5.670.135 + 3.360 + 43 − 42 − 4.273 = 5.669.223, khớp tuyệt đối | T5 |
| Tồn gom theo `product_key` so `product_id` | 5.680.911 so 5.669.223, lệch 11.688 | lỗi test T5 (bước 11 §7) |
| SUM tồn qua 31 ngày | 175.754.845, gấp 31 lần tồn thật | — |
| Kênh App thiếu quảng cáo | 519.946.374 đ (20,1% doanh thu) sẽ mất nếu `INNER JOIN` | drill-across (bước 09) |
| Đối soát bridge | Σ giảm giá 3.040.000 = Σ phân bổ theo trọng số 3.040.000 | bước 08b |

Đã xem giao diện thật bằng Chrome không giao diện (chụp từng tab qua DevTools) và chỉnh các chỗ khó đọc.

## 4. Vấn đề & cách xử lý

| Vấn đề | Xử lý |
|---|---|
| Máy chủ Streamlit chạy từ trước vẫn phục vụ bản cũ (trình theo dõi file trên `/mnt/d` của WSL không phát hiện thay đổi) | Khởi động lại riêng dashboard: `bash dashboard/run.sh stop` rồi `bash dashboard/run.sh` (không ảnh hưởng mock hay ETL) |
| `pd.Timestamp` không chứa được `9999-12-31` (phiên bản hiện hành SCD2) | Cắt `valid_from`/`valid_to` về khoảng dữ liệu bằng kiểu `date` trước khi đổi sang Timestamp |
| Biểu đồ phân tán bán/tồn bị dồn thành các cột rời (số món bán chỉ 1–10) | Đổi sang lưới 2×2 kèm số sản phẩm và số tồn từng ô |
| Treemap mini-dimension bị nhóm "Chưa mua / 0 đơn" chiếm gần hết | Đổi sang cột xếp chồng theo hạng, nêu tỷ lệ 88% doanh thu thuộc khách chưa có lịch sử 12 tháng |
| Bridge danh mục hiện "Danh mục 5451" (danh mục chưa có tên) | Kèm tên danh mục lá có doanh thu lớn nhất bên dưới |

## 5. Giới hạn cần nói khi bảo vệ

- Chỉ có **một khách** mua trước khi chuyển tỉnh (7944) và chưa khách nào mua ở cả hai phiên bản; mock chỉ đổi tỉnh từ 25/01.
- Bridge khuyến mãi mới có **1 nhóm, 1 voucher**; cách nối có và không có trọng số cho cùng kết quả. Trọng số chỉ có tác dụng khi một dòng dùng từ hai voucher.
- Quảng cáo mới có **1 chiến dịch (Web)**; kịch bản đa kênh chạy từ 01/02 chưa được nạp vào kho.
- Mini-dimension: 88% doanh thu thuộc nhóm "Chưa mua" vì kho mới có khoảng một tháng.
- Tồn mô phỏng rất lớn so với tốc độ bán (5,67 triệu món so với khoảng 4.300 món bán/tháng) nên "số ngày đủ bán" lớn; chỉ dùng để xếp hạng tương đối.

## 6. Ảnh hưởng & bước tiếp theo

- **File mới:** `dashboard/common.py`, `dashboard/fact_tabs.py`. **File sửa:** `dashboard/app.py` (nhập từ `common`, thêm màn hình đầu), `dashboard/test_app.py` (thêm màn hình mới và 3 kiểm tra KPI).
- Mở: http://localhost:8501, màn hình đầu là "Phân tích theo bảng Fact".
- Khi nạp thêm batch qua tháng 2, các biểu đồ xu hướng, quảng cáo đa kênh, khách mua ở hai phiên bản sẽ có thêm dữ liệu mà không cần sửa mã.
