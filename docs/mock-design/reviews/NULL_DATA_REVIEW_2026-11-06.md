# Kiểm tra NULL và yêu cầu trước khi viết config mới — 06/11/2026

## Phạm vi

Kiểm tra trực tiếp PostgreSQL `mock_oltp.public`, Control DB, SQLite crawler ở chế độ chỉ đọc, cùng code sinh dữ liệu. Không sửa dữ liệu, schema hoặc config. Business snapshot dùng transaction REPEATABLE READ, READ ONLY.

Lượt `97f7dddd-f285-42a6-8d22-ffdfd0b2b73e` đã COMPLETE đến 05/01/2026, hoàn tất lúc 00:15:10 ngày 06/11/2026 (UTC+7). Có 124 đơn, 105 checkout, 524 khách, 106 vận đơn, 3 yêu cầu trả và 1 khoản hoàn Pending. Đây là kết quả sau hoàn tất, thay cho số tạm thời trong báo cáo kiểm tra khi còn chạy.

**Kết luận:** nhiều NULL đúng ngữ nghĩa hoặc đúng trạng thái. Một số cột thiếu dữ liệu toàn bộ do config, giới hạn code hoặc nguồn crawler. Không được thay toàn bộ NULL bằng 0/chuỗi giả để làm đầy bảng. Validator riêng job hiện tại kiểm tra 12 nhóm, 0 lỗi; điều đó chưa chứng minh mọi nhánh hoặc mọi cột đều được mô phỏng đầy đủ.

## 1. Có thể cải thiện bằng config hiện tại

| Trường | Hiện trạng | Nguyên nhân và việc phải ghi nhớ cho config mới |
|---|---|---|
| `sessions.campaign_id` | 1.575/1.575 NULL | Campaign duy nhất target APP, nhưng variants phiên gắn `campaign=auto` lại ở Web; App Direct không gắn campaign. Phải cấu hình campaign đúng kênh, tạo trước phiên, có biến thể paid traffic phù hợp. Giữ NULL cho các phiên không được attribution |
| `orders.campaign_id` | 124/124 NULL | Kế thừa attribution của phiên. Không fill ID tùy tiện ở đơn; sửa đầu vào phiên trước |
| `customer_addresses.district` | 99/99 NULL | Cả 24 bộ địa phương trong hồ sơ đều để district=null. Có thể nhập chuỗi district nhất quán với bộ tỉnh/đường/phường mô phỏng. Không bắt buộc điền 100%; không khẳng định các địa phương tổng hợp là địa giới thật |
| `products.short_description` | 149/149 chuỗi rỗng | Crawler/raw đã rỗng; hành động SEL-05 sửa mô tả đang tắt. Có thể bật SEL-05, dùng nội dung mô phỏng và variants trên một phần sản phẩm. Đây là hành động seller trong mock, không phải đồng bộ lại ghi đè dữ liệu Tiki |
| `orders.cancelled_at`, `orders.cancellation_reason` | 124/124 NULL | Hiện không có đơn Cancelled; GST-03/CUS-07 đang tắt. Có thể thêm một lượng yêu cầu hủy hợp lý, nhưng phải có đơn còn đủ điều kiện. SYS-01 đã bật không đảm bảo sẽ phát sinh hủy khi chưa đến hạn hoặc đơn đã thanh toán |
| `returns.decision_reason` | 3/3 NULL | Cả ba được duyệt; code chỉ ghi lý do cho từ chối SUP-02, đang tắt. Có thể thêm kịch bản từ chối có lý do khi có yêu cầu Requested; SUP-01 chế độ all sẽ duyệt hết nếu chạy trước, nên cần điều phối quota/thứ tự để còn đầu vào. Không tự coi mọi duyệt trả phải có lý do theo schema hiện tại |

Điền dữ liệu bằng config chỉ có tác dụng cho hành động/lượt mới tương ứng. Lưu hồ sơ địa phương không tự cập nhật 99 địa chỉ đã sinh; sửa config không thay snapshot job đã hoàn tất.

## 2. Không giải quyết được chỉ bằng config hiện tại

| Trường | Hiện trạng | Kết luận |
|---|---|---|
| `customers.gender`, `customers.date_of_birth` | Mỗi cột 524/524 NULL | Bộ sinh person không ghi hai trường, hành động sửa hồ sơ hiện chỉ đổi tên/địa phương. Nếu cần phân khúc nhân khẩu học phải bổ sung code + config tỷ lệ điền, phân bố tuổi, giá trị chưa khai báo. Không suy giới tính từ tên hoặc tự bịa ngày sinh bằng config không được hỗ trợ |
| `sellers.phone` | 9/9 NULL | Code sync tạo seller tối thiểu không ghi phone; hiện không có tham số hành động để điền phone. Cần thêm bộ sinh hồ sơ người bán hoặc nghiệp vụ cập nhật trường này. Phải tôn trọng ID seller và append-only của đồng bộ |
| `products.cost_price` | 149/149 NULL | Sync chủ động để NULL; crawler không cung cấp giá vốn. Không có hành động hiện tại để cấu hình giá vốn. Nếu muốn tính lãi hàng hóa cần bộ sinh giá vốn giả định có rule rõ, không gắn nhãn là dữ liệu Tiki thật. NULL chưa làm sai công thức doanh thu/hoa hồng sàn nhưng chưa tính được biên lợi nhuận theo giá vốn |
| `inventory_movements.reference_code` | 5/1.009 NULL | Chính xác năm phiếu nhập WH-01 mỗi ngày +20 không gán reference_code trong code. Số lượng/sổ kho vẫn khớp, nhưng thiếu mã chứng từ để truy vết. Chưa có config điền reference; cần code sinh mã phiếu ổn định liên kết hành động. Không sửa trực tiếp DB để che thiếu sót |
| `promotions.product_id`, `promotions.max_discount_amount` | Mỗi cột 3/3 NULL | Hợp lệ cho voucher Order/Shipping giảm số tiền cố định hiện tại. Tuy nhiên muốn thêm voucher riêng sản phẩm hoặc phần trăm có trần thì bộ tạo hiện ghi cứng apply_level/discount_type; cần nâng cấp code, không chỉ truyền tham số mới vào JSON |

## 3. Thiếu từ dữ liệu nguồn: không được dùng config để giả làm dữ liệu Tiki thật

Đã đối chiếu SQLite `products` và `product_raw`:

- `products.stock_item`: NULL 149/149 ở cả OLTP, SQLite và raw. Không dùng trường này làm số tồn mock; tồn vận hành nằm ở `inventory_levels` và ledger biến động.
- `products.quantity_sold`: NULL 93/149, đúng 93 raw không có giá trị. Đây là thống kê nguồn Tiki tại lúc cào, không phải tổng lượng bán trong DB mock. Không thay NULL thành 0 hoặc tăng nó theo đơn mock.
- `products.brand_name`: chuỗi rỗng 149/149; raw không có khóa brand. Cần kiểm tra endpoint/thuộc tính nguồn nếu muốn bổ sung dữ liệu thật. Không tự suy tên thương hiệu từ tên sách.
- `products.inventory_status`, `products.short_description`, `products.type`: chuỗi rỗng 149/149; raw hiện cũng rỗng, không phải dữ liệu có giá trị bị mất khi đồng bộ.

Thay đổi crawler ở tương lai không tự backfill các sản phẩm đã đồng bộ: rule append-only vẫn giữ nguyên. Nếu muốn enrichment cho bản ghi cũ phải thiết kế luồng/quy tắc riêng; chưa được tự cập nhật đè qua sync. Riêng mô tả có thể thay đổi bằng hành động seller mô phỏng như mục 1, với nội dung được nhận diện là tổng hợp.

## 4. NULL đúng theo quan hệ hoặc trạng thái

| Nhóm trường | Kiểm tra thực tế và cách hiểu |
|---|---|
| `categories.parent_id` | Chỉ 1/6 NULL: danh mục gốc id 8322, level 1. Không phải tất cả danh mục mất cha |
| Các `customer_id` | 945 phiên vãng lai, 126 dòng giỏ, 26 checkout, 32 đơn và 26 địa chỉ không có tài khoản. Một checkout nhiều shop có thể tạo nhiều đơn. Không ép ID khách đăng ký vào các giao dịch guest |
| `orders.completed_at` | 49 NULL = 47 Processing + 2 Pending. Cả 75 Completed đều có thời gian hoàn tất |
| `orders.shipping_promotion_id` | 52 NULL: không phải mọi đơn đều được voucher phí giao. Không fill promotion giả |
| `shipments.delivered_at` | 31 NULL, khớp 31 In Transit. Cả 75 Delivered đều có thời gian giao |
| `shipments.failed_at`, `returned_at` | Mỗi cột 106 NULL. Hiện không còn shipment Failed/Returned. Ledger delivery_attempts có 3 lần Failed; retry có thể xóa failed_at trạng thái hiện tại. Lịch sử thất bại phải đọc ledger, không kết luận chưa từng giao thất bại |
| `returns.received_at` | 2 NULL tương ứng 2 Approved chưa nhận hàng; 1 Received đã có thời gian nhận |
| `returns.refunded_at` | 3 NULL vì chưa có hoàn tiền hoàn tất. Yêu cầu Received đã sinh khoản refund Pending |
| `refunds.completed_at` | 1/1 NULL cho Pending tạo ngày 05/01 lúc 21:49:05. PAY-02 có delay_days=1 trong kế hoạch nên chưa đến hạn kết thúc tại 05/01 |
| `promotions.seller_id` | 2/3 NULL cho voucher sàn và freeship; voucher seller có seller_id |
| `promotion_usages.released_at` | 144/144 NULL: chưa có hủy/giải phóng các quyền sử dụng này. Không đồng nhất kết thúc lượt chạy với release voucher |
| `page_events.product_id`, `order_id`, `search_keyword` | Tùy loại sự kiện: không phải sự kiện nào cũng có sản phẩm, đơn hoặc từ khóa. Kiểm tra các sự kiện view/add/remove sản phẩm không thiếu product_id, purchase không thiếu order_id, search không thiếu keyword |

Ngoài các thời điểm trên, kiểm tra 99 thanh toán Success đều có transaction_time. Không phát hiện NULL bất hợp lý trong các điều kiện bắt buộc theo trạng thái đã kiểm tra. Các FK quan trọng đang có giá trị không bị thay thế bằng mã giả chỉ để tránh NULL.

## 5. Bảng trống

`seller_payouts` và `seller_payout_items` hiện 0 dòng. Không phải thiếu config bật đối soát: các bộ xử lý tài chính đã bật. Mới mô phỏng 5 ngày, chính sách giữ tiền 8 ngày tính theo đơn và còn chặn các nghĩa vụ liên quan. Phải chạy đủ thời gian/đủ điều kiện; không tạo payout sớm để lấp bảng. Không có bảng NULL toàn bộ theo nghĩa tồn tại một dòng chứa toàn giá trị NULL; cần phân biệt bảng chưa có dòng với cột NULL.

## 6. Checklist bắt buộc khi thiết kế config mới

1. Tạo attribution theo đúng kênh và đúng ngày chiến dịch. Kiểm tra đầu ra có cả phiên/đơn có campaign và phiên/đơn không có campaign.
2. Hồ sơ địa phương có các bộ đầy đủ/thiếu district hợp lý; không tăng count để kỳ vọng district tự có.
3. Cân nhắc bật SEL-05 cho một phần sản phẩm với nhiều nội dung mô phỏng, không sửa giá/thông tin nguồn qua sync.
4. Bổ sung nhánh hủy, từ chối trả và giao thất bại ở mức kiểm thử hợp lý; phải điều phối với các bộ xử lý all để nhánh còn đầu vào. Không bảo đảm mọi quota sẽ thành công.
5. Giữ các NULL đúng nghiệp vụ. Không đặt mục tiêu 100% cột có giá trị.
6. Ghi rõ gender/DOB, seller.phone, cost_price, chứng từ nhập kho và voucher sản phẩm/phần trăm là phần cần code, chưa thể cam kết config mới sẽ tạo được.
7. Dành thời gian chạy tiếp để quan sát hoàn tiền và đối soát; trạng thái cuối 5 ngày không thay thế kiểm thử toàn chu kỳ.
8. Sau chạy, kiểm tra tỷ lệ NULL theo loại sự kiện/trạng thái và theo nguồn dữ liệu, không chỉ đếm tổng NULL từng bảng.

## Phụ lục — Toàn bộ cột NULL hoặc chuỗi rỗng trong snapshot

Bảng sau liệt kê mọi cột có ít nhất một NULL hoặc chuỗi rỗng. Mẫu số là số dòng hiện có của bảng; không coi chuỗi rỗng là dữ liệu đã đầy đủ.

| Bảng.cột | Tổng dòng | NULL | Chuỗi rỗng |
|---|---:|---:|---:|
| `categories.parent_id` | 6 | 1 | 0 |
| `products.brand_name` | 149 | 0 | 149 |
| `products.cost_price` | 149 | 149 | 0 |
| `products.inventory_status` | 149 | 0 | 149 |
| `products.quantity_sold` | 149 | 93 | 0 |
| `products.short_description` | 149 | 0 | 149 |
| `products.stock_item` | 149 | 149 | 0 |
| `products.type` | 149 | 0 | 149 |
| `sellers.phone` | 9 | 9 | 0 |
| `customers.date_of_birth` | 524 | 524 | 0 |
| `customers.gender` | 524 | 524 | 0 |
| `customer_addresses.customer_id` | 99 | 26 | 0 |
| `customer_addresses.district` | 99 | 99 | 0 |
| `orders.campaign_id` | 124 | 124 | 0 |
| `orders.cancellation_reason` | 124 | 124 | 0 |
| `orders.cancelled_at` | 124 | 124 | 0 |
| `orders.completed_at` | 124 | 49 | 0 |
| `orders.customer_id` | 124 | 32 | 0 |
| `orders.shipping_promotion_id` | 124 | 52 | 0 |
| `returns.decision_reason` | 3 | 3 | 0 |
| `returns.received_at` | 3 | 2 | 0 |
| `returns.refunded_at` | 3 | 3 | 0 |
| `promotions.max_discount_amount` | 3 | 3 | 0 |
| `promotions.product_id` | 3 | 3 | 0 |
| `promotions.seller_id` | 3 | 2 | 0 |
| `inventory_movements.reference_code` | 1009 | 5 | 0 |
| `shipments.delivered_at` | 106 | 31 | 0 |
| `shipments.failed_at` | 106 | 106 | 0 |
| `shipments.returned_at` | 106 | 106 | 0 |
| `sessions.campaign_id` | 1575 | 1575 | 0 |
| `sessions.customer_id` | 1575 | 945 | 0 |
| `page_events.order_id` | 4490 | 4366 | 0 |
| `page_events.product_id` | 4490 | 910 | 0 |
| `page_events.search_keyword` | 4490 | 3704 | 0 |
| `cart_items.customer_id` | 315 | 126 | 0 |
| `checkouts.customer_id` | 105 | 26 | 0 |
| `refunds.completed_at` | 1 | 1 | 0 |
| `promotion_usages.released_at` | 144 | 144 | 0 |
