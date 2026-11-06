# Tài liệu chốt thiết kế hệ thống mock

Thư mục này tách riêng rule và các tài liệu đang chốt từ cuộc trao đổi mới ngày 05/11/2026, theo yêu cầu phân biệt với tài liệu trước mốc 10h. Phân loại dựa trên nội dung cuộc trao đổi, không suy từ timestamp của file.

## Chạy lần đầu trên máy mới

Bắt đầu tại [Hướng dẫn từ pull code đến lượt mock đầu tiên](guides/FIRST_MOCK_RUN_GUIDE.md): cài đặt, chuẩn bị nguồn SQLite, ý nghĩa từng trang UI, import cấu hình nhỏ, chạy 2 đơn COD, kiểm tra PostgreSQL và xử lý lỗi.

## Danh sách tài liệu

| Tài liệu | Vai trò / trạng thái |
|---|---|
| [MOCK_SYSTEM_RULES.md](MOCK_SYSTEM_RULES.md) | Các rule đã được xác nhận; nguồn ưu tiên cho những quyết định đã chốt. |
| [TIKI_PRODUCT_FIELD_MAPPING.md](TIKI_PRODUCT_FIELD_MAPPING.md) | Mapping sản phẩm Tiki đã được dùng để trao đổi; các chỗ ghi cần kiểm tra vẫn chưa chốt. |
| [MOCK_CATALOG_SELLER_CONFIG.md](configuration/MOCK_CATALOG_SELLER_CONFIG.md) | Thiết kế màn cấu hình Catalog & Seller; hướng cấu hình đã thống nhất, chi tiết hành động còn có thể chỉnh khi review. |
| [MOCK_CUSTOMER_ORDER_CONFIG.md](configuration/MOCK_CUSTOMER_ORDER_CONFIG.md) | Đề xuất để chốt màn cấu hình Khách hàng & Đơn hàng. Chưa triển khai. |

## Bốn hệ thống bổ sung — đang đề xuất để chốt

| Tài liệu | Nội dung |
|---|---|
| [MOCK_WAREHOUSE_LOGISTICS_CONFIG.md](configuration/MOCK_WAREHOUSE_LOGISTICS_CONFIG.md) | Kho vận: nhập/điều chỉnh/xuất/nhận hoàn, vận đơn, giao hàng, COD, giữ hàng và số dư ngày. |
| [MOCK_MARKETING_CONFIG.md](configuration/MOCK_MARKETING_CONFIG.md) | Marketing: chiến dịch, voucher sàn/shop/freeship, báo cáo quảng cáo và xử lý lượt dùng. |
| [MOCK_WEB_ANALYTICS_CONFIG.md](configuration/MOCK_WEB_ANALYTICS_CONFIG.md) | Analytics: phiên, tìm kiếm, xem sản phẩm, giỏ, checkout và tiếp nhận kết quả mua. |
| [MOCK_FINANCE_CONFIG.md](configuration/MOCK_FINANCE_CONFIG.md) | Tài chính: chính sách hoa hồng, đối soát, duyệt chi, chi trả và điều chỉnh. |

## Kế hoạch kiến trúc và workflow

[MOCK_PLATFORM_ARCHITECTURE_PLAN.md](plans/MOCK_PLATFORM_ARCHITECTURE_PLAN.md) đề xuất 7 trang UI, workflow, API/worker và Control DB tách riêng Business DB. Đang review, chưa triển khai. Người dùng đã xác nhận kết thúc bước thiết kế phần cấu hình để chuyển sang kiến trúc; các giá trị chưa nhập và khoảng trống schema vẫn cần được xử lý ở bước tương ứng.

## Nguyên tắc sử dụng

- Xác nhận mới nhất của người dùng và các rule đã chốt quyết định yêu cầu. Khi phát hiện mâu thuẫn phải ghi rõ và cập nhật tài liệu liên quan, không tự áp luật cũ.
- Các file ngoài thư mục, kể cả schema, ERD, bộ luật sinh dữ liệu và bản kịch bản cũ, chỉ là nguồn tham khảo có thể sai. Các khoảng trống của schema phải được ghi nhận; không tự thêm cột/enum hoặc triển khai nghiệp vụ chưa được chốt.
- Nằm trong thư mục này không đồng nghĩa toàn bộ nội dung đã được duyệt. Phân biệt rõ rule đã chốt, đề xuất và phần còn cần xác nhận.
- Đã chuyển từ thiết kế cấu hình kịch bản sang lên kế hoạch kiến trúc/UI/workflow; đang triển khai theo yêu cầu tiếp theo của người dùng. Chi tiết dữ liệu được chốt tiếp trước khi triển khai các luồng tương ứng.
- Chưa ấn định số lượng mặc định nghiệp vụ. Người dùng cấu hình số lần theo từng hành động, ngày thường và ngày đặc biệt.

## Triển khai

- [Trạng thái thực tế và các giới hạn](reviews/MOCK_IMPLEMENTATION_STATUS.md).
- [Khởi động và hướng dẫn sử dụng](../../scripts/mock_platform/README.md).

- [Tổng quan OLTP, kích hoạt crawler và chạy lại từ đầu](guides/MOCK_OVERVIEW_CONTROLS.md).

- [Nhập JSON và cấu hình vận hành theo khả năng engine hiện tại](guides/REALISTIC_CONFIG_CURRENT_ENGINE.md).

- [Audit trực tiếp OLTP và đối chiếu rule ngày 05/11/2026](reviews/OLTP_DATA_AUDIT_2026-11-05.md).

- [Kế hoạch nâng cấp engine sau lượt thử vận hành 2026](plans/MOCK_ENGINE_UPGRADE_PLAN.md): ưu tiên sửa lỗi, liên kết nghiệp vụ, lịch qua ngày và tiêu chí nghiệm thu.

- [Rà soát đa dạng thực thể và khả năng config hiện tại](reviews/ENTITY_DIVERSITY_CONFIG_REVIEW.md): đối chiếu đủ 27 bảng, trường đã hỗ trợ, trường bị cố định và phương án nâng cấp tối thiểu.

- [Nâng cấp và sử dụng engine v2](guides/ENGINE_V2_UPGRADE_GUIDE.md): schema 33 bảng, migration rõ ràng, UI profile/chính sách, config liên kết mới và giới hạn còn lại.

- [Thư viện cấu hình mẫu đã phân loại](examples/README.md): `scenarios/` cho tab Cấu hình kịch bản; `settings/` để nhập và điền chính sách/hồ sơ ở Thiết lập.

## Bản nâng cấp dùng cấu hình ngày 06/11/2026

[Hướng dẫn engine dùng cấu hình thực thể và kịch bản](guides/CONFIG_DRIVEN_ENGINE_GUIDE.md): cấu hình ai thực hiện, thuộc tính, phạm vi, lịch phiên, lookup và cách nâng cấp giữ dữ liệu cũ. Các báo cáo rà soát trước đó phản ánh trạng thái trước lần nâng cấp này.

[Kết quả triển khai và kiểm chứng](reviews/CONFIG_DRIVEN_UPGRADE_RESULT_2026-11-06.md): những cơ chế đã thêm, dữ liệu hiện có được giữ nguyên và các giới hạn còn lại.

[Rà soát dấu vết mô phỏng trong code và config](reviews/MOCK_REALISM_CODE_CONFIG_REVIEW_2026-11-06.md): lỗi thời gian đã tái hiện, phân bố còn cứng, các điểm chỉ cần sửa config và các cơ chế thực sự cần nâng cấp.

[Bản vận hành bán lẻ Việt Nam 2026](guides/REALISTIC_OPERATIONS_2026.md): code và hai config đã cập nhật sau rà soát, rule thời gian, địa danh, hành trình, ngoại lệ và cách áp dụng.

[Kết quả kiểm chứng bản vận hành mới](reviews/REALISM_UPGRADE_RESULT_2026-11-06.md): 82 bài PostgreSQL, 80 bài SQLite, kiểm tra UI/API và bằng chứng giữ nguyên dữ liệu đang có.
