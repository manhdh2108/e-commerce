# Kiểm tra thực tế dữ liệu OLTP và mức đáp ứng rule — 05/11/2026

## 1. Kết luận

**Chưa thể kết luận hệ thống đã đáp ứng đầy đủ thiết kế mô phỏng sàn thực tế.** Có một lỗi dữ liệu xác nhận được trong Analytics, một khoảng trống audit của lịch sử cũ và nhiều nghiệp vụ/thuộc tính còn giản lược. Các quan hệ bảng, tiền đơn/thanh toán, kho và lịch chạy được kiểm tra dưới đây không phát hiện sai lệch trong snapshot.

Bộ kiểm tra độc lập có **87 nhóm kiểm tra: 86 nhóm không phát hiện vi phạm, 1 nhóm phát hiện 53 sự kiện sai nhóm tác động**. Đây không phải tỷ lệ “98,85% hệ thống đúng”; mỗi nhóm có phạm vi khác nhau và không bao phủ mọi nghiệp vụ tương lai.

Không sửa/xóa dữ liệu, không gọi crawler, không xếp job, không pause/resume hoặc reset môi trường trong lượt kiểm tra này.

## 2. Nguồn bằng chứng và phạm vi thời gian

- Truy vấn trực tiếp PostgreSQL `mock_oltp.public`, Control DB `mock_control.control_records` và SQLite crawler ở chế độ chỉ đọc.
- Snapshot nghiệp vụ lấy trước, snapshot điều khiển lấy sau; mỗi PostgreSQL transaction dùng **REPEATABLE READ, READ ONLY**. Hai database có snapshot riêng, không giả định giao dịch xuyên DB là một snapshot nguyên tử.
- Snapshot bắt đầu **22:02:20**, báo cáo hoàn tất **22:02:22 ngày 05/11/2026, UTC+7**.
- Khi lấy snapshot có job `5f1afc04-828b-4864-803b-251e2c92ac51` đang chạy ngày **16/02/2026**. Checkpoint và số dư cuối ngày đã hoàn tất đến **15/02/2026**. Những kiểm tra chốt ngày chỉ áp dụng đến mốc này.
- Số liệu sẽ tiếp tục tăng do worker đang chạy. Không dùng báo cáo này như dashboard thời gian thực.
- Kết quả máy đọc được: [audit-results-2026-11-05.json](audit-results-2026-11-05.json).
- Mã kiểm tra: [`scripts/mock_platform/diagnostics/audit.py`](../../../scripts/mock_platform/diagnostics/audit.py), lớp `ReadOnlyAudit`.

Đã xác minh riêng bằng truy vấn SQL độc lập cho lỗi phân nhóm Analytics; không chỉ dựa vào kết quả của script audit.

Kiểm tra lại lúc **22:08:23–22:08:25** khi worker đã tiến xa hơn: **688 đơn**, ngày chốt **18/02**, vẫn 87 nhóm kiểm tra và cùng **53 sự kiện sai nhóm**, không phát hiện thêm vi phạm trong bộ kiểm tra này. [Snapshot kiểm tra lại](audit-results-2026-11-05-2208.json). Các bảng số liệu chi tiết bên dưới giữ snapshot gốc 22:02 để không trộn hai thời điểm.

## 3. Số liệu tại snapshot

Tổng **36.291 dòng** trên 27 bảng nghiệp vụ.

| Nhóm | Số lượng |
|---|---:|
| Sản phẩm / seller / danh mục | 149 / 9 / 6 |
| Khách / địa chỉ | 330 / 735 |
| Đơn / dòng hàng / thanh toán | 640 / 640 / 640 |
| Đơn Completed / Cancelled / Pending | 616 / 16 / 8 |
| Thanh toán Success / Failed / Pending | 616 / 18 / 6 |
| Vận đơn Delivered | 616 |
| Review / voucher / chiến dịch / báo cáo quảng cáo | 142 / 96 / 32 / 46 |
| Phiên / sự kiện / mục giỏ | 6.015 / 16.918 / 1.389 |
| Kho / carrier / dòng tồn hiện tại | 1 / 1 / 149 |
| Biến động kho / số dư theo ngày | 874 / 6.854 |
| Chính sách hoa hồng / payout | 1 / 0 |
| Trả hàng / liên kết voucher đã áp vào dòng đơn | 0 / 0 |

Tiền:

- Giá trị 616 đơn hoàn tất: **518.816.600 đồng**.
- Tổng thanh toán thành công trong snapshot: **518.816.600 đồng**.
- Chi quảng cáo: **3.850.000 đồng**.
- Tổng tồn thực tế: **3.614**, đang giữ **8**, khả dụng **3.606** sản phẩm.

Giá bán nguồn có thể đã thấp hơn original_price; việc giảm giá voucher của mock bằng 0 không có nghĩa giá Tiki chưa bao gồm giảm giá nguồn. Engine dùng price để tạo unit_price, không áp lại discount nguồn lần hai.

Không suy ra lợi nhuận từ các số này: giá vốn chưa có, chi phí/ưu đãi/đối soát chưa được mô hình hóa đầy đủ. Tổng tiền thanh toán toàn DB có thể khác tổng đơn hoàn tất ở một snapshot khác nếu có đơn đã trả trước đang vận chuyển; kiểm tra quan trọng là nghĩa vụ của từng đơn.

## 4. Lỗi dữ liệu thật: 53 sự kiện sai nhóm khách

### Bằng chứng

| Mã hành động nguồn | Ý nghĩa | Số sự kiện sai |
|---|---|---:|
| GST-WEB-05 | Khách vãng lai bỏ sản phẩm khỏi giỏ | 14 |
| GST-WEB-06 | Khách vãng lai bắt đầu checkout | 39 |
| **Tổng** | Gắn vào phiên có `customer_id IS NOT NULL` | **53** |

Ví dụ thực:

- `page_events.id = 103`, `event_type = begin_checkout`, thời điểm mô phỏng `2026-01-01 10:00:00`.
- `session_id = 16`, phiên có `customer_id = 98`: là phiên khách đã đăng ký.
- Manifest/action result ghi hành động nguồn là **GST-WEB-06**, thuộc khách vãng lai.

53 trường hợp được đếm từ action result → manifest thay đổi `page_events` → session thực trong Business DB. Chỉ nhìn bảng sự kiện không đủ vì nó không có cột tác nhân; cần truy ngược metadata điều khiển.

### Nguyên nhân trong code

Trong `DomainEngine.analytics()`, nhánh `WEB-05/WEB-06` tại `domain.py` khoảng dòng 854–861 chỉ chọn giỏ Active và phiên chưa đóng, **không lọc `user_matches(session)`** như các nhánh search/view/add-to-cart. Vì vậy hành động guest có thể chọn giỏ của khách đăng nhập.

Đây là lỗi phạm vi tác nhân, không phải lỗi FK. Mọi ID vẫn có thể tham chiếu hợp lệ trong khi ý nghĩa hành động bị sai.

### Mức ảnh hưởng và hướng xử lý

- Sai thống kê hành vi khách vãng lai so với khách có tài khoản trong dữ liệu cũ.
- Không phát hiện sai tiền đơn hoặc tồn kho do 53 sự kiện này trong snapshot được kiểm tra.
- Bộ cấu hình mới đã tắt các hành động WEB-05/06, nên tránh tạo thêm lỗi này từ các hành động đó; **không sửa ngược 53 sự kiện lịch sử**.
- Cần sửa handler để giới hạn đúng nhóm phiên khi chọn giỏ và thêm kiểm tra hồi quy cho cả guest/cust.
- Nếu xử lý lịch sử, phải lựa chọn quy tắc sửa hoặc đánh dấu dữ liệu không tin cậy; không tự chuyển `customer_id` của session thành NULL vì session đó còn các hành vi khác hợp lệ của khách đăng nhập.

## 5. Những kiểm tra không phát hiện sai lệch

### 5.1. Định danh và liên kết

- Không phát hiện orphan trên **40 FK vật lý** và các tham chiếu logic bổ sung: SKU kho → sản phẩm, mã vận đơn → mã đơn.
- Không phát hiện trùng ở **9 ràng buộc UNIQUE** hiện có, gồm SKU, order code, tracking/order code của vận đơn, kho–SKU, số dư ngày, review theo dòng hàng và các khóa khác.
- Seller trên đơn khớp seller của sản phẩm trong dòng đơn.
- Địa chỉ giao hàng thuộc đúng khách của đơn; guest dùng địa chỉ không có customer ID.
- Review khớp product/customer của dòng hàng, đã giao và được tạo sau thời điểm giao.
- Không có vòng lặp cây danh mục; tên danh mục sao chép vào sản phẩm khớp bảng danh mục. Một `parent_id NULL` là danh mục gốc, không phải lỗi.

### 5.2. Tiền và vòng đời đơn

- Giá dòng × số lượng − giảm giá dòng khớp net amount.
- Tổng gross, tổng giảm giá, phí và final amount khớp các dòng hàng.
- Không thu vượt nghĩa vụ; các đơn Completed trong ngày đã chốt được kiểm tra thanh toán thành công đủ số tiền. Không kết luận COD chưa thu giữa hai giai đoạn giao và thu hộ trong ngày đang chạy là lỗi vĩnh viễn.
- Không phát hiện đơn đã trả tiền thành công nhưng bị hủy bằng đường hủy không hoàn tiền.
- Các giao dịch Failed có paid amount bằng 0.
- COD thành công được ghi sau khi giao hàng, không trước lúc giao.
- Completed khớp Delivered/Fulfilled; Cancelled khớp dòng Cancelled và không có vận đơn.
- Mốc tạo/lấy/giao hàng, tạo đơn và đăng ký khách có thứ tự hợp lệ.

### 5.3. Kho

- Tồn hiện tại khớp tổng sổ nhập/xuất theo kho và SKU.
- Tồn giữ không âm, không vượt tồn thực và khớp các dòng đơn chưa hủy/chưa xuất hàng trong snapshot.
- Các bút toán Sale khớp số lượng dòng hàng đã xuất; không phát hiện xuất lặp hoặc xuất sai SKU trong kiểm tra này.
- Số dư tồn và tồn giữ cuối ngày đến 15/02 được tái dựng từ lịch sử nhập/xuất, thời điểm đặt/hủy/lấy hàng và đối chiếu.
- Có **6.854 = 149 × 46** dòng số dư cho 46 ngày từ 01/01 đến 15/02; khóa ngày–kho–SKU không bị trùng. Việc đối chiếu số dư dùng dữ liệu ngày đã hoàn tất, không dùng trạng thái giữa ngày để kết luận sai số dư chốt.

### 5.4. Analytics, Marketing và tài chính đã có dữ liệu

- Sự kiện nằm trong khoảng thời gian của session.
- Customer lưu trên cart khớp customer của session; đây là kiểm tra khác với phạm vi hành động guest/cust bị lỗi ở mục 4.
- Phiên/giỏ của ngày đã hoàn tất không còn mở/Active do các bước cuối ngày của kịch bản đã chạy.
- Báo cáo quảng cáo nằm trong hiệu lực chiến dịch và không vượt ngân sách theo các kiểm tra hiện có.
- Voucher có khoảng hiệu lực và giá trị/giới hạn không âm.
- Không phát hiện chính sách hoa hồng chồng khoảng cho cùng danh mục/hạng.

### 5.5. Lịch chạy và truy vết

- Daily record liên tục đến ngày chốt, không phát hiện nhảy ngày.
- Số lần hành động count của ngày hoàn tất khớp `special[day]` hoặc số ngày thường; không thấy cộng thêm số thường vào override.
- Tháng Một đúng 10 lượt đặt/ngày theo cấu hình cũ. Tháng Hai đã biến thiên: 01/02 là 22, 02/02 là 19, 07/02 là 30, 14/02 là 30, 15/02 là 21 yêu cầu và đơn thực tế tương ứng.
- Không có action chưa hỗ trợ được ghi là đã thực hiện thành công.
- Action ID phù hợp quy tắc seed/ngày/mã/index và khóa receipt sở hữu bởi đúng job.
- Mọi dòng Business DB trong snapshot khớp một ảnh before/after đã có trong journal điều khiển. Kiểm tra này chứng minh có dấu vết phù hợp, **không tự chứng minh chưa từng có sửa tay rồi trả về một ảnh lịch sử**.
- Không thấy manifest PREPARED còn treo tại snapshot Control DB; các manifest quan sát được là DONE.

## 6. Mức đáp ứng các rule đã chốt

Nguồn ưu tiên: [MOCK_SYSTEM_RULES.md](../MOCK_SYSTEM_RULES.md). Các thiết kế chi tiết sáu hệ thống còn có mục đề xuất/chưa triển khai; không gộp toàn bộ thành những rule đã được thực thi.

| Rule | Bằng chứng / kết luận |
|---|---|
| 01 — Sync append-only, hai hệ thống độc lập | **Đạt trên lịch sử sync quan sát được:** mọi thay đổi từ sync chỉ là insert products/sellers/categories, không có update/delete. 149 sản phẩm giữ ID/SKU/seller/offer và giá của snapshot lần nhập đầu. Tất cả 149 có provenance. Không có khác biệt giá với nguồn SQLite hiện tại. Việc chứng minh “chưa từng ghi ngược SQLite” cần code/tests vì SQLite không có đủ audit lịch sử; code sync mở nguồn read-only. |
| 02 — Đồng bộ độc lập, không sinh nghiệp vụ | **Đạt trong journal sync quan sát được:** không có thay đổi orders/customers/payments/inventory/marketing/analytics/finance từ job sync. Bootstrap và run là job riêng. |
| 03 — Ưu tiên rule/tài liệu chốt | Áp dụng khi kiểm tra; không áp tỷ lệ/ngưỡng từ tài liệu cũ như nghĩa vụ đã chốt. Một số đầu tài liệu thiết kế còn ghi “chưa triển khai” dù đã có phần code, nên trạng thái tài liệu vẫn cần làm sạch. |
| 04 — Ngày riêng thay thế ngày thường | **Đạt cho các ngày đã chạy và được đối chiếu.** Chưa có dữ liệu tới 8/8, 10/10, 11/11, 12/12 trong snapshot nên không tuyên bố đã xác minh bằng dữ liệu thật các ngày sale đó. |
| 05 — Chế độ theo count hoặc toàn bộ đầu vào | Có cả hai chế độ; quan sát xử lý thật và EXHAUSTED khi hết đầu vào, không thấy tạo giả đầu vào để đủ số. Chưa có bộ SLA/delay/backlog đầy đủ; “đến hạn” hiện chủ yếu là điều kiện trạng thái và thứ tự cố định của engine. |
| 06 — Giữ ID, bỏ qua SKU/chào bán xung đột | **Đạt về ID trên dữ liệu đã nhập.** 149 ID được đối chiếu. Dữ liệu nguồn hiện có không đủ chứng minh mọi trường hợp xung đột đã xảy ra đều được xử lý; crawler lưu chào bán mới nhất theo ID nên lịch sử chào bán bị ghi đè ở tầng cào không thể được phục hồi chỉ từ snapshot hiện tại. |
| 07 — Sửa cấu hình tại chỗ, giữ snapshot của job | Code mới có snapshot/revision và test bảo vệ sửa đồng thời; **một kế hoạch lịch sử tháng Một chưa có config snapshot/version revision**. Hiện hai cấu hình đều revision 1, không có version_history, nên chưa thấy bằng chứng sửa cấu hình làm lệch job. Không thể gọi toàn bộ lịch sử cũ là bất biến tự chứa đầy đủ. |
| 08 — Cào riêng và reset có xác nhận | Không có crawl_jobs từ UI và chưa có reset trong Control DB này. **Chưa được kiểm chứng bằng lịch sử thật tại DB hiện tại**; không thử xóa/cào để kiểm toán. Chức năng đã có code và test riêng, khác với bằng chứng vận hành trên dữ liệu hiện tại. |

Ngoài 8 rule chung, yêu cầu phạm vi tác nhân ở thiết kế Analytics **chưa đạt** vì 53 trường hợp tại mục 4. Cơ chế actor của các nhóm khác cũng chưa phải một hệ thống xác thực/phân quyền thật; khi không có actor ID hoặc lịch sử người thao tác thì không thể chứng minh mọi hành động “đúng chủ” chỉ bằng FK.

## 7. Các khoảng trống và dữ liệu chưa thực tế

| Khoảng trống code | Bằng chứng trong snapshot / hệ quả |
|---|---|
| Chưa liên kết hành trình mua | Cả **640 orders.session_id**, **640 orders.campaign_id**, **6.015 sessions.campaign_id** đều NULL; 16.918 page_events không có order_id. Không tính conversion/attribution theo phiên hoặc campaign một cách đáng tin. |
| Giỏ chưa đi đến trạng thái đã mua | 1.251 Abandoned, 93 Removed, 45 Active; có 616 đơn giao thành công nhưng không có liên kết cart → order. Không diễn giải tất cả Abandoned là khách thật bỏ mua. |
| Thời gian cố định, chưa có độ trễ đời thực | Cả 616 đơn hoàn tất đều tạo và giao cùng ngày; các hành động cùng loại gom cùng timestamp theo giai đoạn. Không có phân bố giờ hay SLA giao nhiều ngày. |
| Giỏ/đơn quá đơn giản | 640 đơn đều một dòng, số lượng 1; không có checkout nhiều SKU/shop, tách đơn hoặc phân phối giỏ. |
| Voucher chỉ là định nghĩa | 96 vouchers, 0 order_item_promotions; cả 640 đơn giảm giá đơn bằng 0 và shipping_discount chưa được áp. Không kiểm chứng được vòng đời lượt dùng/hoàn voucher. |
| Chưa mô phỏng đầy đủ chi phí | 640 đơn shipping_fee bằng 0; shipments có chi phí mô phỏng riêng. 149 cost_price NULL nên không đủ cơ sở tính lợi nhuận. |
| Hoàn/trả và giao thất bại chưa đóng vòng | returns = 0; không có dữ liệu để kiểm chứng hoàn kho/hoàn tiền. Tất cả 616 vận đơn đã quan sát là Delivered, phù hợp các cấu hình 100% giao thành công. Chưa có bằng chứng mô phỏng trọn vòng thất bại. |
| Tài chính chưa có nghĩa vụ đối soát | seller_payouts = 0; chỉ 1 chính sách cho danh mục 9423 trong khi sản phẩm ở 5 danh mục lá. Không coi có policy là đã tính đúng hoa hồng/thu/chi; chưa được chốt đầy đủ quy tắc phát sinh payout. |
| Profile giản lược | 330 khách chỉ có **1 số điện thoại phân biệt**; 735 địa chỉ chỉ có **1 chuỗi address_detail phân biệt**; gender/DOB đều NULL. Đây là dữ liệu thử nghiệm có chủ đích, nhưng chưa phù hợp phân tích phân khúc/địa lý/người nhận thực tế. |
| Địa chỉ mặc định chưa được mô hình hóa đầy đủ | **238 khách có địa chỉ nhưng không có địa chỉ mặc định**. Không phải vi phạm “nhiều địa chỉ mặc định”; là thiếu logic chọn mặc định và tái sử dụng địa chỉ. Checkout luôn tạo địa chỉ mới nên không phản ánh hành vi thật. |
| Rating không có phân phối tự nhiên | 93 review 5 sao, 49 review 4 sao theo hai cấu hình; không phải kết quả tự phát theo trải nghiệm, không có độ trễ đánh giá đủ thực tế. |
| Dữ liệu nguồn có trường thiếu | 149 stock_item NULL, 93 quantity_sold NULL, 9 seller.phone NULL. Không tự bịa các giá trị Tiki không cung cấp. Đây là hạn chế độ phủ dữ liệu, không đủ căn cứ kết luận sync làm mất dữ liệu. |
| Giá thật không phải giá lịch sử của ngày mock | Cả 149 sản phẩm có crawl_date sau ngày created_at mô phỏng. Chạy lịch tháng Một bằng catalog cào về sau là mô phỏng backfill, không phải bằng chứng giá thị trường Tiki thật tháng Một. |
| Chọn đối tượng chưa mô hình hóa nhu cầu | Chủ yếu chọn đều/ngẫu nhiên trong tập phù hợp; không có cohort, best seller, nhu cầu theo giá/vùng/shop. Sản lượng biến thiên trong file không tạo ra mô hình hành vi có quan hệ nhân quả. |
| Hệ thống chưa có ràng buộc dữ liệu vật lý đầy đủ | Cả **204 cột không phải PK** đang nullable. Trong đó **178 cột được metadata schema đánh dấu bắt buộc** lại không được tạo NOT NULL. Có 27 PK, 40 FK, 9 UNIQUE nhưng **không có CHECK constraint**. Code tạo cột dùng `nullable = n != 'id'`, bỏ qua metadata nullable. Đây là khoảng trống của lớp bảo vệ schema; cần chốt lại các trường được phép NULL trước khi migration, không tự ép NOT NULL lên các dữ liệu hiện còn thiếu. |

Không coi NULL ở `completed_at` của đơn chưa hoàn tất, `cancelled_at` của đơn không hủy, `failed_at` của vận đơn đã giao hoặc `customer_id` của guest là bất thường. Phải đọc NULL theo ý nghĩa trạng thái/trường, không theo một quy tắc “mọi cột phải có giá trị”.

## 8. Những trạng thái hiện tại không phải lỗi

- 8 đơn Pending, 6 lần thanh toán Pending, 225 session chưa đóng và 45 giỏ Active nằm trong bối cảnh lượt chạy đang xử lý ngày 16/02. Chỉ kết luận backlog bất thường sau khi đối chiếu lịch, thời hạn và giai đoạn xử lý tương ứng.
- 18 lần trả trước Failed không tự đồng nghĩa hỏng dữ liệu: cấu hình mới cho phép thất bại thanh toán. 16 đơn đã hủy và một phần đơn Pending thể hiện các thời điểm xử lý khác nhau.
- `EXHAUSTED` khi hết đầu vào của một hành động auto không phải REJECTED/FAILED.
- Bảng returns/payout/liên kết voucher rỗng là phạm vi engine chưa có, không có nghĩa cần INSERT ngẫu nhiên để đủ mọi bảng.

## 9. Vì sao nút “Kiểm tra dữ liệu” vẫn có thể báo đạt?

`BusinessValidator.report()` hiện chỉ kiểm tra một phần: tồn đối chiếu ledger/giữ hàng, tiền đơn so với dòng, không thu vượt nghĩa vụ, thứ tự vận chuyển. Nó không đối chiếu nhóm actor trong action metadata với customer của session, không kiểm tra độ thực tế của phân phối hay phủ toàn bộ nghiệp vụ thiết kế.

Trong lượt khảo sát trước snapshot chính, validator hiện có báo `ok = true` dù lỗi actor đã có trong dữ liệu lịch sử. Cần mở rộng validator, không dùng dấu “đạt” hiện tại như chứng nhận toàn bộ schema và mọi rule đều đúng.

## 10. Thứ tự nên xử lý tiếp

1. **Ưu tiên cao:** sửa phạm vi chọn giỏ cho WEB-05/06; thêm kiểm tra actor vào validator và test. Chốt riêng cách xử lý 53 sự kiện cũ.
2. **Bảo vệ dữ liệu:** rà hợp đồng nullable/miền giá trị và bổ sung NOT NULL/CHECK theo các quyết định đã chốt, kèm migration có kiểm tra dữ liệu cũ. Không tự diễn giải metadata cũ là mọi trường đều đã chốt bắt buộc.
3. **Truy vết:** bổ sung/công bố rõ giới hạn snapshot của kế hoạch cũ; bảo đảm mọi lượt mới lưu snapshot và phiên bản engine/schema cần thiết.
4. **Liên kết nghiệp vụ:** thiết kế cart/session/checkout/order; sau đó mới đo conversion, bỏ giỏ và attribution.
5. **Độ trễ và hàng đợi:** xây scheduler nhiều ngày, SLA và backlog theo nghĩa vụ.
6. **Các nhánh còn thiếu:** chốt và triển khai áp voucher, trả/hoàn tiền, hoàn kho, đối soát. Không chỉ tăng ngẫu nhiên số lượng để tạo cảm giác thực tế.

Lượt kiểm tra này chỉ bổ sung công cụ/báo cáo, chưa thay handler, schema hoặc dữ liệu đang chạy.

## 11. Chạy lại audit

Từ thư mục gốc repository, dùng cùng biến môi trường kết nối của web:

```bash
.venv/bin/python -m scripts.mock_platform.diagnostics.audit \
  --output docs/mock-design/audit-results-latest.json
```

Công cụ dành cho PostgreSQL, không khởi tạo DB hoặc ghi business/control. Nó ghi file JSON theo `--output`. Nên dùng tên mới nếu muốn giữ từng snapshot. Có thể chạy khi worker đang mô phỏng, nhưng nên kiểm tra lại sau khi job hoàn tất để kết luận cho toàn khoảng ngày. Không dùng kết quả snapshot hai DB riêng để suy ra nguyên tử xuyên DB; tránh chạy audit đồng thời một thao tác reset môi trường.

Script đối chiếu các invariant đã nêu, chưa phải chứng minh đầy đủ mọi đường đi và mọi tình huống lỗi của hệ thống. Các trường hợp chưa từng xuất hiện trong dữ liệu cần test riêng trên môi trường tách biệt.
