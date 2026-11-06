# Rà soát ranh giới code và config — 06/11/2026

## 1. Điều chỉnh mục tiêu

Theo làm rõ mới của người dùng: code thực thi các rule, kiểm tra điều kiện và cung cấp cơ chế đọc cấu hình. Tập trường hợp, độ đa dạng, tỷ trọng, số lượng và lịch vận hành do config quyết định. Không thêm nhánh code cho từng địa phương, từng khách, từng hãng vận chuyển hay từng mức phí trong dữ liệu mẫu.

Tài liệu này điều chỉnh đề xuất nâng cấp trước đó: không mặc định triển khai kho gần nhất, bộ tỷ lệ thực tế hoặc lịch sale bằng thuật toán cố định. Những khả năng engine còn thiếu phải được bổ sung dưới dạng cơ chế có tham số, sau đó mới viết config sử dụng chúng. Đây là rà soát và đề xuất thiết kế, chưa phải thông báo đã triển khai.

149 sản phẩm và 9 seller là bộ nguồn test đang có, không phải quy mô mục tiêu hay giới hạn nghiệp vụ. Không chọn hạn mức hoặc thiết kế thuật toán dựa vào giả định catalog chỉ có 149 dòng.

## 2. Hai phần cấu hình phải có trách nhiệm rõ

### Thiết lập môi trường: có những ai, có thuộc tính gì?

Ngoài chính sách mô phỏng, phần này mô tả các nhóm thực thể đã xác định và các bộ thuộc tính để tạo/chọn nhiều thực thể: danh sách giá trị, bộ thuộc tính nhất quán, trọng số, khoảng giá trị, tỷ lệ không khai báo và quy mô quần thể. Không yêu cầu người dùng liệt kê tay từng khách hàng thật.

- Khách: các bộ tên, điện thoại, địa phương, thông tin tùy chọn; có thể thêm các nhóm hành vi/preference nếu engine hỗ trợ và xác định rõ cách dùng.
- Người bán: giữ ID và quan hệ sản phẩm từ nguồn; thuộc tính tổng hợp hoặc nhóm hồ sơ phải được phân biệt với thông tin Tiki thật. Một seller được dùng lại khi xử lý catalog, đơn và ưu đãi, không tạo ba seller khác nhau theo ba hệ thống.
- Nhân viên/quản trị viên: hồ sơ định danh, vai trò, phạm vi phụ trách. Không tự phát sinh thêm bảng tài khoản nghiệp vụ trong OLTP chỉ để có actor mock; có thể lưu registry và liên kết actor trong Control DB.
- Dịch vụ mô phỏng/tiến trình tự động: có định danh, vai trò và cấu hình năng lực/phạm vi phù hợp; không bịa thông tin người cho một tiến trình.
- Kho, carrier và các tài nguyên liên quan: có hồ sơ riêng và được liên kết vào phạm vi làm việc của actor. Kho là tài nguyên, không đồng nhất kho với nhân viên kho. Carrier có thể là tổ chức cung cấp dịch vụ; các hành động vận chuyển vẫn phải gắn đúng vai trò và phạm vi.

Sáu hệ thống chức năng không có nghĩa chỉ có sáu loại thực thể. Phải bám danh sách nhóm tác động đã chốt trong sáu tài liệu cấu hình. Một thực thể có thể xuất hiện ở nhiều hệ thống khi có vai trò tương ứng.

### Cấu hình kịch bản: ai thực hiện việc gì, khi nào và bao nhiêu?

Chọn quần thể/nhóm hồ sơ thực hiện, đối tượng đủ điều kiện, hành động, sản lượng theo ngày, trọng số biến thể, thời điểm/độ trễ và cách xử lý đầu vào đến hạn. Tham số vận hành và thuộc tính actor không được lặp lại thiếu nhất quán ở mọi hành động.

Ví dụ: thiết lập tạo các nhóm khách và kho; kịch bản chọn một nhóm khách để mua hàng. Rule giữ hàng, tách đơn theo seller và quyền dùng địa chỉ vẫn do engine kiểm tra, bất kể config yêu cầu gì.

## 3. Hiện trạng code đã đọc

| Thành phần | Đã có | Thiếu thực sự |
|---|---|---|
| `entities.py` | Danh sách họ/tên/đầu số, bộ địa phương, danh sách kho/carrier; sinh tên và địa chỉ ổn định theo seed | Schema hồ sơ chỉ chấp nhận 6 khóa cố định; chưa có hồ sơ đầy đủ cho seller, staff, dịch vụ; chưa có thuộc tính giới tính/DOB hay trọng số nhóm thực thể |
| `profiles.py` | Các bộ tham số hành động có trọng số, tái lập theo seed | Là biến thể tham số từng hành động, chưa phải quần thể actor có danh tính, thuộc tính và hành vi được dùng lại |
| `actions.json`, `service.py` | Danh mục hành động, trường được hỗ trợ, kiểm tra config, count/all, ngày đặc biệt, độ trễ ngày | Group hiện chủ yếu là nhãn; chưa có hợp đồng actor chung cho toàn bộ hành động. Một số mô tả còn ghi bản đầu không đúng khả năng v2 |
| `domain.py`, `purchase.py` | Các điều kiện hợp lệ, quyền sở hữu trong chuỗi mua, checkout liên kết phiên/giỏ, giữ hàng và hậu quả | Chưa có chọn actor theo nhóm hồ sơ chung. Một số rule/giá trị bị gắn vào tên cụ thể hoặc mặc định chọn ngẫu nhiên |
| `worker.py` | Snapshot, seed, checkpoint, thứ tự xử lý, bootstrap | Khung giờ gắn cứng với priority; bootstrap tồn dùng một lượng cho mọi SKU × mọi kho; kênh/phương thức thanh toán được khai báo cố định trong code |
| `selection.py`, `storage.py` | Có một số lọc SQL cho trạng thái và guest/registered | Nhiều lựa chọn vẫn đọc cả tập dữ liệu rồi lọc Python; bootstrap và linked checkout lặp qua nhiều bảng. Chưa thích hợp để chỉ tăng config lên quy mô lớn mà không đánh giá hiệu năng |
| Audit/UI | Đã có kiểm tra và số liệu hiện tại | Audit trộn lịch sử trước reset theo ID; UI có trạng thái job cũ; báo cáo chưa biểu diễn rõ độ bao phủ và nguyên nhân ít/trống |

Không tìm thấy giới hạn runtime bắt catalog phải có đúng 149 sản phẩm. Có các giới hạn kỹ thuật hiện tại: 10.000 yêu cầu/hành động/ngày, 100.000 yêu cầu tường minh/lượt, guard vòng xử lý tự động, kích thước danh sách hồ sơ. Đây là giới hạn triển khai/bảo vệ, phải được công bố và đánh giá theo năng lực; không tùy tiện bỏ hết hoặc tăng vô hạn.

## 4. Chỉ cần viết lại config, không cần thêm nhánh nghiệp vụ

| Vấn đề đã thấy | Hướng sửa config bằng khả năng hiện có |
|---|---|
| Chiến dịch APP nhưng phiên attribution ở Web | Đặt campaign đúng kênh, ngày hiệu lực và variants phiên phù hợp. Giữ các phiên không attribution hợp lý |
| Mọi đơn phí 20.000, mọi vận đơn chi phí 30.000 | Dùng variants có trọng số cho `shipping_fee` ở checkout và `amount` ở DSP-01; đây là nhiều mức giá, chưa phải công thức giá phụ thuộc tuyến |
| Lượng phiên/giỏ/checkout chưa cân đối | Viết lại count, special và tỷ trọng hành động. Số yêu cầu không đảm bảo số thành công; không để engine tự bù đơn |
| Một bộ tỷ trọng thanh toán/thiết bị/nguồn truy cập | Thay weights và bộ tham số hiện được hỗ trợ; không thêm tỷ lệ mặc định mới vào code |
| Ít review/return và yêu cầu quá sớm | Phân bố yêu cầu theo ngày đã có đầu vào đủ điều kiện; đa dạng rating/reason/value bằng variants |
| Chưa thử hủy, từ chối trả, hoàn hàng sau nhiều lần giao thất bại | Bật và điều phối các hành động đã có, quota và bộ xử lý all; lưu ý hành động chạy trước có thể dùng hết đầu vào |
| Chỉ một campaign, ba voucher, policy một hạng seller | Tăng/đổi các hành động tạo đối tượng hiện hỗ trợ; chuẩn bị policy theo hạng/danh mục/thời gian. Chưa bao gồm loại voucher engine chưa hỗ trợ |
| District rỗng, tên/địa chỉ còn nghèo | Viết lại bộ địa phương/tên/đầu số đã được hỗ trợ; không bịa địa giới thật |
| Kho/carrier ít, chưa dùng hết | Số và thông tin kho/carrier đổi được trong hồ sơ cho bootstrap mới. Chỉ định kho/carrier cố định có sẵn trong params; việc weighted carrier theo phạm vi ở chế độ all còn bị giới hạn, xem mục 5 |
| Payout trống/refund chưa hoàn tất | Chọn khoảng chạy đủ dài và giữ các xử lý đầu vào đến hạn; không cần code tạo payout/refund sớm |

Nhiều mức phí ngẫu nhiên khác với phí được tính theo tuyến. Nhiều lần thêm một sản phẩm với quantity=2 cũng khác với giỏ có hai SKU. Config phải mô tả đúng điều gì engine đang thực hiện.

## 5. Những chỗ thực sự cần sửa code

### 5.1. Mở rộng hợp đồng hồ sơ thực thể và cơ chế sinh/chọn actor

Đây là phần thiếu chính so với yêu cầu mới, không thể chỉ thêm khóa vào JSON hiện tại. Cần:

1. Schema hồ sơ có phiên bản, kiểu thuộc tính được hỗ trợ, danh sách/bộ giá trị, trọng số, khoảng và quy tắc thiếu dữ liệu. Giá trị mẫu và phân bố nằm trong config.
2. Sinh quần thể và định danh ổn định; liên kết actor với ID OLTP khi có, lưu hồ sơ/phân công phục vụ mô phỏng ở Control DB khi phù hợp. Tránh trùng khách/actor hoặc làm thay ID Tiki.
3. Chọn actor theo nhóm/thuộc tính/phạm vi được cấu hình, rồi mới chọn đối tượng hợp lệ; ghi actor và hồ sơ đã dùng để truy vết.
4. Kiểm tra quyền và quan hệ: seller chỉ sửa hàng của mình, khách chỉ dùng tài nguyên thuộc quyền mình, nhân viên theo phạm vi phụ trách. Config chọn phạm vi nhưng không được vượt rule.
5. Các thuộc tính đã sinh phải có nơi được dùng/mapping rõ. Không thêm hàng chục trường chỉ để tồn tại trong file mà engine bỏ qua.

Gender/DOB/seller.phone là ví dụ cần bộ sinh tổng quát này; không viết riêng một hàm điền cố định cho từng mẫu. DOB và các bộ địa phương cần kiểm tra tính nhất quán theo mốc mô phỏng. Giá vốn không phải thuộc tính của actor: nếu đưa vào phạm vi phải là cấu hình dữ liệu vận hành riêng, không trộn vào hồ sơ người tác động.

### 5.2. Tách rule và tên/giá trị mẫu đang gắn trong code

- Giữ phân biệt thanh toán thu khi giao và trả trước bằng semantics/mode hợp lệ; tránh phụ thuộc duy nhất tên chuỗi `COD`. Kênh/phương thức được tham chiếu bằng định danh ổn định và cấu hình được hỗ trợ. Thêm nhà cung cấp cùng mode không cần viết nhánh nghiệp vụ mới; thêm mode có hành vi mới thì vẫn cần rule code.
- Tách hồ sơ seller tổng hợp khỏi đoạn sync đang gán đồng loạt tỉnh và hạng. Sync vẫn chỉ append sản phẩm/category/seller mới, không tự sửa seller đã có. Phải ghi rõ khi nào hồ sơ mô phỏng được áp và khi nào chỉ tạo liên kết/control metadata.
- Mở tham số action còn thiếu khi nghiệp vụ đã chốt, như điện thoại ở SEL-02. Không nhận khóa config rồi im lặng bỏ qua.

### 5.3. Bổ sung cơ chế lịch có tham số

Khung giờ hiện cố định theo priority gây phiên dài khoảng 12 giờ. Cần cơ chế đọc khung giờ/phân bố thời lượng/độ trễ từ config và giữ quan hệ thời gian giữa các sự kiện. Cùng actor/session/journey phải liên kết đúng, không chọn lại một người khác ngẫu nhiên ở mỗi bước khi đang mô phỏng một hành trình.

Code kiểm tra nhân quả và hạn nghiệp vụ; config chọn sáng/tối, thời lượng, ngày sale, tỷ trọng từng nhóm. Không viết code riêng cho 8/8, 10/10, TP.HCM hoặc một nhóm khách cụ thể. Cần đối chiếu cả số lần theo ngày và việc xử lý sự kiện chuyển ngày với checkpoint; chưa coi thêm ô nhập phút là đã giải quyết toàn bộ.

### 5.4. Chọn đối tượng và phân giải tham số có điều kiện

Để config có thể diễn đạt hàng ở kho nào, carrier phục vụ phạm vi nào và mức phí áp dụng cho điều kiện nào, cần bộ lọc/lookup/chiến lược hữu hạn được engine hỗ trợ. Config chứa các bộ điều kiện, tham chiếu nhóm và trọng số; code kiểm tra định dạng, độ ưu tiên, thiếu mapping, đủ tồn, tính tương thích và thực thi.

Không mặc định mọi sàn dùng kho gần nhất. Kho gần/chi phí thấp/chỉ định/weighted là những lựa chọn có thể cung cấp; config quyết định chính sách. Không cho config chạy Python/SQL tùy ý.

Lưu ý hạn chế hiện có: chế độ all chỉ cho variants thay các tham số kết quả trong một allowlist; không cho trộn `carrier`/`warehouse` trong variants vì có thể hết một nhóm đầu vào rồi dừng sớm. Nếu cần carrier có trọng số trong chế độ này, sửa cơ chế chọn/phân giải tham số sau khi lấy đầu vào hợp lệ, không chỉ bỏ validation.

### 5.5. Bootstrap/selector theo quy mô thực tế

- Thay một số tồn cho mọi cặp SKU–kho bằng khả năng đọc cấu hình phạm vi/phân bố tồn. Các lượng và phạm vi nằm trong config; mã chỉ áp rule và ghi ledger.
- Hỗ trợ chọn nhóm theo thuộc tính/catalog hiện có, không yêu cầu viết tay từng ID trong một catalog lớn hoặc liệt kê đủ tích SKU × kho trong file.
- Đẩy lọc đủ điều kiện vào SQL, xử lý theo lô, tránh nạp và quét cả bảng cho mỗi hành động. Giữ transaction, tính tái lập và cơ chế idempotent khi tối ưu.
- Đo chi phí snapshot tồn/ngày theo độ phủ thực sự; catalog lớn không có nghĩa mọi SKU phải hiện ở mọi kho. Các guard kỹ thuật phải được đánh giá và thông báo rõ, không sửa theo đúng số liệu 149.

### 5.6. Sửa lỗi công cụ và truy vết đã xác nhận

- Mã tham chiếu của WH-01/WH-02; định danh actor và config snapshot đi cùng nhật ký hành động.
- Audit phân biệt thế hệ dữ liệu sau reset, không ghép chỉ theo ID tái sử dụng.
- UI làm mới đồng bộ job/checkpoint/counters; hiển thị tên nhóm/hồ sơ cùng cấu hình đã phân giải.
- Preview cảnh báo tham chiếu thiếu, campaign khác kênh, đầu vào chưa có, độ phủ tồn thấp và tính năng chưa hỗ trợ; cảnh báo không được âm thầm đổi config để ép thành công.
- Báo cáo phân biệt: sai rule, config không nhất quán, chưa đến hạn, chưa bao phủ, nguồn thật thiếu. Không coi bảng trống/NULL tự động là lỗi.

## 6. Không tự đưa thêm nghiệp vụ vào lần sửa

Không vì muốn lấp cột mà tự thêm giá vốn, voucher phần trăm, voucher riêng SKU hay mô hình tuyến phức tạp khi chưa chốt chúng thuộc phạm vi. Nếu đưa một nghiệp vụ mới vào, phải định nghĩa semantics và rule trước; config chỉ tạo các biến thể trong semantics được hỗ trợ. Một engine cấu hình được không có nghĩa JSON có thể định nghĩa tùy ý transaction hoặc vô hiệu hóa rule.

Các rule giữ nguyên: ID Tiki và append-only sync, quyền sở hữu, khóa quan hệ, tính nguyên tử checkout/giữ hàng, không thu/hoàn vượt nghĩa vụ, không đối soát trước điều kiện, ngày chạy liên tục, snapshot job không bị đổi bởi sửa config. Điều kiện rẽ nhánh để kiểm tra các rule này vẫn cần có trong code; điều cần tránh là nhánh cho từng tình huống dữ liệu mẫu.

## 7. Trình tự đề xuất sau rà soát

1. Chốt hợp đồng hai loại config và mapping nhóm thực thể–thuộc tính–quyền–hành động–nơi lưu. Đánh dấu thuộc tính đã hỗ trợ, cần cơ chế mới, hoặc ngoài phạm vi.
2. Sửa các cơ chế còn thiếu trong mục 5, giữ phần kịch bản đang hoạt động; có tương thích/migration config cũ rõ ràng, không reset DB người dùng ngầm.
3. Sau khi hợp đồng ổn định, viết lại hai loại config mẫu/mới nhất. Trọng số, danh sách, số lượng, lịch và mapping cụ thể nằm trong bốn file mẫu đã chốt, không chuyển các số đó trở lại code.
4. Kiểm thử cùng engine với ít nhất hai bộ config khác rõ về actor, phân bố và lịch; thay config không cần đổi Python. Kiểm thử thêm catalog lớn hơn bộ test, gồm ID nguồn không được liệt kê trước trong config.
5. Nghiệm thu theo rule, khả năng truy vết actor và tính được điều khiển bằng config; có cả nhánh đúng, từ chối và chưa đến hạn. Không lấy số dòng/cột được lấp đầy làm tiêu chí duy nhất.

Không sửa engine hoặc thay các config đang chạy trong lượt rà soát này.
