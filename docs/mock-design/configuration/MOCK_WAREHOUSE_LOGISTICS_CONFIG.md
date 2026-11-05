# Cấu hình kịch bản mock — Kho vận

> Đã chuyển sang triển khai theo yêu cầu người dùng. Nội dung dưới đây là thiết kế; xem [trạng thái thực tế](../reviews/MOCK_IMPLEMENTATION_STATUS.md) để biết tính năng đã chạy và giới hạn. Không hiểu “đã có thiết kế” là toàn bộ nghiệp vụ đã hoàn thành.

**Trạng thái:** Đề xuất danh sách hành động và form để chốt, chưa triển khai code/UI. Các rule chung đã xác nhận nằm trong [MOCK_SYSTEM_RULES.md](../MOCK_SYSTEM_RULES.md). Schema/ERD cũ chỉ tham khảo, có thể sai; khoảng trống phải báo rõ, không tự bịa cột hoặc trạng thái.

## Form chung và nguyên tắc cấu hình

Mỗi mã hành động có công tắc bật/tắt, số lần ngày thường, từng ngày đặc biệt `YYYY-MM-DD` và số lần riêng, phạm vi đối tượng, khung giờ và các ô riêng ở bảng bên dưới. Không áp con số mặc định nghiệp vụ: người dùng nhập cấu hình.

Số ngày đặc biệt thay thế số ngày thường; không tự nhân hệ số sale. Không có override thì giữ số ngày thường. Số 0 nghĩa là không yêu cầu phát sinh hành động đó. Một lần được đếm theo định nghĩa của từng mã, không theo số dòng DB.

**Đề xuất cần chốt về xử lý hệ quả:** hành động xử lý hàng đợi có thể chọn “Theo số lần cấu hình” hoặc “Tự xử lý toàn bộ đầu vào đến hạn”. Chọn tự động thì hiện “Theo đầu vào” thay cho ô số lượng; cấu hình thời gian/kết quả vẫn áp dụng. Đây chưa phải ngoại lệ rule số lượng đã được duyệt. Giới hạn xử lý gây backlog phải được hiển thị, không âm thầm bỏ yêu cầu.

Manual là nhập cấu hình trước khi chạy hoặc chỉ định đối tượng/kết quả, không phải sửa SQL hay bấm từng giao dịch. Form thiếu thông tin bắt buộc phải báo ngay.

## Vị trí và nhóm tác động

Màn chính → Kho vận → Nhân viên kho / Nhân viên điều phối / Đơn vị vận chuyển mô phỏng / Tiến trình tự động.

Đọc catalog và mã SKU đã nhập; đọc yêu cầu đơn hàng. Không cào hoặc đồng bộ Tiki tại đây. Catalog mới không tự có hàng trong kho.

## 1. Nhân viên kho

| Mã | Hành động | Một lần | Ô cấu hình riêng |
|---|---|---|---|
| WH-01 | Nhập hàng | Một phiếu nhập, có thể nhiều SKU | Kho đích; SKU hợp lệ; số SKU/phiếu; số lượng mỗi SKU; lịch/độ trễ nhận; chọn tự động hoặc danh sách SKU–số lượng. |
| WH-02 | Kiểm kê và điều chỉnh tồn | Một cặp kho–SKU được điều chỉnh | Kho/SKU; tăng/giảm; khoảng chênh lệch hoặc tồn đếm thực; lý do. Không cho tồn thực tế thấp hơn lượng giữ nếu chưa có chính sách xử lý thiếu. |
| WH-03 | Xác nhận xuất hàng cho đơn | Một yêu cầu xuất hợp lệ | Chọn đơn/kho; thứ tự ưu tiên; độ trễ đóng gói/xuất. Phải có giữ hàng/điều kiện đơn hợp lệ. |
| WH-04 | Nhận lại hàng trả | Một yêu cầu nhận lại gắn dòng hàng và số lượng | Nguồn: trả sau giao/giao thất bại; kho nhận; thời gian; số lượng; tình trạng hàng; có thể tái nhập bán hay cách ly. Hàng cách ly chưa có mô hình riêng, xem giới hạn. |

## 2. Nhân viên điều phối

| Mã | Hành động | Một lần | Ô cấu hình riêng |
|---|---|---|---|
| DSP-01 | Tạo vận đơn | Một vận đơn cho đơn đủ điều kiện | Kho xuất; cách chọn carrier; tỷ trọng carrier; độ trễ; mô hình chi phí vận chuyển theo vùng hoặc giá chỉ định. |

Giai đoạn đầu đề xuất một vận đơn cho một đơn vật lý. Tách kiện, giao từng phần và chuyển kho chưa đưa vào phạm vi; không tự sinh nhiều shipment cho một đơn nếu chưa chốt cách đối soát.

## 3. Đơn vị vận chuyển mô phỏng

| Mã | Hành động | Một lần | Ô cấu hình riêng |
|---|---|---|---|
| CAR-01 | Lấy hàng | Một vận đơn được lấy | Carrier/phạm vi; độ trễ từ tạo vận đơn; khung giờ lấy. Phải phối hợp WH-03 để không trừ tồn hai lần. |
| CAR-02 | Cập nhật đang vận chuyển | Một vận đơn chuyển sang đang vận chuyển | Carrier; khoảng trễ từ lấy hàng; chọn đích nếu cần. |
| CAR-03 | Báo kết quả giao hàng | Một kết quả giao cuối cho vận đơn đang giao | Tỷ lệ Delivered/Failed tổng 100%; độ trễ theo vùng; lý do thất bại giả; tự chọn hoặc chỉ định kết quả. |
| CAR-04 | Trả kết quả thu COD | Một kết quả thu hộ gắn lần giao | Chọn đơn COD đã giao đủ điều kiện; độ trễ báo thu; số tiền theo nghĩa vụ đơn, không nhập tiền tùy ý. Không coi COD giao thất bại là đã thu. |

CAR-03 có một chính sách chọn kết quả, không có hai bộ tự xử lý Delivered/Failed giành cùng vận đơn. Nếu muốn số tuyệt đối mỗi kết quả thì form chia quota kết quả trong cùng hành động, tổng không vượt số được xử lý.

## 4. Tiến trình tự động

| Mã | Hành động | Một lần | Ô cấu hình riêng |
|---|---|---|---|
| AUT-WH-01 | Giữ hàng theo yêu cầu đặt đơn | Một yêu cầu giữ cho đơn | Quy tắc chọn kho; cho phép lấy từ mấy kho (giai đoạn đầu một); thời gian giữ; chính sách thiếu hàng. Không phát sinh yêu cầu nếu không có checkout. |
| AUT-WH-02 | Giải phóng hàng đã giữ | Một yêu cầu giải phóng gắn đơn/dòng | Nguồn hủy/hết hạn; phạm vi; độ trễ. Không xả toàn bộ tồn giữ theo SKU khi chỉ một đơn hủy. |
| AUT-WH-03 | Đề xuất bổ sung hàng | Một đề xuất nhập cho cặp kho–SKU | Ngưỡng tồn khả dụng; mức tồn mục tiêu; cách tính nhu cầu; độ trễ cung ứng; tự phê duyệt hay chờ người dùng. Nếu tự duyệt, WH-01 nhận cùng đề xuất, không sinh thêm phiếu nhập độc lập trùng. |
| AUT-WH-04 | Chốt số dư cuối ngày | Một lượt chốt cho một ngày | Phạm vi kho–SKU hoạt động; giờ chốt. Đây là một lượt chạy, không phải một lượt trên mỗi dòng số dư. Mỗi ngày tối đa một kết quả hiệu lực cho cùng kho–SKU. |

AUT-WH-01/02 và các bước vận đơn là xử lý đầu vào; có thể dùng chế độ tự xử lý nếu được chốt. AUT-WH-04 đề xuất chạy theo lịch cuối ngày, không cấu hình 100 lần chốt chỉ vì sale; nếu tắt phải cảnh báo thiếu số dư. WH-01 và nhập theo bổ sung tự động phải được phân nguồn để tránh tăng tồn hai lần.

## Bảng liên quan và ranh giới

| Phạm vi | Bảng dự kiến |
|---|---|
| Đọc đầu vào | `products`, `orders`, `order_items`, `returns`; cấu hình kho/carrier. |
| Quản lý tại đây | `warehouses`, `carriers`, `inventory_levels`, `inventory_movements`, `inventory_daily_balance`, `shipments`. |
| Tác động gửi đi | Kết quả giữ hàng cho đơn; kết quả giao cho đơn hàng; kết quả thu COD cho thanh toán; nhận hàng hoàn cho luồng trả/hoàn tiền. |

Kho không trực tiếp tạo khách, voucher, sửa giá catalog hoặc tự ghi tiền đối soát. Dữ liệu kho/carrier ban đầu là bước khởi tạo cấu hình riêng, không trộn với quota nhập hàng hằng ngày.

## Manual và giới hạn phải hiện

| Trường hợp | Form / giới hạn |
|---|---|
| Khởi tạo kho/carrier | Form mã, tên, vị trí và phạm vi phục vụ; người dùng duyệt cấu hình ban đầu. |
| Tồn đầu | Chọn kho/SKU và số lượng hoặc chính sách sinh tồn; tạo nhập đầu kỳ có nguồn rõ, không tự có sau sync. |
| Hàng hỏng không bán lại | Cần chính sách/mô hình cách ly; khi chưa có không tăng tồn bán được, UI báo chưa hỗ trợ luồng hoàn tất. |
| Hàng số | Không tồn vật lý hoặc vận đơn; không chọn vào hành động kho. Phân loại đầu vào cần được chốt. |
| COD | Schema cũ chưa có chứng từ thu hộ riêng; cần metadata hoặc mở rộng sau. Không giả vờ `shipments` đã chứa trạng thái thu tiền. |
| Thiếu/nhầm SKU hoặc kho không đủ hàng | Báo lỗi/không đủ điều kiện; không tự đổi SKU hoặc tạo hàng. |

## Preview, phụ thuộc và kiểm soát

- Preview theo ngày → nhóm → hành động: số yêu cầu, số có thể lên lịch, đối tượng, cấu hình hiệu lực và lý do thiếu. Sau chạy tách hoàn tất có thay đổi, không thay đổi, từ chối, lỗi và còn chờ.
- Chỉ dùng đối tượng hợp lệ tại thời điểm thực hiện; không tự tạo dữ liệu ở hệ thống khác để đủ quota. Không có đủ đầu vào thì báo thiếu.
- Hành động từ ngày trước có thể được xử lý hôm nay. Độ trễ phải được giữ; không ép mọi hệ quả hoàn tất trong ngày phát sinh.
- Một action ID chỉ hoàn tất một lần. Tiếp tục/retry không tạo tác động trùng. Cách lưu sẽ thiết kế sau.
- Phần bảng đọc/ghi nêu dưới đây chỉ là phạm vi dự kiến để đối chiếu. Chưa chốt cách ghi từng cột, transaction, nhật ký hoặc truyền sự kiện.

## Trạng thái quyết định

**Đã chốt chung:** cấu hình theo nhóm và hành động; số ngày đặc biệt thay thế ngày thường; không có số mặc định tự áp; đồng bộ Tiki độc lập và chỉ thêm mới.

**Đề xuất để review:** nhóm, danh sách hành động, đơn vị đếm, các ô riêng và chế độ xử lý theo đầu vào trong tài liệu này.

**Thiết kế sau:** chi tiết ghi dữ liệu, audit, đồng hồ có hiệu lực, chống lặp và truyền tác động giữa các hệ thống.
