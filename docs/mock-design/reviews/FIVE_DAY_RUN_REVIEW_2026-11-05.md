# Đối chiếu UI và OLTP: lượt chạy 01–05/01/2026

Kiểm tra ngày 05–06/11/2026. Chỉ đọc UI, cấu hình, nhật ký và PostgreSQL; không sửa dữ liệu nghiệp vụ, không reset hoặc chạy lại.

## Kết luận

Lượt chạy hoàn tất đúng checkpoint đến 05/01/2026; ngày tiếp theo là 06/01. Dữ liệu đã phát sinh vượt qua 12 nhóm kiểm tra của validator khi giới hạn đúng lượt chạy. Tuy nhiên, chưa thể coi đây là bài kiểm thử đầy đủ các luồng thương mại điện tử: tồn đầu bằng 0 khiến 104/105 yêu cầu checkout bị từ chối, chỉ tạo được một đơn.

- Job: `e0fdd9c0-c36e-4129-b86c-c2df5e728beb`.
- Plan: `12754829-41af-475d-bfed-25cea996c1b7`.
- Kịch bản: **Vận hành liên kết 2026 · profile & nghiệp vụ qua ngày**.
- PostgreSQL nghiệp vụ: `127.0.0.1:55432/mock_oltp`, schema `public`.
- PostgreSQL điều khiển: `mock_control`, tách biệt dữ liệu nghiệp vụ.

## Kết quả thực tế

| Chỉ số | Kết quả |
|---|---:|
| Hành động DONE | 7.879 |
| Yêu cầu REJECTED | 123 |
| Lượt tự xử lý không còn đầu vào EXHAUSTED | 95 |
| Sản phẩm / người bán | 149 / 9 |
| Khách hàng | 24 |
| Phiên / sự kiện truy cập | 1.575 / 4.367 |
| Giỏ hàng (dòng) | 315 |
| Checkout / đơn / dòng đơn | 1 / 1 / 1 |
| Thanh toán thành công / vận đơn đã giao | 1 / 1 |
| Yêu cầu trả / hoàn tiền / đối soát | 1 / 0 / 0 |
| Kho / đơn vị vận chuyển | 6 / 5 |
| Tồn thực tế / tồn đang giữ | 99 / 0 |

6.115 yêu cầu trong bản xem trước là số lượng yêu cầu cấu hình tường minh. Hành động tự xử lý đầu vào đến hạn không nằm toàn bộ trong con số này, nên không đối chiếu trực tiếp với tổng DONE.

123 yêu cầu bị từ chối gồm 104 checkout thiếu hàng (78 khách đăng ký, 26 khách vãng lai), 15 yêu cầu đánh giá và 4 yêu cầu trả hàng chưa tìm được dòng đơn đủ điều kiện. Đây là kết quả điều kiện nghiệp vụ, không phải 123 lỗi SQL. EXHAUSTED là tín hiệu bộ xử lý tự động không còn đầu vào phù hợp.

## Vì sao gần như không có đơn?

Nhật ký bootstrap xác nhận **0 khách nền, 0 tồn đầu**; UI Thiết lập môi trường cũng hiện hai giá trị 0. Khách nền bằng 0 không chặn hoàn toàn vì kịch bản tạo khách mới trong quá trình chạy. Tồn đầu bằng 0 là nút thắt chính.

WH-01 chỉ nhập 20 đơn vị của một SKU tại kho 1 mỗi ngày. Sau năm ngày chỉ có 5 dòng tồn cho 149 sản phẩm; năm kho còn lại chưa có hàng. Tổng nhập 100, xuất bán 1, còn 99. Checkout yêu cầu một kho đủ hàng cho toàn bộ dòng của shop nên bị từ chối khi không đủ; engine không tự tạo tồn để đáp ứng quota đơn.

Để thử đầy đủ luồng mua hàng, lần chạy mới cần cấu hình tồn đầu dương hoặc thiết kế lượng nhập kho/phủ SKU tương ứng với lượng checkout. Hồ sơ có 6 kho chỉ tạo thực thể kho, không tự cấp hàng. Không bấm bootstrap lại để kỳ vọng bổ sung tồn sau khi bootstrap đã hoàn tất; cần dùng luồng nhập kho hoặc chuẩn bị một môi trường/lượt test mới theo quy trình reset.

## Hồ sơ đa dạng và chính sách có áp dụng không?

- Hồ sơ đa dạng đã áp dụng: 24 khách có 24 tên và 24 điện thoại khác nhau; phân bố tỉnh/thành TP.HCM 10, Hà Nội 10, Đà Nẵng 4.
- Có 6 kho, 5 carrier; bộ hồ sơ có 24 địa phương tổng hợp. Địa chỉ vẫn là dữ liệu thử nghiệm, không đại diện địa giới hành chính thật.
- Thiết bị: Mobile 1.173, Desktop 402. Không có Tablet vì kịch bản hiện tại chỉ chọn hai loại trên.
- Nguồn truy cập: Organic 947, Direct 383, Social 167, Email 78.
- Chính sách trên UI, trong cấu hình đã lưu và snapshot kế hoạch đều là **trả hàng 7 ngày, giữ tiền đối soát 8 ngày, tối đa 3 lần giao**.
- File mẫu đa dạng đề xuất giữ tiền **10 ngày**. Vì vậy không nên hiểu rằng mọi phần của file mẫu đã được lưu giống hệt. Nhập/fill form và lưu hồ sơ thực thể không thay thế thao tác lưu chính sách; chính sách cho lượt này thực tế là 8 ngày.

## Đối chiếu chuỗi nghiệp vụ của đơn duy nhất

Đơn `id=1`, checkout `id=1`, khách 14, shop 229023, sản phẩm 279704449, số lượng 1:

1. Tạo đơn ngày 03/01 lúc 11:25.
2. Thanh toán Momo thành công ngày 03/01 lúc 12:19:31, số tiền 601.550 đồng.
3. Tạo vận đơn ngày 04/01, lấy hàng và chuyển vận trong ngày; giao thành công ngày 05/01 lúc 17:16:56. Đơn Completed.
4. Yêu cầu trả ngày 05/01 lúc 19:56:09, duyệt lúc 20:29:58; chưa nhận hàng trả.

Tiền đơn khớp: **616.550 − 20.000 + 20.000 − 15.000 = 601.550 đồng**. Tiền trả hàng dự kiến 596.550 đồng là phần tiền hàng sau giảm giá, không hoàn phí giao theo chính sách hiện tại.

Chưa có refund là hợp lý: cấu hình nhận hàng trả trễ 2 ngày, nên đến cuối 05/01 chưa đến hạn nhận; sau đó mới đến bước hoàn tiền với độ trễ riêng. Nếu các bộ xử lý vẫn bật, nhận hàng trả sớm nhất từ 07/01 và hoàn tiền từ 08/01 theo lịch hiện tại.

Chưa có đối soát cũng hợp lý: đơn mới hoàn tất 05/01, đang có yêu cầu trả chưa đóng và chưa hết thời gian giữ tiền. Chưa có đánh giá không chứng minh lỗi: cấu hình yêu cầu độ trễ sau hoàn tất, còn nhiều yêu cầu đánh giá trước đó không có đơn đủ điều kiện.

## Các vấn đề của công cụ/UI được phát hiện

### Báo cáo toàn lịch sử đối chiếu nhầm sau reset

File `audit-five-day-run-2026-11-05.json` có 109 phép kiểm tra, chỉ mục analytics actor báo 2.269 vi phạm. **Không dùng con số này để kết luận lượt hiện tại sai actor.**

Control DB giữ nhật ký các lượt cũ, còn OLTP đã được reset và dùng lại ID. Audit/validator toàn lịch sử đang tìm sự kiện chỉ theo ID, nên có thể đem nhật ký cũ đối chiếu với sự kiện mới. Kiểm tra độc lập tìm được 2.428 tham chiếu ID sự kiện từ job cũ trùng ID hiện tại; số này không đồng nghĩa số vi phạm actor. Ví dụ sự kiện ID 67: nhật ký cũ ghi 01/01 lúc 10:00:00, bản ghi hiện tại là 10:29:47 và nội dung khác.

Validator giới hạn đúng job hiện tại trả về `ok=true`, **0 lỗi, 12 nhóm kiểm tra**. Cần nâng cấp audit để phân biệt thế hệ dữ liệu sau reset hoặc xác minh nguồn gốc bản ghi, tránh trộn nhật ký cũ với dữ liệu mới.

### Tổng quan có phần chưa tự làm mới

Khi mở trang đang giữ trạng thái cũ, dashboard số liệu OLTP đã cập nhật nhưng thẻ checkpoint/danh sách job vẫn có thể hiện lượt trước (đã thấy mốc 18/02). Chuyển sang Theo dõi lượt chạy thì hiện đúng hoàn tất 05/01, 7.879 DONE, 123 REJECTED và một yêu cầu chờ nhận hàng trả. Cần thống nhất cập nhật các phần UI, đặc biệt sau reset và hoàn tất job.

Danh sách hành động gần nhất chỉ hiện 100 mục nên các checkout bị từ chối trước đó dễ bị khuất bởi nhiều sự kiện analytics. Nên bổ sung tổng hợp theo hành động/lý do và bộ lọc thất bại. Phần kiểm tra trước khi chạy cũng nên cảnh báo tồn đầu bằng 0 hoặc độ phủ tồn quá thấp so với catalog.

## Giới hạn của kết luận

Không phát hiện vi phạm trong các kiểm tra đã thực hiện cho dữ liệu hiện tại không đồng nghĩa mọi nhánh engine đã được kiểm thử. Chỉ một đơn thành công không đủ đánh giá phân bố nhiều sản phẩm/shop/kho, nhiều lần giao thất bại, nhiều dòng đơn, hoàn tiền và đối soát hoàn tất. Cần một lần test có đủ tồn và thời gian chạy dài hơn để bao phủ các nhánh đó.

Lần kiểm tra này không thay đổi config, checkpoint hay dữ liệu OLTP.
