# Cấu hình kịch bản mock — Web analytics

> Đã chuyển sang triển khai theo yêu cầu người dùng. Nội dung dưới đây là thiết kế; xem [trạng thái thực tế](MOCK_IMPLEMENTATION_STATUS.md) để biết tính năng đã chạy và giới hạn. Không hiểu “đã có thiết kế” là toàn bộ nghiệp vụ đã hoàn thành.

**Trạng thái:** Đề xuất danh sách hành động và form để chốt, chưa triển khai code/UI. Các rule chung đã xác nhận nằm trong [MOCK_SYSTEM_RULES.md](MOCK_SYSTEM_RULES.md). Schema/ERD cũ chỉ tham khảo, có thể sai; khoảng trống phải báo rõ, không tự bịa cột hoặc trạng thái.

## Form chung và nguyên tắc cấu hình

Mỗi mã hành động có công tắc bật/tắt, số lần ngày thường, từng ngày đặc biệt `YYYY-MM-DD` và số lần riêng, phạm vi đối tượng, khung giờ và các ô riêng ở bảng bên dưới. Không áp con số mặc định nghiệp vụ: người dùng nhập cấu hình.

Số ngày đặc biệt thay thế số ngày thường; không tự nhân hệ số sale. Không có override thì giữ số ngày thường. Số 0 nghĩa là không yêu cầu phát sinh hành động đó. Một lần được đếm theo định nghĩa của từng mã, không theo số dòng DB.

**Đề xuất cần chốt về xử lý hệ quả:** hành động xử lý hàng đợi có thể chọn “Theo số lần cấu hình” hoặc “Tự xử lý toàn bộ đầu vào đến hạn”. Chọn tự động thì hiện “Theo đầu vào” thay cho ô số lượng; cấu hình thời gian/kết quả vẫn áp dụng. Đây chưa phải ngoại lệ rule số lượng đã được duyệt. Giới hạn xử lý gây backlog phải được hiển thị, không âm thầm bỏ yêu cầu.

Manual là nhập cấu hình trước khi chạy hoặc chỉ định đối tượng/kết quả, không phải sửa SQL hay bấm từng giao dịch. Form thiếu thông tin bắt buộc phải báo ngay.

## Vị trí và nhóm tác động

Màn chính → Web analytics → Khách vãng lai / Khách đã đăng ký / Bộ mô phỏng phiên và hành vi / Bộ tiếp nhận kết quả giao dịch.

Bộ mô phỏng và bộ tiếp nhận là tiến trình kỹ thuật, không phải người dùng thật. Hành động xem catalog vẫn được nhóm khách thực hiện; không sinh hai lần chỉ vì có mặt ở hai màn.

## 1. Khách vãng lai

| Mã | Hành động | Một lần | Ô cấu hình riêng |
|---|---|---|---|
| GST-WEB-01 | Bắt đầu phiên truy cập | Một session mới của khách chưa đăng nhập | Kênh được hỗ trợ; traffic Organic/Paid Ads/Social/Direct/Email; thiết bị; thời lượng phiên; khung giờ; campaign hợp lệ nếu Paid. |
| GST-WEB-02 | Tìm kiếm | Một sự kiện search trong phiên | Phiên có sẵn; số/cụm từ tìm kiếm theo mẫu hoặc chỉ định; khoảng trễ; không tự tạo session mới khi thiếu. |
| GST-WEB-03 | Xem chi tiết sản phẩm | Một sự kiện view_product | Phạm vi sản phẩm; chọn đều/theo độ phổ biến; phiên đủ điều kiện; khoảng trễ giữa thao tác. |
| GST-WEB-04 | Thêm sản phẩm vào giỏ | Một hành động thêm SKU/sản phẩm trong phiên | Sản phẩm; số lượng; chọn mới/đã xem trước; khoảng trễ. Quy tắc gộp cùng sản phẩm sẽ chốt ở dữ liệu. |
| GST-WEB-05 | Bỏ sản phẩm khỏi giỏ | Một mục giỏ được bỏ | Giỏ Active; phạm vi; khoảng trễ. Giai đoạn đầu bỏ cả mục, chưa giảm một phần số lượng. |
| GST-WEB-06 | Bắt đầu checkout | Một sự kiện begin_checkout trên giỏ hợp lệ | Giỏ/phạm vi; khoảng trễ; chỉ ghi ý định analytics hoặc chuyển yêu cầu checkout: phải chọn rõ chế độ. |

## 2. Khách đã đăng ký

Có sáu hành động tương ứng mã `CUS-WEB-01` đến `CUS-WEB-06`: bắt đầu phiên, tìm kiếm, xem sản phẩm, thêm giỏ, bỏ mục giỏ, bắt đầu checkout. Mỗi mã có quota và form riêng như nhóm khách vãng lai, cộng bộ chọn customer ID hoặc tập khách hợp lệ. Không có khách phù hợp thì báo thiếu; đăng ký thuộc hệ thống Khách hàng & Đơn hàng.

Không đưa đăng nhập/đăng xuất vào danh sách khi chưa có mô hình xác thực. Không tự chuyển một session guest thành registered rồi giả định đã có tài khoản.

## 3. Bộ mô phỏng phiên và hành vi

| Mã | Hành động | Một lần | Ô cấu hình riêng |
|---|---|---|---|
| AUT-WEB-01 | Kết thúc phiên đến hạn | Một phiên kết thúc | Timeout/thời lượng; độ trễ; tập phiên. Không thêm enum event_type `end_session` trái schema. |
| AUT-WEB-02 | Đánh dấu giỏ bị bỏ | Một mục giỏ đủ hạn chuyển Abandoned | Ngưỡng không hoạt động; điều kiện phiên đã kết thúc/chưa checkout thành công; khoảng trễ. Một giỏ nhiều mục có thể tạo nhiều lần theo định nghĩa mục giỏ. |
| AUT-WEB-03 | Sinh chuỗi hành vi theo phiên | Một kế hoạch hành vi cho một phiên | Số bước; xác suất chuyển bước; thời gian giữa bước; phân bố sản phẩm; tỷ lệ kết thúc/bỏ giỏ/checkout; nguồn customer/traffic. |

**Hai chế độ loại trừ nhau trên cùng phạm vi:**

- “Theo từng hành động”: người dùng nhập số riêng cho các hành động khách ở mục 1–2; tắt AUT-WEB-03 cho phạm vi đó.
- “Theo kịch bản phiên”: số phiên và form chuỗi hành vi là đầu vào; các số tìm kiếm/xem/thêm giỏ/checkout được suy ra, hiện chỉ đọc. Không giữ quota độc lập rồi sinh thêm lần nữa.

Nếu cấu hình tỷ lệ nhánh phải tổng 100% cho cùng một lựa chọn. Đây là đề xuất cách điều khiển, cần chốt trước khi triển khai, không tự thay số hành động người dùng đã nhập.

## 4. Bộ tiếp nhận kết quả giao dịch

| Mã | Hành động | Một lần | Ô cấu hình riêng |
|---|---|---|---|
| EVT-WEB-01 | Ghi nhận kết quả đặt hàng | Một purchase event gắn một đơn được hệ thống đơn hàng xác nhận tạo thành công | Cách liên kết session/checkout; độ trễ ghi nhận; chỉ nhận giao dịch thật trong mock. Giai đoạn đầu đề xuất một event/đơn, nhiều shop có thể nhiều event trong một checkout. |
| EVT-WEB-02 | Đóng mục giỏ đã đặt | Một mục giỏ được xác nhận Ordered | Yêu cầu checkout thành công; liên kết mục giỏ; độ trễ. Checkout thất bại không tự đóng giỏ là Ordered. |

Không có quota purchase độc lập để tự tạo doanh thu. Purchase biểu thị tạo đơn theo định nghĩa đề xuất ở đây, không tự có nghĩa thanh toán/giao hàng thành công. Nếu muốn đổi nghĩa, phải chốt trước và dùng nhất quán.

## Một nguồn kế hoạch cho các màn

- Các hành động VIS-01 ở Catalog & Seller là góc nhìn cấu hình của cùng hành động xem sản phẩm; không thêm 100 lượt VIS và thêm 100 lượt WEB khi mục tiêu chỉ là 100.
- Hành động checkout do analytics phát yêu cầu và hành động đặt hàng trong Khách hàng & Đơn hàng phải chọn **một nơi làm nguồn sản lượng**. Form hiện bộ chọn “Nguồn checkout: cấu hình đơn hàng / kịch bản phiên”. Nơi còn lại chỉ nhận/hiển thị kết quả liên kết.
- Traffic Paid dùng campaign/click khả dụng của Marketing. Thiếu nguồn thì báo thiếu, không tự tạo ngân sách hoặc click. Không giả định một click luôn một phiên nếu chưa chốt mô hình.
- Đơn hàng có thể không có session khi chọn nguồn đặt trực tiếp; không tạo phiên giả hồi tố chỉ để lấp mọi trường nullable.

## Bảng liên quan và ranh giới

Đọc `products`, `sellers`, `categories`, `customers`, `marketing_campaigns`, số liệu click và kết quả đơn. Phạm vi ghi chính là `sessions`, `page_events`, `cart_items`. Yêu cầu mua hàng chuyển sang hệ thống đơn hàng; analytics không trực tiếp tạo `payments`, trừ kho hoặc sửa giá.

## Manual và giới hạn phải hiện

| Trường hợp | Form / giới hạn |
|---|---|
| Kịch bản truy cập cụ thể | Form chuỗi bước có loại hành động, khoảng trễ, đối tượng; có thể dùng mẫu rồi chỉnh, không bắt nhập JSON. |
| Từ khóa tìm kiếm | Ô danh sách từ khóa; schema chưa có cột lưu query, cần metadata hoặc mở rộng sau. |
| Xem danh mục/shop | Chưa có event/cột đích phù hợp; hiện chưa hỗ trợ ghi nghiệp vụ, không tự thêm enum. |
| Ràng buộc campaign | Bộ chọn campaign đang hiệu lực; thiếu dữ liệu thì báo chưa sẵn sàng. |
| Nhận diện khách vãng lai qua nhiều phiên | Schema chưa có visitor ID; giai đoạn đầu không hứa phân tích unique guest chính xác. |
| Liên kết checkout nhiều shop | Cần metadata checkout; chưa có khóa checkout chung trong schema cũ. |

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
