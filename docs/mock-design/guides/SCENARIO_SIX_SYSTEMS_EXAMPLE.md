# Kịch bản thử đã cấu hình cho 6 hệ thống

Đã lưu vào Control DB theo yêu cầu người dùng. **Chưa chạy trên Business DB chính.**

- Tên phiên bản: **Thử nghiệm 6 hệ thống · 10 checkout/ngày · sale ×3**.
- Version ID: `1fb0daf2-1ffa-44e9-8e93-8dc78841cc45`.
- Ngày kế tiếp khi lập cấu hình: `2026-01-01`.
- Catalog hiện có 149 sản phẩm, 9 seller; dữ liệu nền 100 khách, tồn đầu 20/SKU.
- Ngày đặc biệt: 2026-08-08, 2026-10-10, 2026-11-11, 2026-12-12. Số lần riêng thay thế số ngày thường.
- Các bước thanh toán/giao hàng trong bản thử đặt 100% thành công để dễ đối chiếu; không phải tỷ lệ thực tế của Tiki.

## Hành động đã bật

| Hệ thống | Mã | Hành động | Ngày thường | Ngày đặc biệt | Cấu hình riêng |
|---|---|---|---|---|---|
| Catalog & Seller | `SEL-01` | Đổi tên shop | 1 | 1 | {} |
| Khách hàng & Đơn hàng | `GST-01` | Đăng ký tài khoản | 5 | 15 | {"province": "TP. Hồ Chí Minh"} |
| Khách hàng & Đơn hàng | `GST-02` | Đặt hàng không đăng nhập | 2 | 6 | {"quantity": 1, "method": "COD", "channel": "Web"} |
| Khách hàng & Đơn hàng | `CUS-03` | Thêm địa chỉ nhận hàng | 3 | 9 | {"province": "TP. Hồ Chí Minh"} |
| Khách hàng & Đơn hàng | `CUS-05` | Đặt hàng sau khi đăng nhập | 8 | 24 | {"quantity": 1, "method": "Momo", "channel": "App"} |
| Khách hàng & Đơn hàng | `CUS-09` | Đánh giá sản phẩm đã mua | 3 | 9 | {"rating": 5, "value": "Đánh giá thử nghiệm sau mua hàng."} |
| Khách hàng & Đơn hàng | `ORD-01` | Xác nhận xử lý đơn | Theo đầu vào | Theo đầu vào | {} |
| Khách hàng & Đơn hàng | `PAY-01` | Trả kết quả thanh toán trả trước | Theo đầu vào | Theo đầu vào | {"success_rate": 100} |
| Kho vận | `WH-01` | Nhập hàng | 3 | 9 | {"warehouse": 1, "quantity": 10} |
| Kho vận | `DSP-01` | Tạo vận đơn | Theo đầu vào | Theo đầu vào | {"warehouse": 1, "amount": 30000} |
| Kho vận | `CAR-01` | Lấy hàng | Theo đầu vào | Theo đầu vào | {} |
| Kho vận | `CAR-02` | Cập nhật đang vận chuyển | Theo đầu vào | Theo đầu vào | {} |
| Kho vận | `CAR-03` | Báo kết quả giao hàng | Theo đầu vào | Theo đầu vào | {"success_rate": 100} |
| Kho vận | `CAR-04` | Trả kết quả thu COD | Theo đầu vào | Theo đầu vào | {} |
| Kho vận | `AUT-WH-04` | Chốt số dư cuối ngày | 1 | 1 | {} |
| Marketing | `MKT-01` | Tạo chiến dịch | 1 | 1 | {"value": "Chiến dịch thử nghiệm 6 hệ thống", "amount": 2000000, "days": 7} |
| Marketing | `MKT-03` | Tạo voucher sàn | 1 | 1 | {"amount": 20000, "min_order": 200000, "limit": 100, "days": 7} |
| Marketing | `MKT-04` | Tạo voucher freeship | 1 | 1 | {"amount": 15000, "min_order": 150000, "limit": 100, "days": 7} |
| Marketing | `SHOP-MKT-01` | Tạo voucher shop | 1 | 1 | {"amount": 10000, "min_order": 100000, "limit": 100, "days": 7} |
| Marketing | `ADS-01` | Trả báo cáo quảng cáo theo ngày | 1 | 1 | {"amount": 100000, "quantity": 30} |
| Marketing | `AUT-MKT-03` | Đánh giá hiệu lực theo thời gian | 1 | 1 | {} |
| Web analytics | `GST-WEB-01` | Bắt đầu phiên truy cập | 10 | 30 | {"channel": "Web", "device": "Mobile", "traffic": "Organic"} |
| Web analytics | `GST-WEB-02` | Tìm kiếm | 10 | 30 | {"value": "Sách nghệ thuật"} |
| Web analytics | `GST-WEB-03` | Xem chi tiết sản phẩm | 20 | 60 | {} |
| Web analytics | `GST-WEB-04` | Thêm sản phẩm vào giỏ | 4 | 12 | {"quantity": 1} |
| Web analytics | `GST-WEB-05` | Bỏ sản phẩm khỏi giỏ | 1 | 3 | {} |
| Web analytics | `GST-WEB-06` | Bắt đầu checkout | 2 | 6 | {} |
| Web analytics | `AUT-WEB-01` | Kết thúc phiên đến hạn | Theo đầu vào | Theo đầu vào | {"channel": "Web", "device": "Mobile", "traffic": "Organic"} |
| Web analytics | `AUT-WEB-02` | Đánh dấu giỏ bị bỏ | Theo đầu vào | Theo đầu vào | {"quantity": 1} |
| Web analytics | `CUS-WEB-01` | Bắt đầu phiên truy cập | 20 | 60 | {"channel": "App", "device": "Mobile", "traffic": "Direct"} |
| Web analytics | `CUS-WEB-02` | Tìm kiếm | 10 | 30 | {"value": "Sách kiến trúc"} |
| Web analytics | `CUS-WEB-03` | Xem chi tiết sản phẩm | 40 | 120 | {} |
| Web analytics | `CUS-WEB-04` | Thêm sản phẩm vào giỏ | 8 | 24 | {"quantity": 1} |
| Web analytics | `CUS-WEB-05` | Bỏ sản phẩm khỏi giỏ | 2 | 6 | {} |
| Web analytics | `CUS-WEB-06` | Bắt đầu checkout | 6 | 18 | {} |
| Tài chính | `FIN-POL-01` | Tạo chính sách hoa hồng | 0 | 1 lần ngày 2026-01-01; sau đó 0 | {"category": 9423, "tier": "Normal", "rate": 5, "start": "2026-01-01"} |

## Lưu ý về phạm vi

- Catalog chỉ bật đổi tên shop mô phỏng, không đổi tên/giá sản phẩm hoặc tự khóa shop trong gói thử này.
- Tạo 2 checkout guest COD và 8 checkout đăng nhập Momo mỗi ngày; ngày sale lần lượt là 6 và 24. Thanh toán/xử lý đơn/vận chuyển dùng nguồn đầu vào thực tế, không sinh thêm yêu cầu cho đủ quota.
- Chỉ dùng CAR-01 để xuất/lấy hàng, không bật WH-03 song song để tránh tác động trùng. Chốt tồn 1 lượt/ngày.
- Analytics tự tạo phiên và các hành động đọc/giỏ; checkout analytics hiện chỉ là ý định, chưa liên kết vào đơn. Không dùng các số này để kết luận tỷ lệ chuyển đổi thật.
- Marketing tạo voucher và báo cáo; bản hiện tại chưa áp voucher vào checkout. 30 click/báo cáo và 100.000 VND/báo cáo là tham số độc lập; không tự coi bằng số session Organic/Direct.
- Tài chính chỉ bật tạo chính sách hoa hồng Normal 5% cho danh mục Photography (ID 9423), một lần ngày đầu. Chưa bật đối soát/chi trả vì handler lập nghĩa vụ chưa sẵn sàng. Không tạo chính sách giống nhau lặp mỗi ngày.
- Các hành động khác vẫn tắt. Đây là cấu hình thử nhỏ, không phải toàn bộ kịch bản nghiệp vụ hoặc bảo đảm đủ tồn khi chạy cả năm.

## Kiểm chứng trước khi lưu

Chạy trên bản sao dữ liệu trong SQLite tách biệt: hoàn tất 265 hành động, 0 từ chối, tạo 10 đơn, 10 giao dịch thanh toán, 10 vận đơn và 1 chính sách hoa hồng; kiểm tra cuối ngày đạt. Không chạy job này trên `mock_oltp` chính.

Preview cho ngày đầu có 166 yêu cầu định lượng và 9 luồng xử lý theo đầu vào. Số 265 hoàn tất bao gồm kết quả xử lý tự động, nên không phải chỉ tiêu cố định của mọi ngày.

## Sử dụng trên web

1. Tải lại web để lấy draft mới.
2. Mở **Cấu hình kịch bản** và lần lượt chọn 6 tab để xem/chỉnh.
3. Nếu chỉnh, lưu phiên bản mới; phiên bản đã lưu không tự đổi.
4. Vào **Lập kế hoạch & Chạy**, chọn phiên bản trên, chọn một ngày từ checkpoint.
5. Xem trước rồi tự quyết định bấm chạy. Cấu hình này chưa phát lệnh chạy trên môi trường chính.

Bản JSON ví dụ cũ đã được dọn; dùng [mẫu liên kết mới nhất](../examples/scenarios/upgraded-linked-2026.json). Nội dung tài liệu này là tham khảo thiết kế trước đây.
