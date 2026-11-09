# Bước 14 — Thiết kế lại dashboard: chế độ Thống kê cho người dùng nghiệp vụ

> Ngày thực hiện: 09/11/2026 · Mã: [dashboard/stats.py](../../dashboard/stats.py) (mới), [.streamlit/config.toml](../../.streamlit/config.toml) (mới), sửa [dashboard/app.py](../../dashboard/app.py), [dashboard/common.py](../../dashboard/common.py), [dashboard/fact_tabs.py](../../dashboard/fact_tabs.py), [dashboard/test_app.py](../../dashboard/test_app.py), [dw/tests/run_tests.py](../../dw/tests/run_tests.py)
> Dữ liệu: kho `dwh` ở batch 7 (nghiệp vụ 03/01 → 31/01/2026) · Kiểm thử: `test_app.py` 9/9 màn hình, nhóm T5 9/9 PASS

## 1. Mục tiêu

Yêu cầu: giao diện thân thiện với người dùng, mục đích chính là **thống kê**, phân tích chỉ là phần nhỏ. Dashboard trước đó tổ chức theo kỹ thuật và dùng nhiều thuật ngữ kho dữ liệu.

## 2. Đầu vào

- 6 màn hình của bước 13, mở đầu bằng màn hình 3 tab theo 3 bảng fact.
- `dw.*`, `mart.*` ở batch 7. Streamlit 1.50, Plotly 6.3.

## 3. Phân tích trước khi làm

- Các màn hình kỹ thuật vẫn cần cho buổi bảo vệ nên giữ nguyên, chỉ chuyển sang một chế độ riêng.
- Biểu đồ doanh thu đọc được từ `mart.mv_sales_day_product` vì doanh thu và số món cộng được. Số đơn và số khách là đếm phân biệt nên phải tính từ `dw.fact_order_item`, không cộng từ MV.

## 4. Cách thực hiện

| Chế độ | Màn hình | Nội dung |
|---|---|---|
| **Thống kê** (mặc định) | Tổng quan | Lọc 7 ngày / 14 ngày / toàn bộ và theo kênh; 5 thẻ số kèm mức tăng giảm so với kỳ trước; doanh thu theo ngày và kênh; top danh mục, sản phẩm, cửa hàng; tỉnh khách, hình thức thanh toán; "Nhận xét nhanh" |
| | Bán hàng chi tiết | Màn hình "Tổng quan bán hàng" cũ, giữ nguyên, nhiều bộ lọc và bảng xuất CSV |
| | Tồn kho | Chọn ngày; 5 thẻ số; tồn theo kho và nhóm hàng; hàng vào và ra mỗi ngày; 10 sản phẩm bán nhiều nhất, 10 sản phẩm tồn nhiều nhất; "Nhận xét nhanh" |
| | Quảng cáo | 5 thẻ số; ngân sách và tiền đã chi; doanh thu từng kênh có và chưa có chiến dịch; bảng chiến dịch; "Nhận xét nhanh" |
| **Kỹ thuật kho dữ liệu** | 3 bảng Fact và kỹ thuật, SCD, Đối soát vận hành, Chất lượng dữ liệu, Hiệu năng | Giữ nguyên các màn hình cũ, dùng khi bảo vệ |

Ngôn ngữ đời thường ("Doanh thu", "Giá trị mỗi đơn", "Cửa hàng"), đầu trang chỉ có một dòng về thời điểm dữ liệu, trục tiền tính bằng triệu đồng, ngày dạng `dd/mm`. Theme sáng và thanh công cụ tối giản đặt trong `.streamlit/config.toml`.

## 5. Quá trình thực hiện (diễn biến thật)

| Việc | Kết quả |
|---|---|
| Viết `stats.py`, chuyển `short()` sang `common.py`, thêm công tắc chế độ | `test_app.py` qua 9/9 |
| Xem giao diện bằng Chrome không giao diện | Phát hiện các lỗi ở mục 7 mà kiểm thử không bắt được |
| Chạy `run_tests.sh --only T5` | T5.9 thất bại ở mọi màn hình; sửa xong 9/9 PASS, 29/29 nút CSV khớp bảng |

Số đo thời gian: truy vấn của Tổng quan tổng 0,5 giây (13 câu), Tồn kho 0,7 giây (10 câu), Quảng cáo 0,1 giây (3 câu). Trong trình duyệt, lần mở đầu sau khi khởi động máy chủ mất khoảng 38 giây, chủ yếu để nạp thư viện từ `/mnt/d`; chuyển màn hình sau đó mất 0,5–2 giây.

## 6. Kiểm tra kết quả

- `test_app.py`: 9/9 màn hình không lỗi. Tổng quan chọn "Toàn bộ dữ liệu" khớp SQL độc lập: doanh thu 2,59 tỷ, 2.996 đơn, 1.105 khách.
- Nhóm T5 (`run_tests.sh --only T5`): 9/9 PASS.
- Đã xem ảnh chụp của Tổng quan, Tồn kho, Quảng cáo.
- **Chưa làm:** chưa chạy lại bộ T1–T7 đầy đủ sau thay đổi này (file bằng chứng `evidence/11_kiem_thu_T1-T7.txt` vẫn là lần chạy trước). Chưa chụp màn hình "Bán hàng chi tiết" và các màn hình kỹ thuật ở chế độ mới; chúng chỉ được kiểm bằng `test_app.py`. Các tương tác ở Tổng quan chỉ kiểm qua `test_app.py`, chưa bấm thử trong trình duyệt.

## 7. Vấn đề & cách xử lý

| Vấn đề | Nguyên nhân | Xử lý |
|---|---|---|
| T5.9 thất bại ở mọi màn hình | `run_tests.py` không có `dashboard/` trong `sys.path` nên `import common` lỗi. Lỗi đã có từ bước 13 khi tách `common.py`, lúc đó chỉ chạy `test_app.py`. Tên màn hình cũ trong T5.9 cũng hết hiệu lực | Thêm đường dẫn; đổi sang cặp (chế độ, màn hình) |
| Bảng chiến dịch hiện tỷ lệ click 0,01% | Định dạng cột in số nguyên trạng, trong khi giá trị là tỷ số 0,0113 | Nhân 100, nay hiện 1,13% |
| "Sản phẩm hết hàng" đếm sai đơn vị | Đếm dòng sản phẩm × kho có tồn 0 | Đếm sản phẩm có tổng tồn 0 ở mọi kho (hiện là 0) |
| Nhãn số ở cuối thanh ngang bị cắt | Trục không chừa chỗ | Nới trục thêm 25–35% |
| Bảng sản phẩm mất cột số | Cột tên chiếm hết chiều rộng | Cố định độ rộng cột, cắt tên còn 44 ký tự |
| Dấu chấm cuối câu nhận xét thành dấu phẩy | `replace(".", ",")` áp lên cả câu | Bỏ `replace`, gộp phần so sánh kỳ trước thành một dòng |
| Đo trong Chrome không giao diện mất khoảng 30 giây mỗi lần chuyển trang | Tab không được tính là đang mở nên bị hãm (đo lại với tab được giả lập là đang mở: 0,5–2 giây) | Không phải lỗi của dashboard |
| Máy chủ Streamlit không nhận code mới | Theo dõi file trên `/mnt/d` không phát hiện thay đổi | Sau khi sửa code phải `bash dashboard/run.sh stop` rồi `bash dashboard/run.sh` |

## 8. Ảnh hưởng & bước tiếp theo

- Kịch bản [KICH_BAN_DEMO.md](../KICH_BAN_DEMO.md) đã cập nhật: thêm 1 phút chế độ Thống kê, tổng khoảng 24 phút; hướng dẫn mở dashboard một lần trước giờ demo.
- Bảng màn hình ở [Master Blueprint](../MASTER_BLUEPRINT.md) mục 7.2 đã cập nhật.
- **Tiếp theo:** chạy lại `bash dw/tests/run_tests.sh` đầy đủ và cập nhật file bằng chứng trước ngày nộp.
