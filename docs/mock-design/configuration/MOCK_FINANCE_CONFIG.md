# Cấu hình kịch bản mock — Tài chính

> Đã chuyển sang triển khai theo yêu cầu người dùng. Nội dung dưới đây là thiết kế; xem [trạng thái thực tế](../reviews/MOCK_IMPLEMENTATION_STATUS.md) để biết tính năng đã chạy và giới hạn. Không hiểu “đã có thiết kế” là toàn bộ nghiệp vụ đã hoàn thành.

**Trạng thái:** Đề xuất danh sách hành động và form để chốt, chưa triển khai code/UI. Các rule chung đã xác nhận nằm trong [MOCK_SYSTEM_RULES.md](../MOCK_SYSTEM_RULES.md). Schema/ERD cũ chỉ tham khảo, có thể sai; khoảng trống phải báo rõ, không tự bịa cột hoặc trạng thái.

## Form chung và nguyên tắc cấu hình

Mỗi mã hành động có công tắc bật/tắt, số lần ngày thường, từng ngày đặc biệt `YYYY-MM-DD` và số lần riêng, phạm vi đối tượng, khung giờ và các ô riêng ở bảng bên dưới. Không áp con số mặc định nghiệp vụ: người dùng nhập cấu hình.

Số ngày đặc biệt thay thế số ngày thường; không tự nhân hệ số sale. Không có override thì giữ số ngày thường. Số 0 nghĩa là không yêu cầu phát sinh hành động đó. Một lần được đếm theo định nghĩa của từng mã, không theo số dòng DB.

**Đề xuất cần chốt về xử lý hệ quả:** hành động xử lý hàng đợi có thể chọn “Theo số lần cấu hình” hoặc “Tự xử lý toàn bộ đầu vào đến hạn”. Chọn tự động thì hiện “Theo đầu vào” thay cho ô số lượng; cấu hình thời gian/kết quả vẫn áp dụng. Đây chưa phải ngoại lệ rule số lượng đã được duyệt. Giới hạn xử lý gây backlog phải được hiển thị, không âm thầm bỏ yêu cầu.

Manual là nhập cấu hình trước khi chạy hoặc chỉ định đối tượng/kết quả, không phải sửa SQL hay bấm từng giao dịch. Form thiếu thông tin bắt buộc phải báo ngay.

## Vị trí và nhóm tác động

Màn chính → Tài chính → Nhân viên quản lý chính sách hoa hồng / Nhân viên đối soát / Dịch vụ chi trả mô phỏng / Người bán tra cứu / Tiến trình tự động.

Tài chính đọc giao dịch đã phát sinh; không tạo đơn hoàn tất, thanh toán thành công hoặc trả hàng giả để có doanh thu/đủ quota đối soát.

## 1. Nhân viên quản lý chính sách hoa hồng

| Mã | Hành động | Một lần | Ô cấu hình riêng |
|---|---|---|---|
| FIN-POL-01 | Tạo chính sách hoa hồng | Một chính sách cho danh mục–hạng seller–khoảng hiệu lực | Danh mục; hạng Normal/Preferred/Mall; tỷ lệ; ngày bắt đầu/kết thúc; chọn từng cặp hoặc mẫu áp nhiều cặp, preview số chính sách sẽ tạo. |
| FIN-POL-02 | Thay chính sách cho kỳ tương lai | Một cặp danh mục–hạng có chính sách kế tiếp | Chính sách hiện tại; tỷ lệ mới; ngày hiệu lực tương lai; ngày kết thúc; kiểm tra không chồng khoảng. Không sửa tỷ lệ của giao dịch cũ. |

Mỗi chính sách đếm một lần, một mẫu áp 10 cặp là 10 chính sách. Chốt chi tiết cách khép khoảng cũ và giữ nguyên chứng từ sau; không tạo hai chính sách cùng hiệu lực để giải thích theo chọn ngẫu nhiên.

## 2. Nhân viên đối soát

| Mã | Hành động | Một lần | Ô cấu hình riêng |
|---|---|---|---|
| FIN-REC-01 | Lập đối soát seller | Một seller trong một kỳ được lập đối soát | Seller/tập seller; lịch kỳ tuần/tháng/tùy chọn ngày đầu–cuối; độ trễ sau đóng kỳ; chính sách đơn đủ điều kiện, hoàn hàng và bên chịu voucher; ngưỡng trả tối thiểu nếu có. |
| FIN-REC-02 | Kiểm tra và duyệt chi | Một hồ sơ đối soát được duyệt đủ điều kiện chuyển tiền | Cách chọn hồ sơ; thời gian kiểm tra; ngưỡng bất thường; chọn tự động/chỉ định kết quả duyệt hoặc giữ chờ. Chưa có trạng thái duyệt riêng trong schema. |

Không nhập tùy ý tổng doanh thu, phí và tiền phải trả để ép đạt mục tiêu. Có thể cấu hình số hồ sơ xử lý/ngày nhưng nội dung phải từ giao dịch hợp lệ. Mỗi seller–kỳ chỉ có một hồ sơ hiệu lực trong phạm vi ban đầu; chạy lại không tạo khoản phải trả thứ hai.

## 3. Dịch vụ chi trả mô phỏng

| Mã | Hành động | Một lần | Ô cấu hình riêng |
|---|---|---|---|
| FIN-PAY-01 | Trả kết quả chi tiền seller | Một lệnh chi đủ điều kiện nhận kết quả | Phạm vi seller/kỳ; độ trễ; mô hình thành công/treo/chưa thành công ở metadata; nếu chỉ định hiện hồ sơ và kết quả. Không gọi ngân hàng hoặc chuyển tiền thật. |

Schema `seller_payouts.payout_status` chỉ có Pending/Paid; thất bại hoặc chờ không tự đổi thành enum Failed. Trạng thái lần thử cần metadata/mô hình sau. Không cho đánh dấu Paid khi chưa có nghĩa vụ hợp lệ; không chi lại khoản đã hoàn tất.

## 4. Người bán tra cứu

| Mã | Hành động | Một lần | Ô cấu hình riêng |
|---|---|---|---|
| FIN-SEL-01 | Xem đối soát của shop | Một lượt tra cứu một hồ sơ/kỳ | Seller; kỳ hoặc cách chọn kỳ; số lượt theo ngày. Chỉ hồ sơ của chính shop. |

Đây là đọc, không cập nhật số tiền hoặc trạng thái. Schema chưa có nhật ký truy cập tài chính; nếu cần đếm thực hiện chỉ lưu metadata điều khiển, không tự tạo payment hoặc session analytics.

Yêu cầu khiếu nại đối soát hoặc rút tiền theo yêu cầu chưa đưa vào phạm vi vì cần mô hình và chính sách bổ sung.

## 5. Tiến trình tự động

| Mã | Hành động | Một lần | Ô cấu hình riêng |
|---|---|---|---|
| AUT-FIN-01 | Chạy lịch lập kỳ | Một lượt xử lý lịch cho ngày đang chạy | Lịch đóng kỳ; tập seller; độ trễ; chính sách tạo hồ sơ rỗng hay bỏ qua khi không có giao dịch. Gọi cùng luồng FIN-REC-01, không tạo bản ghi song song. |
| AUT-FIN-02 | Tiếp nhận điều chỉnh do hoàn tiền | Một nghĩa vụ điều chỉnh gắn giao dịch gốc | Nguồn hoàn; cách chọn; thời gian hiệu lực; nguyên tắc đưa vào kỳ chưa chốt/kỳ tiếp theo. Không điều chỉnh hai lần cho cùng nghĩa vụ. |
| AUT-FIN-03 | Xếp lệnh chi đến hạn | Một hồ sơ đã duyệt đến hạn được xếp chi | Lịch trả tiền; ngưỡng tối thiểu; thời gian chờ; phạm vi. Kết quả do FIN-PAY-01 xử lý. |

AUT-FIN-01 là một lượt chạy có thể sinh nhiều hồ sơ, không đếm nhầm một lượt bằng một seller. Khi bật tự lập kỳ, FIN-REC-01 là bộ xử lý dùng chung, không phát thêm hồ sơ từ quota độc lập. Với điều chỉnh và chi trả, chế độ theo đầu vào chỉ chạy khi được chốt; backlog phải nhìn thấy.

## Bảng liên quan và ranh giới

| Phạm vi | Bảng dự kiến |
|---|---|
| Đọc | `sellers`, `products`, `categories`, `orders`, `order_items`, `payments`, `returns`, `promotions`, `order_item_promotions`; sự kiện giao/hoàn liên quan. |
| Quản lý chính | `seller_commission_rates`, `seller_payouts`. |
| Cần mô hình điều khiển | Duyệt đối soát, lần thử chi trả, điều chỉnh và giá trị/chính sách đã chốt tại giao dịch. |

Đổi hạng seller hoặc danh mục sản phẩm về sau không được hồi tố hoa hồng của giao dịch cũ. Catalog hiện tại không đủ để tính lại chính xác nếu đã thay đổi; cơ chế chốt thuộc tính tại giao dịch sẽ thiết kế sau, không tự coi schema cũ đã lưu đủ.

## Manual và giới hạn phải hiện

| Trường hợp | Form / giới hạn |
|---|---|
| Chính sách mới | Ô danh mục, hạng, tỷ lệ, khoảng hiệu lực; báo chồng kỳ/thiếu chính sách. |
| Đối soát kỳ đặc biệt | Ô đầu–cuối kỳ, seller, thời gian lập/chi; kiểm tra không tính trùng các nghĩa vụ. |
| Tiền âm, hoàn lớn hơn doanh thu kỳ | Cần chốt chuyển dư sang kỳ sau hay cơ chế thu hồi. Khi chưa chốt, giữ chờ và báo lý do, không giả lập chuyển tiền âm. |
| Hoàn sau kỳ đã trả | Cần chính sách điều chỉnh kỳ sau/thu hồi; không sửa hồ sơ Paid hoặc giả vờ đã lấy tiền lại. |
| Khiếu nại, thuế, hóa đơn, tài khoản ngân hàng | Ngoài phạm vi hiện tại; schema chưa đủ. Không yêu cầu người dùng nhập thông tin tài chính thật. |
| Duyệt/treo/thất bại chi | Form kết quả chỉ định ở metadata; không thêm enum hoặc cột nghiệp vụ chưa thống nhất. |

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
