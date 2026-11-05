# Kịch bản và màn cấu hình mock — Catalog & Seller

> Đã chuyển sang triển khai theo yêu cầu người dùng. Nội dung dưới đây là thiết kế; xem [trạng thái thực tế](../reviews/MOCK_IMPLEMENTATION_STATUS.md) để biết tính năng đã chạy và giới hạn. Không hiểu “đã có thiết kế” là toàn bộ nghiệp vụ đã hoàn thành.

## 1. Phạm vi đã xác định

Tài liệu này mô tả người dùng chọn hành động và cấu hình sản lượng như thế nào. Chưa thiết kế cách ghi dữ liệu xuống các bảng, transaction hoặc giao tiếp nội bộ.

Đây là hướng thiết kế mới theo yêu cầu người dùng, thay thế phần cấu hình và số lượng mặc định trong mục 8 của [tài liệu kịch bản trước](../../reference/MOCK_CATALOG_SELLER_SCENARIOS.md). Không coi các giá trị 1/100 từng đề xuất là cấu hình đã chốt.

Có 5 bên tác động trong tổng thể, nhưng **Catalog & Seller hiển thị 4 nhóm nghiệp vụ**. Tiến trình đồng bộ Tiki được tách ra ngoài màn chính vì cung cấp đầu vào cho nhiều hệ thống.

## 2. Bố cục người dùng nhìn thấy

```text
Màn chính hệ thống mock
├── Đồng bộ dữ liệu Tiki                 ← chức năng độc lập, chủ động gọi
└── Các hệ thống mô phỏng
    └── Catalog & Seller
        ├── Người bán
        ├── Quản trị viên catalog
        ├── Nhân viên quản lý người bán
        └── Khách truy cập
```

Trong mỗi nhóm hiển thị danh sách hành động cụ thể. Chọn một hành động để cấu hình, không chỉ chọn một số lượng tổng cho cả nhóm.

### Form chung của mỗi hành động

| Ô điều khiển | Ý nghĩa |
|---|---|
| Bật hành động | Cho phép hành động tham gia kế hoạch chạy. |
| Số lần / ngày thường | Số nguyên không âm, bắt buộc nếu bật. Không đặt sẵn con số nghiệp vụ chưa được chốt. |
| Ngày đặc biệt | Thêm từng ngày đầy đủ `YYYY-MM-DD`, ví dụ `2026-11-11`; có thể chọn từ lịch chung. |
| Số lần / ngày đặc biệt | Số tuyệt đối cho từng ngày đã thêm, kể cả 0. |
| Chọn đối tượng | Tự chọn từ tập hợp lệ hoặc chỉ định ID; tên hiển thị kèm ID để tránh nhầm. |
| Cấu hình riêng | Các ô bổ sung theo từng hành động ở mục 3; không yêu cầu nhập JSON để dùng chức năng cơ bản. |
| Mô tả | Nói rõ một lần hành động được tính là gì và điều kiện thực hiện. |

**Quy tắc số lượng đã chốt:** ngày có cấu hình riêng dùng số của ngày đó để thay thế ngày thường, không cộng hoặc nhân thêm. Ngày được đánh dấu đặc biệt nhưng chưa có số riêng của hành động thì dùng số ngày thường, UI phải nói rõ. Không tự áp hệ số sale.

Ví dụ với “Người bán → Sửa tên sản phẩm”: ngày thường 5 lần; ngày `2026-11-11` 20 lần; ngày `2026-12-12` 10 lần. Các hành động khác có số riêng độc lập.

Không dùng một ô “số lần ngày đặc biệt” mơ hồ cho mọi ngày. Có thể hỗ trợ sao chép cấu hình sang nhiều ngày nhưng mỗi ngày phải có giá trị cuối cùng rõ ràng.

## 3. Danh sách nhóm → hành động → ô cấu hình riêng

Mỗi dòng dưới đây có đầy đủ các ô chung ở mục 2, bao gồm số lần ngày thường và ngày đặc biệt.

### 3.1. Nhóm Người bán

| Mã | Hành động hiển thị | Một lần là gì? | Ô cấu hình riêng cần hiện |
|---|---|---|---|
| SEL-01 | Đổi tên shop | Một shop nhận một tên mới | Phạm vi shop; cách tạo tên: mẫu tự động / danh sách tên; ô mẫu hoặc danh sách tên mới tương ứng. |
| SEL-02 | Đổi thông tin liên hệ shop | Một shop đổi email, điện thoại hoặc cả hai | Checkbox Email/Điện thoại; cách tạo: tự động / chỉ định; nếu chỉ định hiện shop, email mới, điện thoại mới. Không gửi email/SMS thật. |
| SEL-03 | Đổi địa điểm kinh doanh | Một shop chuyển sang một địa điểm mới | Phạm vi shop; tỉnh/thành đích: chọn hợp lệ tự động / chỉ định; nếu chỉ định hiện các ô địa phương liên quan. |
| SEL-04 | Sửa tên sản phẩm | Một sản phẩm nhận một tên sửa đổi | Phạm vi shop/sản phẩm; cách sửa: chuẩn hóa tên / dùng mẫu / danh sách tên đích; hiện mẫu hoặc cặp sản phẩm–tên nếu cần. |
| SEL-05 | Sửa mô tả sản phẩm | Một sản phẩm nhận một mô tả mới | Phạm vi sản phẩm; cách tạo: mẫu / chỉ định; ô mẫu mô tả hoặc cặp sản phẩm–mô tả. Không tự bịa thông số kỹ thuật. |
| SEL-06 | Tạm dừng bán sản phẩm | Một sản phẩm đang bán được tạm dừng | Phạm vi sản phẩm; lý do tạm dừng: chọn mẫu / nhập riêng. |
| SEL-07 | Mở lại sản phẩm đã tạm dừng | Một sản phẩm được mở bán lại | Chỉ chọn sản phẩm do seller tạm dừng và được phép mở; khoảng thời gian đã tạm dừng tối thiểu; có thể chỉ định sản phẩm. Không mở sản phẩm bị sàn gỡ hoặc shop đang khóa. |
| SEL-08 | Đề nghị chuyển danh mục | Một yêu cầu chuyển danh mục cho một sản phẩm | Danh mục nguồn; danh mục đích hoặc bảng mapping nguồn–đích; phạm vi sản phẩm; lý do. Chưa có mapping hợp lệ thì hiện yêu cầu bổ sung, không tự đoán. |

Người bán chỉ tác động lên shop/sản phẩm của mình. Việc chọn đối tượng tự động vẫn phải gắn đúng seller thực hiện.

**Chưa đưa vào danh sách giai đoạn này:** đổi giá, giá vốn, thương hiệu, ảnh, tên pháp lý, mã sản phẩm, SKU hoặc chuyển quyền sở hữu. Nếu muốn bổ sung sẽ chốt thành hành động riêng với form riêng; không ẩn chúng trong một nút “sửa sản phẩm” chung.

### 3.2. Nhóm Quản trị viên catalog

| Mã | Hành động hiển thị | Một lần là gì? | Ô cấu hình riêng cần hiện |
|---|---|---|---|
| CAT-01 | Chấp thuận chuyển danh mục | Xử lý chấp thuận một yêu cầu hợp lệ | Cách chọn yêu cầu: cũ nhất / chỉ định; danh mục/phạm vi được xử lý. UI hiển thị phụ thuộc vào yêu cầu SEL-08 đã có. |
| CAT-02 | Từ chối chuyển danh mục | Xử lý từ chối một yêu cầu đang chờ | Cách chọn yêu cầu; lý do từ chối: mẫu / nhập riêng. Không xử lý lại yêu cầu đã xong. |
| CAT-03 | Gỡ sản phẩm vi phạm mô phỏng | Một sản phẩm bị sàn ngừng cho bán | Phạm vi sản phẩm; lý do vi phạm giả: chọn mẫu / nhập riêng; tùy chọn chỉ định đích. Gắn nhãn rõ đây là vi phạm giả lập. |
| CAT-04 | Đổi tên danh mục | Một danh mục được đổi tên | **Bắt buộc nhập** danh mục đích và tên mới; checkbox đổi slug; nếu bật hiện slug mới hoặc tùy chọn sinh từ tên. Nhiều lần cần nhiều đích hợp lệ. |

Không có tạo/xóa danh mục tùy ý hoặc di chuyển cả nhánh trong phạm vi ban đầu. Danh mục thật mới được bổ sung qua đồng bộ ngoài màn chính.

### 3.3. Nhóm Nhân viên quản lý người bán

| Mã | Hành động hiển thị | Một lần là gì? | Ô cấu hình riêng cần hiện |
|---|---|---|---|
| MGR-01 | Xét hạng người bán | Một shop được xét, có thể giữ nguyên hạng | Chế độ: theo dữ liệu hoạt động / chỉ định kết quả để thử; phạm vi shop. Theo dữ liệu: kỳ quan sát, bộ chính sách đã chọn. Chỉ định: danh sách shop và hạng đích `Normal`/`Preferred`/`Mall`, lý do. |
| MGR-02 | Khóa người bán | Một shop Active bị khóa | Phạm vi shop; lý do vi phạm giả; chọn tự động / chỉ định ID. Hiển thị cảnh báo phạm vi ảnh hưởng của thao tác trong preview. |

Chế độ xét hạng theo dữ liệu chỉ khả dụng khi đã có chính sách và dữ liệu từ hệ thống liên quan. Nếu chưa có, UI vô hiệu hóa chế độ đó và giải thích; không âm thầm đổi thành chọn hạng ngẫu nhiên. Chỉ định kết quả là kiểm thử hành động thay hạng, không gọi là đánh giá hiệu suất thật.

Chưa đưa mở khóa shop vào phạm vi vì cần chốt điều kiện và xử lý các sản phẩm bị dừng trước đó.

### 3.4. Nhóm Khách truy cập

| Mã | Hành động hiển thị | Một lần là gì? | Ô cấu hình riêng cần hiện |
|---|---|---|---|
| VIS-01 | Xem chi tiết sản phẩm | Một lượt xem, không phải một khách hoặc một phiên | Phạm vi sản phẩm; cách chọn: đều / theo độ phổ biến nguồn; phạm vi khách/phiên do analytics cung cấp. |
| VIS-02 | Xem danh sách danh mục | Một lượt mở trang danh mục | Phạm vi danh mục hoặc danh mục chỉ định. |
| VIS-03 | Xem trang shop | Một lượt mở trang shop | Phạm vi shop hoặc shop chỉ định. |

Đây là hành động đọc. Không làm tăng số bán hay số đánh giá Tiki. Phần định nghĩa phiên/khách và ghi nhận lượt xem phải dùng chung với analytics để tránh sinh trùng.

Hiện VIS-02/VIS-03 chưa có event chuyên biệt trong schema analytics. UI cần hiển thị nhãn **“Chưa hỗ trợ ghi nhận nghiệp vụ”** và không cho chạy như tính năng đã hoàn tất. VIS-01 cũng cần module analytics sẵn sàng; nếu chưa có chỉ cấu hình/lưu kế hoạch, chưa báo đã thực hiện.

## 4. Đồng bộ Tiki — đặt ngoài màn chính

### 4.1. Giới hạn tác động

Chức năng này chỉ có nhiệm vụ **bổ sung đầu vào mới** theo [Rule 01](../MOCK_SYSTEM_RULES.md):

- Chỉ thêm sản phẩm, người bán và danh mục chưa tồn tại, đúng mapping và liên kết hợp lệ.
- Không cập nhật giá, thông tin hoặc trạng thái của bản ghi đã có.
- Không xóa, không mở lại sản phẩm/shop, không ghi ngược crawler.
- Không tạo đơn hàng, khách hàng, thanh toán, tồn kho đầu kỳ, biến động kho, chiến dịch, lượt xem, hoa hồng hoặc đối soát.
- Không tự kích hoạt hàng loạt hành động ở các hệ thống khác sau đồng bộ. Các hệ thống khác có thể sử dụng catalog mới khi được chạy theo kế hoạch riêng.
- Nếu chưa bảo đảm khóa, liên kết hoặc trạng thái bán hợp lệ thì báo lỗi/hoãn, không sửa bản ghi cũ để ép nhập thành công.

Đây là ranh giới giữa cung cấp dữ liệu mới và mô phỏng hoạt động nghiệp vụ. Việc hệ thống nào được sử dụng sản phẩm vừa nhập và từ thời điểm nào sẽ chốt ở bước thiết kế dữ liệu.

### 4.2. Form riêng của chức năng đồng bộ

| Ô / nút | Yêu cầu |
|---|---|
| Nguồn dữ liệu crawler | Chọn cấu hình nguồn hoặc đường dẫn DB; chỉ đọc. |
| Phạm vi | Toàn bộ sản phẩm mới / chọn danh mục / chọn ID cụ thể. |
| Giới hạn sản phẩm mới | Tất cả hợp lệ hoặc tối đa N sản phẩm; không tạo giả để đủ N. |
| Xem trước | Hiển thị số sản phẩm, seller, danh mục dự kiến thêm; số đã có; lỗi; phần hoãn vì giới hạn. |
| Thực hiện đồng bộ | Người dùng chủ động gọi; không có lịch ngày thường/ngày đặc biệt của nhóm này. |
| Kết quả và lịch sử | Số thực tế thêm/bỏ qua/hoãn/lỗi; lý do và thời điểm của từng lượt. |

Hệ thống tự xử lý từng bản ghi sau khi người dùng gọi đồng bộ; không yêu cầu nhập tay sản phẩm. Một lượt gọi không đồng nghĩa một sản phẩm mới.

## 5. Các trường hợp manual hoặc chưa hỗ trợ phải hiện rõ

| Trường hợp | UI cần hiện gì? |
|---|---|
| Đổi tên danh mục | Ô chọn ID danh mục, tên mới và cấu hình slug ngay trong CAT-04. |
| Chỉ định tên/mô tả/liên hệ | Các ô nhập cụ thể ngay trong hành động tương ứng; không yêu cầu sửa file hoặc SQL. |
| Chuyển danh mục | Bộ chọn nguồn–đích hoặc bảng mapping ngay trong SEL-08; thiếu mapping thì báo thiếu cấu hình. |
| Xét hạng chỉ định | Danh sách shop–hạng đích và lý do ngay trong MGR-01. |
| Xét hạng theo hoạt động chưa đủ điều kiện | Nhãn chưa sẵn sàng, nêu thiếu chính sách/dữ liệu nào; không yêu cầu sửa DB tay. |
| Khóa/gỡ vì vi phạm mô phỏng | Ô lý do giả lập rõ ràng; không yêu cầu xác minh pháp lý thật. |
| Khóa sản phẩm nguồn/SKU xung đột lúc đồng bộ | Danh sách lỗi và lý do; cần chốt chính sách xử lý, không tự sửa ID hoặc nguồn. |
| Hành động chưa có schema/module hỗ trợ | Hiện lý do, không cho chạy như đã hỗ trợ; không gán công việc cho người dùng INSERT thủ công. |

Manual ở đây chủ yếu là **cấu hình trước khi chạy**. Không yêu cầu người dùng thực hiện từng lần trong ngày mô phỏng. Danh sách giá trị chỉ định không đủ số lần yêu cầu thì phải báo thiếu; không tự lặp cùng một lệnh không đổi để đủ số lượng.

## 6. Preview và cách đếm số lần

Preview theo từng ngày, từng nhóm và từng hành động, ít nhất gồm: số yêu cầu, số có thể lên lịch, số thiếu và lý do. Sau chạy có số hoàn tất, không thay đổi, từ chối, lỗi và còn chờ.

Một hành động có thể ảnh hưởng nhiều bản ghi nhưng vẫn chỉ tính một lần theo định nghĩa trong bảng. Một shop bị khóa không được tính thành nhiều lần khóa theo số sản phẩm.

Số thực hiện bị giới hạn bởi quyền, trạng thái và đối tượng hợp lệ. Không tự thêm hành động khác hoặc thay đổi dữ liệu sai để bù quota. Chạy lại phải không lặp những hành động đã hoàn tất.

## 7. Trạng thái quyết định

**Đã chốt:** người dùng chọn số lần cho từng hành động, không áp số ví dụ làm mặc định. Số ngày đặc biệt thay thế số ngày thường; không tự tăng mọi hành động vì là ngày sale. Đồng bộ đặt ngoài màn chính và chỉ thêm mới.

**Đang đề xuất để review:** danh sách chi tiết hành động và các ô cấu hình riêng. Không coi toàn bộ thiết kế là đã duyệt chỉ vì file nằm trong thư mục mới.

**Thiết kế ở bước sau, không phải câu hỏi đang chờ trả lời:** cách ghi dữ liệu, lưu nhật ký, thời điểm hiệu lực và truyền tác động sang các hệ thống.

**Cần quyết định trước khi code đồng bộ:** khóa cho sản phẩm nhiều chào bán, xử lý SKU xung đột và trạng thái khởi tạo. Những vấn đề này thuộc chức năng đồng bộ ngoài màn chính.

Chưa triển khai code hoặc UI trong bước này.
