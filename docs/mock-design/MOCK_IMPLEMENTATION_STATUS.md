# Trạng thái triển khai Mock Studio

Bản triển khai ngày 05/11/2026. Đây là báo cáo thực tế, không thay thế rule hoặc tự xác nhận nghiệp vụ chưa chốt.

## Đã triển khai

- 7 trang UI với 6 tab cấu hình, trường riêng từng hành động, ngày thường/ngày đặc biệt, draft và phiên bản trong Control DB.
- Hai database PostgreSQL riêng: điều khiển và nghiệp vụ; đồng bộ chỉ đọc SQLite crawler; chức năng cào chủ động ghi SQLite riêng. Tạo cấu trúc nghiệp vụ theo thao tác chuẩn bị môi trường.
- API và worker là hai tiến trình; tiến độ SSE + polling fallback, job bền, pause/resume và chặn job ghi chồng nhau.
- Đồng bộ append-only bằng snapshot nguồn; preview không ghi nghiệp vụ; báo trùng/thiếu SKU hoặc khác chào bán cùng ID.
- Luồng đơn một shop/một sản phẩm → giữ hàng → thanh toán trả trước hoặc COD → xuất/giao/thu COD; một số hành động catalog, khách hàng, marketing và analytics.
- Khôi phục bằng before/after manifest giữa hai DB. Không retry mù khi trạng thái đích không khớp. Kiểm thử sau target commit không chèn trùng.
- Kiểm tra số tiền đơn/thanh toán, tồn theo ledger, lượng giữ và thứ tự thời gian vận chuyển.

Registry hiện có **89 mã hành động**, **66 có handler được bật**. “Có handler” không có nghĩa đã hoàn thiện toàn bộ biến thể nghiệp vụ hoặc tất cả form đã có đủ tùy chọn theo thiết kế. Các luồng còn đơn giản được ghi rõ ở UI/README.

## Các giới hạn quan trọng

- Chưa hoàn thiện mọi nghiệp vụ của 27 bảng; schema được tạo đầy đủ không có nghĩa bảng nào cũng đã có bộ sinh thực thi.
- Checkout một sản phẩm, một shop; chưa áp voucher, chưa gắn session/campaign cho đơn, chưa hỗ trợ multi-shop. Phí giao khách trả bằng 0 trong gói thử.
- Thời gian hành động có thứ tự cố định trong ngày; chưa có độ trễ nhiều ngày theo chính sách carrier/payment. Chọn tháng/năm là lặp ngày liên tục, chưa chứng minh hiệu năng quy mô lớn.
- Chưa có màn chọn đối tượng dạng tìm kiếm tên: dùng ID rõ ràng hoặc chọn hợp lệ tự động. Chưa có form cấu hình tự do kho/carrier; bootstrap tạo một kho/carrier mô phỏng có ghi chú.
- Cây danh mục nhập gốc/lá; chưa khẳng định dựng đủ cây trung gian từ Tiki. Tên không có nguồn được đánh dấu theo ID, provenance lưu riêng.
- Hạng seller/thành viên chỉ định để thử; chưa tính theo hiệu suất. Điều chỉnh tồn hiện chỉ tăng. Báo cáo quảng cáo có số chi chỉ định và CTR 1%, chưa có form CPC/CPM đầy đủ.
- Control DB dùng một bảng tài liệu có `kind/id/data`, chưa phân thành nhiều bảng vật lý như gợi ý kiến trúc. Không trộn nó vào Business DB.
- Chưa migration schema/version engine tự động, chưa phục hồi trường hợp có tác nhân ngoài ghi Business DB. Bộ kiểm tra không thay cho toàn bộ các bất biến của nghiệp vụ tương lai.

## Hành động khóa trên UI

| Hệ thống | Mã | Hành động | Lý do |
|---|---|---|---|
| Catalog & Seller | `VIS-02` | Xem danh sách danh mục | Schema chưa có event xem danh mục. |
| Catalog & Seller | `VIS-03` | Xem trang shop | Schema chưa có event xem shop. |
| Khách hàng & Đơn hàng | `GST-04` | Yêu cầu trả hàng của khách vãng lai | Cần chốt quy trình trả hàng và phạm vi số lượng. |
| Khách hàng & Đơn hàng | `CUS-08` | Yêu cầu trả hàng | Cần chốt quy trình trả hàng và phạm vi số lượng. |
| Khách hàng & Đơn hàng | `ORD-03` | Hủy một phần dòng hàng | Cần chốt phân bổ tiền/voucher và hoàn tiền khi hủy dòng. |
| Khách hàng & Đơn hàng | `SUP-01` | Chấp thuận yêu cầu trả hàng | Phụ thuộc quy trình trả hàng sẽ chốt ở bước dữ liệu. |
| Khách hàng & Đơn hàng | `SUP-02` | Từ chối yêu cầu trả hàng | Phụ thuộc quy trình trả hàng. |
| Khách hàng & Đơn hàng | `PAY-02` | Trả kết quả hoàn tiền | Cần chốt hoàn tiền một phần, thu hồi và chính sách đủ điều kiện. |
| Khách hàng & Đơn hàng | `SYS-04` | Hoàn tất đơn hàng số | Cần chốt phân loại hàng số trước khi tự hoàn tất. |
| Kho vận | `WH-04` | Nhận lại hàng trả | Cần chốt kiểm tra tình trạng hàng hoàn và tái nhập. |
| Kho vận | `AUT-WH-01` | Giữ hàng theo yêu cầu đặt đơn | Giữ hàng thực thi cùng checkout, không tạo thêm lệnh độc lập. |
| Kho vận | `AUT-WH-02` | Giải phóng hàng đã giữ | Giải phóng hàng thực thi cùng hủy đơn, không tạo lặp. |
| Kho vận | `AUT-WH-03` | Đề xuất bổ sung hàng | Cần chốt chính sách mức tồn/lead time; dùng WH-01 để nhập chủ động. |
| Marketing | `AUT-MKT-01` | Kiểm tra và giữ lượt voucher cho checkout | Chưa chốt cộng dồn/phân bổ voucher; không tự áp vào đơn. |
| Marketing | `AUT-MKT-02` | Hoàn lượt voucher khi đơn hủy | Phụ thuộc ledger lượt voucher. |
| Web analytics | `AUT-WEB-03` | Sinh chuỗi hành vi theo phiên | Chế độ chuỗi phiên cần chốt phân bố và nguồn checkout. |
| Web analytics | `EVT-WEB-01` | Ghi nhận kết quả đặt hàng | Chờ chốt liên kết checkout–session; không tự tạo purchase. |
| Web analytics | `EVT-WEB-02` | Đóng mục giỏ đã đặt | Chờ liên kết checkout–giỏ. |
| Tài chính | `FIN-POL-02` | Thay chính sách cho kỳ tương lai | Cần chốt khép khoảng chính sách và ảnh hưởng hợp đồng đã chốt. |
| Tài chính | `FIN-REC-01` | Lập đối soát seller | Cần chốt giá trị hoa hồng và nghĩa vụ tại giao dịch. |
| Tài chính | `AUT-FIN-01` | Chạy lịch lập kỳ | Phụ thuộc đối soát đã chốt. |
| Tài chính | `AUT-FIN-02` | Tiếp nhận điều chỉnh do hoàn tiền | Chưa chốt cách hoàn tiền ảnh hưởng kỳ đã trả. |
| Tài chính | `AUT-FIN-03` | Xếp lệnh chi đến hạn | Chưa có nghĩa vụ đối soát hợp lệ; không phát lệnh chi giả. |

## Sử dụng và kiểm thử

[Hướng dẫn chạy và dùng](../../scripts/mock_platform/README.md). Crawler và `docs/database.md` của người dùng được giữ nguyên. Dữ liệu UI kiểm thử nằm trong database tách biệt, không tự nạp vào `mock_oltp`.

Trước khi tuyên bố hoàn thành toàn bộ nghiệp vụ: cần chốt phần dữ liệu còn thiếu rồi triển khai các handler bị khóa và mở rộng kiểm thử tương ứng. Hiện bản UI/điều khiển và các luồng thử được nêu trên đã chạy được, toàn bộ nghiệp vụ sàn chưa hoàn tất.

## Kết quả xác minh cuối lượt triển khai

- 10 bài kiểm thử đều đạt với hai SQLite tách biệt.
- Cùng 10 bài kiểm thử đều đạt với hai PostgreSQL database kiểm thử tách biệt (tạo và dọn riêng).
- Ruff kiểm tra lỗi tên/import và `git diff --check` đạt.
- Đã dùng trình duyệt thao tác Preview → Chạy → Theo dõi, hoàn tất 16 hành động/0 từ chối của luồng COD trên môi trường kiểm thử riêng.
- Đã xác minh form tự động ẩn quota, form theo hành động và sidebar 7 trang. Dữ liệu thử không nạp vào `mock_oltp` của môi trường chính.
- Có cảnh báo deprecation từ dependency TestClient/httpx trong test; chưa ảnh hưởng kết quả.

## Đang chờ xác nhận quy tắc dữ liệu

Đã gửi người dùng ba đề xuất về điều kiện trả/hoàn tiền, đối soát theo tháng và cộng dồn/hoàn lượt voucher. Chưa nhận câu trả lời thì không tự bật các handler phụ thuộc các quyết định đó. Hai quyết định về xử lý tự động và SKU/chào bán đã được xác nhận tại Rule 05–06.

Ngày đặc biệt trong UI hiện ghi đè số lần; chưa có override riêng toàn bộ tham số hành động theo ngày. Các form nâng cao và phần dữ liệu còn thiếu được nêu ở trên, chưa tuyên bố hoàn thành toàn bộ thiết kế nghiệp vụ.

## Cập nhật cách trình bày cấu hình

- Trang cấu hình có hai cách xem: **Tổng quan cấu hình** và **Chỉnh sửa bản nháp**.
- Tổng quan phân biệt bản nháp và từng phiên bản đã lưu; hiển thị đủ 6 hệ thống, hành động bật/tắt, tác nhân, số thường/đặc biệt và tham số.
- Tên hành động tiếng Việt là nội dung chính trong cấu hình, preview và tiến độ; mã nội bộ nằm sau phần chi tiết kỹ thuật.
- Bảng tổng quan/preview chuyển thành khối thông tin có nhãn ở màn hẹp để đọc không cần nhớ các mã.
- Kiểm tra JavaScript và bộ kiểm thử trình bày đạt; 10 test backend hiện có đạt. Lượt cập nhật này không chạy job hoặc sửa config/dữ liệu nghiệp vụ của người dùng.
- Chưa xác minh trực quan trong browser do công cụ trình duyệt từ chối truy cập; không có ảnh UI mới được tạo trong lượt này.

## Chỉnh sửa cấu hình đã lưu

Đã thêm **Chỉnh sửa cấu hình này → Lưu thay đổi** trên UI và `PUT /api/versions/{id}`. Cập nhật cùng ID, có kiểm tra xung đột lần lưu và lưu lịch sử trong Control DB. Preview giữ config snapshot/revision; sửa cấu hình làm kế hoạch cũ không còn được tạo job mới. Worker đọc snapshot, kể cả job cũ trước cập nhật và job tạm dừng được tiếp tục.

Kiểm thử bổ sung: sửa cùng ID, preview cũ hết hiệu lực, chống ghi đè đồng thời, queued job và pause/resume giữ cấu hình cũ. 13 test đạt trên SQLite, 1 test khóa hàng chỉ chạy PostgreSQL; 14 test đạt trên PostgreSQL. Bộ kiểm tra JavaScript riêng xác minh buffer chỉnh sửa không ghi đè bản nháp và giữ nội dung khi lưu bị xung đột. Chưa xác minh trực quan do quyền truy cập browser đang bị chặn.

## Nâng cấp Tổng quan và điều khiển nguồn

Đã thêm dashboard đọc OLTP, biểu đồ đơn theo ngày, kích hoạt/dừng crawler riêng, kiểm tra sản phẩm mới ở SQLite và thời điểm đồng bộ gần nhất. Xóa toàn bộ OLTP qua job có xem trước, xác nhận, kiểm tra stale preview, rollback transaction và phục hồi khi Control DB gián đoạn sau business commit. Giữ cấu hình/SQLite; checkpoint và dữ liệu nền được đặt lại. Không có xóa từng ngày. Chi tiết: [hướng dẫn điều khiển](MOCK_OVERVIEW_CONTROLS.md).

## Import cấu hình và bộ lịch 2026

Đã có import JSON theo bước xem trước → lưu cấu hình mới, kiểm tra cấu trúc/kiểu dữ liệu/ngày/tham số và hành động được hỗ trợ. Có xuất cấu hình và tải mẫu lịch biến thiên 2026. Bộ mẫu chỉ dùng handler hiện có; không bổ sung hành vi tự dao động, delay nhiều ngày, attribution, áp voucher, hoàn tiền hoặc tạo đối soát. [Giả định và giới hạn](REALISTIC_CONFIG_CURRENT_ENGINE.md).
