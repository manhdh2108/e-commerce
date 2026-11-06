# Kiểm tra các bảng ít/trống và độ bao phủ kịch bản — 06/11/2026

## Kết luận và phạm vi

Đã đọc trực tiếp **toàn bộ 33 bảng** trong PostgreSQL `mock_oltp.public` bằng transaction REPEATABLE READ, READ ONLY; đối chiếu snapshot kế hoạch, kết quả hành động và metadata phương thức thanh toán trong Control DB. Không thay đổi dữ liệu, checkpoint hoặc config.

Lượt `97f7dddd-f285-42a6-8d22-ffdfd0b2b73e` đã COMPLETE đến 05/01/2026. Chỉ có **hai bảng hoàn toàn trống: seller_payouts và seller_payout_items**. Chưa có dấu hiệu chúng bị bỏ quên bởi cấu hình: nguyên nhân là chưa đến hạn đối soát. Những bảng ít như returns/refunds/reviews phần lớn đúng lượng đầu vào và độ trễ. Tuy nhiên, bài test chưa bao phủ nhiều nhánh và không được hiểu là đã kiểm thử đủ chỉ vì mọi bảng khác có dòng.

## 1. Hai bảng trống: đối soát

- `seller_payouts`: 0; `seller_payout_items`: 0.
- FIN-REC-01, FIN-REC-02, FIN-PAY-01 đều bật chế độ xử lý đầu vào; mỗi ngày không có đầu vào đủ điều kiện.
- Đơn hoàn tất sớm nhất **03/01/2026 17:02:26**. Chính sách của lượt giữ tiền **8 ngày**. Không đơn nào đủ tuổi đối soát trong 01–05/01.
- Mốc đủ tuổi sớm nhất về lý thuyết là **11/01/2026 17:02:26**; phải đến lượt xử lý tài chính sau mốc đó, có đủ tiền thu và không còn nghĩa vụ trả/hoàn chặn thì mới có thể tạo payout. Không bảo đảm chạy đến 11/01 là mọi đơn được đối soát.
- Muốn kiểm thử phải chạy liên tục từ 06/01 đến qua các mốc cần thiết, có thể lấy khoảng 15–20 ngày làm cửa sổ test đầu tiên; vẫn phải kiểm tra các nghĩa vụ thực tế. Không hạ thời gian giữ tiền hoặc ghi payout giả chỉ để lấp bảng.

## 2. Những bảng giao dịch ít dòng

### Returns 3, refunds 1

CUS-08 yêu cầu một lượt/ngày (tổng 5); hai ngày đầu chưa có dòng đơn đủ điều kiện nên bị từ chối. Ba yêu cầu từ ngày 03–05/01 được tạo và duyệt.

WH-04 trễ 2 ngày sau duyệt nên đến cuối 05/01 mới nhận được yêu cầu ngày 03/01. Nhận hàng sinh một nghĩa vụ refund Pending 790.000 đồng lúc **05/01 21:49:05**. PAY-02 trễ thêm 1 ngày từ nghĩa vụ nên chưa thể hoàn trong 05/01. Hai yêu cầu còn lại Approved chưa đến lúc nhận. Ít dòng là đúng chuỗi hiện tại; chưa kiểm thử hoàn tiền Completed, trả bị từ chối, trả một phần đa dạng hoặc hoàn do hủy đơn.

### Product_reviews 6

Config yêu cầu lần lượt **2,3,4,4,2** lượt, tổng 15. Chín yêu cầu ba ngày đầu bị từ chối vì chưa có đơn giao xong đủ độ trễ 1 ngày. Ngày 04/01 tạo 4, ngày 05/01 tạo 2, đúng config. Đến cuối 05/01 có 34 dòng đơn khách đăng ký đã qua ngưỡng thời gian cơ bản, chưa loại hết các điều kiện/đã đánh giá; không có quy tắc mọi dòng đủ điều kiện đều phải được đánh giá. Chỉ sáu mẫu ra 4 đánh giá 5 sao và 2 đánh giá 4 sao không chứng minh bộ chọn bỏ qua 2–3 sao. Cần nhiều mẫu và chủ động kịch bản nếu muốn kiểm thử sao thấp.

### Campaigns 1, ad_spend_logs 5, promotions 3

Một campaign APP được tạo ngày 01/01, kéo dài đến 01/02. Chi quảng cáo một log/ngày tạo đủ 5 log. Ba voucher (sàn, phí giao, shop) đều cấu hình tạo một lần ngày 01/01. Đây là số lượng hợp lệ cho một bài test nhỏ, không cần tự tăng vì ít.

Điểm chưa hợp lý về độ bao phủ là có quảng cáo nhưng **0 phiên/đơn có campaign_id** do cấu hình attribution lệch kênh. Sửa phối hợp campaign–channel–traffic; thêm nhiều campaign mà vẫn lệch kênh không giải quyết. Voucher đang dùng toàn Fixed Amount/Order hoặc Shipping; voucher phần trăm có trần và riêng sản phẩm cần nâng cấp code, không tự hứa làm được bằng config.

### Commission_rates 5

Có đúng năm danh mục lá; cả chín seller đang Normal, nên năm policy Normal là đủ cho giao dịch hiện có. Cùng mức 5% chưa đa dạng nhưng không phải thiếu policy. Trước khi cấu hình đổi hạng seller hoặc thêm danh mục, phải chuẩn bị policy phù hợp hạng–danh mục–thời gian; không tăng số policy ngẫu nhiên gây chồng hiệu lực.

## 3. Các bảng không nhỏ nhưng cần đối chiếu tỷ lệ

- **101 payments / 124 orders:** 99 Success, 2 Failed. 23 đơn không có payment đều là **COD đang Processing**, được xác minh bằng metadata. Chưa thu tiền trước giao là hợp lý; không tạo payment giả để đủ một dòng cho mỗi đơn.
- **106 shipments / 124 orders:** thiếu 18 vận đơn, gồm 16 Processing mới ngày 05/01 chờ độ trễ DSP-01 và hai Pending ngày 04–05/01. Hai Pending có phương thức ZaloPay/Momo, thanh toán thất bại; chưa có vận đơn là đúng.
- **78 delivery_attempts / 106 shipments:** 75 Delivered, 3 Failed đã retry; còn 31 In Transit. Vận đơn chưa đến lần giao chưa cần attempt.
- **99 addresses / 524 customers:** 73 địa chỉ tài khoản của 73 khách, 26 địa chỉ guest; khách chưa có hành động tạo địa chỉ/đặt hàng không bắt buộc phải có địa chỉ.
- **4.470 inventory_daily_balance:** đủ 149 SKU × 6 kho × 5 ngày, không thiếu snapshot ngày.

## 4. Toàn bộ bảng và nhận xét

| Bảng | Số dòng | Nhận xét |
|---|---:|---|
| `categories` | 6 | 6 = 1 danh mục gốc + 5 lá; khớp catalog sách đã nhập. Chưa đại diện nhiều ngành hàng. |
| `products` | 149 | 149 sản phẩm thật từ SQLite; số lượng giới hạn bởi nguồn, không tăng bằng quota mock. |
| `sellers` | 9 | 9 seller đúng ID nguồn; 8 có đơn, một shop chỉ có 1 sản phẩm chưa được mua. Tất cả Normal/Active và cùng tỉnh: thiếu đa dạng hồ sơ/trạng thái, không phải lỗi thiếu hàng seller. |
| `customers` | 524 | 500 nền + 24 đăng ký mới. Không bắt buộc mọi khách phát sinh đơn hoặc địa chỉ. |
| `customer_addresses` | 99 | 99 địa chỉ: 73 gắn khách đăng ký, 26 guest. 73 khách khác nhau có địa chỉ; không cần tạo địa chỉ cho cả 524 khách nếu chưa có hành động liên quan. |
| `channels` | 3 | Web/App/Livestream là danh mục tham chiếu. Đơn dùng Web 91, App 33, Livestream 0: chưa có kịch bản Livestream. |
| `payment_methods` | 5 | 5 phương thức là master data; không cần nhiều dòng hơn chỉ vì nhiều đơn. |
| `orders` | 124 | 124 đơn từ 105 checkout do tách theo shop; 75 Completed, 47 Processing, 2 Pending. |
| `order_items` | 129 | 129 dòng của 124 đơn; chưa nhiều đơn nhiều dòng, cần thử giỏ nhiều SKU cùng shop. |
| `payments` | 101 | 101 bản ghi: 99 Success + 2 Failed. 23 đơn chưa có payment đều COD và đang Processing; chưa thu tiền khi chưa giao là hợp lý. |
| `returns` | 3 | 5 yêu cầu cấu hình, 2 không có đầu vào đầu kỳ, 3 tạo thành công; hiện 2 Approved + 1 Received. Chưa có nhánh Rejected. |
| `product_reviews` | 6 | 15 yêu cầu cấu hình, 9 bị từ chối trong 3 ngày đầu khi chưa có đơn đủ điều kiện; 4 ngày 04/01 và 2 ngày 05/01 thành công. Chưa đủ mẫu để đánh giá phân bố sao. |
| `promotions` | 3 | 3 voucher được tạo ngày 01/01: sàn, freeship, seller; không tạo thêm 02–05/01 theo config. Có 76 dòng áp hàng và 144 usage, nên không phải voucher không được dùng. |
| `order_item_promotions` | 76 | 76 lần áp giảm hàng lên dòng đơn. Không cần bằng số voucher hoặc số đơn. |
| `warehouses` | 6 | 6 kho theo hồ sơ, cả 6 đã có vận đơn; số kho là cấu trúc mạng lưới, không phải quota ngày. |
| `inventory_levels` | 894 | 149 SKU × 6 kho = 894; đủ độ phủ nhưng tồn ban đầu đồng đều 200 là giả định test. |
| `inventory_movements` | 1009 | Sổ biến động đã có dữ liệu, không thiếu theo số lượng: {'Import': 899, 'Sale': 109, 'Return': 1}. Năm phiếu WH-01 thiếu reference_code như báo cáo NULL; cần sửa truy vết, không phải tăng count. |
| `inventory_daily_balance` | 4470 | 894 dòng/ngày × 5 ngày = 4.470; đủ snapshot theo thiết kế hiện tại. |
| `carriers` | 5 | 5 carrier theo hồ sơ; cả 5 được dùng (14,23,29,17,23 vận đơn). Tên dịch vụ chưa đồng nghĩa đã có SLA/tuyến riêng. |
| `shipments` | 106 | 106 vận đơn. 18 đơn chưa có vận đơn gồm 16 Processing mới ngày 05/01 và 2 Pending; DSP-01 trễ 1 ngày, chưa phải bỏ sót. |
| `marketing_campaigns` | 1 | 1 chiến dịch APP chạy 01/01–01/02 đúng config tạo 1 lần. Ít không sai; thiếu attribution phiên/đơn và đa kênh là điểm cần chỉnh. |
| `ad_spend_logs` | 5 | 1 campaign × 1 log/ngày × 5 ngày = 5; tổng chi 280.000/3.000.000 ngân sách. Click chưa có chuỗi attribution tương ứng. |
| `sessions` | 1575 | 1.575 phiên theo cấu hình; không cần bằng số khách vì có guest và khách lặp lại. |
| `page_events` | 4490 | 4.490 sự kiện; một phiên có nhiều sự kiện. Tính tự nhiên thời gian phiên vẫn hạn chế như báo cáo trước. |
| `cart_items` | 315 | 315 dòng: 129 Converted, 176 Abandoned, 10 Removed. Converted khớp 129 checkout_lines, không phải 124 đơn. |
| `seller_commission_rates` | 5 | 5 danh mục lá × một hạng Normal = 5 policy, tất cả 5%; đủ độ phủ hiện tại. Muốn nhiều hạng/lịch sử giá cần thêm config và tránh khoảng hiệu lực chồng lấn. |
| `seller_payouts` | 0 | 0 vì chưa đơn nào hết 8 ngày giữ tiền; FIN-REC-01/02 và FIN-PAY-01 đều bật, không thiếu nút bật config. |
| `checkouts` | 105 | 105 = 79 khách đăng ký + 26 guest; tất cả yêu cầu checkout trong 5 ngày thành công. |
| `checkout_lines` | 129 | 129 dòng; khớp dòng hàng và giỏ đã chuyển đổi. |
| `refunds` | 1 | 1 Pending từ return Received ngày 05/01 21:49:05; PAY-02 trễ 1 ngày, chưa đến hạn hoàn. |
| `promotion_usages` | 144 | 144 usage theo voucher đơn/phí ship; có thể nhiều usage cho một đơn, không cần bằng order_item_promotions. |
| `seller_payout_items` | 0 | 0 vì chưa có payout đủ điều kiện; không tạo dòng chi tiết khi chưa đối soát. |
| `delivery_attempts` | 78 | 78 lượt = 75 Delivered + 3 Failed; 3 thất bại đã được retry, 31 vận đơn còn In Transit. Không cần bằng tổng số vận đơn. |

## 5. Yêu cầu phải mang sang bước viết config mới

1. **Đủ chu kỳ:** giữ xử lý đầu vào đến hạn cho hoàn tiền/đối soát, thiết kế lịch chạy đủ dài; không đánh đồng số ngày test với lỗi bảng trống.
2. **Đúng thứ tự đầu vào:** dời/phân bố yêu cầu đánh giá, trả hàng sau giai đoạn đã có đơn đủ điều kiện; vẫn có thể giữ một phần yêu cầu sớm để kiểm thử từ chối.
3. **Bổ sung nhánh hiện chưa được bao phủ:** hủy trước lấy hàng, từ chối trả, giao thất bại đủ số lần và hoàn hàng về kho, refund Completed, payout qua Pending/Approved/Paid. Phải phối hợp quota với bộ xử lý all để còn đầu vào cho nhánh khác; không bật mọi hành động all rồi coi mỗi nhánh đều chạy được.
4. **Marketing:** đồng bộ kênh campaign với phiên và attribution; có thể thêm campaign/voucher phù hợp quy mô test. Không cần mọi đơn nhận voucher hoặc gắn campaign.
5. **Catalog/master:** 6 danh mục và 9 seller là phạm vi nguồn sách hiện tại. Muốn nhiều ngành hàng phải mở rộng crawler rồi chủ động append-only sync; không giả thêm ID sản phẩm Tiki để tăng số dòng.
6. **Hạng seller và policy:** nếu thử hạng khác Normal, phải đảm bảo policy phù hợp trước khi tạo đơn. Master data ít dòng không tự là bất thường.
7. **Những phần cần code:** tham chiếu phiếu nhập, nhân khẩu học, giá vốn, tính tự nhiên thời gian/định tuyến kho và các loại voucher chưa hỗ trợ giữ nguyên danh sách trong báo cáo NULL/realism; config mới không che các giới hạn này.
8. **Tiêu chí nghiệm thu:** đo nhánh đã thực sự sinh và liên kết hợp lệ, không chỉ đặt mục tiêu tất cả bảng phải có nhiều dòng. Một nhánh chưa đủ thời gian cần ghi “chưa kiểm thử”, không ghi “đã đúng”.

Tham chiếu: [Báo cáo NULL](NULL_DATA_REVIEW_2026-11-06.md), [Báo cáo tính thực tế khi chạy](RERUN_REALISM_REVIEW_2026-11-06.md).
