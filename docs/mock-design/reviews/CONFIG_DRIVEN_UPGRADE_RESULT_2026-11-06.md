# Kết quả nâng cấp engine dùng cấu hình — 06/11/2026

## Mục tiêu và phần đã thực hiện

Code giữ các rule nghiệp vụ và cơ chế chọn/sinh dữ liệu; config mô tả quần thể, thuộc tính, phân bố, phạm vi, lịch và tham số kết quả. Không dùng số sản phẩm Tiki thử nghiệm làm giới hạn thiết kế.

| Phần | Kết quả |
|---|---|
| Hồ sơ thực thể | Phân bố có trọng số, tỷ lệ NULL, khoảng số/ngày; thuộc tính khách và seller có mapping rõ; kênh và phương thức thanh toán từ config. |
| Ai thực hiện | Nhóm customers/sellers/carriers/virtual, vai trò, phạm vi và thuộc tính; giữ danh tính qua hành trình, kiểm tra quyền sở hữu và chọn người có yêu cầu đủ điều kiện ở chế độ xử lý toàn bộ. |
| Kịch bản | Chọn nhóm actor, lọc đối tượng, khung giờ, thời lượng phiên, offset trong phiên và lookup tham số theo context. Không tự tạo đơn khi đầu vào không đủ. |
| Tồn đầu | Quy tắc theo sản phẩm/kho, coverage và phân bố lượng tồn; quy tắc đầu tiên khớp được dùng. UI giải thích khi quy tắc thay thế ô tồn chung. |
| Truy vết | Nhật ký có actor, thời điểm hiệu lực, tham số sau lookup và các ID được chọn; dấu liên kết và metadata nằm trong Control DB. |
| Hiệu năng | Lọc SQL cho luồng chọn liên kết/tồn; cache ID và lookup trong transaction; nạp metadata phiên theo lô thay vì truy vấn từng phiên. Thêm 11 index truy vấn. |
| UI và audit | Tóm tắt actor/lịch/lookup, làm mới checkpoint cùng tổng quan; không ghép lịch sử trước reset với ID hoặc backlog của dữ liệu hiện tại. |

Plan lưu snapshot hồ sơ và chính sách; thay thiết lập sau khi lập plan không thay tài nguyên mặc định của plan đó. Plan preview trước lần nâng cấp cần tạo lại vì fingerprint engine thay đổi.

## Config và cách dùng

Thư viện vẫn đúng **4 file JSON**, gồm một mẫu cơ bản và một bản đầy đủ cho mỗi loại:

- Thiết lập mới nhất: [diverse-ecommerce.json](../examples/settings/diverse-ecommerce.json), có 21 nhóm actor phủ sáu hệ thống.
- Kịch bản mới nhất: [upgraded-linked-2026.json](../examples/scenarios/upgraded-linked-2026.json), có 45 hành động bật, trong đó 19 hành động xử lý tự động.
- [Hướng dẫn nhập và sử dụng](../guides/CONFIG_DRIVEN_ENGINE_GUIDE.md).

Chưa tự áp hai config vào môi trường đang chạy. Import/fill/lưu config không sinh nghiệp vụ và không bổ sung thuộc tính vào các dòng cũ. Hồ sơ seller mới chỉ áp khi đồng bộ thêm seller mới; đồng bộ nguồn vẫn append-only.

## Bằng chứng kiểm tra

- SQLite: **68 passed, 2 skipped** (hai kiểm tra yêu cầu PostgreSQL).
- PostgreSQL: **70 passed**, toàn bộ bộ hồi quy hoàn tất trong 12 phút 37 giây trên môi trường thử hiện tại.
- JavaScript: **6 bộ kiểm tra đạt**; kiểm tra UI trên môi trường SQLite riêng, không lưu thử vào môi trường chính.
- Luồng tích hợp 20 ngày với bản config mới chạy trong DB thử riêng: có hành trình liên kết, trả hàng/hoàn tiền và đối soát. Đây là workload thu nhỏ để kiểm tra rule, không phải benchmark bản config đầy đủ.
- Catalog thử 251 sản phẩm; kiểm tra migration index lặp lại an toàn và tái tạo index thiếu.
- Kiểm tra truy vấn với 100 phiên xác nhận đọc metadata runtime theo lô, dưới 10 truy vấn cho thao tác xem hàng trong fixture.
- Audit trực tiếp môi trường hiện có: **109 kiểm tra, 0 vi phạm** trong phạm vi rule audit đã triển khai. Không suy từ kết quả này rằng hệ thống đã mô phỏng đầy đủ thương mại điện tử thực tế.
- So sánh hash toàn bộ **33 bảng, 14.575 dòng** trước/sau nâng cấp: **không bảng nào thay đổi dữ liệu**. Vẫn 124 đơn và checkpoint 05/01/2026. Chỉ áp 11 index; không chạy sync, bootstrap, mock hay reset vào dữ liệu này.

## Giới hạn còn lại

- Lịch thực thi vẫn theo các giai đoạn hành động của engine, chưa phải hàng đợi sự kiện thời gian thực tùy ý.
- Filter và lookup dùng tập cú pháp được hỗ trợ, không chạy Python/SQL hoặc biểu thức tự do trong JSON. Thuộc tính metadata tự nó không tạo hành vi nếu chưa được tham chiếu trong config.
- Actor ảo tạo danh tính khi dùng; actor nghiệp vụ lấy các ID có trong OLTP. Không tự tạo thêm seller/carrier thật bằng tham số `count` của nhóm.
- Không thêm semantics mới như voucher phần trăm/riêng SKU, giá vốn hoặc SLA chỉ để lấp NULL. Rule nghiệp vụ mới vẫn cần code và kiểm thử.
- Giữ giới hạn bảo vệ 10.000 yêu cầu tường minh/hành động/ngày và 100.000/lượt. Chưa benchmark hàng triệu sản phẩm hoặc cam kết năng lực production.

## Sắp xếp source sau nâng cấp

Đã chuyển 28 module Python và 4 tài nguyên khỏi thư mục gốc package vào các nhóm trách nhiệm. Xem [cấu trúc source và lệnh công cụ hiện hành](../../../scripts/mock_platform/README.md#cấu-trúc-source). Đã cập nhật import nội bộ, test, đường dẫn đọc JSON/static, fingerprint, mount SQL trong Docker Compose và các đường dẫn trong tài liệu. Crawler thật, database và lệnh `scripts/start_mock.sh` giữ nguyên.

Kiểm chứng riêng sau khi sắp xếp: 68 bài SQLite đạt (2 bài yêu cầu PostgreSQL được bỏ qua), 9 bài PostgreSQL liên quan đến migration/index, phục hồi, crawler và API đạt; 6 bộ JavaScript đạt. Import thành công toàn bộ 37 module/package ngoài test, các CLI công cụ chạy được `--help`, Docker Compose hợp lệ. Trang chính, JavaScript/CSS và API Tổng quan trả HTTP 200. Hash của 33 bảng/14.575 dòng vẫn khớp bản trước nâng cấp.

