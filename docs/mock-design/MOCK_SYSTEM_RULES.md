# Quy tắc đã chốt cho hệ thống mock

Tài liệu ghi nhận các quy tắc đã được thống nhất. Những quy tắc tiếp theo sẽ được bổ sung vào file này khi được chốt.

## Rule 01 — Đồng bộ dữ liệu crawler sang mock chỉ thêm mới

**Trạng thái:** Đã chốt.

### Hai hệ thống độc lập

Hệ thống cào Tiki và hệ thống mock là hai hệ thống riêng biệt, quản lý dữ liệu riêng. Hệ thống cào tiếp tục hoạt động theo luồng hiện tại.

Khi người dùng yêu cầu đồng bộ, hệ thống mock đọc dữ liệu từ database crawler để bổ sung catalog. Cào thêm dữ liệu không tự động làm database mock thay đổi. Thao tác đồng bộ không ghi ngược vào database crawler.

### Nguyên tắc append-only

| Trường hợp | Hành vi đồng bộ |
|---|---|
| Sản phẩm chưa tồn tại trong database mock | Thêm mới theo mapping đã thống nhất. |
| Sản phẩm đã tồn tại trong database mock | Bỏ qua toàn bộ bản ghi, kể cả khi giá hoặc thông tin bên crawler thay đổi. |
| Mã danh mục chưa tồn tại | Thêm mới dữ liệu cần thiết để liên kết sản phẩm. |
| Mã người bán chưa tồn tại | Thêm mới dữ liệu cần thiết để liên kết sản phẩm. |
| Danh mục hoặc người bán đã tồn tại | Giữ nguyên, không cập nhật đè. |
| Sản phẩm không còn xuất hiện trong dữ liệu crawler | Giữ nguyên trong database mock; không xóa hoặc tự đổi trạng thái. |
| Đồng bộ lại cùng dữ liệu | Không tạo bản ghi trùng. |

### Giá và dữ liệu đã có

Sản phẩm trong database mock giữ thông tin và giá được nhập tại lần đồng bộ đầu tiên. Giá mới ở crawler không ghi đè giá sản phẩm đã có trong mock.

Đồng bộ không sửa hoặc xóa dữ liệu mô phỏng đã tồn tại, bao gồm giá vốn, tồn kho, đơn hàng, thanh toán và các dữ liệu nghiệp vụ khác.

Quy tắc này áp dụng cho **thao tác đồng bộ**. Nó không tự quy định cách các nghiệp vụ mô phỏng được phép thay đổi trạng thái trong quá trình chạy; các quy tắc đó sẽ được chốt riêng.

### Định danh và liên kết

- Kiểm tra bản ghi đã tồn tại bằng khóa định danh được chốt cho từng thực thể; không dùng tên hoặc giá để nhận diện sản phẩm.
- Chưa tự tạo lại ID để biến một sản phẩm đã có thành sản phẩm mới.
- Bản ghi mới phải bảo đảm các liên kết danh mục và người bán cần thiết.
- Chiến lược khóa sản phẩm khi nguồn có nhiều chào bán cho cùng một sản phẩm sẽ được xác minh và chốt riêng; không mặc định thay đổi khóa của schema hiện tại.

### Kết quả mỗi lần đồng bộ

Mỗi lần đồng bộ cần ghi nhận thời điểm thực hiện và thống kê số bản ghi thêm mới, bỏ qua, lỗi theo từng thực thể. Bản ghi thiếu dữ liệu bắt buộc hoặc không bảo đảm liên kết phải được báo rõ; không sửa dữ liệu đã có để ép đồng bộ thành công.

### Ví dụ

1. Lần đầu, crawler có sản phẩm A giá 100.000 đồng. Database mock chưa có A → thêm A với giá 100.000 đồng.
2. Sau đó crawler cập nhật A thành 90.000 đồng và có thêm sản phẩm B → lần đồng bộ tiếp theo bỏ qua A, chỉ thêm B nếu hợp lệ.
3. Đồng bộ lại mà không có thực thể mới → không thêm trùng, không thay đổi dữ liệu đã có.

## Tài liệu liên quan

[Ánh xạ trường sản phẩm Tiki vào schema OLTP](TIKI_PRODUCT_FIELD_MAPPING.md) mô tả nguồn và cột đích. Mapping không có nghĩa là được cập nhật đè bản ghi; hành vi đồng bộ phải tuân thủ Rule 01 trong tài liệu này.

## Rule 02 — Vị trí và giới hạn của chức năng đồng bộ

**Trạng thái:** Đã chốt theo yêu cầu người dùng.

Đồng bộ Tiki là chức năng độc lập đặt ngoài màn chính, không nằm trong lịch hành động ngày thường/ngày đặc biệt của Catalog & Seller. Người dùng chủ động yêu cầu đồng bộ.

Đồng bộ chỉ bổ sung sản phẩm, danh mục và người bán mới cần thiết theo Rule 01. Không tự sinh hoặc sửa đơn hàng, khách hàng, thanh toán, tồn kho, marketing, analytics, chính sách hoa hồng hay đối soát; không tự kích hoạt các hành động nghiệp vụ của hệ thống khác. Catalog mới có thể được các hệ thống khác sử dụng trong kế hoạch chạy riêng sau đó.

Màn Catalog & Seller hiển thị 4 nhóm nghiệp vụ: Người bán, Quản trị viên catalog, Nhân viên quản lý người bán, Khách truy cập. Tổng thể vẫn có 5 bên tác động nếu tính tiến trình đồng bộ bên ngoài. Cấu hình hành động cụ thể được mô tả trong [MOCK_CATALOG_SELLER_CONFIG.md](MOCK_CATALOG_SELLER_CONFIG.md).

## Rule 03 — Nơi lưu tài liệu và cách chốt logic mới

**Trạng thái:** Đã chốt theo yêu cầu người dùng ngày 05/11/2026.

Rule và các tài liệu đang chốt logic mock cho từng hệ thống được lưu riêng trong `docs/mock-design/`. Tài liệu Markdown cũ ngoài thư mục này chỉ mang tính tham khảo, có thể sai hoặc không còn phù hợp; không tự coi các tỷ lệ, ngưỡng và hành vi cũ là yêu cầu đã chốt.

Không dùng thời gian sửa file để xác định một nội dung đã được duyệt. Trạng thái phải dựa vào nội dung người dùng đã xác nhận. Tài liệu trong thư mục mới cũng có thể chứa phần đề xuất; phần đó không tự trở thành rule đã chốt chỉ vì được chuyển vào thư mục.

Giai đoạn hiện tại tập trung chốt cấu hình mock: nhóm tác động, hành động cụ thể, đơn vị đếm, số lần ngày thường/ngày đặc biệt và form cấu hình riêng. Chi tiết ghi và liên kết dữ liệu được bàn sau. Không tự triển khai code khi mới đang chốt tài liệu. Người dùng đã yêu cầu chuyển sang triển khai trong lượt sau; trạng thái tính năng theo file MOCK_IMPLEMENTATION_STATUS.md.

## Rule 04 — Số lần hành động vào ngày đặc biệt

**Trạng thái:** Đã chốt qua xác nhận tiếp tục của người dùng.

Mỗi hành động có số lần ngày thường và số lần riêng theo ngày đặc biệt. Số riêng của ngày đặc biệt thay thế số ngày thường, không cộng hoặc nhân thêm. Không có giá trị riêng thì dùng cấu hình ngày thường; giá trị 0 nghĩa là không yêu cầu phát sinh hành động đó.

Chế độ xử lý theo đầu vào đã được người dùng xác nhận sau đó tại Rule 05.

## Rule 05 — Xử lý các yêu cầu đến hạn

**Trạng thái:** Người dùng xác nhận trong lượt triển khai ngày 05/11/2026.

Các hành động xử lý hệ quả phù hợp được hỗ trợ hai chế độ: theo số lần cấu hình hoặc tự xử lý toàn bộ yêu cầu đến hạn/đủ điều kiện. Chế độ tự động không dùng số ngày thường/ngày đặc biệt; UI hiện rõ thay thế bằng “Theo đầu vào”. Không tự tạo yêu cầu nghiệp vụ để có việc xử lý.

## Rule 06 — Khóa sản phẩm và xung đột đầu vào bản đầu

**Trạng thái:** Người dùng xác nhận trong lượt triển khai ngày 05/11/2026.

Giữ ID sản phẩm Tiki làm khóa. Nếu cùng ID có nhiều chào bán hoặc SKU trùng/thiếu thì báo lỗi rõ và bỏ qua bản ghi xung đột. Không đổi mã, tự cấp SKU thay thế hoặc ghi đè bản ghi cũ. Các giá trị nguồn không xung đột vẫn tuân thủ đồng bộ chỉ thêm mới.

## Rule 07 — Chỉnh sửa trực tiếp cấu hình đã lưu

**Trạng thái:** Đã chốt theo yêu cầu người dùng.

Người dùng được chọn cấu hình đã lưu, chỉnh sửa và lưu thay đổi vào đúng cấu hình đó, không bắt buộc tạo cấu hình khác. Việc lưu chỉ cập nhật dữ liệu điều khiển, không tự chạy mock hoặc sửa dữ liệu nghiệp vụ.

Mỗi kế hoạch giữ snapshot cấu hình. Khi cấu hình được sửa, phải preview lại trước khi tạo job mới từ kế hoạch cũ. Job đã xếp/đang chạy/tạm dừng và lịch sử vẫn giữ snapshot đã dùng, không đổi cấu hình giữa chừng. Các lần sửa được lưu nội bộ để đối chiếu. Khi có sửa đồng thời, phải báo xung đột thay vì ghi đè âm thầm.

## Rule 08 — Cào chủ động và xóa toàn bộ dữ liệu để chạy lại

**Trạng thái:** Người dùng xác nhận khi nâng cấp Tổng quan.

- Tổng quan có nút kích hoạt crawler Tiki hiện có. Crawler chỉ ghi SQLite nguồn; không tự đồng bộ OLTP. Người dùng chủ động sang tab Đồng bộ để kiểm tra và thực hiện nhập mới theo Rule 01.
- Thao tác chạy lại bản này là **xóa toàn bộ dữ liệu trong 27 bảng OLTP**, gồm cả sản phẩm, danh mục, người bán đã đồng bộ và dữ liệu nền. Giữ cấu trúc bảng, cấu hình kịch bản, thiết lập môi trường và SQLite crawler.
- Xóa checkpoint, trạng thái runtime, dấu đã tạo dữ liệu nền và thống kê ngày của đợt dữ liệu cũ. Giữ lịch sử lượt chạy để đối chiếu, đánh dấu thuộc dữ liệu cũ; hủy các lượt dang dở để không tiếp tục ghi từ lịch sử đã xóa. Kế hoạch/xem trước cũ hết hiệu lực.
- Trước khi xóa, hiển thị số dòng từng bảng và yêu cầu nhập `XOA TOAN BO`. Chặn khi còn lượt ghi đang chạy/chờ. Không tự xóa chỉ vì khởi động web hoặc mở trang.
- Chạy lại theo thứ tự: đồng bộ SQLite → OLTP, tạo dữ liệu nền, xem trước kế hoạch, chạy từ ngày bắt đầu đã thiết lập.
- Chưa triển khai xóa từ ngày được chọn trở về trước: người dùng đồng ý dùng nút xóa toàn bộ thay thế vì dữ liệu các ngày sau có liên kết/phụ thuộc vào dữ liệu trước.
