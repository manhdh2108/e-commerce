# Kết quả sửa engine và cấu hình vận hành — 06/11/2026

Đã thực hiện sau [báo cáo rà soát](MOCK_REALISM_CODE_CONFIG_REVIEW_2026-11-06.md). Các rule và cơ chế nằm trong Python OOP; vocabulary, phân bố, lịch và tình huống vận hành nằm trong JSON. Không xóa dữ liệu cũ hoặc tự áp cấu hình thay người dùng.

## Code đã sửa

| Phần | Kết quả |
|---|---|
| Nhân quả thời gian | Clock theo dữ liệu nguồn, delay=0 vẫn kiểm tra; payment/confirmation không trước order. Kiểm tra độc lập phát hiện khi cố tình làm sai timestamp. |
| Hồ sơ và quần thể | Pattern phone/email, tên seller có config; sampling theo thuộc tính OLTP và availability theo nhóm; tài khoản nền có lịch sử tuổi tài khoản. |
| Hành trình | Từ khóa lấy từ catalog, giữ sở thích phiên, ưu tiên nhóm sản phẩm từng xem; xác suất ưu tiên không bị loãng theo kích thước catalog. Guest giữ người nhận ổn định qua nhiều checkout. |
| Vận hành | Khung giờ theo trọng số, độ trễ sau đầu vào, phase điều khiển thứ tự; cycle đảm bảo xử lý các bundle trước khi kết luận hết đầu vào. |
| Nhà cung cấp | Hoàn tiền/chi trả có xác suất thất bại và lịch thử lại; không xóa nghĩa vụ hoặc ghi thành công giả. Lượt thử ở Control DB. |
| Config và UI | Canonical JSON được dùng trực tiếp bởi UpgradedScenario, export không ghi đè nguồn; import/edit giữ các khóa mới và thời lượng phiên; có tóm tắt lịch và ưu tiên. |
| Hiệu năng | Metadata cần cho kiểm tra thời gian/retry được nạp theo lô; tránh thêm truy vấn runtime cho từng phiên/SKU. |

## Hai config đầy đủ

- [Thiết lập](../examples/settings/diverse-ecommerce.json): 32 họ, 104 tên, 20 bộ địa phương/bốn thành phố, sáu kho, năm carrier, 21 nhóm tác động; phone seller không còn bị giới hạn vào chín số. Khách nền có tuổi tài khoản 7–1.095 ngày. Tên và địa danh bớt các dấu vết DEMO/mô phỏng trong dữ liệu mới.
- [Kịch bản](../examples/scenarios/upgraded-linked-2026.json): 52 hành động bật, 19 xử lý theo đầu vào; lịch 365 ngày có biến thiên riêng cho từng chỉ số; retry/hủy/từ chối; cả năm carrier được phân bổ; policy đủ ba hạng seller; 310 nội dung review được chọn theo nhóm rating.
- Vẫn đúng **bốn file JSON** trong examples, gồm hai mẫu tối thiểu và hai bản đầy đủ mới nhất.

Lịch ngày cụ thể ghi đè count; quota là yêu cầu, không bảo đảm đầu vào đủ để thành công. Tên người/shop và contact được tổng hợp, không phải hồ sơ đã xác minh; email giữ example.com. Thương hiệu/địa danh thật và các giới hạn được giải thích trong [hướng dẫn vận hành](../guides/REALISTIC_OPERATIONS_2026.md).

## Kiểm chứng

- PostgreSQL: **82 passed**, bộ hồi quy đầy đủ trên database thử riêng.
- SQLite: **80 passed, 2 skipped**; hai bài bị bỏ qua yêu cầu PostgreSQL.
- JavaScript: **6 bộ kiểm tra đạt**, có ca sửa lịch theo trọng số vẫn giữ duration/after_seconds/preferences/cycle/phase.
- Sau lần cập nhật dữ liệu config cuối cùng, đã chạy lại fixture tích hợp 20 ngày với chính hai file mới nhất: có orders, promotion usages, hoàn tiền và đối soát; validator không báo lỗi. Fixture giảm quota và tắt remove-cart để không xóa toàn bộ giỏ của catalog chỉ có một SKU; đây là kiểm tra liên kết, không phải benchmark sản lượng thực.
- Các ca mới bao gồm lỗi checkout lúc tối, validator bắt thời gian sai, pattern và lịch có trọng số, roundtrip config, ba tier policy, danh tính guest, ưu tiên sản phẩm đã xem, xác suất độc lập kích thước catalog, refund retry, giờ nhân sự, sampling và lịch sử khách nền.
- API preview cho hai file mới trả HTTP 200, giữ đủ các thuộc tính mới, không tạo/ghi đè job hoặc cấu hình đã lưu. Trang chính, API và static assets được phục vụ tại cổng 8765.
- Audit chỉ đọc DB đang có: **109 kiểm tra, 0 vi phạm** trong phạm vi audit hiện hành. Hash của **33 bảng, 14.575 dòng** khớp trước/sau; vẫn **124 đơn**, checkpoint **05/01/2026**. Đây là bằng chứng bảo toàn dữ liệu cũ, không phải kết quả chạy config mới vào DB đó.
- Container PostgreSQL đã được tạo lại để dùng mount SQL trong resources sau khi sắp xếp source; giữ nguyên volume `scripts_mock-platform-data`.

Đọc trang bằng trình duyệt tích hợp bị chính sách trình duyệt chặn trong phiên này. Không lách quyền qua bề mặt khác; việc kiểm chứng UI dựa trên các test JavaScript và API, chưa có xác nhận trực quan mới trong phiên.

## Phạm vi còn lại

Engine vẫn chạy theo phase/ngày; chưa phải event queue thời gian thực toàn sàn. Các quota traffic và chi quảng cáo chưa là mô hình demand nội sinh; voucher vẫn theo semantics fixed amount, và chưa có phân loại hàng trả không thể bán. Không tự cập nhật chỉ số lịch sử Tiki/giá vốn để lấp NULL. Không có cam kết dữ liệu tổng hợp không thể bị nhận ra bằng mọi phép phân tích.

Muốn áp dụng: nhập/lưu cả thiết lập và kịch bản, preview plan mới. Dữ liệu đã có không được backfill tên/contact/carrier theo JSON mới. Dùng môi trường mới hoặc chủ động xem trước/xác nhận reset nếu cần chạy lại từ đầu; xem hướng dẫn vận hành trước khi làm.
