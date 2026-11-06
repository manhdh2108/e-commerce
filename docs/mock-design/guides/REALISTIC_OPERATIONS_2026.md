# Hồ sơ và kịch bản vận hành bán lẻ Việt Nam 2026

Đây là bản cấu hình mới sau đợt rà soát dấu vết dữ liệu mô phỏng. Rule nằm trong code; danh sách tên, địa phương, trọng số, lịch, lượng hành động và các xác suất nằm trong JSON. Các số vận hành là giả định có thể chỉnh, không phải số liệu đo từ Tiki hay cam kết hành vi của các hãng vận chuyển.

## Hai file cần nhập

| File | Chức năng |
|---|---|
| [diverse-ecommerce.json](../examples/settings/diverse-ecommerce.json) | Hồ sơ thực thể, mạng lưới kho/carrier, tồn đầu và chính sách |
| [upgraded-linked-2026.json](../examples/scenarios/upgraded-linked-2026.json) | Lịch hành động năm 2026, hành trình, độ trễ, ngoại lệ, lookup |

Thư viện examples vẫn chỉ có **bốn JSON**: hai bản trên và hai mẫu tối thiểu trước đây. Mẫu hai đơn COD dùng để kiểm tra cài đặt; bản đầy đủ dành cho thử vận hành.

## Dữ liệu thực thể

- 32 họ × 104 tên, tương ứng 3.328 tổ hợp tên; 30 đầu số, số điện thoại sinh theo seed; email có local-part biến thiên.
- Khách nền có tuổi tài khoản phân bố từ 7 ngày đến 3 năm trước mốc bắt đầu; không còn tất cả đăng ký đúng 00:00 ngày đầu. Cấu hình nằm ở `entity_profile.bootstrap.customer_history_days`; hồ sơ không khai báo khóa này giữ cách bootstrap cũ để tương thích.
- 20 bộ địa phương tại TP. Hồ Chí Minh, Hà Nội, Đà Nẵng, Cần Thơ, dùng tên phường và đường thật. Không còn `Khu vực mô phỏng Nam/Bắc/Trung`. `district` để NULL theo bộ địa chỉ lựa chọn, không dựng lại quận để lấp trường.
- Sáu kho có tên theo địa danh; năm carrier có tên GHN, GHTK, Viettel Post, Bưu điện Việt Nam, J&T Express. Cả năm có khả năng được chọn trong lookup dispatch.
- Seller có phone dạng pattern, email, tên người và 80 lựa chọn tên cửa hàng; không còn chín số phone cố định. Hạng seller Normal/Preferred/Mall có policy hoa hồng tương ứng; hạng khách Member/Silver/Gold có phân bố và trọng số hoạt động.
- 21 nhóm tác động giữ đúng vai trò đã chốt. Các nhóm nhân sự có tên thông thường, giờ hoạt động 08:00–21:59:59. Tiến trình dịch vụ được ghi theo tên dịch vụ, không dùng tên nhân viên giả cho callback tự động.
- Kho và số nhà/người nhận là dữ liệu tổng hợp trên vocabulary địa danh thật; không phải cơ sở đã xác minh của carrier hoặc hồ sơ người thật. Email giữ domain `example.com`; không gửi thư hay gọi API các carrier. Nguồn/provenance và danh tính ảo vẫn được ghi rõ trong Control DB.

Tên phường được đối chiếu với [danh mục đơn vị hành chính trên Cổng Chính phủ](https://xaydungchinhsach.chinhphu.vn/danh-sach-3321-don-vi-hanh-chinh-cap-xa-tai-34-tinh-thanh-sau-sap-xep-sap-nhap-119250710102358656.htm). Thương hiệu carrier tham khảo trang chính thức [GHN](https://ghn.vn/), [GHTK](https://ghtk.vn/), [Viettel Post](https://viettelpost.vn/). Việc dùng tên thương hiệu không đồng nghĩa giả định giá/SLA trong JSON là bảng giá hay SLA chính thức.

## Các rule code đã thay đổi

### Nhân quả thời gian

Thanh toán, xác nhận, vận chuyển và các bước xử lý phải theo sau dữ liệu nguồn, kể cả khi delay_days bằng 0. Clock tính thời điểm theo đầu vào, độ trễ và giờ hoạt động; không cho ghi ngược thời gian chỉ vì worker đang ở một phase trước đó. Đối tượng chưa đến hạn hoặc không còn nằm trong ngày/khung giờ hợp lệ được giữ để lần xử lý sau.

Validator độc lập kiểm tra thêm updated_at không trước created_at, payment không trước order, phiên đăng nhập không trước đăng ký và shipment không trước order. Kiểm thử tái hiện đơn checkout lúc 20 giờ xác nhận các bước sau không còn ghi lúc trưa cùng ngày; cố tình sửa ngược thời gian trong DB thử sẽ bị validator phát hiện.

### Hành trình và danh tính

- Từ khóa có thể lấy từ sản phẩm, danh mục hoặc thương hiệu của catalog hiện có, thay vì ba từ khóa cố định. Sở thích danh mục được giữ theo phiên trong Control.
- View có thể ưu tiên sở thích từ tìm kiếm; thêm giỏ có thể ưu tiên sản phẩm đã xem. Trọng số áp dụng giữa **nhóm ưu tiên và phần còn lại**, không bị loãng khi catalog có thêm nhiều SKU.
- Guest quay lại giữ cùng tên/phone/địa chỉ cơ sở theo danh tính actor, không sinh một người khác chỉ vì ID checkout thay đổi. Đơn guest vẫn để customer_id NULL đúng hợp đồng.
- Metadata `segment` có thể được lookup tham số; sampling theo hạng khách điều khiển mức độ hoạt động. Thuộc tính chỉ có tên nhưng không được tham chiếu sẽ không tự tạo hành vi.

### Ngoại lệ và hậu xử lý

Retry thanh toán, hủy bởi khách và từ chối trả hàng đã được bật với lịch biến thiên. `phase` cho phép bố trí hủy trước xác nhận và từ chối trước duyệt, để nhánh không bị xử lý-all của bước trước tiêu thụ hết đầu vào. Handler vẫn kiểm tra quyền, trạng thái, thời gian, lượng tồn và nghĩa vụ tiền; quota không bảo đảm sẽ phát sinh đủ bản ghi thành công.

Hoàn tiền và chi trả hỗ trợ success_rate/retry_days. Khi nhà cung cấp thất bại, nghĩa vụ vẫn Pending/Approved; lượt thử và ngày thử lại được lưu trong Control DB. Đến hạn mới thử tiếp, không vòng lặp vô hạn và không đánh dấu hoàn/chi thành công khi xử lý thất bại. Đây chưa phải một bảng ledger callback của nhà cung cấp trong OLTP.

### Một nguồn cấu hình chính

`UpgradedScenario.build()` đọc bản JSON được duy trì, không còn dựng một bản cũ mất actor/schedule/lookup. Lệnh xuất yêu cầu đường dẫn riêng:

```bash
.venv/bin/python -m scripts.mock_platform.config.upgraded_scenario --output /tmp/retail-2026.json
```

Lệnh từ chối ghi đè file latest. Bản lịch này dành cho 2026; không tự đổi năm của một calendar đã chốt.

## Các tham số mới

### Khung giờ có trọng số và độ trễ theo đầu vào

```json
{
  "windows": [
    {"start": "07:00:00", "end": "10:59:59", "weight": 15},
    {"start": "18:00:00", "end": "21:59:59", "weight": 35}
  ],
  "duration_seconds": {"kind": "integer", "min": 600, "max": 3300}
}
```

Đặt trong schedule của tạo phiên. Đây là trọng số chọn khung, không phải số phiên chính xác. Hành vi phiên vẫn có offset_seconds tính từ mở phiên; nếu không thỏa thứ tự sự kiện hoặc phiên đã hết thời lượng thì bị từ chối.

```json
{"start":"08:00:00","end":"21:59:59","after_seconds":{"kind":"integer","min":60,"max":7200}}
```

Đặt trong schedule của bước xử lý: after_seconds là độ trễ tối thiểu từ nguồn; thời điểm thực hiện còn phụ thuộc lượt xử lý hiện tại, delay_days và giờ cho phép. Không tự chuyển sự kiện đã quá khung sang quá khứ.

### Ưu tiên và quần thể

```json
{"products":{"source":"session_views","weight":15,"require":false}}
```

Đặt trong preferences. Nếu cả hai nhóm đều có sản phẩm đủ điều kiện, weight 15 nghĩa là odds nhóm đã xem : nhóm còn lại = 15 : 1. require=true chỉ cho chọn nhóm đã xem; không có đầu vào thì báo hết điều kiện. `session_interest` là nguồn ưu tiên danh mục từ tìm kiếm.

```json
{"field":"membership_tier","weights":{"Member":1,"Silver":1.7,"Gold":2.8},"default":1}
```

Đặt trong sampling của actor group OLTP. Đây là trọng số hoạt động của từng thực thể, không phải quota hành động hay tỷ lệ dân số mong muốn. Nhóm nhân sự có thể truyền availability với start/end để kiểm soát giờ thực hiện.

### Phân bố chuỗi và xử lý nhiều nhóm

```json
{"kind":"pattern","value":"09{digits:8}"}
```

Dùng cho thuộc tính chuỗi được hỗ trợ trong hồ sơ. Token chỉ gồm digits, letters, token với độ dài 1..32; không thực thi biểu thức/Python. Các field mới gồm customer email và seller seller_name/email, bên cạnh những field đã có.

`variant_mode: "random"` giữ cách chọn theo trọng số. `variant_mode: "cycle"` duyệt lần lượt các bundle; ở mode all chỉ dừng khi cả một vòng không còn đầu vào hợp lệ. Bản mới dùng cycle để tạo policy cho cả ba hạng seller. `phase` là thứ tự xử lý tương đối của hành động; không thay cho kiểm tra nhân quả thời gian.

UI có phần tùy chọn nâng cao trong editor hành động; các trường mới được giữ qua import, chỉnh sửa và lưu. Tổng quan cấu hình hiển thị khung giờ, độ trễ, cách chọn bundle và ưu tiên sản phẩm.

## Lịch và độ đa dạng

Bản đầy đủ bật 52 hành động, trong đó 19 xử lý theo đầu vào. Calendar có yếu tố ngày trong tuần, sale và biến thiên riêng cho từng chỉ số. Không còn khóa tỷ lệ phiên = 15 × checkout hoặc view = 2 × phiên suốt năm. Hành động hiếm dùng lịch số lượng nguyên biến thiên; không còn mặc định một yêu cầu trả hàng cho mọi ngày thường và sale.

Các chỉ số có calendar đủ 365 ngày dùng số theo ngày trong `special`, ghi đè `count` ngày thường. Muốn chỉnh sản lượng một ngày trong năm 2026, sửa số của ngày đó; chỉ sửa count sẽ không thay thế calendar đã khai báo. Hành động cập nhật liên hệ seller có lịch một lần vào đầu tháng, không ép sửa tên/mô tả sản phẩm Tiki để tạo hoạt động catalog.

Guest và khách đăng ký có phân bố channel/traffic/method khác nhau. Tồn có coverage theo vùng, nhập hàng phân tán qua kho và lượng; review có nhiều cặp rating/nội dung nhất quán. Những phân bố này là giả định vận hành có thể thay đổi trong JSON; không phải cố định ngành hàng sách hoặc 149 sản phẩm đã crawl thử.

## Áp dụng trên máy đang có dữ liệu

1. Tải lại web. **Thiết lập môi trường → Nhập JSON** hồ sơ mới, kiểm tra và lưu cả policy lẫn profile.
2. **Cấu hình kịch bản → Nhập JSON** kịch bản mới; xem tổng quan 6 hệ thống và các quota ngày. Lưu thành cấu hình để lập plan.
3. Với một môi trường mới: lưu profile trước → đồng bộ Tiki → tạo dữ liệu nền → lập kế hoạch từ ngày bắt đầu. Với môi trường đang chạy: tiếp tục đúng ngày sau checkpoint và xem cảnh báo thiếu tài nguyên.
4. Hồ sơ mới **không đổi các dòng cũ**. Nếu carrier_code mới chưa có trong DB cũ, dispatch theo code mới sẽ bị từ chối; không tự tạo carrier hoặc sửa ID âm thầm. Muốn kiểm tra toàn bộ profile mới từ đầu, chủ động dùng môi trường test riêng hoặc chức năng xóa toàn bộ đã có sau khi tự xem trước/xác nhận.
5. Plan preview trước khi code đổi cần preview lại. Job đã tạo từ engine cũ không tự chuyển sang semantics mới. Không reset hoặc áp config thay bạn trong đợt cập nhật này.

Ô tồn chung không áp dụng nếu profile có inventory rules; UI đã ghi rõ. Số khách nền là quy mô ban đầu, không chặn việc đăng ký thêm khách qua ngày. Seed để tái lập lựa chọn, không phải chỉ số sản lượng.

## Giới hạn vẫn cần hiểu đúng

Engine còn chạy theo phase và ngày, chưa phải mô hình hàng đợi sự kiện toàn sàn theo thời gian thực. Marketing attribution, quota traffic và chi quảng cáo vẫn là các đầu vào cấu hình riêng; budget chưa tự sinh demand. Voucher vẫn theo semantics fixed amount đã hỗ trợ; hàng trả trong kịch bản này được giả định còn có thể bán. Email, số nhà, tên người/shop là dữ liệu tổng hợp, không phải hồ sơ đã xác minh.

Giá và các chỉ số lịch sử Tiki giữ vai trò snapshot nguồn; không cập nhật giả `quantity_sold`, `review_count`, `rating_average` hoặc giá vốn để làm đầy trường. Báo cáo vận hành mô phỏng phải tính từ đơn/review phát sinh. Giới hạn bảo vệ số hành động/lượt vẫn có; chia khoảng chạy liên tục nếu calendar cả năm vượt giới hạn preview.

Độ tự nhiên đã tăng, nhưng không có bảo đảm rằng một bộ dữ liệu tổng hợp không thể bị nhận ra bằng mọi phép phân tích thống kê. Các kiểm tra cần bao gồm cả tính đúng nghiệp vụ và độ hợp lý phân bố, không chỉ trạng thái COMPLETE.
