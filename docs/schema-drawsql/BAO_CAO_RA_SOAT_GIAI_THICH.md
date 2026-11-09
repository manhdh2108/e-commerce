# Rà soát giải thích sơ đồ OLTP và DW

Ngày rà soát: 10/11/2026. Phạm vi: toàn bộ 52 mô tả bảng và 13 mô tả nhóm trong hai HTML, cùng phần hướng dẫn DW. Kết luận trước sửa: **đa số đúng về vai trò và cấu trúc, nhưng chưa hoàn toàn đúng về chi tiết thực thi và chưa nêu đủ giới hạn nguồn**. Đã cập nhật hai builder, nội dung hover và tái sinh hai HTML.

## Căn cứ và giới hạn

Đọc đối chiếu schema snapshot OLTP, `business_schema.json`, phần khai báo bảng trong `storage.py`, các nhánh nghiệp vụ trong `domain.py`, `engine/finance.py`, bootstrap/sync trong `worker.py`, kiểm tra nghiệp vụ trong `validation.py`, Rule 01–08, Master Blueprint, ba DDL core DW, Extract/Transform/Load và SQL mart. Quét cú pháp toàn bộ 37 file Python trong `scripts`, `dw`, `dashboard`, `bench` bằng `ast.parse`, không import hay thực thi nghiệp vụ.

Đây là **rà soát tĩnh**, không chạy mock/ETL, không sửa dữ liệu và không chứng nhận trạng thái database live. Không coi các con số đo trong Blueprint ngày 09/11 là số liệu hiện tại. Không khẳng định đã đọc từng dòng mọi mã giao diện/crawler/benchmark: chúng không quyết định grain, FK hoặc ngữ nghĩa của các mô tả này.

Một giới hạn quan trọng: `scripts/mock_platform/business_schema.json` có **27 bảng**, snapshot dùng vẽ có **33 bảng**. Sáu bảng chỉ có trong snapshot là `checkouts`, `checkout_lines`, `delivery_attempts`, `promotion_usages`, `refunds`, `seller_payout_items`. Các cột snapshot bổ sung ở orders/order_items/returns/order_item_promotions/shipments/page_events cũng chưa có đầy đủ trong schema code. Vì thế mô tả 33 bảng đúng theo cấu trúc snapshot không đồng nghĩa checkout hiện tại tạo và xử lý được cả 33 bảng.

Code mock còn lỗi cú pháp tại `domain.py:2`, `storage.py:302`, `worker.py:400`; có dấu xung đột merge chưa giải quyết. `engine/finance.py` còn tham chiếu các đường dẫn/module không có trong checkout như `.domain`, `.outcomes`. Công thức tài chính trong file đó có thể đọc được để hiểu thiết kế triển khai, nhưng chưa thể xác nhận tích hợp/chạy được từ checkout hiện tại. Không sửa các lỗi engine trong lần rà soát mô tả này.

## Các chỗ đã sửa hoặc bổ sung

| Nội dung | Nhận định | Giải thích đã cập nhật | Bằng chứng |
|---|---|---|---|
| `inventory_levels` | “số lượng có sẵn” dễ nhầm với khả dụng | `on_hand` là tồn vật lý; có thể bán = `on_hand − reserved` | `scripts/mock_platform/operations.py`, `DataOperations.dashboard`; `domain.py`, `checkout` |
| `fact_inventory_snapshot.stockout_flag` | Chưa đúng nếu hiểu chỉ tồn vật lý bằng 0 mới hết hàng | Flag = 1 khi **khả dụng** bằng 0; vẫn có thể còn tồn vật lý nhưng giữ hết | `dw/etl/transform.py`, entity `inventory_daily` |
| Không có dòng snapshot | Khẳng định “không kinh doanh” quá tuyệt đối | Đây là ý nghĩa theo thiết kế sparse; dữ liệu thực tế còn phải loại trừ lỗi hoặc thiếu nạp | `domain.py`, `AUT-WH-04`; `dw/etl/transform.py`; Blueprint §4.1 |
| `fact_ad_spend` | “upsert tháng đang mở” sai với code | Xóa và INSERT lại **các tháng batch chạm tới**, từ bản mới nhất mỗi log ngày của batch hiện tại + các batch SUCCESS; có thể gồm tháng đã kết thúc | `dw/etl/load.py`, `AD_SRC`, `load_ad_spend` |
| “Fact không DELETE” trong Blueprint | Không đúng tuyệt đối với triển khai hiện tại | Guide ghi rõ ngoại lệ `fact_ad_spend`, thao tác trong transaction | `dw/etl/load.py`, `load_ad_spend` |
| `active_days` | Mô tả thiếu định nghĩa | `count(DISTINCT log_date)` có dữ liệu; không phải độ dài khoảng chạy chiến dịch | `dw/etl/load.py`, `load_ad_spend` |
| `dim_product` và giá vốn SCD2 | Danh sách cột load có giá vốn nhưng hash không bao phủ | Đổi riêng tỷ lệ giá vốn chưa chắc sinh phiên bản SCD2; giá vốn vẫn là ước tính | `dw/etl/load.py`, `SCD_DIMS`, `load_scd`; `dw/etl/transform.py`, entity `product` |
| Tên `list_price` ở dimension/fact | Dễ tưởng cùng nguồn | Dimension lấy `products.price`; fact lấy `order_items.list_price` | `dw/etl/transform.py`, entity `product` và `order_item_sales` |
| `dim_customer_profile` | “trước giao dịch” chưa đủ chính xác | Cửa sổ **365 ngày trước ngày hoàn tất**; loại mọi dòng cùng ngày; không loại Returned; hạng lấy tại batch | `dw/etl/load.py`, `PROFILE_SQL` |
| Cây danh mục | Không nên ngụ ý cây có lịch sử SCD2 | Product có phiên bản; tên/cấu trúc cây là **SCD1**, closure dựng lại mỗi batch | `dw/etl/load.py`, `load_category` |
| Bridge voucher | Bridge không tự ngăn double-count | Phải nhân tiền với trọng số khi JOIN; SUM nguyên tiền sau JOIN vẫn lặp | `dw/sql/40_mart/401_mart.sql`, `mv_promotion_month` |
| Weight thực tế = 1 | Là kết quả đo cũ, không phải ràng buộc mô hình | Ghi rõ là nhận định Blueprint tại 09/11; DDL cho nhiều voucher; không xác nhận dữ liệu live | Blueprint §10; `302_dimensions.sql`, `bridge_promotion_group` |
| `seller_net_amount` trong DW và payout | Không được coi là cùng số tiền | DW = net − hoa hồng, chưa trừ hoàn; FinanceWorkflow còn xét trợ giá voucher sàn, lượng trả và điều kiện quyết toán | `dw/etl/transform.py`, `order_item_sales`; `dw/etl/load.py`, `load_order_item`; `engine/finance.py`, `FIN-REC-01` |
| WARN và quarantine | “WARN giữ lại” đúng nhưng thiếu audit | WARN vẫn nạp staging **và cũng ghi audit.quarantine**; ERROR bị loại khỏi staging | `dw/etl/transform.py`, `run_entity` |
| Sáu bảng OLTP ngoài schema code | Ý nghĩa phù hợp tên/cột/FK snapshot, hành vi chưa đủ code để xác nhận | Thêm chú thích nguồn và giới hạn trực tiếp vào mô tả sáu bảng | `oltp_snapshot_schema.sql`; `business_schema.json` |

## Các điểm đúng đã giữ

- Core DW có 19 bảng logic, 200 cột, 26 FK: 3 fact, 14 dimension, 2 bridge; không tính partition con.
- OLTP snapshot có 33 bảng, 282 cột, 56 FK. Đây là snapshot, không phải mô hình 27 bảng trong source hiện tại.
- Ngày hoàn tất là `fact_order_item.date_key`; ngày đặt là `order_date_key`, cùng trỏ `dim_date`.
- Grain và PK ba fact đúng với DDL. Dòng bán hàng lấy đơn Completed với item Fulfilled/Returned. Batch có thể cập nhật lại đơn hoàn tất trước cửa sổ khi payment/return đến muộn, không chỉ nạp đơn vừa hoàn tất trong cửa sổ.
- Product/Seller/Customer tra SCD2 theo ngày hoàn tất; tồn kho tra Product theo `balance_date`. Khoảng hiệu lực `[valid_from, valid_to)`.
- Seller tier SCD3 liên hệ logic bằng `seller_id`, không có FK vật lý sang Seller SCD2. `seller_id` ở Product/Promotion, `root_category_key`, `batch_id` cũng không tự suy diễn thành FK.
- Customer profile có FK trực tiếp từ fact, không có FK từ Customer sang profile.
- Hai FK ancestor/descendant và self-FK category đúng. Closure gồm depth 0 cho chính nó; giới hạn đệ quy code là 10.
- Bridge voucher chỉ lưu trọng số; tiền phân bổ nằm trong truy vấn mart. Khuyến mãi phí giao ở đầu đơn không tự được đưa vào bridge dòng hàng.
- Drill-across tổng hợp riêng từng fact rồi FULL OUTER JOIN: `(month_key, channel_key)` cho quảng cáo; `(month_key, product_id)` cho tồn kho. Không dùng surrogate `product_key` để gộp các phiên bản sản phẩm trong báo cáo này.
- Tồn cuối kỳ không SUM theo thời gian; tỷ số và distinct count phải tính lại ở grain báo cáo.
- Khóa −1/0 chỉ cho dimension được DDL sinh sentinel; không áp dụng mặc định cho Date/Month hoặc bảng tier SCD3.
- Watermark chặn ngày chưa chốt. B3–B5 cùng transaction; SUCCESS commit trước refresh mart; refresh lỗi không hủy batch đã SUCCESS.
- Fulfillment, Fact_Return, Seller_Settlement, Customer_Activity là phạm vi mở rộng, chưa được vẽ như fact đã tồn tại.

## Lưu ý về sáu nhóm OLTP

Sáu nhóm là cách phân vùng sơ đồ theo nghiệp vụ. Không đồng nghĩa mỗi nhóm là database/service độc lập hay chỉ hệ thống đó được ghi các bảng bên trong. Ví dụ `order_item_promotions` đang đặt cạnh đơn hàng nhưng thuộc luồng khuyến mãi; `seller_commission_rates` đặt trong Tài chính nhưng Blueprint §3.1 liệt kê cùng nguồn Catalog. Cách đặt này không thay đổi FK, quyền sở hữu hoặc luồng ETL.

## Kiểm chứng đã thực hiện

- AST parse toàn bộ 37 file Python của bốn thư mục nêu trên; ba file mock lỗi, các file DW/dashboard/bench parse được. Parse được không có nghĩa chạy tích hợp được.
- Tái sinh SQL/metadata trong thư mục tạm, so khớp cấu trúc DW với metadata dùng vẽ; không ghi vào database.
- Builder kiểm tra đủ mô tả cho mọi bảng và đúng số nhóm; tái sinh cả hai HTML.
- Không chạy bộ kiểm thử tích hợp mock vì source có lỗi cú pháp; không dùng kết quả kiểm thử cũ trong Blueprint như bằng chứng chạy mới.
