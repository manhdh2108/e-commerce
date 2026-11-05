# Tài liệu chốt thiết kế hệ thống mock

Thư mục này tách riêng rule và các tài liệu đang chốt từ cuộc trao đổi mới ngày 05/11/2026, theo yêu cầu phân biệt với tài liệu trước mốc 10h. Phân loại dựa trên nội dung cuộc trao đổi, không suy từ timestamp của file.

## Danh sách tài liệu

| Tài liệu | Vai trò / trạng thái |
|---|---|
| [MOCK_SYSTEM_RULES.md](MOCK_SYSTEM_RULES.md) | Các rule đã được xác nhận; nguồn ưu tiên cho những quyết định đã chốt. |
| [TIKI_PRODUCT_FIELD_MAPPING.md](TIKI_PRODUCT_FIELD_MAPPING.md) | Mapping sản phẩm Tiki đã được dùng để trao đổi; các chỗ ghi cần kiểm tra vẫn chưa chốt. |
| [MOCK_CATALOG_SELLER_CONFIG.md](MOCK_CATALOG_SELLER_CONFIG.md) | Thiết kế màn cấu hình Catalog & Seller; hướng cấu hình đã thống nhất, chi tiết hành động còn có thể chỉnh khi review. |
| [MOCK_CUSTOMER_ORDER_CONFIG.md](MOCK_CUSTOMER_ORDER_CONFIG.md) | Đề xuất để chốt màn cấu hình Khách hàng & Đơn hàng. Chưa triển khai. |

## Bốn hệ thống bổ sung — đang đề xuất để chốt

| Tài liệu | Nội dung |
|---|---|
| [MOCK_WAREHOUSE_LOGISTICS_CONFIG.md](MOCK_WAREHOUSE_LOGISTICS_CONFIG.md) | Kho vận: nhập/điều chỉnh/xuất/nhận hoàn, vận đơn, giao hàng, COD, giữ hàng và số dư ngày. |
| [MOCK_MARKETING_CONFIG.md](MOCK_MARKETING_CONFIG.md) | Marketing: chiến dịch, voucher sàn/shop/freeship, báo cáo quảng cáo và xử lý lượt dùng. |
| [MOCK_WEB_ANALYTICS_CONFIG.md](MOCK_WEB_ANALYTICS_CONFIG.md) | Analytics: phiên, tìm kiếm, xem sản phẩm, giỏ, checkout và tiếp nhận kết quả mua. |
| [MOCK_FINANCE_CONFIG.md](MOCK_FINANCE_CONFIG.md) | Tài chính: chính sách hoa hồng, đối soát, duyệt chi, chi trả và điều chỉnh. |

## Kế hoạch kiến trúc và workflow

[MOCK_PLATFORM_ARCHITECTURE_PLAN.md](MOCK_PLATFORM_ARCHITECTURE_PLAN.md) đề xuất 7 trang UI, workflow, API/worker và Control DB tách riêng Business DB. Đang review, chưa triển khai. Người dùng đã xác nhận kết thúc bước thiết kế phần cấu hình để chuyển sang kiến trúc; các giá trị chưa nhập và khoảng trống schema vẫn cần được xử lý ở bước tương ứng.

## Nguyên tắc sử dụng

- Xác nhận mới nhất của người dùng và các rule đã chốt quyết định yêu cầu. Khi phát hiện mâu thuẫn phải ghi rõ và cập nhật tài liệu liên quan, không tự áp luật cũ.
- Các file ngoài thư mục, kể cả schema, ERD, bộ luật sinh dữ liệu và bản kịch bản cũ, chỉ là nguồn tham khảo có thể sai. Các khoảng trống của schema phải được ghi nhận; không tự thêm cột/enum hoặc triển khai nghiệp vụ chưa được chốt.
- Nằm trong thư mục này không đồng nghĩa toàn bộ nội dung đã được duyệt. Phân biệt rõ rule đã chốt, đề xuất và phần còn cần xác nhận.
- Đã chuyển từ thiết kế cấu hình kịch bản sang lên kế hoạch kiến trúc/UI/workflow; đang triển khai theo yêu cầu tiếp theo của người dùng. Chi tiết dữ liệu được chốt tiếp trước khi triển khai các luồng tương ứng.
- Chưa ấn định số lượng mặc định nghiệp vụ. Người dùng cấu hình số lần theo từng hành động, ngày thường và ngày đặc biệt.

## Triển khai

- [Trạng thái thực tế và các giới hạn](MOCK_IMPLEMENTATION_STATUS.md).
- [Khởi động và hướng dẫn sử dụng](../../scripts/mock_platform/README.md).

- [Tổng quan OLTP, kích hoạt crawler và chạy lại từ đầu](MOCK_OVERVIEW_CONTROLS.md).

- [Nhập JSON và cấu hình vận hành theo khả năng engine hiện tại](REALISTIC_CONFIG_CURRENT_ENGINE.md).
