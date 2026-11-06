# Engine dùng cấu hình thực thể và kịch bản

Cập nhật 06/11/2026. Code thực thi rule và các cơ chế có tham số. Danh sách thực thể, thuộc tính, phân bố và lịch vận hành nằm trong config. Không suy rằng thêm một thuộc tính tên `shift` hay `segment` sẽ tự tạo hành vi: nó là dữ liệu mô tả, chỉ ảnh hưởng lựa chọn/kết quả khi được khai báo trong phạm vi hoặc lookup tương ứng.

Sau rà soát, đã bổ sung clock nhân quả, pattern thuộc tính, sampling/availability, lịch theo trọng số, preferences và cycle/phase. Hai file đầy đủ đã được viết lại; xem [hướng dẫn vận hành hiện hành](REALISTIC_OPERATIONS_2026.md) cho các phần bổ sung và cách import.

## 1. Hai loại file

Vẫn chỉ giữ bốn file mẫu trong [examples](../examples/README.md):

| Loại | Mẫu cơ bản | Bản đầy đủ mới nhất |
|---|---|---|
| Kịch bản | `scenarios/first-run-cod.json` | `scenarios/upgraded-linked-2026.json` |
| Thiết lập | `settings/policy-only.json` | `settings/diverse-ecommerce.json` |

Thiết lập gồm `business_policy` và `entity_profile`. Kịch bản gồm các hành động với `actor_pool`, quota, `selection`, `schedule`, `variants`, `parameter_rules`.

## 2. Quy trình sử dụng

1. Khởi động PostgreSQL và web theo hướng dẫn chạy lần đầu.
2. **Thiết lập môi trường → Nhập thiết lập bằng JSON:** chọn bản đầy đủ, kiểm tra, điền form; lưu **cả chính sách và hồ sơ** bằng hai nút tương ứng. Bảng “Các nhóm tác động trong hồ sơ” cho biết loại, quy mô, vai trò và thuộc tính.
3. Với môi trường mới, lưu hồ sơ **trước khi đồng bộ lần đầu** nếu muốn hồ sơ người bán tổng hợp áp dụng cho seller mới. Đồng bộ vẫn append-only, không sửa seller đã nhập.
4. Đồng bộ SQLite → OLTP; tạo dữ liệu nền. Số khách nền là số khách ban đầu. Nếu hồ sơ có `inventory`, các quy tắc đó **thay thế** ô tồn chung; UI ghi rõ điều này.
5. **Cấu hình kịch bản → Nhập JSON:** chọn bản kịch bản đầy đủ. Có thể xem/sửa nhóm người thực hiện, phạm vi, giờ và tham số theo điều kiện trên từng hành động. Một số cấu hình nâng cao vẫn dùng JSON, có phần tóm tắt đọc được trên UI.
6. Xem trước kế hoạch mới; đọc cảnh báo đầu vào/campaign/quần thể. Bắt đầu từ ngày kế tiếp của checkpoint, không bỏ ngày.
7. Theo dõi lượt chạy: có actor đã thực hiện và tổng hợp DONE/REJECTED/EXHAUSTED theo hành động, ngoài 100 kết quả gần nhất.

Import/fill/lưu config không sinh dữ liệu nghiệp vụ. Config mới không tự bổ sung DOB/phone vào các bản ghi cũ. Không reset DB người dùng khi cập nhật code. Plan cũ đã preview cần tạo lại vì fingerprint engine thay đổi; job/lịch sử đã hoàn tất được giữ nguyên.

## 3. Hồ sơ thực thể

Các khóa cũ `surnames`, `given_names`, `phone_prefixes`, `locations`, `warehouses`, `carriers` vẫn dùng được. Thêm các khóa tùy chọn:

| Khóa | Ý nghĩa |
|---|---|
| `customer_attributes` | Bộ sinh các cột khách được hỗ trợ: gender, date_of_birth, membership_tier |
| `seller_attributes` | Phone, shop_name, province/city, tier cho seller mới; không thay ID nguồn |
| `actors` | Các nhóm tác động, vai trò, tập thực thể và thuộc tính metadata |
| `inventory` | Phạm vi sản phẩm/kho, độ phủ, phân bố lượng tồn đầu |
| `channels` | Danh sách tên kênh và loại kênh |
| `payment_methods` | Tên phương thức và nhóm semantics được hỗ trợ |

Các thuộc tính được ghi vào OLTP chỉ là các cột đã được hỗ trợ và có mapping rõ. Thuộc tính tùy chỉnh của actor nằm trong Control DB, không tự biến thành cột OLTP. Không sinh giá vốn hoặc dữ liệu Tiki không có trong nguồn chỉ vì muốn lấp NULL.

### Bộ sinh giá trị

Ví dụ:

```json
{
  "gender": {
    "kind": "choice", "values": ["Male", "Female"],
    "weights": [48, 52], "null_rate": 0.15
  },
  "date_of_birth": {
    "kind": "date", "min": "1960-01-01", "max": "2007-12-31", "null_rate": 0.25
  }
}
```

Các loại được hỗ trợ: `constant`, `choice`, `integer`, `number`, `date`. `null_rate` từ 0 đến 1. Thuộc tính OLTP có kiểm tra kiểu riêng; ngày sinh không được sau mốc mô phỏng. Giá trị được chọn ổn định theo seed và danh tính. Các bộ địa phương giữ các trường liên quan trong cùng một bản ghi; hồ sơ seller chọn từ địa phương đã khai báo, không mặc định tất cả ở một tỉnh.

### Nhóm actor

```json
{
  "id": "customers",
  "entity": "customers",
  "roles": ["orders/2. Khách đã đăng ký", "analytics/Khách đã đăng ký"],
  "where": {"membership_tier": ["Member", "Silver"]},
  "attributes": {
    "segment": {"kind": "choice", "values": ["regular", "engaged"], "weights": [7, 3]}
  }
}
```

- `entity`: customers/sellers/carriers dùng các ID hiện có; `virtual` mô tả nhân viên, dịch vụ, guest không có bảng tài khoản tương ứng trong schema.
- `roles`: sao chép chính xác hệ thống/nhóm từ mẫu hoặc danh mục UI. Engine kiểm tra vai trò và loại thực thể; không tự cho khách đóng vai nhân viên.
- `count`: số danh tính ảo tối đa trong nhóm, mặc định 1; không phải quota hành động. Với thực thể OLTP, số thành viên do dữ liệu và `where` quyết định, không sinh thêm seller/carrier bằng `count`.
- `where`: lọc thuộc tính bản ghi OLTP bằng danh sách giá trị; không nhận SQL/Python.
- `scope`: tùy chọn các danh sách ID customer_id/seller_id/warehouse_id/carrier_id để giới hạn phạm vi. Tham chiếu phải phù hợp thực thể và rule nghiệp vụ.
- `attributes`: thuộc tính metadata tổng hợp cho từng danh tính. Một actor thực được dùng lại qua nhiều vai trò. Thuộc tính đã tạo giữ theo danh tính, không bị ghi đè khi đổi file; các nhóm chồng nhau nên dùng bộ định nghĩa nhất quán.

Bản đầy đủ có 21 nhóm cấu hình phủ các nhóm tác động của sáu hệ thống. Số nhóm không phải giới hạn của engine. Danh tính được tạo/chọn khi thực hiện hành động, không phải tạo trước hàng nghìn tài khoản nhân viên trong OLTP.

Khách vãng lai trong chuỗi phiên giữ cùng actor qua xem/tìm/giỏ/checkout. Khách đăng ký và seller giữ quan hệ theo ID thật trong DB. Chế độ xử lý toàn bộ đầu vào chọn actor theo đối tượng đủ điều kiện, tránh dừng chỉ vì chọn trúng thành viên chưa có việc.

## 4. Kịch bản

Các khóa cũ count/special/mode/params/variants/delay_days giữ nguyên. File cũ không khai báo actor vẫn chạy ở chế độ tương thích và được cảnh báo; không tự đổi kết quả cũ.

### Chọn phạm vi

```json
{
  "actor_pool": "customers",
  "selection": {"products": {"category_id": [625, 112]}}
}
```

Có thể dùng tham chiếu context thay danh sách cố định, ví dụ `{"warehouses":{"province":{"ref":"address.province"}}}` để chỉ chọn kho cùng tỉnh với địa chỉ của checkout. Đây là chính sách do config chọn; không tự áp hoặc tự chuyển sang kho ngoài phạm vi khi thiếu hàng. Tham chiếu chưa có context được báo rõ.

`selection` là bảng → cột → danh sách giá trị, áp dụng khi engine chọn các đối tượng của hành động. Cần dùng ID danh mục có trong nguồn của mình; mẫu trên chỉ minh họa cú pháp, không phải các ID bắt buộc. Checkout liên kết vẫn tiêu thụ giỏ và giữ hàng nguyên tử: nếu giỏ không phù hợp phạm vi/rule, yêu cầu bị từ chối, không tự loại dòng để ép thành công.

Có thể tham chiếu kho/carrier bằng `warehouse_code`/`carrier_code` thay cho ID phát sinh. Mã không tồn tại hoặc xung đột ID phải được báo lỗi, không tự tạo tài nguyên.

### Lịch phiên và độ trễ

Mở phiên:

```json
{"start":"08:00:00","end":"21:30:00","duration_seconds":{"kind":"integer","min":1200,"max":3600}}
```

Hành động tiếp theo trong phiên:

```json
{"offset_seconds":{"kind":"integer","min":300,"max":600}}
```

Đặt cấu hình này trong `schedule`. Offset tính từ lúc mở **phiên được chọn**, không từ giờ máy hoặc giờ hành động trước. Rule kiểm tra không diễn ra trước sự kiện đã có hoặc ngoài thời lượng phiên. Checkout dùng offset phải ở chế độ linked. `delay_days` vẫn dùng cho các hệ quả qua ngày như giao hàng/nhận trả/hoàn tiền.

Engine vẫn duyệt các giai đoạn nghiệp vụ theo thứ tự nhân quả; đây không phải bộ thực thi JSON tùy ý hoặc một hàng đợi sự kiện thời gian thực tổng quát. Cấu hình khung giờ/offset mâu thuẫn có thể làm thiếu đầu vào. Phiên/hành động chuyển ngày phải đợi ngày tương ứng; không ghi lén sang ngày chưa được chạy. Bản mẫu để các phiên kết thúc trong ngày và đóng các phiên đến hạn ở cuối ngày.

### Tham số theo điều kiện

```json
[
  {
    "when": {"actor.attributes.segment":["engaged"]},
    "params": {"shipping_fee":15000}
  },
  {
    "when": {},
    "params": {"shipping_fee":{"kind":"choice","values":[20000,30000],"weights":[7,3]}}
  }
]
```

Đặt trong `parameter_rules`; quy tắc khớp **đầu tiên** được áp. Context hỗ trợ actor, selected (theo tên bảng), order, address, warehouse, params khi chúng đã được chọn. Có thể khai báo bảng tra phí/tuyến trong config, không cần nhánh Python cho từng tỉnh.

Chỉ được thay các tham số kết quả đã hỗ trợ của hành động: amount, shipping_fee, success_rate, rating, value, reason, carrier/carrier_code. Không dùng lookup để đổi chủ sở hữu hoặc đối tượng đang xử lý. `when` là phép so khớp với danh sách, chưa phải ngôn ngữ biểu thức/công thức tùy ý. Quy tắc cần context order/warehouse chỉ được phân giải khi context đó có; fallback ở cuối giúp hành vi khi chưa khớp được rõ ràng.

## 5. Tồn đầu và catalog lớn

```json
[
  {
    "products":{"category_id":[625]},
    "warehouses":{"province":["Hà Nội"]},
    "quantity":{"kind":"integer","min":5,"max":50},
    "coverage":0.8
  },
  {"quantity":{"kind":"integer","min":3,"max":20},"coverage":0.5}
]
```

Đặt trong `entity_profile.inventory`. Quy tắc đầu tiên khớp sản phẩm/kho được dùng; coverage là xác suất có tồn tại cặp đó, không phải bảo đảm chính xác tỷ lệ. Không có quy tắc khớp thì không cấp tồn cho cặp. Không khai báo inventory thì dùng ô tồn chung như trước. Không cần liệt kê toàn bộ SKU hay tích SKU × kho.

149 sản phẩm chỉ là dữ liệu test. Đã bổ sung lọc SQL cho linked checkout, tồn khả dụng và phạm vi; bỏ quét lại toàn bộ balance theo mỗi SKU; cache ID/chỉ mục vị trí trong một transaction; đọc runtime theo khóa thay vì nạp toàn bộ lịch sử cho mỗi lệnh.

DB mới tự có các index truy vấn. DB cũ có migration **chỉ thêm index**, không sửa dòng/ID:

```bash
.venv/bin/python -m scripts.mock_platform.infrastructure.indexes
.venv/bin/python -m scripts.mock_platform.infrastructure.indexes --apply
```

Dừng/chờ hết tác vụ ghi trước khi áp. Giới hạn bảo vệ 10.000 yêu cầu/hành động/ngày và 100.000 yêu cầu tường minh/lượt vẫn được công bố; có thể chia khoảng chạy liên tục. Chưa có cam kết hiệu năng cho hàng triệu sản phẩm chỉ từ kiểm thử catalog nhỏ; cần benchmark với workload thực tế.

## 6. Dữ liệu và kiểm tra

- Các cột/bảng OLTP giữ nguyên, không cần migration thêm cột cho actor metadata.
- Registry actor, dấu liên kết phiên, lịch và journal nằm trong Control DB; các trường nghiệp vụ có mapping được ghi OLTP qua hành động hợp lệ.
- WH-01/WH-02 có reference_code từ ID hành động. Audit bỏ job thuộc đợt trước reset và xác minh ảnh sự kiện, tránh ghép nhầm ID tái sử dụng.
- UI Tổng quan làm mới cả checkpoint/thẻ catalog/danh sách job. Job lịch sử trước reset không nhận backlog của dữ liệu hiện tại.
- Không bổ sung giá vốn, voucher phần trăm/riêng SKU, SLA hoặc cơ chế nghiệp vụ mới chỉ để “cho đầy bảng”. Muốn thêm semantics mới vẫn cần rule code và kiểm thử tương ứng.
