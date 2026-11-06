# Kiểm tra lượt chạy lại và mức độ sát thực tế — 06/11/2026

## Phạm vi và kết luận

Đọc UI tại localhost:8765, PostgreSQL mock_control và mock_oltp.public, snapshot kế hoạch và code đang thực thi. Không sửa config, không dừng/reset/chạy thêm nghiệp vụ.

**Đã khắc phục nút thắt thiếu tồn của lượt trước. Quan hệ nghiệp vụ được kiểm tra chưa phát hiện sai, nhưng phân bố hành vi, thời gian, tồn kho và attribution quảng cáo vẫn chưa sát vận hành thực tế.** Đây là nhận xét từ dữ liệu và code của engine, không phải so sánh với một bộ tỷ lệ chuẩn của mọi sàn.

Lượt `97f7dddd-f285-42a6-8d22-ffdfd0b2b73e`, cấu hình **update 6/11**, kế hoạch 01–05/01/2026. Tại snapshot cuối lúc heartbeat **00:13:49 ngày 06/11/2026 (UTC+7)**: RUNNING, đang xử lý ngày 04/01, checkpoint hoàn tất đến 03/01. Các số sau là tại thời điểm kiểm tra, không phải kết quả cuối 5 ngày. Business snapshot được đọc bằng transaction REPEATABLE READ, READ ONLY; trạng thái Control có thể tiến thêm trong lúc đối chiếu.

## Số liệu xác nhận

| Chỉ số | Số lượng |
|---|---:|
| Khách nền / tồn đầu mỗi SKU mỗi kho / seed | 500 / 200 / 42 |
| Sản phẩm / kho / dòng tồn | 149 / 6 / 894 |
| Tổng tồn đầu | 178.800 |
| Khách hiện có | 521 |
| Checkout thành công / đơn / dòng đơn | 91 / 107 / 111 |
| Đơn hoàn tất / Processing / Pending | 44 / 62 / 1 |
| Thanh toán Success / Failed | 80 / 1 |
| Vận đơn Delivered / In Transit | 44 / 32 |
| Yêu cầu trả Approved / đánh giá | 2 / 4 |
| Refund / đối soát | 0 / 0 |
| Tồn thực tế / đang giữ | 178.790 / 41 |

Đơn theo ngày: **20, 26, 30, 31** cho 01–04/01. 91 checkout gồm 69 khách đăng ký và 22 khách vãng lai; một checkout có thể tách nhiều đơn theo shop, nên 107 đơn không phải lỗi tạo vượt 91 checkout. Chưa ghi nhận checkout bị từ chối trong lượt này tại snapshot.

Có 11 yêu cầu không đủ điều kiện: 9 đánh giá và 2 trả hàng do chưa có dòng đơn đủ điều kiện ở thời điểm yêu cầu. Không coi việc chưa giao xong của đơn mới hoặc chưa có refund/đối soát là lỗi tự động: phải xét thời gian đến hạn, nhận hàng trả và chính sách giữ tiền. Chính sách snapshot là 7 ngày trả hàng, 8 ngày giữ tiền, 3 lần giao.

## Kiểm tra quan hệ và rule

- Validator giới hạn actor theo đúng job hiện tại: **12 nhóm, 0 lỗi** ở thời điểm thực hiện. Các kiểm tra gồm tồn/sổ biến động/giữ hàng, tiền đơn và dòng đơn, thanh toán, quyền sở hữu khách–phiên–giỏ–địa chỉ–đơn, thời gian giao, đánh giá, giới hạn trả/hoàn và ledger đối soát. Một bảng chưa có dữ liệu không chứng minh nhánh đó đã được kiểm thử đầy đủ.
- Audit snapshot độc lập: **108/109 kiểm tra không có vi phạm**. Mục actor toàn lịch sử tiếp tục báo sai do nhật ký trước reset trùng ID với bản ghi mới. Không dùng tổng lỗi mục này để kết luận dữ liệu hiện tại sai. Đây là lỗi công cụ cần sửa như báo cáo trước.
- Nguồn Tiki 149 sản phẩm, đủ 149 provenance, không chênh giá so với nguồn hiện tại; không có ID mới chưa nhập tại thời điểm audit. Điều này phù hợp snapshot hiện tại; không thay thế bài test riêng chứng minh append-only khi crawler đổi giá về sau.
- Không tự tạo dữ liệu bổ sung chỉ vì mở UI hay thực hiện kiểm tra.

## Những phần còn chưa sát thực tế

| Điểm quan sát | Ý nghĩa | Giải pháp bằng config hay code? |
|---|---|---|
| Mỗi SKU ở mỗi kho khởi tạo đúng 200 đơn vị; 178.800 hàng so với vài chục đơn/ngày | Phù hợp bài test tránh thiếu hàng; chưa mô phỏng mặt hàng bán mạnh/yếu, hàng chỉ có ở một số kho, thiếu hàng cục bộ | Hiện chỉ đổi được một lượng tồn đầu chung; tồn đầu theo sản phẩm/kho/phân bố cần thêm code và cấu hình |
| Phiên đã đóng dài khoảng 11,87–12,97 giờ, trung bình 12,42 giờ | Bộ tạo mở phiên ở giai đoạn buổi sáng và đóng ở giai đoạn tối, chưa thể hiện thời lượng phiên tự nhiên | Cần code lịch sự kiện/thời lượng phiên. Seed hoặc tăng khách nền không giải quyết |
| 107/107 đơn phí giao 20.000đ; 76/76 vận đơn chi phí 30.000đ | Đây là giá trị cố định của config, chưa phân biệt quãng đường, dịch vụ hoặc trọng lượng | Có thể thêm variants mức phí vào config; tính phí phụ thuộc tuyến, trọng lượng, carrier cần code |
| Có chi quảng cáo, nhưng 0 phiên và 0 đơn có campaign_id | Không phân tích được hiệu quả chiến dịch từ click đến đơn | Có thể sửa config: chiến dịch thực tế target APP, còn variants Social/Email có campaign=auto lại ở Web. Các phiên App hiện là Direct không yêu cầu attribution. Cần có campaign phù hợp kênh và phiên được gắn campaign; không ép mọi lượt organic/direct vào quảng cáo |
| Kho được chọn ngẫu nhiên trong các kho đủ hàng | Có tuyến giao liên vùng dù nơi nhận có kho đủ hàng. Giao liên vùng tự nó hợp lệ; engine chưa tối ưu kho theo vị trí/chi phí/SLA | Có thể chỉ định kho và carrier trong config; chọn tự động theo địa lý/SLA cần code |
| 103/107 đơn chỉ có một dòng; chỉ 4 đơn có hai dòng | Dữ liệu đa dòng chưa nhiều. Một phần giỏ nhiều shop đã tách thành nhiều đơn hợp lệ | Cần điều chỉnh cấu hình hành vi giỏ và kiểm chứng cách chọn phiên/giỏ; không nhầm tăng quantity với tăng số SKU khác nhau |
| Giờ hành động tập trung theo từng giai đoạn cố định | Đã tránh mọi bản ghi cùng timestamp, nhưng xem hàng/mua/thanh toán không phân bố cả ngày và phụ thuộc lịch tổng thể hơn lịch riêng của từng khách | Cần nâng cấp code lập lịch theo sự kiện, sau đó cấu hình phân bố giờ và độ trễ |
| Toàn bộ khách trong snapshot phân tích đều chưa có gender/date_of_birth | NULL có thể hợp lệ nếu trường tùy chọn; hiện chưa thử được phân khúc có thông tin và thiếu thông tin | Cần thêm bộ sinh và config tỷ lệ điền nếu muốn kiểm thử phân khúc này |

Các tỷ lệ xác suất như thanh toán thành công 94%, giao thành công 95% không bắt buộc mẫu nhỏ phải ra đúng tuyệt đối. Không tự kết luận lỗi chỉ vì kết quả 5 ngày lệch tỷ lệ cấu hình.

## UI được kiểm tra

Tab đang mở giữ trạng thái lượt cũ. Khi chuyển sang monitor ban đầu, phần tiến độ còn hiện lượt trước trong khi bảng nghiệp vụ đọc DB mới. Sau reload, monitor hiện đúng lượt RUNNING ngày 03/01 và số đang chờ khớp giai đoạn DB tại thời điểm đó. Đây là vấn đề làm mới/chọn job của UI; cần cập nhật toàn bộ trạng thái khi phát hiện reset hoặc job mới, không chỉ refresh các bảng số liệu.

## Thứ tự xử lý đề xuất

1. Giữ lượt đang chạy để quan sát. Không cần tiếp tục tăng tồn: mức 200 đã rất dư cho bài test này.
2. Với kế hoạch tiếp theo, chỉnh config attribution theo đúng kênh, thêm variants phí và cân đối số yêu cầu đánh giá/trả với đầu vào đủ điều kiện. Không thay đổi snapshot của job đang chạy.
3. Sửa UI lấy đúng job và audit nhận diện thế hệ dữ liệu sau reset.
4. Nâng cấp engine về thời lượng phiên, lịch sự kiện, chọn kho theo vị trí và tồn đầu có phân bố. Đây là các phần không thể giải quyết chỉ bằng seed/count.
5. Đánh giá lại sau khi đủ thời gian cho trả hàng–nhận hàng–hoàn tiền và đối soát. Chạy 5 ngày chưa bao phủ trọn chu kỳ; không nên tạo refund hay payout sớm để lấp bảng.
