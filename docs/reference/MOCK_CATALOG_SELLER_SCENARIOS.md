# Thiết kế kịch bản mock — Catalog và người bán

> **Cập nhật hướng cấu hình:** Xem [MOCK_CATALOG_SELLER_CONFIG.md](../mock-design/configuration/MOCK_CATALOG_SELLER_CONFIG.md). Đồng bộ được tách ra màn chính; Catalog & Seller còn 4 nhóm nghiệp vụ. Danh sách hành động và form trong tài liệu mới thay thế phần cấu hình/số mặc định ở mục 8 dưới đây. Chi tiết tác động dữ liệu trong tài liệu này tiếp tục là đề xuất để bàn sau.

**Trạng thái: Đề xuất để thảo luận, chưa triển khai.** Quyền và hành vi dưới đây chưa được coi là rule đã chốt. Rule đã chốt về đồng bộ append-only tại [MOCK_SYSTEM_RULES.md](../mock-design/MOCK_SYSTEM_RULES.md) luôn được giữ nguyên.

Cơ sở: [schema OLTP](../data-model/oltp/OLTP_SCHEMA.md), [ERD](../data-model/oltp/OLTP_ERD.md), [mapping Tiki](../mock-design/TIKI_PRODUCT_FIELD_MAPPING.md), mục 5 và 15 của [bộ luật sinh dữ liệu cũ](../data-model/oltp/DATA_GENERATION_RULES.md). Tần suất và giả định của bộ luật cũ là tài liệu tham khảo, chưa tự động áp dụng cho thiết kế mới.

## 1. Phạm vi và cách hiểu thực thể

Nhóm này quản lý ba bảng nghiệp vụ: `categories`, `sellers`, `products`.

Sáu hệ thống là sáu nhóm chức năng, không tương ứng một–một với sáu loại người dùng. Riêng catalog/người bán có nhiều vai trò tác động. Mỗi hành động có một hệ thống xử lý chính; tác động sang kho, đơn hàng, marketing và tài chính được chuyển cho hệ thống tương ứng xử lý.

Mục tiêu thiết kế theo thứ tự: **ai hành động → có quyền gì → điều kiện → thay đổi dữ liệu nào → ảnh hưởng gì → mới lên kế hoạch sinh hành động**.

## 2. Các bên tác động và quyền đề xuất

| Bên tác động | Quyền trong nhóm này | Giới hạn |
|---|---|---|
| Người bán, định danh bằng `sellers.id` | Xem hồ sơ của mình; sửa thông tin shop được phép; sửa thông tin sản phẩm thuộc shop; tạm dừng hoặc mở lại sản phẩm của mình | Không sửa shop khác; không tự sửa `tier`, `status` của seller; không đổi ID, SKU hoặc chủ sở hữu; không tạo tùy ý sản phẩm giả. Thay đổi giá là quyền đề xuất cần chốt riêng. |
| Quản trị viên catalog của sàn | Quản lý cấu trúc và nội dung danh mục; sửa phân loại sai; gỡ sản phẩm vi phạm | Không sửa ID nguồn; không xóa bản ghi đang được tham chiếu. Không mặc định có quyền đổi giá bán của shop. |
| Nhân viên quản lý người bán của sàn | Xét hạng; khóa shop; kiểm tra hồ sơ; phê duyệt thay đổi nhạy cảm nếu cần | Cần lý do và điều kiện; không tự sửa đơn hàng hoặc tiền đối soát từ module catalog. |
| Tiến trình đồng bộ do người dùng yêu cầu | Đọc crawler; thêm danh mục, người bán và sản phẩm chưa tồn tại | Không UPDATE hoặc DELETE bản ghi đã có; không ghi ngược crawler. Đây là tiến trình kỹ thuật, không phải người bán. |
| Tiến trình xét hạng theo lịch, nếu bật | Tính đề xuất hạng từ dữ liệu hoạt động và thực hiện chính sách được cấu hình | Dùng quyền của sàn; thiếu dữ liệu đầu vào thì bỏ qua/báo chưa đủ điều kiện, không bịa kết quả. |
| Khách truy cập | Đọc catalog và thông tin shop được công khai | Không ghi trực tiếp ba bảng này. Lượt xem, giỏ và đơn do hệ thống khác tiếp nhận. |

Schema chưa có `users`, bảng vai trò, yêu cầu duyệt hoặc nhật ký thao tác. Khi mock có thể biểu diễn vai trò trong dữ liệu điều khiển, ví dụ `actor_type`, `actor_id`, mà chưa cần xây hệ thống đăng nhập. Đây là quyền mô phỏng, chưa phải phân quyền đã tồn tại trong database.

## 3. Dữ liệu nền và quyền thay đổi theo từng trường

### 3.1. `products`

| Nhóm cột | Nguồn ban đầu | Hành động được đề xuất sau khi nhập |
|---|---|---|
| `id`, `sku`, `seller_id`, `seller_product_id` | Tiki theo mapping; kiểm tra thiếu/trùng | Cố định trong phạm vi hiện tại; không đổi chủ sở hữu hoặc định danh. |
| `name`, `brand_name`, `short_description`, `thumbnail_url` | Tiki, cho phép thiếu ở trường tùy chọn | Người bán sửa trong phạm vi sản phẩm của mình; nếu thiếu bằng chứng thương hiệu thì chưa tự phát sinh sự kiện đổi thương hiệu. |
| `url_key`, `url_path` | Tiki | Giữ để đối chiếu nguồn. Đổi tên trong mock không tự đổi đường dẫn Tiki. |
| `price`, `original_price`, `discount`, `discount_rate` | Giá thật ở lần nhập đầu | Chưa tự phát sinh đổi giá. Nếu chốt cho phép seller đổi giá mô phỏng, cập nhật nhóm giá nhất quán và ghi rõ là giá mô phỏng. |
| `category_id`, `category_name` | Danh mục lá đã chuẩn hóa | Seller đề nghị hoặc quản trị viên sửa; cập nhật ID và tên đồng bộ. |
| `is_active` | Trạng thái bán mô phỏng lúc mở bán | Seller được tạm dừng/mở lại nếu shop Active; sàn có thể gỡ. Không suy từ `is_visible` của Tiki. |
| `cost_price` | Giá vốn mô phỏng | Chỉ sinh khi có quy tắc sở hữu/định giá được chốt. Thay đổi giá vốn phải là hành động riêng, không tự đổi theo giá bán. |
| `quantity_sold`, `rating_average`, `review_count`, `inventory_status`, `stock_item`, `type` | Giá trị nguồn quan sát | Giữ làm tín hiệu nguồn; không cộng đơn mock vào số bán Tiki hoặc suy số tồn từ các trường này. |
| `crawl_date` | Ngày quan sát nguồn dùng cho lần nhập đầu | Đồng bộ lại không ghi đè. Không phải ngày lên sàn mô phỏng. |
| `created_at`, `updated_at` | Đồng hồ mô phỏng | Tạo mới: bằng thời điểm đăng bán thực sự; cập nhật: dùng thời điểm hành động thay đổi dữ liệu. |

Đối với giá: append-only cấm đồng bộ ghi đè giá. Nó chưa quyết định có cho seller đổi giá trong mô phỏng hay không. Đề xuất giai đoạn đầu giữ giá nhập, tắt kịch bản đổi giá cho đến khi chốt rõ.

### 3.2. `sellers`

| Cột | Nguồn / quyền đề xuất |
|---|---|
| `id` | Mã seller từ catalog Tiki; không tự sinh seller ID giả. |
| `seller_name`, `shop_name`, `province`, `city`, `email`, `phone` | Hồ sơ mô phỏng; seller sửa thông tin thông thường của mình. Tên pháp lý hoặc thay đổi nhạy cảm có thể cần sàn duyệt, chưa chốt luồng duyệt. Email thử nghiệm dùng `example.com`. |
| `tier` | Sàn quản lý: `Normal`, `Preferred`, `Mall`. Không suy việc có nhiều sản phẩm đồng nghĩa được Tiki công nhận Mall. |
| `status` | Sàn quản lý: `Active`, `Suspended`. Seller không tự mở khóa. |
| `created_at`, `updated_at` | Thời điểm tạo và thay đổi trong mô phỏng; không giả định là lịch sử thật của Tiki. |

### 3.3. `categories`

| Cột | Nguồn / quyền đề xuất |
|---|---|
| `id` | Ưu tiên ID Tiki đã xác minh; giai đoạn đầu không tạo nút tổng hợp tùy ý. |
| `category_name`, `slug` | Nguồn đã xác minh hoặc giá trị dẫn xuất có ghi nhận. Quản trị viên quản lý. |
| `parent_id`, `level` | Dựng từ cây đã xác minh; quản trị viên quản lý. Không chu trình; gốc có cha null và level 1. |

Bảng `categories` không có `created_at`, `updated_at`, trạng thái đóng hoặc lịch sử chỉnh sửa. Không tự tham chiếu các cột chưa tồn tại. Nhật ký hành động phải nằm ngoài bảng này nếu cần kiểm chứng thời điểm thay đổi.

## 4. Kịch bản và quan hệ dữ liệu

### C01 — Đồng bộ một sản phẩm mới từ crawler

- **Tác nhân:** tiến trình đồng bộ, được người dùng chủ động gọi.
- **Điều kiện:** sản phẩm chưa có theo khóa đã chốt; ID, SKU, giá và liên kết hợp lệ. Trường hợp nhiều chào bán chung ID hoặc SKU xung đột phải báo lỗi/chờ xử lý, không âm thầm đổi mã.
- **Thứ tự:** kiểm tra dữ liệu → thêm cây danh mục còn thiếu từ cha xuống con → thêm seller còn thiếu → thêm sản phẩm.
- **Dữ liệu:** `products.seller_id = sellers.id`; `products.category_id = categories.id` của danh mục lá; `category_name` đúng tên lá đó.
- **Nguyên tử:** thực hiện trong transaction phù hợp; sản phẩm lỗi không để lại hồ sơ seller/danh mục phát sinh dở dang chỉ phục vụ sản phẩm lỗi. Không bỏ qua lỗi nếu seller/danh mục đã có nhưng không tương thích.
- **Giữ nguyên:** mọi thực thể đã tồn tại, kể cả giá hoặc tên khác nguồn mới.
- **Ảnh hưởng ngoài:** catalog mới trở thành đầu vào để các hệ thống khác cân nhắc sử dụng. Không tự sinh tồn kho, đơn hàng hoặc quảng cáo chỉ vì đồng bộ xong.
- **Giới hạn:** nếu seller đã tồn tại và đang Suspended, không được tự mở shop; sản phẩm mới phải không bán được, hoặc bị hoãn nhập theo chính sách sẽ chốt.

### C02 — Người bán đưa sản phẩm đã chuẩn bị lên bán

- **Tác nhân:** người bán; sản phẩm phải lấy từ tập dữ liệu thật đã đồng bộ/chọn làm đầu vào.
- **Điều kiện:** shop Active, danh mục hợp lệ, giá hợp lệ, trạng thái sản phẩm cho phép.
- **Dữ liệu:** nếu sản phẩm chưa đăng trong OLTP thì INSERT tại thời điểm đăng; nếu đã đăng nhưng tạm dừng thì đây là hành động mở lại `is_active` và `updated_at`.
- **Ràng buộc mô hình:** schema không có Draft/PendingApproval. Giai đoạn đầu không giả vờ có trạng thái nháp; không INSERT bản ghi mang `created_at` trong tương lai. Nếu muốn giữ hàng đợi chưa đăng, dùng metadata điều khiển riêng.
- **Ảnh hưởng ngoài:** có thể xuất hiện trong catalog; đủ điều kiện nhận đơn chỉ khi các kiểm tra của hệ thống đơn hàng/kho cũng đạt. `is_active = true` không đồng nghĩa có tồn kho.

### C03 — Người bán sửa tên/mô tả/ảnh sản phẩm

- **Điều kiện:** đúng `seller_id`, shop được phép thao tác, sản phẩm tồn tại; tên mới không rỗng.
- **Dữ liệu:** UPDATE đúng trường được yêu cầu và `products.updated_at`; ID, SKU, seller, giá và URL nguồn giữ nguyên.
- **Phụ thuộc:** hành động phải chứa giá trị mới hợp lệ; không sửa ngẫu nhiên trường không liên quan.
- **Ảnh hưởng ngoài:** lượt xem sau đó đọc nội dung mới. `order_items` hiện không có cột snapshot tên sản phẩm; không khẳng định đơn cũ giữ tên cũ bằng schema hiện tại.

### C04 — Người bán tạm dừng / mở lại sản phẩm

- **Điều kiện:** sản phẩm thuộc shop. Mở lại chỉ khi seller Active và sản phẩm không còn bị sàn cấm.
- **Dữ liệu:** UPDATE `products.is_active`, `updated_at`; không DELETE.
- **Ảnh hưởng ngoài:** dừng nhận đơn mới khi ngừng bán. Không tự xóa giỏ; checkout phải kiểm tra lại. Đơn đã tạo được xử lý theo quy tắc đơn hàng, không tự mất hiệu lực.
- **Giới hạn:** một boolean không phân biệt seller tạm dừng, sàn gỡ và khóa shop. Muốn mở lại an toàn cần metadata lý do/trạng thái trước đó. Chưa có metadata thì không bật kịch bản tự động mở lại.

### C05 — Người bán đề nghị đổi phân loại, sàn chấp thuận

- **Điều kiện:** sản phẩm thuộc shop, danh mục đích tồn tại và là lá; không chọn ngẫu nhiên một ngành hàng vô lý.
- **Dữ liệu:** UPDATE đồng thời `products.category_id`, `category_name`, `updated_at`.
- **Ảnh hưởng ngoài:** đơn phát sinh sau thay đổi dùng phân loại hiện tại để tìm chính sách liên quan. Không hồi tố phí đã chốt của đơn cũ.
- **Giới hạn:** nếu chuyển làm thay đổi loại hàng vật lý/số/dịch vụ hoặc mô hình kho, phải có luồng phối hợp riêng. Giai đoạn đầu chỉ chuyển giữa các lá tương thích trong cùng ngành. Schema không có yêu cầu duyệt; ý định và kết quả duyệt nếu mô phỏng sẽ ghi ở nhật ký điều khiển.

### C06 — Người bán cập nhật hồ sơ shop

- **Điều kiện:** chỉ hồ sơ của mình; thông tin hợp lệ; tỉnh và thành phố tương thích.
- **Dữ liệu:** UPDATE các trường được chọn trong `sellers` và `updated_at`. Không đổi `id`, `tier`, `status`.
- **Ví dụ:** đổi `shop_name`; hoặc chuyển địa điểm thì cập nhật cả `province`, `city`.
- **Ảnh hưởng ngoài:** catalog hiển thị thông tin mới; không đổi địa chỉ kho trong `warehouses` hoặc địa chỉ giao hàng của khách, vì đây là các thực thể độc lập.

### C07 — Sàn xét thay đổi hạng người bán

- **Tác nhân:** nhân viên quản lý seller hoặc tiến trình định kỳ của sàn.
- **Điều kiện:** có chính sách được chốt và dữ liệu quan sát đủ. Nếu dùng số đơn, tỷ lệ hủy, đánh giá thì phải tính từ các bảng mô phỏng tại thời điểm xét; không lấy lượng bán Tiki thay cho hiệu quả shop trong mock.
- **Dữ liệu:** UPDATE `sellers.tier`, `updated_at` khi thực sự đổi hạng.
- **Ảnh hưởng ngoài:** tài chính có thể chọn chính sách hoa hồng theo hạng mới cho giao dịch sau đó; không tự tạo/sửa `seller_commission_rates` hoặc hồi tố đối soát.
- **Giới hạn:** khi chưa mock đơn hàng/đánh giá, có thể đặt hạng khởi tạo hoặc phát lệnh đổi hạng thủ công để thử cơ chế; không tuyên bố đã mô phỏng xét hạng theo hiệu suất.

### C08 — Sàn khóa người bán vi phạm

- **Điều kiện:** shop đang Active; có lý do/lệnh khóa mô phỏng rõ ràng.
- **Dữ liệu trong catalog:** cùng transaction đổi `sellers.status = 'Suspended'`, cập nhật thời gian và đặt các sản phẩm đang bán của shop thành `is_active = false`.
- **Ảnh hưởng ngoài:** gửi sự kiện để hệ thống đơn hàng xử lý đơn chưa hoàn tất theo chính sách; kho giải phóng hàng chỉ khi có yêu cầu hợp lệ từ luồng đơn; marketing ngừng cho sử dụng ưu đãi của shop theo chính sách riêng; tài chính vẫn phải xử lý nghĩa vụ đang tồn tại.
- **Không được làm:** xóa seller/sản phẩm, tự xóa đơn, tự xóa tồn kho hoặc tiền phải trả.
- **Giới hạn:** giai đoạn đầu không tự mở lại shop vì cần phân biệt các lý do sản phẩm ngừng bán và xử lý trạng thái tồn đọng.

### C09 — Quản trị viên đổi tên danh mục

- **Điều kiện:** danh mục tồn tại, tên mới hợp lệ.
- **Dữ liệu:** UPDATE `categories.category_name`; đồng thời cập nhật `products.category_name` của các sản phẩm trực tiếp tham chiếu danh mục đó nếu đây là cột tên lá đồng bộ. Sửa slug theo chính sách riêng, không mặc định bắt buộc đổi.
- **Phụ thuộc:** cập nhật tên danh mục và các tên sao chép trong một transaction để tránh lệch dữ liệu; sản phẩm bị đổi tên danh mục cũng cập nhật `updated_at`.
- **Giới hạn:** chưa bật di chuyển cả nhánh hoặc xóa danh mục. Những hành động đó cần kiểm tra cây và sản phẩm đang liên kết; schema cũng thiếu thời gian sửa danh mục.

### C10 — Người bán thay đổi giá bán thường ngày — chờ chốt

- **Điều kiện nếu được bật:** đúng shop, sản phẩm hợp lệ; giá mới > 0; xác định rõ giá gốc và giá bán.
- **Dữ liệu:** cập nhật nhóm giá nhất quán và `updated_at`. Đề xuất `discount = original_price - price`, tỷ lệ giảm theo đơn vị thống nhất; không vừa giữ discount cũ vừa đổi giá mới.
- **Ảnh hưởng ngoài:** đơn được tạo trước giữ `order_items.list_price`, `unit_price` đã chốt; đơn sau dùng giá mới. Không sửa `payments` hoặc giá dòng đơn cũ.
- **Phân biệt:** flash sale/voucher do marketing quản lý, không tự ghi đè catalog. Việc đồng bộ crawler vẫn tuyệt đối append-only.
- **Giai đoạn đầu:** tắt, để sản phẩm giữ giá thật được nhập. Nếu bật sau này, phải ghi rõ giá đã được mô phỏng thay đổi, không gọi là giá Tiki mới nhất.

### C11 — Thao tác sai hoặc không có quyền

Ví dụ seller A sửa sản phẩm của seller B; seller tự nâng Mall; mở sản phẩm khi shop Suspended; gán danh mục không tồn tại; nhập giá âm; đồng bộ trùng.

Kết quả: từ chối và ghi lý do trong nhật ký điều khiển; không thay đổi các bảng nghiệp vụ. Đồng bộ trùng là kết quả bỏ qua bình thường, không nhất thiết là lỗi. Thao tác đặt lại đúng giá trị hiện tại là không đổi dữ liệu; không tăng `updated_at` nếu không có thay đổi thực sự.

## 5. Các phụ thuộc phải bảo đảm

1. Danh mục cha tồn tại trước con; không chu trình; level đúng; sản phẩm chọn danh mục lá hợp lệ.
2. Seller tồn tại trước sản phẩm; thời gian tạo sản phẩm không trước seller. Nếu giữ luật cũ cách ít nhất một ngày, phải lên lịch nhập phù hợp thay vì bịa timestamp tương lai.
3. Không tạo seller không có nguồn ID thật; hồ sơ giả phải được nhận diện là giả trong tài liệu/metadata.
4. Mọi hành động seller phải đối chiếu `products.seller_id` với người thực hiện.
5. Seller Suspended không có sản phẩm được phép nhận đơn mới. Kiểm tra cả trạng thái shop và sản phẩm ở checkout, không chỉ tin cache catalog.
6. `quantity_sold`, điểm và số review Tiki không đổi do đơn hoặc đánh giá mock.
7. Thay đổi chủ dữ liệu không được sửa ngược chứng từ tiền, tồn kho hoặc giao dịch đã phát sinh.
8. Đồng bộ lặp lại không hoàn tác các thay đổi nghiệp vụ trong mock và không làm sản phẩm bị khóa tự hoạt động lại.
9. Khi đồng bộ gặp danh mục/seller có sẵn nhưng thiếu hoặc khác thuộc tính, báo khác biệt; không sửa bản ghi đó để hoàn thiện liên kết.
10. Khóa sản phẩm/SKU và trường hợp nhiều chào bán phải được xác minh trước khi code đồng bộ; không tự cấp SKU thay thế rồi gọi là mã thật.

## 6. Cách chuyển các hành động thành kế hoạch mock

### Bước 1 — Chuẩn bị catalog đầu vào

Người dùng yêu cầu đồng bộ. Kiểm tra nguồn, mapping, khóa, giá và cây danh mục; hiển thị số thêm/bỏ qua/lỗi. Chỉ nhập dữ liệu mới theo Rule 01. Đặt rõ thời điểm nhập trong dòng thời gian mô phỏng; không nhận đơn có thời điểm trước khi sản phẩm/seller tồn tại.

Nhập catalog không đồng nghĩa kích hoạt tất cả luồng. Tồn đầu kho, chiến dịch và phiên khách sẽ do kế hoạch của từng hệ thống quyết định.

### Bước 2 — Tạo danh sách hành động theo tác nhân

Mỗi hành động điều khiển có tối thiểu:

| Thuộc tính | Mục đích |
|---|---|
| `action_id` | Khóa chống thực hiện lặp. |
| `action_type` | Ví dụ `SELLER_UPDATE_PROFILE`, `PRODUCT_PAUSE`, `SELLER_SUSPEND`. |
| `actor_type`, `actor_id` | Ai thực hiện; seller ID phải là mã đã có. |
| `target_type`, `target_id` | Seller, product hoặc category bị tác động. |
| `scheduled_at` | Thời điểm thực hiện theo đồng hồ mô phỏng. |
| `payload` | Giá trị muốn đổi; không chỉ có tên sự kiện chung chung. |
| `reason`, `depends_on` | Lý do và hành động phải hoàn tất trước nếu có. |
| `status`, `result` | Chờ, hoàn tất, từ chối hoặc lỗi; ghi lý do và giá trị trước/sau. |

Đây là đề xuất metadata điều khiển, không phải các cột đã tồn tại trong ba bảng OLTP.

### Bước 3 — Cho người dùng kiểm soát mức sinh hành động

| Nhóm cấu hình | Tham số cần có |
|---|---|
| Phạm vi | Ngày chạy, seed, tập shop/sản phẩm/danh mục đủ điều kiện. |
| Sản lượng | Số hành động từng loại mỗi ngày hoặc tỷ lệ trên tập đủ điều kiện; nếu có số tuyệt đối thì dùng số đó, không nhân thêm tỷ lệ. |
| Thời gian | Khung giờ seller thao tác, giờ quản trị, lịch xét hạng. |
| Lựa chọn đối tượng | Phân bố theo shop/ngành; giới hạn số lần tác động lên cùng đối tượng. |
| Nội dung thay đổi | Danh sách/miền giá trị hợp lệ; tỉnh–thành tương thích; tên shop hợp lệ. |
| Bật/tắt kịch bản | Bật riêng C03–C11; các kịch bản phụ thuộc hệ thống chưa có thì chưa tự chạy. |
| Giới hạn | Số hành động không vượt tập đủ điều kiện; thiếu đối tượng thì báo số thực hiện thiếu, không lặp hoặc vi phạm quyền để đủ quota. |

Không chốt trước tỷ lệ đổi tên/khóa shop/đổi giá từ bộ luật cũ. Ưu tiên gói thử nhỏ, chọn đích rõ ràng để kiểm tra đúng hành vi trước khi sinh số lượng lớn.

### Bước 4 — Xử lý và chuyển tác động sang hệ thống khác

Đọc trạng thái tại thời điểm hành động → kiểm tra quyền/điều kiện → cập nhật nguyên tử dữ liệu catalog → ghi kết quả và sự kiện liên quan → hệ thống nhận xử lý theo thời gian của nó.

Nhật ký và sự kiện cần được lưu bền cùng thay đổi để có thể tiếp tục sau lỗi mà không phát lại tác động hai lần. Cơ chế lưu cụ thể sẽ thiết kế khi triển khai; chưa yêu cầu dùng message broker. Khi hệ thống nhận chưa tồn tại, chỉ ghi sự kiện chờ, không khẳng định kho/đơn hàng đã được xử lý.

### Bước 5 — Kiểm chứng bằng ví dụ xác định

| Trường hợp | Kết quả cần quan sát |
|---|---|
| Đồng bộ A lần đầu rồi đồng bộ A đã đổi giá | A chỉ có một dòng, giá trong mock không đổi. |
| Seller A sửa sản phẩm của B | Bị từ chối; không cột nào thay đổi. |
| Seller sửa tên sản phẩm của mình | Chỉ tên và thời gian sửa đổi; URL nguồn, giá, SKU giữ nguyên. |
| Sàn khóa shop có ba sản phẩm, một sản phẩm đã tạm dừng | Shop Suspended; cả ba không bán được; không tự mở lại sản phẩm cũ. |
| Seller sửa tỉnh thành | Hồ sơ shop thay đổi; kho và địa chỉ khách không đổi. |
| Đổi danh mục sản phẩm | ID/tên danh mục đồng bộ; bản ghi danh mục đích đã tồn tại. |
| Đổi tên danh mục | Tên trong danh mục và sản phẩm liên quan nhất quán. |
| Chạy lại cùng action ID | Không tạo thêm tác động nghiệp vụ hoặc sự kiện trùng. |
| Không đủ dữ liệu xét hạng | Báo chưa đủ điều kiện; không chọn tier ngẫu nhiên rồi gọi là xét theo hiệu suất. |

## 7. Thứ tự triển khai đề xuất

1. Chốt quyền, khóa và trạng thái khởi tạo; hoàn thiện đồng bộ append-only.
2. Làm nhật ký hành động, kiểm tra quyền và cập nhật hồ sơ/shop/nội dung sản phẩm: C03, C06, C11.
3. Làm tạm dừng và khóa shop: C04, C08; ghi sự kiện chờ cho các hệ thống liên quan.
4. Làm sửa phân loại và tên danh mục: C05, C09.
5. Nối dữ liệu hệ thống khác rồi mới bật xét hạng theo hiệu suất: C07.
6. Chỉ bật đổi giá, mở lại sau khóa, giá vốn và thay đổi cây danh mục khi có rule riêng được chốt.

Không code hệ thống mới trong bước tài liệu này. Những lựa chọn cần chốt tiếp gồm quyền thay đổi giá, trạng thái khi nhập sản phẩm của shop đang khóa, cách lưu lý do ngừng bán và chiến lược khóa với nhiều chào bán cùng sản phẩm.

## 8. Giới hạn hành động và số lần thực hiện của 5 nhóm

Mục này cụ thể hóa danh sách hành động của giai đoạn đầu. Không phát sinh thêm loại hành động ngoài danh sách. Tiến trình xét hạng thuộc quyền của nhóm quản lý người bán, không tính thành nhóm thứ sáu.

**Trạng thái con số:** các số dưới đây là hồ sơ thử nghiệm đề xuất `catalog_small_v1`, chưa phải số liệu thực tế của Tiki hoặc cấu hình đã được người dùng phê duyệt. Người dùng có thể đặt số tuyệt đối theo ngày cho từng mã hành động, kể cả 0 để tắt. Không áp tỷ lệ ngẫu nhiên hoặc hệ số sale lên các số này nếu chưa được yêu cầu.

### 8.1. Nhóm 1 — Người bán

| Mã | Hành động cụ thể | Dữ liệu được phép đổi | Số yêu cầu mặc định / ngày mô phỏng | Cách thực hiện / điều kiện |
|---|---|---|---:|---|
| SEL-01 | Đổi tên shop | `sellers.shop_name`, `updated_at` | 1 | Tự động sinh tên mô phỏng; đúng seller, shop Active. |
| SEL-02 | Đổi thông tin liên hệ | `sellers.email`, `phone`, `updated_at` | 0 | Có thể tự động; email thử nghiệm và số điện thoại giả, không gửi thông báo thật. |
| SEL-03 | Đổi địa điểm kinh doanh | `sellers.province`, `city`, `updated_at` | 0 | Có thể tự động với cặp địa phương hợp lệ; không đổi vị trí kho. |
| SEL-04 | Sửa tên sản phẩm | `products.name`, `updated_at` | 1 | Tự động biến đổi có kiểm soát từ tên gốc, giữ nhận diện mặt hàng; giữ URL Tiki. |
| SEL-05 | Sửa mô tả ngắn | `products.short_description`, `updated_at` | 1 | Tự động từ mẫu mô phỏng và thuộc tính đã có; không bịa chứng nhận hoặc thông số kỹ thuật. |
| SEL-06 | Tạm dừng bán sản phẩm | `products.is_active = false`, `updated_at` | 1 | Chọn sản phẩm đang bán thuộc seller Active; ghi lý do `SELLER_PAUSE`. |
| SEL-07 | Mở lại sản phẩm do chính shop tạm dừng | `products.is_active = true`, `updated_at` | 0 | Có thể tự động sau khi có metadata lý do; shop Active, không còn lệnh gỡ của sàn. Chỉ mở sản phẩm đã tạm dừng trước ngày đang chạy trong hồ sơ mặc định. |
| SEL-08 | Đề nghị chuyển danh mục sản phẩm | Chỉ tạo yêu cầu trong metadata điều khiển | 0 | Có thể tự động khi có tập danh mục đích tương thích; chỉ CAT-01 mới thực sự đổi bảng sản phẩm. |

Mặc định không mô phỏng đổi giá, giá vốn, thương hiệu, ảnh, tên pháp lý, mã SKU hoặc chủ sở hữu. Những hành động này không nằm trong danh sách tự chạy của giai đoạn đầu. Đổi ảnh có thể tự động nếu có tập ảnh nguồn hợp lệ, nhưng hiện không cần đưa vào phạm vi.

### 8.2. Nhóm 2 — Quản trị viên catalog

| Mã | Hành động cụ thể | Dữ liệu được phép đổi | Số yêu cầu mặc định / ngày mô phỏng | Cách thực hiện / điều kiện |
|---|---|---|---:|---|
| CAT-01 | Chấp thuận một yêu cầu chuyển danh mục | `products.category_id`, `category_name`, `updated_at`; trạng thái yêu cầu | 0 | Có thể tự động từ hàng đợi SEL-08; danh mục đích tồn tại, là lá và tương thích. Không có yêu cầu hợp lệ thì không tự tạo thêm để đủ quota. |
| CAT-02 | Từ chối một yêu cầu chuyển danh mục | Chỉ trạng thái/lý do trong metadata | 0 | Có thể tự động theo điều kiện kiểm tra hoặc kết quả từ chối được cấu hình; không đổi `products`. |
| CAT-03 | Gỡ một sản phẩm vi phạm mô phỏng | `products.is_active = false`, `updated_at`; lý do gỡ trong metadata | 0 | Có thể tự động theo danh sách đích hoặc sự kiện vi phạm giả đã cấu hình; không khẳng định sản phẩm Tiki thật vi phạm. |
| CAT-04 | Đổi tên một danh mục | `categories.category_name`, tùy chọn `slug`; tên danh mục và thời gian sửa của sản phẩm liên quan | 0 | Chỉ chạy khi người dùng cung cấp ID và tên đích. Có thể thực thi tự động lệnh đã cấu hình; không tự bịa phân loại ngành hàng. |

Không cho người bán tạo danh mục. Giai đoạn đầu không mô phỏng xóa danh mục, chuyển cả nhánh, tạo nút tổng hợp hoặc mở lại sản phẩm bị sàn gỡ. Danh mục mới từ dữ liệu thật đi qua tiến trình đồng bộ, không tính là CAT-04.

### 8.3. Nhóm 3 — Nhân viên quản lý người bán

| Mã | Hành động cụ thể | Dữ liệu được phép đổi | Số yêu cầu mặc định / ngày mô phỏng | Cách thực hiện / điều kiện |
|---|---|---|---:|---|
| MGR-01 | Xét hạng một seller | `sellers.tier`, `updated_at` nếu kết quả khác hiện tại | 0 | Tự động khi đã có chính sách và dữ liệu đơn/đánh giá đủ. Khi chưa có, cần người dùng chỉ định tier đích để kiểm thử; phải gắn nhãn thao tác chỉ định. |
| MGR-02 | Khóa một seller | `sellers.status`, `updated_at`; trạng thái và thời gian sửa của sản phẩm liên quan | 0 | Có thể tự động từ số lượng được đặt hoặc danh sách đích; cần lý do vi phạm giả, seller đang Active. Tác động tới nhiều sản phẩm vẫn tính là một lệnh khóa. |

Không mở lại shop trong giai đoạn đầu. Không tự đặt ngưỡng xét hạng hoặc dùng số lượng sản phẩm Tiki để khẳng định tư cách Mall. Hồ sơ seller được sinh khi nhập mã seller mới, không tính là hành động seller tự đổi hồ sơ hoặc tự nâng hạng.

### 8.4. Nhóm 4 — Tiến trình đồng bộ

| Mã | Hành động cụ thể | Dữ liệu sinh ra | Số mặc định | Người dùng cần làm gì? |
|---|---|---|---|---|
| SYN-01 | Chạy một lượt đồng bộ append-only | Thêm `categories`, `sellers`, `products` chưa có; nhật ký đồng bộ | 0 lượt tự động / ngày | Chủ động bấm/gọi đồng bộ. Một yêu cầu tạo một lượt; hệ thống tự xử lý dữ liệu, không cần nhập từng dòng. |

Một lượt đồng bộ có thể thêm 0, 1 hoặc nhiều sản phẩm. Số lượt chạy khác với số dòng thêm. Đề xuất cho phép giới hạn `max_new_products` mỗi lượt: mặc định lấy toàn bộ bản ghi mới hợp lệ, hoặc người dùng nhập giới hạn. Khi giới hạn, chọn theo ID đã sắp xếp để tái lập; các bản ghi ngoài giới hạn được ghi là hoãn xử lý, không phải đã đồng bộ.

Thống kê riêng số sản phẩm mới, danh mục mới, seller mới, bản ghi đã có, bản ghi hoãn và lỗi. Không tạo sản phẩm giả cho đủ quota khi nguồn không còn sản phẩm mới. Lượt đã chạy xong không tự chạy lại khi tiếp tục ngày mô phỏng.

### 8.5. Nhóm 5 — Khách truy cập

| Mã | Hành động cụ thể | Tác động trực tiếp lên catalog | Số yêu cầu mặc định / ngày mô phỏng | Dữ liệu ở hệ thống khác |
|---|---|---|---:|---|
| VIS-01 | Xem trang chi tiết sản phẩm | Đọc sản phẩm đang được công khai, không UPDATE | 100 | Khi module analytics có: `sessions` và `page_events` loại `view_product`. Không phải 100 khách hoặc 100 phiên. |
| VIS-02 | Xem danh sách danh mục | Đọc cây và danh sách sản phẩm, không UPDATE | 0 | Schema chưa có event chuyên biệt cho xem trang danh mục; hiện chỉ ghi metadata hành động. |
| VIS-03 | Xem trang shop | Đọc shop và sản phẩm công khai, không UPDATE | 0 | Schema chưa có event chuyên biệt hoặc cột seller đích cho lượt xem shop; hiện chỉ ghi metadata hành động. |

Không gán VIS-02/VIS-03 vào `page_events.event_type` bằng giá trị tự thêm trái schema. Không tăng `products.quantity_sold`, `review_count` hoặc `rating_average` khi khách đọc catalog.

VIS-01 là nhu cầu gửi sang module analytics, không phải một bộ sinh clickstream thứ hai. Khi chưa triển khai analytics chỉ lưu kế hoạch/yêu cầu, chưa tính là đã tạo lượt xem nghiệp vụ. Nếu analytics đã sinh lượt xem, phải dùng chung nguồn kế hoạch để không đếm trùng.

### 8.6. Tổng hồ sơ thử nghiệm mặc định

Mỗi ngày đề xuất **4 hành động ghi nghiệp vụ**: 1 đổi tên shop, 1 sửa tên sản phẩm, 1 sửa mô tả, 1 tạm dừng bán; cộng **100 lượt xem sản phẩm** do analytics thực thi khi sẵn sàng. Các hành động còn lại bằng 0 và chỉ chạy khi người dùng bật/đặt số lượng. Không tự chạy đồng bộ.

Đây là hồ sơ thử nhỏ để nhìn được tác động, không phải phân bố thực tế hoặc cấu hình phù hợp chạy cả năm. Ví dụ tạm dừng một sản phẩm/ngày sẽ làm cạn tập đang bán; preview phải báo điều đó và người dùng có thể giảm số hoặc bật mở lại với điều kiện đúng. Không tự cân bằng bằng cách mở lại hoặc thêm sản phẩm.

### 8.7. Quy tắc đếm và kiểm soát số lần

- Mỗi mã có `requested_count` theo ngày, là số nguyên không âm. Số theo ngày được chỉ định ghi đè mặc định ngày đó. Mặc định 0 nghĩa là tắt.
- Đếm theo **một hành động trên một đối tượng**, không theo số cột hoặc số dòng bị ảnh hưởng. Một lần chuyển địa điểm cập nhật hai cột vẫn là một hành động; một lần khóa shop làm 20 sản phẩm ngừng bán vẫn là một hành động và có thêm thống kê 20 sản phẩm bị ảnh hưởng.
- Preview cho biết số yêu cầu, số có thể lên lịch và lý do thiếu. Khi chạy báo riêng: thành công có thay đổi, thành công không thay đổi, bị từ chối, lỗi kỹ thuật, còn chờ và không lên lịch vì thiếu điều kiện. Không đổi số yêu cầu trong báo cáo để che thiếu sản lượng.
- Không thể cam kết tất cả số yêu cầu đều thành công nếu trạng thái không cho phép. Thiếu shop/sản phẩm/yêu cầu duyệt thì báo thiếu; không sửa sai quyền hoặc tạo giả dữ liệu nguồn để đủ số.
- Một đối tượng tối đa một lần cho cùng mã trong ngày. Các mã sửa nội dung khác nhau có thể dùng chung sản phẩm. Không chọn cùng sản phẩm cho tạm dừng và mở lại trong cùng ngày của hồ sơ mặc định.
- Đối tượng được chọn từ tập hợp lệ, sắp ID trước khi lấy mẫu có seed. Kiểm tra lại quyền và trạng thái lúc thực thi; preview không bảo đảm trạng thái sẽ không đổi.
- Thực thi theo thời gian; các tác động phụ thuộc phải chờ tác động trước. Khóa shop có hiệu lực trước thì các hành động seller sau đó phải được kiểm tra lại, không chạy theo snapshot đầu ngày.
- Mỗi hành động có ID duy nhất. Chạy lại/tiếp tục không lặp hành động đã hoàn tất. Retry lỗi kỹ thuật dùng cùng ID, không tính thành một nhu cầu nghiệp vụ mới.
- Xét hạng nhưng giữ nguyên hạng vẫn tính một lần xét, đồng thời báo không thay đổi. Một yêu cầu bị từ chối cũng được tính là một lần xử lý, nhưng không tính là một lần cập nhật thành công.

### 8.8. Việc nào cần người dùng manual, việc nào chưa đủ mô hình?

| Việc | Phân loại | Lý do / thao tác cần thiết |
|---|---|---|
| Yêu cầu đồng bộ | Người dùng chủ động kích hoạt | Đúng rule đã chốt; xử lý bản ghi bên trong vẫn tự động. |
| Đặt số lần, ngày chạy, đối tượng cố định nếu muốn | Cấu hình trước khi chạy | Sau đó hệ thống tự sinh và xử lý theo kế hoạch. |
| Chọn khóa khi cùng product ID có nhiều chào bán; SKU trùng/thiếu | Cần chốt chính sách trước khi triển khai | Chưa tự cấp mã giả hoặc chọn đè một chào bán. |
| Cho phép đổi giá/giá vốn, mở khóa shop, mở lại sản phẩm bị sàn gỡ | Cần chốt rule | Chưa đưa vào danh sách tự chạy; có thể mock sau khi có chính sách và trạng thái cần thiết. |
| CAT-04 đổi tên danh mục | Người dùng nhập lệnh đích | Không khó về kỹ thuật; cần giá trị mong muốn để giữ phân loại có nghĩa. |
| Chuyển danh mục khi không có danh sách đích tương thích | Người dùng cung cấp mapping đích | Có mapping thì có thể tự sinh SEL-08 và xử lý CAT-01; không đoán ngành từ ID. |
| Xét hạng theo hiệu suất khi chưa có đơn/đánh giá/chính sách | Chưa thể mock đúng căn cứ | Có thể chỉ định thay hạng để thử cập nhật, nhưng phải phân biệt với xét hạng theo dữ liệu. |
| Duyệt hồ sơ pháp lý, xác minh thương hiệu, xác định vi phạm thật | Ngoài khả năng xác minh của bộ mock | Chỉ giả lập kết quả có nhãn; nếu cần kết luận thật thì người có thẩm quyền cung cấp. |
| Xem trang danh mục/shop thành event analytics chuyên biệt | Schema chưa hỗ trợ trực tiếp | Chốt mở rộng schema hoặc chỉ giữ metadata; không cần người dùng INSERT tay. |
| Hủy đơn/hoàn tiền/giải phóng tồn sau khóa shop | Chờ module nhận và rule tương ứng | Catalog chỉ phát sự kiện. Không yêu cầu người dùng sửa DB tay để giả vờ hoàn tất. |

Phần lớn hành động không cần người dùng thao tác từng bản ghi. Các chỗ manual chủ yếu là kích hoạt, cung cấp cấu hình hoặc chốt chính sách; phần chưa đủ schema/phụ thuộc sẽ được báo chưa hỗ trợ thay vì đẩy sang người dùng sửa database trực tiếp.
