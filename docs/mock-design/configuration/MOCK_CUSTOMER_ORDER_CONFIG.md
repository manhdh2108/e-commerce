# Cấu hình kịch bản mock — Khách hàng & Đơn hàng

> Đã chuyển sang triển khai theo yêu cầu người dùng. Nội dung dưới đây là thiết kế; xem [trạng thái thực tế](../reviews/MOCK_IMPLEMENTATION_STATUS.md) để biết tính năng đã chạy và giới hạn. Không hiểu “đã có thiết kế” là toàn bộ nghiệp vụ đã hoàn thành.

**Trạng thái:** Đề xuất danh sách hành động và form cấu hình để chốt cùng người dùng. Chưa triển khai code/UI; chưa chốt cách ghi dữ liệu chi tiết.

Các tài liệu cũ bên dưới chỉ dùng tham khảo cấu trúc, có thể có sai sót; không quyết định logic mới. Nếu khác yêu cầu đã chốt, phải ghi nhận điểm cần đối chiếu thay vì ép thiết kế mới theo tài liệu cũ.

Cơ sở tham khảo: [schema OLTP](../../data-model/oltp/OLTP_SCHEMA.md), [ERD](../../data-model/oltp/OLTP_ERD.md), các mục khách hàng, đơn hàng, thanh toán và sau bán của [bộ luật cũ](../../data-model/oltp/DATA_GENERATION_RULES.md). Không tự áp tỷ lệ hoặc ngưỡng trong bộ luật cũ thành cấu hình đã chốt.

## 1. Vị trí và phạm vi màn hình

```text
Màn chính
├── Đồng bộ Tiki                         ← độc lập, chỉ thêm catalog mới
└── Các hệ thống mô phỏng
    ├── Catalog & Seller
    └── Khách hàng & Đơn hàng
        ├── Khách vãng lai
        ├── Khách đã đăng ký
        ├── Người bán xử lý đơn
        ├── Nhân viên chăm sóc khách hàng / xử lý sau bán
        ├── Dịch vụ thanh toán mô phỏng
        └── Tiến trình tự động của hệ thống
```

Số nhóm tác động phụ thuộc chức năng, không bắt buộc mỗi hệ thống đều có 5 nhóm. Người bán ở màn này chỉ xử lý đơn; các thao tác sản phẩm/shop ở Catalog & Seller không được sinh lặp tại đây.

Thanh toán và hoàn tiền nằm trong phạm vi nhóm đơn hàng của schema hiện tại. Dịch vụ thanh toán được giả lập, không gọi cổng thật. Giao nhận do hệ thống Kho vận xử lý; không thêm nút giả giao hàng thành công độc lập tại đây để bỏ qua vận chuyển.

## 2. Form chung cho từng hành động

Mỗi hành động trong mục 3 có form riêng:

| Ô cấu hình | Nội dung |
|---|---|
| Bật/tắt | Bật hành động vào kế hoạch. Ban đầu chưa có số mặc định nghiệp vụ. |
| Số lần ngày thường | Số nguyên không âm cho chính hành động đó. |
| Ngày đặc biệt và số lần | Từng ngày `YYYY-MM-DD` cùng số tuyệt đối riêng. |
| Phạm vi / đối tượng | Chọn tự động trong tập hợp lệ hoặc chỉ định ID. |
| Cấu hình riêng | Các trường được liệt kê cho từng mã ở mục 3. |
| Preview | Số yêu cầu, số có thể chạy, phụ thuộc còn thiếu và lý do không đủ. |

Theo cách cấu hình đã được người dùng đồng ý: số của ngày đặc biệt **thay thế** số ngày thường; không cộng hoặc nhân thêm hệ số. Nếu hành động không có override của ngày đó thì dùng số ngày thường. Giá trị 0 là không yêu cầu chạy hành động đó.

Không yêu cầu nhập JSON hoặc sửa SQL để cấu hình các chức năng thông thường.

## 3. Nhóm tác động và hành động cụ thể

### 3.1. Khách vãng lai

| Mã | Hành động | Một lần được tính là | Ô cấu hình riêng |
|---|---|---|---|
| GST-01 | Đăng ký tài khoản | Một tài khoản mới được đăng ký | Phân bố tỉnh/thành, tuổi, giới tính hoặc không khai báo; tên tự sinh; chính sách email/điện thoại thử nghiệm; tùy chọn tạo địa chỉ ban đầu. |
| GST-02 | Đặt hàng không đăng nhập | Một lần checkout của khách vãng lai | Form đặt hàng chung ở mục 4; địa chỉ dùng một lần; phương thức được phép. Đề xuất ban đầu chỉ kênh Web. |
| GST-03 | Yêu cầu hủy đơn của khách vãng lai | Một yêu cầu hủy đối với một đơn đủ điều kiện | Cách chọn đơn thuộc khách vãng lai; thời gian từ đặt đến hủy; lý do; ngưỡng cho phép hủy theo chính sách. |
| GST-04 | Yêu cầu trả hàng của khách vãng lai | Một yêu cầu trả cho một dòng hàng đã giao | Cách chọn dòng; cửa sổ trả hàng; toàn bộ/một phần; lý do; số lượng hoặc khoảng số lượng hợp lệ. |

Khách vãng lai chỉ được tác động vào đơn thuộc mình. Mô hình xác thực bằng mã đơn/token là giả định ở lớp điều khiển; schema chưa có token. Không cho chọn bất kỳ đơn nào rồi coi là đơn của khách đó. Tài khoản mới không tự mua hàng nếu không có hành động riêng.

### 3.2. Khách đã đăng ký

| Mã | Hành động | Một lần được tính là | Ô cấu hình riêng |
|---|---|---|---|
| CUS-01 | Đổi thông tin cá nhân | Một hồ sơ được đổi các trường đã chọn | Tập khách; checkbox tên/email/điện thoại/giới tính/ngày sinh; tạo tự động hoặc nhập đích. Không tự đổi hạng thành viên. |
| CUS-02 | Đổi nơi cư trú trong hồ sơ | Một khách đổi nơi cư trú khai báo | Tỉnh/thành mới tự chọn hợp lệ hoặc chỉ định. Không mặc định đổi địa chỉ giao hàng. |
| CUS-03 | Thêm địa chỉ nhận hàng | Một địa chỉ mới của một khách | Tỉnh, phường/xã, mô hình hành chính; tên/số người nhận; chi tiết địa chỉ tự sinh hoặc nhập riêng; đặt làm mặc định hay không. |
| CUS-04 | Đổi địa chỉ mặc định | Một khách chọn một địa chỉ có sẵn làm mặc định | Tập khách; địa chỉ thuộc khách được chỉ định hoặc chọn tự động. Không sửa nội dung địa chỉ đã gắn với đơn cũ. |
| CUS-05 | Đặt hàng sau khi đăng nhập | Một lần checkout của một khách | Form mục 4; phân bố người mua lần đầu/mua lại; nguồn địa chỉ mặc định/địa chỉ khác. |
| CUS-06 | Thử thanh toán lại | Một lần thử mới cho một đơn trả trước chưa thanh toán thành công | Phạm vi đơn đã thất bại; độ trễ; cùng phương thức/đổi phương thức; phương thức đích. Kết quả do PAY-01 xử lý. |
| CUS-07 | Yêu cầu hủy đơn | Một yêu cầu hủy cho một đơn của khách | Phạm vi đơn; lý do; khoảng trễ từ lúc đặt; điều kiện trước khi lấy hàng. Không mặc định bảo đảm yêu cầu được chấp thuận. |
| CUS-08 | Yêu cầu trả hàng | Một yêu cầu trả cho một dòng hàng đã giao | Cửa sổ trả; lý do `Damaged`, `Wrong Item`, `Not As Described`, `Changed Mind`; toàn bộ/một phần; khoảng số lượng. |
| CUS-09 | Đánh giá sản phẩm đã mua | Một đánh giá cho một dòng hàng hợp lệ | Khoảng ngày sau giao; phân bố 1–5 sao; tỷ lệ có bình luận; bình luận mẫu hoặc chỉ định. |

Không cho sửa/xóa địa chỉ đang được đơn cũ tham chiếu trong giai đoạn đầu. Nếu khách muốn đổi địa chỉ lưu, dùng thêm địa chỉ mới; đổi địa chỉ trên đơn đã đặt là chức năng riêng chưa đưa vào phạm vi. Review chỉ dành cho khách đã đăng ký, đã mua và đủ điều kiện; không sinh review giả không gắn giao dịch.

### 3.3. Người bán xử lý đơn

| Mã | Hành động | Một lần được tính là | Ô cấu hình riêng |
|---|---|---|---|
| ORD-01 | Xác nhận xử lý đơn | Một đơn của shop được xác nhận xử lý | Phạm vi shop/đơn; độ trễ từ khi đủ điều kiện; ưu tiên đơn cũ nhất hoặc chỉ định. Phân biệt COD với trả trước. |
| ORD-02 | Hủy toàn bộ đơn từ phía shop | Một đơn chưa lấy hàng bị shop hủy hợp lệ | Phạm vi shop; lý do mô phỏng; độ trễ; giới hạn trạng thái đủ điều kiện. |
| ORD-03 | Hủy một phần dòng hàng | Một dòng bị hủy trong đơn còn dòng khác tiếp tục | Chọn đơn nhiều dòng; số dòng hủy mỗi hành động: một; lý do; thời điểm trước lấy hàng. Giai đoạn đầu chỉ hủy cả dòng, không hủy một phần số lượng của dòng. |

Người bán chỉ xử lý đơn của shop mình. Không có quyền tự đánh dấu khách đã trả tiền, giao thành công, đổi số tiền đơn tùy ý hoặc sửa đánh giá của khách.

Schema không có cột seller-confirmed riêng. ORD-01 là hành động điều khiển cần thống nhất cách biểu diễn khi thiết kế dữ liệu; không bịa enum `Confirmed` trong `orders.order_status`.

### 3.4. Nhân viên chăm sóc khách hàng / xử lý sau bán

| Mã | Hành động | Một lần được tính là | Ô cấu hình riêng |
|---|---|---|---|
| SUP-01 | Chấp thuận yêu cầu trả hàng | Một yêu cầu đang chờ được chấp thuận | Cách chọn yêu cầu; thời gian xử lý; nhóm lý do/đối tượng được áp dụng. Không tự chọn lại yêu cầu đã từ chối. |
| SUP-02 | Từ chối yêu cầu trả hàng | Một yêu cầu đang chờ bị từ chối | Cách chọn yêu cầu; khoảng trễ; lý do từ chối mẫu/nhập riêng. |

Yêu cầu hủy đơn hợp lệ có thể được hệ thống xử lý tự động; chưa thêm một luồng duyệt hủy thủ công khi chưa có yêu cầu nghiệp vụ. Nhân viên sau bán không tự đánh dấu đã nhận hàng hoàn hoặc hoàn tiền xong; các mốc đó thuộc hệ thống liên quan.

### 3.5. Dịch vụ thanh toán mô phỏng

| Mã | Hành động | Một lần được tính là | Ô cấu hình riêng |
|---|---|---|---|
| PAY-01 | Trả kết quả thanh toán trả trước | Một kết quả cuối cho một lần thử đang chờ | Phương thức áp dụng; phân bố thành công/thất bại; độ trễ phản hồi; chọn tự động/chỉ định lần thử và kết quả. |
| PAY-02 | Trả kết quả hoàn tiền | Một yêu cầu hoàn tiền được hoàn tất | Phạm vi yêu cầu hợp lệ; khoảng trễ theo phương thức; cách chọn cũ nhất/chỉ định. Chưa tự thêm enum hoàn tiền thất bại vào schema. |

Không gõ số tiền thanh toán/hoàn tiền ngẫu nhiên: số tiền phải dựa vào nghĩa vụ giao dịch, sẽ chốt chi tiết sau. Không gọi API thanh toán, chuyển khoản hoặc gửi OTP thật.

**COD:** kết quả thu hộ gắn với giao nhận, sẽ nhận từ hệ thống Kho vận, không đưa vào PAY-01 để sinh thành công trước khi giao hàng.

PAY-02 gồm hoàn do hủy đơn đã trả tiền, hủy dòng đã trả tiền và trả hàng đủ điều kiện. Có chấp thuận trả hàng chưa có nghĩa đã đủ điều kiện hoàn tiền nếu còn chờ nhận hàng; không bỏ qua bước phụ thuộc đó.

### 3.6. Tiến trình tự động của hệ thống

| Mã | Hành động | Một lần được tính là | Ô cấu hình riêng |
|---|---|---|---|
| SYS-01 | Hủy đơn quá hạn thanh toán | Một đơn quá hạn bị xử lý hủy | Thời hạn theo phương thức; thời điểm/quãng chạy kiểm tra; phạm vi phương thức. |
| SYS-02 | Hủy đơn shop quá hạn xác nhận | Một đơn quá hạn bị xử lý hủy | Ngưỡng chờ xác nhận; phạm vi shop; lịch kiểm tra. |
| SYS-03 | Xét hạng thành viên | Một khách được xét, có thể giữ nguyên hạng | Lịch xét; cửa sổ quan sát; chính sách chi tiêu/đơn đủ điều kiện; tập khách. Nếu thiếu chính sách/dữ liệu thì chưa bật. |
| SYS-04 | Hoàn tất đơn hàng số | Một đơn hàng số đủ điều kiện được hoàn tất | Phạm vi sản phẩm đã phân loại là hàng số; khoảng trễ sau thanh toán thành công. Không áp dụng cho hàng vật lý. |

Các tiến trình bảo đảm vòng đời không được bỏ qua nghĩa vụ chỉ để vừa quota. Cách dùng số lần đối với loại này được phân biệt ở mục 5.

Không thêm hành động “hoàn tất đơn vật lý ngẫu nhiên”: trạng thái hoàn tất phải do kết quả giao hàng của Kho vận. Cũng không thêm nút “tăng tổng tiền”, “tạo dòng thanh toán thành công” độc lập với hành vi thực tế.

## 4. Form cấu hình riêng cho hành động đặt hàng

GST-02 và CUS-05 dùng chung cấu trúc form nhưng có số lần riêng. Không thêm một ô tổng “số đơn” độc lập để vô tình sinh trùng với hai hành động này.

| Nhóm ô | Nội dung người dùng cấu hình |
|---|---|
| Đơn vị sản lượng | Số **lần checkout** mỗi ngày; không gọi nhầm là số đơn vì một checkout nhiều shop có thể tạo nhiều đơn. Preview hiển thị số đơn dự kiến riêng. |
| Kênh | Phân bố Web/App/Livestream trên các kênh được phép. Tổng 100%. Khách vãng lai ban đầu chỉ Web. |
| Người mua | Phạm vi khách; với đăng nhập: tỷ lệ mua lần đầu/mua lại. Thiếu khách hợp lệ thì báo thiếu, không tự đăng ký để bù. |
| Sản phẩm | Phạm vi ngành/shop/sản phẩm; chọn đều hoặc theo độ phổ biến nguồn; chỉ sản phẩm hợp lệ tại lúc đặt. |
| Giỏ mua | Khoảng số sản phẩm khác nhau; khoảng số lượng mỗi sản phẩm; tỷ lệ checkout một shop/nhiều shop; số shop nếu nhiều shop. Không trộn hàng số và vật lý trong một đơn. |
| Địa chỉ | Mặc định/địa chỉ khác; khách vãng lai dùng địa chỉ một lần; cấu hình địa phương hoặc phân bố. |
| Phương thức trả tiền | Tỷ trọng COD/Momo/ZaloPay/Credit Card/Bank Transfer, tổng 100% trong tập được phép; quy tắc không COD cho hàng số. Không chọn sẵn kết quả thành công ở đây. |
| Voucher | Tỷ lệ thử dùng voucher; loại shop/sàn/freeship; chọn từ ưu đãi còn hiệu lực của Marketing hoặc chỉ định mã. Không tự sinh voucher tại đây để đủ tỷ lệ. |
| Khung giờ | Phân bố lượt checkout theo giờ hoặc các khung giờ có trọng số. |

Ngày đặc biệt có thể ghi đè số lần và các tham số riêng người dùng muốn thay đổi, ví dụ tỷ trọng kênh, số sản phẩm hoặc sử dụng voucher. Thuộc tính không được ghi đè giữ cấu hình thường; UI cần hiển thị cấu hình cuối cùng của ngày đó.

Chưa cam kết chỉ tiêu GMV/AOV như các quota độc lập khi số checkout và giỏ đã cố định. Nếu bổ sung mục tiêu tiền sau này phải kiểm tra khả thi, không sửa giá thật hoặc tiền giao dịch chỉ để đạt mục tiêu.

## 5. Phân biệt tạo nhu cầu và xử lý hệ quả

### 5.1. Hai chế độ điều khiển xử lý

Không nên dùng một quota cứng giống nhau cho cả khách đặt hàng và việc bắt buộc hủy đơn quá hạn. UI cần phân biệt:

- **Phát sinh hành động:** số lần ngày thường/ngày đặc biệt là số yêu cầu muốn tạo. Ví dụ đăng ký, đặt hàng, yêu cầu trả hàng, đánh giá.
- **Xử lý yêu cầu đang chờ:** có hai chế độ chọn rõ trên form: `Theo số lần cấu hình` hoặc `Tự xử lý toàn bộ yêu cầu đến hạn`. Trong chế độ tự động, các ô số lần ngày thường/ngày đặc biệt không áp dụng và phải hiện “Theo đầu vào”, thay bằng cấu hình thời gian, kết quả và điều kiện.

Đề xuất PAY-01, PAY-02, ORD-01, SUP-01/SUP-02 hỗ trợ xử lý hàng đợi. SYS-01, SYS-02, SYS-04 mặc định theo toàn bộ nghĩa vụ đến hạn; nếu đặt giới hạn xử lý để thử tắc nghẽn phải cảnh báo backlog, không âm thầm bỏ qua. SYS-03 theo lịch xét; giới hạn số khách/lượt nếu cần.

Với SUP-01/SUP-02: nếu xử lý toàn bộ thì dùng một chính sách phân bố chấp thuận/từ chối chung, tổng 100%; không để hai bộ tự xử lý toàn bộ giành cùng yêu cầu. Nếu chạy số lượng riêng thì chúng chia sẻ hàng đợi và mỗi yêu cầu chỉ có một kết quả.

### 5.2. Quan hệ số lần cần nhìn rõ trên UI

| Quan hệ | Cách hiểu |
|---|---|
| 100 checkout nhiều shop | Có thể sinh hơn 100 đơn; chưa chắc 100 lần đều được tạo đơn thành công. |
| 100 yêu cầu đặt hàng | Không bảo đảm 100 thành công nếu thiếu hàng/shop khóa/thông tin sai. |
| 20 lần thử lại | Chỉ thực hiện nếu có đủ lần thất bại và đơn còn được phép trả; không tạo thất bại giả cho đủ số. |
| 10 chấp thuận trả hàng | Cần ít nhất 10 yêu cầu đủ điều kiện; có thể đến từ các ngày trước. |
| 10 đánh giá | Cần 10 dòng hàng đủ điều kiện và khách đăng ký; không cần 10 đơn mới trong ngày đó. |
| 5 kết quả hoàn tiền | Cần 5 nghĩa vụ hoàn đến hạn; không tạo trả hàng giả để đủ quota. |

Kết quả của một hành động có thể kéo sang ngày khác. Không ép đơn giao và hoàn tiền cùng ngày với checkout để đạt số ngày hiện tại.

## 6. Manual và giới hạn hiện tại

| Trường hợp | Form / trạng thái cần hiện |
|---|---|
| Muốn đặt đơn bằng khách/sản phẩm cụ thể | Bộ chọn ID khách, shop, sản phẩm và địa chỉ hợp lệ; không nhập SQL. |
| Muốn tên, địa chỉ, bình luận cụ thể | Ô nhập hoặc danh sách đích ngay trong từng hành động. |
| Thử kết quả thanh toán cụ thể | Chọn lần thử và Success/Failed tại PAY-01, gắn nhãn mô phỏng. |
| Muốn xét hạng theo chính sách riêng | Form ngưỡng và cửa sổ dữ liệu, hoặc chọn bộ chính sách đã lưu; chưa đủ chính sách thì khóa chạy. |
| Đăng nhập/đăng xuất, đổi mật khẩu, khóa tài khoản khách | Chưa có mô hình tài khoản/xác thực tương ứng; không đưa vào danh sách có thể chạy. |
| Nhân viên xác nhận seller xử lý đơn | ORD-01 cần metadata hành động; chưa có cột xác nhận riêng trong schema. Đây là việc thiết kế mô hình sau, không bắt người dùng cập nhật DB tay. |
| Theo dõi checkout nhiều shop | Schema chưa có `checkout_id`; kế hoạch cần giữ liên kết ở metadata, chưa tự thêm cột nghiệp vụ. |
| Địa chỉ đơn hàng cũ | Không sửa địa chỉ được tham chiếu; cần chốt cơ chế snapshot nếu muốn hỗ trợ sửa địa chỉ lưu hoặc đổi địa chỉ giao của đơn. |
| Yêu cầu đổi trả và hủy | Schema chưa lưu đầy đủ tác nhân/lý do hủy/lịch sử duyệt; chi tiết audit sẽ thiết kế sau. |
| Thiếu catalog, tồn kho, voucher, phiên truy cập hoặc kết quả giao hàng | Hiện rõ hệ thống phụ thuộc và dữ liệu thiếu. Không tự sinh thay phần của hệ thống khác hoặc yêu cầu người dùng sửa DB tay. |

Hầu hết hành động tự động được sau khi cấu hình. Manual là chọn cấu hình đặc biệt hoặc dữ liệu đích, không phải bấm làm từng giao dịch.

## 7. Preview và nguyên tắc kiểm soát

- Hiển thị theo ngày → nhóm → hành động, số cấu hình, số có thể thực hiện và lý do thiếu.
- Hành động xử lý tự động hiển thị số yêu cầu đến hạn dự kiến và giới hạn nếu có; không giả vờ biết trước chính xác tất cả phản hồi sẽ phát sinh.
- Khi chọn số lượng, đếm theo định nghĩa “một lần” ở bảng; số dòng ghi DB không phải số hành động.
- Hành động từ các ngày trước có thể được xử lý ngày đang chạy. Chạy lại không xử lý trùng giao dịch đã hoàn tất.
- Tỷ trọng trong cùng một lựa chọn phải tổng 100%; quota tuyệt đối không tự đổi thành tỷ lệ. Mọi lựa chọn phải thỏa điều kiện nghiệp vụ.
- Preview phải cảnh báo xung đột: cùng đơn dự định hủy và thanh toán, cùng yêu cầu vừa duyệt vừa từ chối, tỷ lệ mua lại nhưng chưa có khách mua trước.
- Thứ tự thời gian và kết quả hợp lệ quyết định hành động nào còn được chạy; số yêu cầu không bảo đảm mọi hành động đều thành công.

## 8. Nội dung cần chốt tiếp

1. Danh sách 6 nhóm và các hành động ở mục 3 có đúng phạm vi mong muốn không?
2. Có dùng hai chế độ xử lý ở mục 5 để không phải tự nhập số kết quả cho mọi thanh toán/đơn đến hạn không?
3. Các ngưỡng nghiệp vụ như thời hạn thanh toán, trả hàng, xác nhận và chính sách hạng sẽ có form cấu hình; chưa tự áp số trong bộ luật cũ.

Tài liệu này chỉ chốt cấu hình kịch bản. Cách dữ liệu liên kết và thay đổi trong các bảng sẽ được thiết kế sau khi danh sách hành động được thống nhất.
