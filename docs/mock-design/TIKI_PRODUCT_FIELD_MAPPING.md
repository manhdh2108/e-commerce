# Ánh xạ dữ liệu sản phẩm Tiki vào schema OLTP

Tài liệu này đề xuất bộ trường cần lấy từ Tiki để có sản phẩm và giá thật làm nền cho dữ liệu mô phỏng. Đây là thiết kế mapping, chưa phải thay đổi code hoặc database.

Đối chiếu với [OLTP_SCHEMA.md](../data-model/oltp/OLTP_SCHEMA.md), [OLTP_ERD.md](../data-model/oltp/OLTP_ERD.md), [SCHEMA.md](../data-model/crawler/SCHEMA.md), crawler hiện tại và JSON thực tế trong `data/tiki_crawl.db`.

## 1. Cách đọc các liên kết

- **Ánh xạ trực tiếp:** giá trị nguồn đi vào một cột có sẵn trong schema, có thể cần đổi kiểu.
- **Chuyển đổi:** phải trích xuất, chuẩn hóa hoặc lựa chọn giá trị trước khi ghi.
- **Chỉ lưu ở tầng cào:** chưa có cột tương ứng trong schema nghiệp vụ. Lưu để kiểm tra nguồn hoặc phục vụ lần nạp sau.
- **Tham chiếu khi mock:** dữ liệu nguồn giúp tạo bản ghi mô phỏng; không có nghĩa API Tiki đã cung cấp bản ghi nghiệp vụ đó.

“Tầng cào” ở đây là nơi giữ dữ liệu đầu vào và metadata crawler. Schema OLTP là mô hình các hệ thống nguồn mà mình muốn mô phỏng. Cách triển khai tầng staging sẽ chốt riêng; tài liệu này không giả định chúng là cùng một database.

## 2. Bộ trường ưu tiên lấy

### 2.1. Nhận diện sản phẩm

| Trường lấy từ Tiki | Cột đích trong schema OLTP | Cách ánh xạ | Liên kết / lưu ý |
|---|---|---|---|
| `id` | `products.id` | Trực tiếp, bigint | PK sản phẩm; các bảng nghiệp vụ tham chiếu qua `product_id`, chi tiết ở mục 4. |
| `sku` | `products.sku` | Trực tiếp, varchar | Dùng nối với kho vận qua SKU. Giữ dạng chuỗi, không bỏ số 0 đầu. |
| `name` | `products.name` | Trực tiếp | Thuộc tính mô tả, không phải khóa nối bảng. |
| `seller_id` | `products.seller_id`; dùng tạo `sellers.id` | Trực tiếp cho mã | Phải có dòng `sellers` tương ứng trước khi nạp sản phẩm. API listing không cung cấp đủ hồ sơ người bán. |
| `seller_product_id` | `products.seller_product_id` | Chuyển sang varchar theo schema | Giữ mã nguồn; schema hiện tại chưa có bảng khác tham chiếu cột này. |
| `url_key` | `products.url_key` | Trực tiếp | Slug sản phẩm; không dùng làm ID hoặc FK. |
| `url_path` | `products.url_path` | Trực tiếp | Đường dẫn kiểm tra sản phẩm, có thể chứa tham số người bán; không phải khóa nối. |

**Điểm cần kiểm tra trước khi nạp:** crawler hiện dùng duy nhất `id` làm PK. Nếu cùng `id` xuất hiện với nhiều `seller_id` hoặc `seller_product_id`, cập nhật đè có thể làm mất các chào bán. Cần thống kê trường hợp đó trước khi chốt chiến lược lưu. Chưa tự ghép ID hoặc khẳng định ba loại mã này thay thế được nhau.

### 2.2. Giá sản phẩm

| Trường lấy từ Tiki | Cột đích trong schema OLTP | Cách ánh xạ | Liên kết / lưu ý |
|---|---|---|---|
| `price` | `products.price` | Trực tiếp, decimal | Giá bán quan sát tại thời điểm cào; làm cơ sở tạo `order_items.unit_price` khi mock, không phải FK. |
| `original_price` | `products.original_price` | Ưu tiên giá trị nguồn này | Làm cơ sở tạo `order_items.list_price` khi mock, không phải FK. |
| `list_price` | Không có cột riêng trong `products`; fallback cho `products.original_price` | Theo schema hiện tại: chỉ fallback khi `original_price` thiếu | Nên giữ giá trị nguồn riêng ở tầng cào. Không nhầm với `order_items.list_price`, vốn là giá niêm yết được chốt lúc đặt đơn. |
| `discount` | `products.discount` | Trực tiếp | Giảm giá nguồn; không sao chép thẳng thành `order_items.discount_amount`, vì dòng đơn còn có quy tắc và voucher riêng. |
| `discount_rate` | `products.discount_rate` | Trực tiếp, kiểm tra đơn vị | Giữ giá trị nguồn; nếu chuẩn hóa từ phần trăm sang tỷ lệ phải quy định rõ. Không có FK. |

Giá thật ở đây là **giá API trả tại thời điểm quan sát**, chưa thể khẳng định là số tiền cuối cùng khách trả sau voucher, phí giao hàng hoặc ưu đãi riêng.

Giữ nguyên `null`, 0 và các giá trị bất thường trong dữ liệu nguồn; ghi nhận lỗi chất lượng riêng, không âm thầm sửa JSON gốc. Ví dụ dữ liệu đã cào có `original_price = 600000` nhưng `list_price = 0`.

**Lịch sử giá:** schema OLTP hiện chỉ giữ giá hiện tại; crawler cũng chưa có bảng lịch sử giá. Có thể đề xuất một bảng quan sát giá riêng ở tầng cào với định danh sản phẩm/chào bán, các trường giá và `observed_at`. Bảng này chưa tồn tại và không phải yêu cầu thêm lịch sử vào `products`. Cào hôm nay cũng không cung cấp giá thật của những ngày quá khứ chưa từng cào.

### 2.3. Danh mục và thông tin hiển thị

| Trường đầu vào | Cột đích trong schema OLTP | Cách ánh xạ | Liên kết / lưu ý |
|---|---|---|---|
| `primary_category_path` từ API | Không có cột nguyên chuỗi tương ứng | Giữ ở tầng cào; có thể tách ID để dựng `categories` | Không đủ để tự có tên, slug hoặc xác nhận đầy đủ cây danh mục. Cần đối chiếu API danh mục. |
| `root_category_id` do crawler ghi | `categories.id` của danh mục gốc, nếu đã xác nhận | Từ ngữ cảnh lần cào | Không đưa trực tiếp vào `products.category_id` của OLTP vì cột đó yêu cầu danh mục lá. |
| `leaf_category_id` do crawler ghi | `products.category_id` → `categories.id` | Chọn một danh mục lá hợp lệ làm danh mục chính | Một sản phẩm có thể được quan sát ở nhiều danh mục; cần quy tắc chọn nhất quán, không lấy tùy dòng cuối. |
| Tên danh mục lá từ API danh mục hoặc nguồn đã xác minh | `categories.category_name`; `products.category_name` | Chuẩn hóa theo danh mục chính | Không lấy tên danh mục gốc gán cho ID danh mục lá. |
| ID cha từ cây API danh mục | `categories.parent_id` | Tham chiếu dòng cha trong `categories` | Chỉ danh mục gốc mới có `parent_id = null`; thiếu dữ liệu cha chưa đồng nghĩa là gốc. |
| Độ sâu từ cây danh mục | `categories.level` | Tính từ cây, gốc là 1 | Không lấy độ dài chuỗi path một cách máy móc nếu chưa xác minh các nút hệ thống. |
| Slug danh mục, nếu API có | `categories.slug` | Trực tiếp nếu xác minh được | Nếu tự sinh từ tên phải ghi rõ là giá trị dẫn xuất. Không lấy `url_key` của sản phẩm làm slug danh mục. |
| `brand_name` | `products.brand_name` | Trực tiếp, cho phép thiếu | Không có bảng `brands` trong schema hiện tại. |
| `thumbnail_url` | `products.thumbnail_url` | Trực tiếp | Dùng hiển thị, không có FK. |
| `short_description` | `products.short_description` | Trực tiếp | Cho phép trống; không có FK. |

`root_category_id` và `leaf_category_id` hiện có trong bảng hạ tầng `product_categories`. Đây là ngữ cảnh do crawler lưu, không phải hai trường mặc định có trong từng JSON sản phẩm.

**Khác biệt hiện tại cần xử lý khi nạp:** `products.category_id` và `category_name` của SQLite crawler đang chứa danh mục gốc. Cùng tên cột nhưng ý nghĩa khác với OLTP. Không sao chép nguyên hai cột này sang OLTP.

### 2.4. Chỉ số tham khảo từ Tiki

| Trường lấy từ Tiki | Cột đích trong schema OLTP | Cách ánh xạ | Không được hiểu thành |
|---|---|---|---|
| `quantity_sold.value` | `products.quantity_sold` | Trích số trong object; chấp nhận dạng số nếu nguồn trả dạng số | Số đơn hoặc số lượng bán phát sinh trong hệ thống mock. |
| `rating_average` | `products.rating_average` | Trực tiếp | Kết quả tính chắc chắn từ các dòng `product_reviews` mô phỏng. |
| `review_count` | `products.review_count` | Trực tiếp | Số dòng `product_reviews` đã tạo trong DB mô phỏng. |

Có thể dùng các chỉ số này làm trọng số chọn sản phẩm hoặc tham khảo phân bố. Không tạo ngược đơn hàng hoặc đánh giá để cố khớp toàn bộ số lũy kế Tiki.

### 2.5. Trạng thái nguồn: giữ để đối chiếu, chưa dùng để quyết định mô phỏng

| Trường lấy từ Tiki | Cột có sẵn trong schema OLTP | Mapping đề xuất / giới hạn |
|---|---|---|
| `is_visible` | Không có cột cùng nghĩa | Giữ trong JSON nguồn. Không tự đổi thành `products.is_active`. |
| `is_active`, nếu API thực sự trả | `products.is_active` | Chỉ ánh xạ sau khi xác nhận nghĩa; tách quyết định cho tham gia mock khỏi trạng thái nguồn. |
| `availability` | Không có cột tương ứng | Giữ trong JSON nguồn; chưa suy diễn mã trạng thái. |
| `shippable` | Không có cột tương ứng | Giữ trong JSON nguồn; không dùng tạo shipment thật. |
| `inventory_status` | `products.inventory_status` | Có thể chép nguyên trạng thái nguồn; không suy ra số tồn. |
| `stock_item` | `products.stock_item` | Object/list được lưu thành JSON text; null giữ null. Không tự ánh xạ sang số lượng kho. |
| `type` | `products.type` | Có thể chép nguyên; nếu trống thì giữ trống/null theo quy tắc nạp. Không tự phân loại nghiệp vụ khi chưa có quy tắc. |

Crawler hiện đang fallback `is_active` từ `is_visible`. Đây là hành vi hiện có, **không phải mapping được khuyến nghị**. Mẫu đã cào có `is_visible = false` cùng `shippable = true`, `availability = 1`; chỉ các giá trị đó chưa đủ kết luận sản phẩm hết hàng hoặc ngừng bán. Tài liệu này chưa sửa crawler.

## 3. Metadata: trường không ánh xạ vào nghiệp vụ hoặc chỉ ánh xạ một phần

| Trường do mình quản lý | Nơi lưu hiện tại / đề xuất | Liên hệ với schema OLTP |
|---|---|---|
| `observed_at` | Đề xuất timestamp đầy đủ của lần quan sát | Có thể lấy ngày local để tạo `products.crawl_date`. Schema không có cột timestamp quan sát riêng. |
| `crawl_date` | Hiện có trong SQLite `products` | Ánh xạ `products.crawl_date`; không phải ngày sản phẩm lên sàn. |
| `crawl_run_id` | Hiện có `crawl_runs.id`; các checkpoint trang dùng `run_id` | Không có cột đích trong các bảng nghiệp vụ. Hiện chưa có liên kết trực tiếp từ mỗi dòng `products` đến một run. |
| `raw_json` | Hiện có `product_raw.raw_json`, nối bằng `product_id` | Không có cột đích trong bảng nghiệp vụ. Hiện chỉ giữ JSON mới nhất, không phải mọi phiên bản. |
| `content_hash` | Hiện có `product_checkpoints.content_hash` | Dùng phát hiện thay đổi, không ánh xạ vào `products.updated_at` bằng giá trị hash. |
| `first_seen_at` | Hiện có `product_checkpoints.first_seen_at` | Không có cột tương đương; không phải `products.created_at`. |
| `last_seen_at` | Hiện có `product_checkpoints.last_seen_at` | Không có cột tương đương; không phải thời điểm sản phẩm thay đổi. |
| `last_changed_at` | Hiện có `product_checkpoints.last_changed_at` | Thời điểm crawler phát hiện payload thay đổi; không tự đồng nhất với `products.updated_at` của ngày mô phỏng. |
| `root_category_id`, `leaf_category_id` | Hiện có `product_categories` | Dùng dựng danh mục/quan hệ như mục 2.3; không có hai cột tương ứng trong OLTP `products`. |

Các bảng hạ tầng crawler không thuộc 27 bảng nghiệp vụ OLTP. Checkpoint trang giúp tiếp tục cào; checkpoint sản phẩm giúp phát hiện thay đổi. Hai loại checkpoint phục vụ hai việc khác nhau.

## 4. Các khóa sản phẩm sẽ nối sang những bảng nào?

### 4.1. Khóa `products.id`

| Cột tham chiếu trong schema | Dữ liệu thật cung cấp gì? | Phần phải mô phỏng |
|---|---|---|
| `order_items.product_id` | ID sản phẩm được chọn mua | Dòng đơn, số lượng, giá tại giao dịch, trạng thái. |
| `product_reviews.product_id` | ID sản phẩm được đánh giá | Đánh giá sau mua, khách hàng, thời điểm, nội dung. |
| `promotions.product_id` | ID sản phẩm áp dụng khuyến mãi cấp Item | Chương trình, điều kiện, thời hạn và ngân sách. |
| `page_events.product_id` | ID sản phẩm được xem hoặc tương tác | Phiên truy cập, sự kiện, thời điểm. |
| `cart_items.product_id` | ID sản phẩm được thêm vào giỏ | Giỏ, khách/phiên, số lượng và trạng thái. |

Các quan hệ trên không có nghĩa dữ liệu cào tự tạo bản ghi cho những bảng đó.

### 4.2. Khóa `products.sku`

| Cột nối nghiệp vụ | Ý nghĩa |
|---|---|
| `inventory_levels.sku` | Tồn hiện tại của sản phẩm tại kho. |
| `inventory_movements.sku` | Các lần nhập, xuất, hoàn hoặc điều chỉnh. |
| `inventory_daily_balance.sku` | Số dư kho theo ngày. |

Đây là nối bằng mã nghiệp vụ qua các hệ thống, không mặc định có FK vật lý giữa database. SKU phải được kiểm tra thiếu/trùng trước khi dùng để nối; ERD kỳ vọng SKU duy nhất. Số tồn, lượng giữ chỗ và biến động đều phải mô phỏng, không lấy từ `quantity_sold` hoặc `stock_item` khi chưa có dữ liệu xác thực.

### 4.3. Mã người bán

`seller_id` từ Tiki cung cấp mã để tạo `sellers.id` và nối `products.seller_id`. Sau đó bộ mock dùng cùng mã cho:

- `orders.seller_id`.
- `promotions.seller_id`, khi khuyến mãi thuộc shop.
- `seller_payouts.seller_id`.

Tên shop, tên người bán, địa chỉ, email, điện thoại, tier và trạng thái không tự có từ một mã `seller_id`. Theo schema hiện tại, hồ sơ này được mô phỏng nếu không lấy thêm nguồn thật đã xác minh.

### 4.4. Mã danh mục

Sau khi dựng danh mục, `categories.id` được tham chiếu bởi:

- `products.category_id`.
- `categories.parent_id`, để dựng quan hệ cha–con.
- `seller_commission_rates.category_id`, để áp dụng chính sách hoa hồng.

ID danh mục có thể dùng dữ liệu thật; tỷ lệ hoa hồng, hạng người bán và thời hạn chính sách là dữ liệu mô phỏng.

## 5. Những cột trong `products` chưa được dữ liệu Tiki đề xuất cung cấp trực tiếp

| Cột OLTP | Nguồn dự kiến |
|---|---|
| `cost_price` | Mô phỏng theo quy tắc giá vốn; không suy ra đây là giá vốn thật từ giá bán hoặc giá gốc. |
| `created_at` | Ngày sản phẩm tham gia hệ thống mô phỏng theo kịch bản. Không gán `first_seen_at` rồi gọi đó là ngày lên sàn thật. |
| `updated_at` | Thời điểm thay đổi trạng thái/thuộc tính trong hệ thống mô phỏng. Phân biệt với thời điểm cào. |
| `is_active` | Chưa có mapping nguồn đủ chắc chắn cho mẫu hiện tại; cần quy tắc hoạt động của hệ thống mô phỏng rõ ràng. |

Các cột còn lại của `products` đều đã được đề cập ở mục 2–3, nhưng danh mục cần làm giàu và một số thuộc tính nguồn có thể thiếu. Không mặc định rằng tất cả sản phẩm đều có đủ dữ liệu.

## 6. Phạm vi lấy dữ liệu cho bước đầu

1. **Bắt buộc lấy và kiểm tra:** `id`, `sku`, `name`, `seller_id`, `seller_product_id`, `price`, `original_price`, `list_price`; ngữ cảnh danh mục và thời điểm quan sát. Trường nguồn thiếu vẫn giữ trong raw và báo chất lượng; không bịa mã hoặc giá thật để đủ cột.
2. **Ưu tiên giữ:** `discount`, `discount_rate`, `brand_name`, `url_key`, `url_path`, `thumbnail_url`, `primary_category_path`, `quantity_sold`, `rating_average`, `review_count`, `short_description`.
3. **Giữ nguyên trong raw, chỉ tách cột khi cần:** các cờ trạng thái và thông tin kho nguồn. Những cột đã có trong schema có thể nạp theo mục 2.5, nhưng chưa dùng để điều khiển nghiệp vụ khi chưa rõ nghĩa.
4. **Giữ metadata riêng:** run, checkpoint, hash và JSON nguồn. Lịch sử giá là đề xuất bổ sung, chưa được crawler hỗ trợ.

Bước này tạo danh mục sản phẩm và giá tham chiếu thật. Đơn hàng, khách hàng, kho vận, thanh toán, khuyến mãi, clickstream và tài chính sẽ được tạo bởi bộ mock trong bước thiết kế sau; không coi chúng là dữ liệu đã cào từ Tiki.
