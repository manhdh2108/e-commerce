# Bộ cấu hình quy mô vừa — năm 2026

Đây là mức thử nghiệm cho engine hiện tại, không phải chuẩn phân loại quy mô sàn trên thị trường. Hai file được bổ sung riêng, không thay bộ khoảng 100 lượt/ngày.

| File | Nơi nhập |
|---|---|
| [medium-ecommerce.json](settings/medium-ecommerce.json) | Thiết lập môi trường → Nhập thiết lập bằng JSON |
| [medium-linked-2026.json](scenarios/medium-linked-2026.json) | Cấu hình kịch bản → Nhập cấu hình JSON |

## Sản lượng yêu cầu

Ngày thường trong phép tính này loại các ngày đôi 1/1–12/12 và 27/11. Trung bình **999,93 lượt đặt/ngày**, dao động **569–1.766**. Không dùng số mặc định trên form để suy ra sản lượng: từng ngày năm 2026 có quota riêng và ghi đè mặc định.

| Ngày | Tổng lượt đặt yêu cầu |
|---|---:|
| 02/01 | 948 |
| 08/08 | 5.300 |
| 10/10 | 6.307 |
| 11/11 | 3.782 |
| 12/12 | 4.172 |

Đếm tổng GST-02 và CUS-05. Đây là yêu cầu checkout, không bảo đảm số đơn tạo thành công, số đơn hoàn tất hay doanh thu. Checkout nhiều người bán có thể tách nhiều dòng orders. Giữ nguyên các nhóm thanh toán, địa phương, kênh, lịch theo giờ và các nhánh hậu mãi của bộ đầy đủ; tăng sản lượng đầu vào và xử lý theo số lần tương ứng. Những hành động tự xử lý đầu vào đến hạn tiếp tục dùng chế độ all. Hành động quản trị catalog, lịch chiến dịch và chốt ngày không nhân đồng loạt theo số đơn. 27/11 giữ đặc điểm lịch cũ, chưa được thiết kế thành đợt Black Friday riêng.

## Thực thể, tồn nền và đầu vào

- 21 nhóm thực thể, nhóm khách vãng lai 100.000 danh tính ảo. Đây là tập được chọn để tạo hành động, không phải 100.000 phiên mỗi ngày.
- Nhóm nhân sự có 12 hoặc 48 danh tính tùy vai trò; giữ sáu kho, năm hãng vận chuyển và các mã liên kết đang có. Số nhân sự này không tạo thêm năng lực xử lý hoặc SLA tự động.
- Tồn nền theo từng SKU/kho tăng bốn lần khoảng lượng của bộ đầy đủ, tỷ lệ phủ tăng 0,1, tối đa 0,98. Kho TP.HCM: 48–720; Hà Nội: 40–600; Đà Nẵng: 20–360; Cần Thơ: 20–400, khi SKU được chọn theo tỷ lệ phủ.
- Quota nhập hàng tăng cùng sản lượng; lượng mỗi lần nhập tăng ba lần. Vẫn có thể thiếu tồn theo SKU được mua; lượng cung tổng không bảo đảm đúng SKU cần dùng.
- Khách nền đề xuất **10.000** khi tạo môi trường mới, seed có thể giữ **42** để tái lập. Đây là ô UI riêng, JSON không tự điền số khách nền. Khách đăng ký mới vẫn được tạo theo lịch hành động.
- Nếu hồ sơ có inventory rules, engine dùng các quy tắc đó thay cho ô tồn chung. Đổi ô tồn chung không ghi đè các phân bố này.
- Nên dùng catalog đủ đa dạng, chẳng hạn từ vài nghìn SKU có thể bán; đây là khuyến nghị thử nghiệm, không phải điều kiện bắt buộc của validator. Catalog chỉ 149 sản phẩm vẫn chạy được nhưng có thể tập trung mua và thiếu tồn sớm hơn. Không tạo thêm hoặc đổi ID Tiki để đạt số SKU này.

## Cách dùng

1. Nhập file thiết lập, kiểm tra → điền biểu mẫu → **Lưu hồ sơ** và **Lưu chính sách**. Phải lưu hồ sơ có actors để các nhóm của kịch bản khớp vai trò.
2. Nếu bắt đầu môi trường mới: lưu hồ sơ trước đồng bộ và tạo nền, đồng bộ catalog từ SQLite, rồi tạo nền với 10.000 khách. Chỉ tạo nền sau khi chuẩn bị môi trường/ngày bắt đầu theo quy trình UI. Không tự xóa DB để dùng bộ này.
3. Nếu môi trường đã tạo nền: import không cập nhật lại tồn kho, khách hay kho/carrier đã có. Cần xem tồn và lượng khách hiện tại; không coi cấu hình mới đã bổ sung dữ liệu nền cũ.
4. Nhập kịch bản medium, xem trước và lưu thành cấu hình riêng.
5. Lập kế hoạch **một ngày mỗi lượt** từ ngày tiếp theo checkpoint, đặt độ chậm 0 để không thêm thời gian chờ. Ngày đã hoàn tất không tự chạy lại.
6. Theo dõi số yêu cầu/thành công/bị từ chối và lý do; kiểm tra số checkout, số orders, tồn SKU và các yêu cầu đến hạn còn chờ trước khi tăng khoảng chạy.

## Giới hạn được giữ nguyên

Mỗi hành động/ngày không quá 10.000 lần. Quota quan sát như tìm kiếm/xem sản phẩm được giới hạn và giảm ở ngày đỉnh để tổng yêu cầu có số lần không vượt 90.000/ngày (đỉnh thực tế 89.999), còn khoảng trống dưới giới hạn 100.000/lượt. Vì thế traffic là mẫu thu nhỏ, không phải bản sao toàn bộ lượt xem của sàn thực. Giới hạn này không tính số tác vụ chế độ all, số dòng ghi ra hay số đơn sau tách người bán; thời gian chạy thực tế vẫn có thể lớn.

Hai ngày ghép lại có thể vượt 100.000; dùng xem trước để kiểm tra, không mặc định chạy cả tháng/năm một lượt. Không thay giới hạn engine để ép nhập bộ này.

Đã kiểm tra hai file bằng chính bộ kiểm tra nhập của ứng dụng trong môi trường SQLite tạm biệt lập, kiểm tra vai trò của mọi actor_pool và quota 365 ngày. Chưa chạy sinh dữ liệu quy mô vừa hoặc đo tốc độ PostgreSQL; không bảo đảm 1.000 checkout thành công/ngày hay hiệu năng trên máy cụ thể. Chưa import hai file vào môi trường đang dùng, chưa tạo job và chưa sửa dữ liệu OLTP.
