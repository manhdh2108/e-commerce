# Cấu hình kịch bản mock — Marketing

> Đã chuyển sang triển khai theo yêu cầu người dùng. Nội dung dưới đây là thiết kế; xem [trạng thái thực tế](MOCK_IMPLEMENTATION_STATUS.md) để biết tính năng đã chạy và giới hạn. Không hiểu “đã có thiết kế” là toàn bộ nghiệp vụ đã hoàn thành.

**Trạng thái:** Đề xuất danh sách hành động và form để chốt, chưa triển khai code/UI. Các rule chung đã xác nhận nằm trong [MOCK_SYSTEM_RULES.md](MOCK_SYSTEM_RULES.md). Schema/ERD cũ chỉ tham khảo, có thể sai; khoảng trống phải báo rõ, không tự bịa cột hoặc trạng thái.

## Form chung và nguyên tắc cấu hình

Mỗi mã hành động có công tắc bật/tắt, số lần ngày thường, từng ngày đặc biệt `YYYY-MM-DD` và số lần riêng, phạm vi đối tượng, khung giờ và các ô riêng ở bảng bên dưới. Không áp con số mặc định nghiệp vụ: người dùng nhập cấu hình.

Số ngày đặc biệt thay thế số ngày thường; không tự nhân hệ số sale. Không có override thì giữ số ngày thường. Số 0 nghĩa là không yêu cầu phát sinh hành động đó. Một lần được đếm theo định nghĩa của từng mã, không theo số dòng DB.

**Đề xuất cần chốt về xử lý hệ quả:** hành động xử lý hàng đợi có thể chọn “Theo số lần cấu hình” hoặc “Tự xử lý toàn bộ đầu vào đến hạn”. Chọn tự động thì hiện “Theo đầu vào” thay cho ô số lượng; cấu hình thời gian/kết quả vẫn áp dụng. Đây chưa phải ngoại lệ rule số lượng đã được duyệt. Giới hạn xử lý gây backlog phải được hiển thị, không âm thầm bỏ yêu cầu.

Manual là nhập cấu hình trước khi chạy hoặc chỉ định đối tượng/kết quả, không phải sửa SQL hay bấm từng giao dịch. Form thiếu thông tin bắt buộc phải báo ngay.

## Vị trí và nhóm tác động

Màn chính → Marketing → Nhân viên marketing sàn / Người bán tạo ưu đãi / Nền tảng quảng cáo mô phỏng / Tiến trình tự động.

Khách áp voucher tại checkout thuộc hệ thống Khách hàng & Đơn hàng. Marketing cung cấp điều kiện/ưu đãi, không tạo lại hành động khách đặt đơn.

## 1. Nhân viên marketing sàn

| Mã | Hành động | Một lần | Ô cấu hình riêng |
|---|---|---|---|
| MKT-01 | Tạo chiến dịch | Một campaign mới | Tên/mẫu tên; loại Mega Sale/Flash Sale/Brand Awareness/Retargeting/Livestream Show; mã kênh WEB/MOBILE_APP/LIVE; ngân sách; ngày bắt đầu/kết thúc; độ trễ từ tạo đến chạy. |
| MKT-02 | Điều chỉnh ngân sách chiến dịch | Một campaign được đổi ngân sách | Campaign hợp lệ; tăng/giảm hoặc số tiền đích; thời điểm hiệu lực; không thấp hơn phần chi đã cam kết theo chính sách sẽ chốt. |
| MKT-03 | Tạo voucher sàn | Một mã voucher mới | Tên/mẫu mã; phạm vi Order/Item; nếu Item hiện sản phẩm; Fixed Amount/Percentage; giá trị; trần giảm; đơn tối thiểu; eligibility; thời gian hiệu lực; tổng lượt và lượt/khách. |
| MKT-04 | Tạo voucher freeship | Một mã freeship mới | Phạm vi Shipping; mức/kiểu giảm; trần; đơn tối thiểu; eligibility; thời gian; giới hạn lượt. |

Một campaign không tự có voucher hoặc quảng cáo; muốn phát sinh phải bật hành động tương ứng. Ngày tạo khác ngày bắt đầu campaign/voucher. Số ngày đặc biệt áp vào ngày hành động tạo, không tự hiểu là ngày có hiệu lực.

## 2. Người bán tạo ưu đãi

| Mã | Hành động | Một lần | Ô cấu hình riêng |
|---|---|---|---|
| SHOP-MKT-01 | Tạo voucher shop | Một mã voucher thuộc shop | Shop Active; phạm vi Order/Item; sản phẩm thuộc shop nếu Item; kiểu/mức giảm; trần; đơn tối thiểu; thời gian; giới hạn lượt; eligibility được hỗ trợ. |

Không cho shop phát voucher sàn, dùng sản phẩm shop khác hoặc tự quyết phần trợ giá do sàn chịu. Đổi giá catalog không nằm ở Marketing.

## 3. Nền tảng quảng cáo mô phỏng

| Mã | Hành động | Một lần | Ô cấu hình riêng |
|---|---|---|---|
| ADS-01 | Trả báo cáo quảng cáo theo ngày | Một báo cáo cho campaign–kênh–ngày hoạt động | Campaign; kênh; khoảng chi ngày hoặc chính sách phân ngân sách; CPM/CPC lựa chọn rõ một mô hình; CTR hoặc miền impressions/clicks; độ trễ báo cáo; có thể chỉ định số liệu cụ thể. |

Số lần ADS-01 là số báo cáo, không phải số impressions/clicks. Các chỉ số nằm trong form báo cáo; không tăng số báo cáo để tăng lượng truy cập. Đề xuất một báo cáo cuối cùng cho một campaign–kênh–ngày; giới hạn không tạo trùng cùng khóa đó. Chỉnh báo cáo muộn/tái công bố chưa đưa vào phạm vi vì cần chính sách phiên bản.

Impressions, clicks, chi phí phải nhất quán với mô hình và ngân sách; không cam kết mọi click đều thành session hoặc mua hàng. Analytics tiêu thụ nguồn traffic quảng cáo chung, không sinh thêm click thứ hai để khớp đơn.

## 4. Tiến trình tự động

| Mã | Hành động | Một lần | Ô cấu hình riêng |
|---|---|---|---|
| AUT-MKT-01 | Kiểm tra và giữ lượt voucher cho checkout | Một yêu cầu dùng một voucher | Thứ tự áp; chính sách cộng dồn; giữ lượt bao lâu; điều kiện khách; phạm vi. Chọn từ voucher còn hiệu lực, không tạo mới để đủ tỷ lệ. |
| AUT-MKT-02 | Hoàn lượt voucher khi đơn hủy | Một yêu cầu hoàn lượt sử dụng hợp lệ | Trường hợp được hoàn; hạn/độ trễ hoàn lượt; chỉ một lần trên quyền sử dụng đã giữ/đã chốt. |
| AUT-MKT-03 | Đánh giá hiệu lực theo thời gian | Một lượt kiểm tra lịch | Lịch kiểm tra; thời gian bắt đầu/kết thúc lấy từ campaign/voucher. Không buộc đổi trạng thái trong bảng khi schema chưa có cột status. |

Các kiểm tra điều kiện có thể tính trực tiếp khi dùng voucher thay vì sinh hàng loạt tác vụ; lựa chọn thực thi bàn sau. Không cấu hình quota để voucher hết hạn vẫn dùng được vì chưa đến lượt kiểm tra. Các hành động này xử lý hệ quả, không tạo nhu cầu checkout.

## Bảng liên quan và ranh giới

| Phạm vi | Bảng dự kiến |
|---|---|
| Đọc | `products`, `sellers`, thông tin khách/đơn phục vụ điều kiện và lượt dùng. |
| Quản lý | `promotions`, `marketing_campaigns`, `ad_spend_logs`. |
| Liên kết giao dịch | `order_item_promotions`, `orders.shipping_promotion_id`: một luồng áp dụng tại checkout, không hai module tự ghi trùng. Quyền ghi cụ thể thiết kế sau. |
| Tác động ra ngoài | Nguồn traffic Paid cho analytics; ưu đãi đủ điều kiện cho checkout; dữ liệu chi phí/khuyến mãi cho đối soát liên quan. |

## Manual và giới hạn phải hiện

| Trường hợp | Form / giới hạn |
|---|---|
| Muốn mã, campaign hoặc voucher cụ thể | Ô mẫu mã/tên hoặc danh sách chỉ định; validate mã trùng và ngày hiệu lực. |
| Cộng dồn và bên chịu chi phí | Form chính sách được lựa chọn; chưa có chính sách thì không bật luồng áp dụng tự động. |
| Chỉ số quảng cáo đặc biệt | Ô nhập chi phí, impression, click theo ngày; kiểm tra tính khả thi, không JSON bắt buộc. |
| Giữ lượt, tiêu lượt và hoàn lượt | Schema cũ chưa có bảng ledger lượt dùng; cần metadata/mô hình sau, không tăng/giảm `usage_limit` để giả làm lượt còn. |
| Dừng campaign, thu hồi/sửa voucher đã dùng | Chưa đưa vào phạm vi ban đầu vì thiếu trạng thái/lịch sử phù hợp; không xóa dữ liệu để mô phỏng dừng. |
| Liên kết campaign–voucher | Schema hiện chưa có quan hệ trực tiếp; nếu muốn gắn phải cấu hình ở metadata hoặc chốt mở rộng. |

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
