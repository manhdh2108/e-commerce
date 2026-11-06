# Mock Studio v2 — nâng cấp và chạy cấu hình mới

Bản này triển khai sửa lỗi đã xác minh, profile tham số, dữ liệu nền có cấu hình và các luồng mua–kho–giao–trả–hoàn–đối soát. Python tiếp tục theo OOP trong `scripts/mock_platform/`.

## 1. Bạn nhận được gì?

| Phần | Hành vi mới |
|---|---|
| Cấu hình hành động | Thêm nhiều nhóm tham số có tên/trọng số; xem và sửa bằng form, import/export JSON v2. Config scalar và định dạng v1 vẫn được đọc. |
| Thiết lập | Sửa bộ họ/tên/đầu số, địa phương theo bộ, danh sách kho và carrier; sửa chính sách mô phỏng. |
| Checkout | Chọn đặt trực tiếp hoặc nhận yêu cầu từ phiên/giỏ; nhiều dòng, tách theo shop, giữ tồn nguyên tử. |
| Hành trình | Giữ đúng scope guest/registered, nối cart → checkout → line → order, ghi từ khóa tìm kiếm và sự kiện mua. |
| Thời gian | Giãn thời điểm trong từng giai đoạn; độ trễ tối thiểu theo ngày, tiếp tục xử lý đầu vào còn chờ ở những ngày sau. |
| Ưu đãi | Ledger lượt dùng; phân bổ giảm giá xuống dòng hàng; phân biệt bên tài trợ; hoàn lượt khi hủy toàn bộ đơn. |
| Sau bán | Yêu cầu/xét/nhận hàng trả, hoàn tiền riêng; hủy đơn đã trả tiền trước lấy hàng; giao lại hoặc nhận hàng giao thất bại về kho. |
| Tài chính | Snapshot hoa hồng trên dòng; đối soát sau thời gian giữ tiền và khi hết nghĩa vụ chờ; ledger dòng, duyệt và chi. |
| Kiểm tra | FK, chủ sở hữu, tiền, tồn, thời gian, actor Analytics, giới hạn trả/hoàn và đối soát; CHECK/UNIQUE bổ sung trong PostgreSQL. |
| An toàn chạy lại | Snapshot config/hồ sơ/policy/seed, fingerprint code, ảnh trước runtime và commit sequence. Không dựng lại snapshot legacy bằng cấu hình hiện tại. |

Cấu hình mẫu mới: [upgraded-linked-2026.json](../examples/scenarios/upgraded-linked-2026.json). Đây là giả định thử nghiệm có lịch 2026, không phải số đo hoạt động Tiki. Quota đặt hàng là **số yêu cầu checkout**; một checkout nhiều shop có thể tạo nhiều order. Quota không bảo đảm số giao dịch thành công.

## 2. Schema thay đổi thế nào?

Giữ nguyên 27 bảng cũ và ID Tiki; thêm **6 bảng**, tổng cộng **33 bảng nghiệp vụ**:

| Bảng mới | Mục đích |
|---|---|
| `checkouts` | Nhóm một yêu cầu checkout, phiên/khách và thời điểm. |
| `checkout_lines` | Nối mục giỏ đã tiêu thụ với dòng đơn; UNIQUE ngăn tiêu thụ hai lần. |
| `promotion_usages` | Lượt ưu đãi đã dùng/được hoàn, số tiền và khách/đơn liên quan. |
| `refunds` | Nghĩa vụ và kết quả hoàn; giữ nguyên lịch sử tiền đã thu ở `payments`. |
| `delivery_attempts` | Số lần, kết quả và thời điểm giao. |
| `seller_payout_items` | Dòng hàng thuộc kỳ đối soát, cơ sở tiền/hoàn/hoa hồng/thực nhận. |

Các cột bổ sung: `orders.checkout_id`; snapshot hoa hồng/category/tier trên `order_items`; `page_events.search_keyword`; `order_item_promotions.funded_by`; mốc transit/returned trên `shipments`; kho và mốc approved/received và lý do xét trên `returns`; lý do hủy trên `orders`.

Migration chỉ thêm cấu trúc và ràng buộc sau preflight. Không đổi giá/ID nguồn, không tạo đơn, không điền ngược snapshot hoa hồng cho đơn cũ. Dòng cũ không đủ snapshot không được tự tính đối soát bằng policy hiện tại.

## 3. Nâng cấp DB đang có

Chạy tại thư mục gốc repository, dùng cùng biến `MOCK_CONTROL_URL` và `MOCK_BUSINESS_URL` như ứng dụng:

```bash
.venv/bin/python -m scripts.mock_platform.infrastructure.migrations
```

Lệnh mặc định chỉ xem trước: bảng/cột cần thêm, CHECK/UNIQUE và dữ liệu xung đột. Nó không apply migration. Khi preflight đạt:

1. Hoàn tất job bằng engine cũ; dừng `start_mock.sh` bằng Ctrl+C. Không đổi code thực thi giữa một job dang dở.
2. Giữ bản sao DB nếu muốn có đường quay về cấu trúc cũ. Migration hiện là bổ sung một chiều, chưa có lệnh downgrade.
3. Apply rõ ràng rồi khởi động:

```bash
.venv/bin/python -m scripts.mock_platform.infrastructure.migrations --apply
./scripts/start_mock.sh
```

Migration dùng khóa ghi chung, chặn khi còn job chờ/chạy/tạm dừng/lỗi/dang dở. PostgreSQL áp DDL trong transaction; preflight phát hiện xung đột thì dừng, không sửa dữ liệu để ép qua constraint. Mở web không tự migrate. Migration DB cũ được hỗ trợ trên PostgreSQL; SQLite dùng DB test mới.

Kế hoạch cũ phải preview lại. Job legacy thiếu snapshot/fingerprint không được resume ngầm bằng code mới. Nếu DB cũ còn job dang dở, hoàn tất bằng phiên bản cũ hoặc dùng cặp DB test khác.

**Dữ liệu lỗi lịch sử vẫn là lịch sử:** ví dụ 53 sự kiện sai nhóm actor đã phát hiện trước nâng cấp không được tự xóa/đổi nhãn. Nút kiểm tra toàn DB vẫn báo chúng. Kiểm tra actor cuối ngày của job mới được phân biệt theo job, còn tiền/tồn/quan hệ được đối chiếu trên toàn DB.

## 4. Muốn kiểm chứng từ đầu mà giữ DB cũ

Có thể tạo hai database mới trên cùng PostgreSQL, ví dụ `mock_control_v2` và `mock_oltp_v2` (qua DBeaver hoặc công cụ PostgreSQL), rồi đặt hai URL kết nối tương ứng trước khi khởi động.

Đây là tên gợi ý, không bị gắn cố định trong code. Dùng cùng host/port/user/password của PostgreSQL mà bạn đã cấu hình. Control và OLTP bắt buộc là hai database khác nhau.

Trên DB mới, vào Thiết lập → Chuẩn bị môi trường để tạo cấu trúc mới; không cần migrate một DB trống. Sau đó:

1. **Đồng bộ Tiki:** xem trước rồi thực hiện. Crawler vẫn riêng; nút cào không tự đồng bộ.
2. **Thiết lập:** chỉnh hồ sơ địa phương, kho/carrier, chính sách; lưu trước khi tạo dữ liệu nền.
3. **Dữ liệu nền:** chọn số khách/tồn. Tồn là lượng **mỗi SKU tại mỗi kho**, không phải tổng chia đều. Chọn lượng phù hợp số checkout dự kiến.
4. **Cấu hình kịch bản → Nhập/Xuất:** tải mẫu mới, chọn file, kiểm tra, lưu. Import không chạy mock hoặc thay dữ liệu nền.
5. **Lập kế hoạch:** chọn đúng ngày chạy tiếp. Nên chạy ít ngày trước rồi mở rộng; để thấy trả/hoàn và đối soát, chạy cả những ngày sau giao hàng/cửa sổ giữ tiền.
6. **Theo dõi:** xem nhóm tham số đã chọn và các nhóm nghiệp vụ đang chờ. `COMPLETE` nghĩa khoảng ngày đã xử lý xong, không có nghĩa mọi đơn đã giao và mọi nghĩa vụ đã hết.
7. **Lịch sử & Dữ liệu:** kiểm tra và xem các bảng; hoặc mở DBeaver.

Không chạy reset chỉ vì code vừa nâng cấp. Nút xóa toàn bộ vẫn cần preview/xác nhận và sẽ xóa cả catalog cùng 33 bảng nghiệp vụ; muốn chạy lại trên môi trường đó phải đồng bộ lại trước.

## 5. Cấu hình mới trên UI

### Nhập file để điền chính sách và hồ sơ

Trong **Thiết lập → Nhập thiết lập bằng JSON**, chọn [bộ thiết lập đa dạng](../examples/settings/diverse-ecommerce.json) hoặc [chỉ chính sách](../examples/settings/policy-only.json). Bấm **Kiểm tra & xem trước → Điền vào biểu mẫu**, xem/chỉnh các ô rồi bấm **Lưu chính sách / Lưu hồ sơ** tương ứng. Không tự tạo dữ liệu nền hoặc sửa OLTP. Xem [hướng dẫn file thiết lập](../examples/settings/README.md).

Ví dụ đã tách thành `examples/scenarios/` (hành động/lịch) và `examples/settings/` (chính sách/hồ sơ), không nhập lẫn hai loại.

### Nhóm tham số theo trọng số

Trong một hành động, mở **Phân bố nhiều nhóm tham số trong ngày** → Thêm nhóm. Mỗi nhóm có tên, trọng số và bộ tham số tương thích.

Ví dụ 7 phần Mobile/Organic và 3 phần Desktop/Email là xác suất 70%/30%, không cam kết chính xác 7 và 3 lượt khi chỉ chạy 10 lần. Muốn chỉnh từng ngày, số ở ngày đặc biệt vẫn chỉ **thay quota**, không thay profile và không nhân mọi hành động.

Không có nhóm: dùng bộ tham số cố định phía trên. Chế độ toàn bộ đầu vào chỉ cho trộn tham số kết quả; bộ lọc đối tượng giữ cố định để không kết thúc sớm khi một nhóm hết đầu vào. Trong chế độ linked, quantity/sản phẩm lấy từ giỏ, channel lấy từ phiên; các trường direct không ghi đè giỏ/phiên. Method, phí giao và lựa chọn ưu đãi vẫn áp tại checkout.

Profile đi cùng snapshot kế hoạch/job. Sửa config đã lưu giữ ID cấu hình và tăng revision; job đã xếp giữ bản cũ. Sửa policy/hồ sơ ở Thiết lập áp cho kế hoạch mới; kế hoạch đã preview giữ snapshot của nó.

### Độ trễ

Các handler hệ quả có ô số ngày tối thiểu từ bước trước, ví dụ tạo vận đơn, giao/nhận trả, hoàn tiền hoặc đánh giá. Chưa đến hạn thì không xử lý; nếu chọn `Tự xử lý đầu vào đủ điều kiện`, worker xử lý phần đến hạn và để phần còn lại cho những ngày sau.

Độ trễ và chính sách gắn với đơn lúc tạo. Đổi config hôm sau không âm thầm đổi lịch/nghĩa vụ của đơn cũ. Nếu tắt handler thì nghĩa vụ có thể còn chờ; bật lại với chế độ xử lý hợp lệ để tiếp tục.

Bản này dùng giai đoạn theo giờ và độ trễ theo ngày, chưa phải bộ mô phỏng sự kiện với phân bố SLA theo phút/giờ hay lịch làm việc/lễ của từng carrier.

### Hồ sơ thực thể

Tên, đầu số, địa phương đều là dữ liệu tổng hợp. Province/city/ward/district/street được chọn theo một bộ, tránh ghép địa chỉ mâu thuẫn. District có thể NULL có chủ đích. Bộ mẫu không tuyên bố là địa giới thật hiện hành.

Khách đã có địa chỉ mặc định được tái dùng khi checkout; địa chỉ đầu tiên được đặt mặc định. Đổi mặc định không sửa nội dung địa chỉ trên đơn cũ. Guest dùng địa chỉ với `customer_id=NULL`.

Kho và carrier trong hồ sơ được tạo lúc bootstrap. Sửa danh sách sau bootstrap **chưa tự bổ sung/cập nhật thực thể trong OLTP**. Bản này chưa có form nhập thêm master sau bootstrap hoặc routing theo vùng/COD/SLA từng hãng. Handler chọn kho đủ tồn và carrier đã có; có thể chỉ định ID để kiểm thử.

## 6. Bộ chính sách thử nghiệm được chọn

| Quy tắc | Hành vi / khả năng chỉnh |
|---|---|
| Trả hàng | Mặc định yêu cầu trong 7 ngày sau hoàn tất và đã thu đủ. Có thể đổi số ngày ở Thiết lập cho kế hoạch/đơn mới. |
| Nhận hàng trả | Duyệt trước, nhận thực tế rồi mới tăng tồn và tạo nghĩa vụ hoàn. Mẫu cấu hình đặt độ trễ nhận 2 ngày. |
| Hoàn tiền | Hoàn tiền hàng sau giảm giá theo số lượng trả; phần làm tròn còn lại ở lượt trả cuối. Không hoàn phí giao cho trả hàng tự nguyện. Mẫu trễ xử lý hoàn 1 ngày. |
| Hủy trước lấy hàng | Hủy toàn bộ, giải phóng giữ, hoàn toàn bộ thực thu nếu có, hoàn lượt voucher. Không hủy phần đã lấy hàng bằng handler này. |
| Giao thất bại | Không nhập lại tồn ngay. Có giao lại hoặc bước nhận hàng trả về; mẫu chỉ nhận về khi đã hết lượt giao. Mặc định tối đa 3 lần giao, có thể chỉnh. |
| Hàng giao thất bại về kho | Nhập lại đúng kho–SKU, hủy đơn, hoàn toàn bộ thực thu nếu có. Không tự thu COD. |
| Voucher | Tối đa một voucher hàng (shop **hoặc** sàn) cộng một voucher phí giao. Chỉ Fixed Amount, tự chọn mức hợp lệ tốt nhất hoặc ID cụ thể. |
| Giới hạn theo khách | Bản đầu yêu cầu tài khoản khi áp voucher; không giả nhận diện bền vững cho direct guest. |
| Hoàn lượt ưu đãi | Hoàn khi hủy toàn bộ đơn; trả hàng sau giao không hoàn lượt. |
| Bên tài trợ | Seller Voucher do seller chịu; Platform Voucher do sàn chịu. Snapshot `funded_by` giữ cơ sở đối soát, không trừ nhầm trợ giá sàn khỏi quyền nhận của seller. |
| Hoa hồng | Chốt rate/category/tier ở checkout. Cơ sở là tiền hàng seller được hưởng sau giảm giá seller và sau hàng trả, không gồm phí giao. Thiếu rate thì chờ/không lập đối soát cho dòng đó, không tự lấy 0%. |
| Đối soát | Mặc định giữ ít nhất 8 ngày sau hoàn tất, dài hơn cửa sổ trả; đã thu đủ và không còn trả/hoàn chưa kết thúc. Có thể chỉnh số ngày với kiểm tra quan hệ. |
| Chi seller | Mỗi dòng vào một ledger đối soát, sau đó duyệt và chi; không tính lại theo giá/tier/category hiện tại. |

Đây là các quy tắc mô phỏng được triển khai, không phải suy đoán chính sách thật của một sàn. Các lựa chọn mang tính cấu trúc như cách cộng voucher/phí hoàn chưa có mọi biến thể trên form; không nhập thêm khóa JSON tùy ý để thay đổi chúng.

Ví dụ đối soát: hàng 300.000đ, voucher sàn 30.000đ, khách trả tiền hàng 270.000đ; seller vẫn có cơ sở tiền hàng 300.000đ trước hoa hồng. Nếu trả 1/3 hàng thì khách nhận lại 90.000đ, cơ sở hàng còn lại của seller 200.000đ; hoa hồng 5% là 10.000đ, payout 190.000đ. Phí giao được xử lý ngoài phần tiền hàng seller này.

## 7. Kiểm tra nhanh bằng SQL

Các truy vấn chỉ đọc, chạy trên Business DB:

```sql
-- Một checkout đã tách thành những đơn nào?
SELECT c.checkout_code, o.order_code, o.seller_id, o.session_id,
       o.total_gross_amount, o.total_discount_amount, o.final_amount
FROM checkouts c JOIN orders o ON o.checkout_id = c.id
ORDER BY c.id, o.id;

-- Từ mục giỏ đến dòng đơn.
SELECT cl.checkout_id, cl.cart_item_id, cl.order_item_id, oi.order_id
FROM checkout_lines cl JOIN order_items oi ON oi.id = cl.order_item_id;

-- Khoản đã thu và khoản hoàn là hai lịch sử riêng.
SELECT order_id, payment_status, paid_amount FROM payments ORDER BY id;
SELECT order_id, return_id, amount, refund_status FROM refunds ORDER BY id;

-- Bên tài trợ giảm giá và các dòng đối soát.
SELECT order_item_id, promotion_id, applied_discount_amount, funded_by
FROM order_item_promotions ORDER BY id;
SELECT * FROM seller_payout_items ORDER BY id;
```

## 8. Phạm vi còn giới hạn

- Không phải toàn bộ hành động trong tài liệu đề xuất đều đã mở. Các thao tác chưa có đường xử lý đầy đủ như hủy một phần trước giao, sản phẩm số, tự động bổ sung hàng và điều chỉnh tài chính sau kỳ trả vẫn khóa.
- Chưa có phần trăm voucher, cộng nhiều voucher hàng, hoàn phí giao tùy lý do hoặc luồng tranh chấp.
- Chưa có tích hợp cổng tiền thật, ngân hàng, carrier thật; đây là dữ liệu tổng hợp.
- Không tự điền DOB/gender/giá vốn hay thuộc tính nguồn chưa có chỉ để hết NULL.
- Chưa có routing địa lý, giới hạn năng lực kho/đơn vị vận chuyển và biểu cước theo tuyến. Nhiều carrier ở đây chưa đồng nghĩa mô phỏng đầy đủ mạng vận tải.
- Không hứa tốc độ cả năm ở mọi máy; vẫn có giới hạn 100.000 yêu cầu explicit/lượt, 10.000/action/ngày, tối đa 367 ngày và ngưỡng bảo vệ auto. Bài thử nhỏ kiểm chứng logic không thay thế benchmark tải lớn.
- Dữ liệu lỗi cũ không tự biến thành dữ liệu đúng; đối chiếu audit lịch sử với kết quả job mới.

Xem [kế hoạch gốc](../plans/MOCK_ENGINE_UPGRADE_PLAN.md) để phân biệt phần đã giao trong bản v2 và những hướng mở rộng tiếp theo.

## 9. Kết quả chuyển môi trường hiện tại

Đã apply migration trên DB đang dùng sau khi xác nhận không có job dang dở. [Bằng chứng checksum](../reviews/engine-v2-migration-result.json) xác nhận toàn bộ giá trị ở các cột cũ của 27 bảng được giữ nguyên; 6 bảng mới được thêm mà không tạo lượt mock. Cấu hình mẫu mới đã được lưu thêm trong Control DB với tên “Vận hành liên kết 2026 · profile & nghiệp vụ qua ngày”. Các cấu hình cũ được giữ nguyên.
