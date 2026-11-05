# Rà soát độ đa dạng thực thể: config tại thời điểm audit làm được gì?

> Báo cáo dưới đây mô tả baseline trước nâng cấp. Engine v2 đã bổ sung một phần khả năng được đề xuất; xem [hướng dẫn v2](../guides/ENGINE_V2_UPGRADE_GUIDE.md) để biết trạng thái code mới.

Ngày rà soát: 05/11/2026. Đây là đánh giá khả năng code hiện tại và đề xuất nâng cấp, chưa phải bộ tỷ lệ nghiệp vụ đã chốt.

## 1. Kết luận

**Một phần làm được bằng config hiện tại; phần còn lại cần mở khả năng trong code rồi mới điều khiển qua config.** Không cần viết lại engine chỉ để đa dạng dữ liệu, nhưng cũng không thể nhập các trường JSON mà handler chưa đọc và mong chúng có hiệu lực.

Phân biệt ba nhu cầu:

1. **Đổi một giá trị:** ví dụ cả nhóm phiên khách đã đăng ký dùng Desktop thay vì Mobile. Config hiện tại làm được với những trường được handler hỗ trợ.
2. **Trộn nhiều giá trị trong cùng ngày:** ví dụ một hành động tạo phiên có cả Mobile, Desktop và Tablet với các tỷ lệ do người dùng chọn. Config hiện tại chưa làm được.
3. **Đổi trường đang gán cố định:** ví dụ tên người nhận, điện thoại, phường, danh sách kho/carrier. Cần bổ sung code và form cấu hình tương ứng.

Ưu tiên tận dụng loại 1. Với loại 2, bổ sung một cơ chế profile dùng chung. Với loại 3, bổ sung generator/dữ liệu nền có cấu hình, tránh mỗi handler tự tạo dữ liệu theo một cách khác nhau.

## 2. Phạm vi đọc dữ liệu và bằng chứng

Đã đọc toàn bộ hàng và cột của **27 bảng, 231 cột** trong một transaction PostgreSQL `REPEATABLE READ READ ONLY`. Snapshot tổng hợp lúc **22:35:18 ngày 05/11/2026, UTC+7** nằm tại [entity-diversity-snapshot-2026-11-05.json](entity-diversity-snapshot-2026-11-05.json): số dòng, số NULL, số giá trị phân biệt không NULL và ba giá trị phổ biến nhất của từng cột.

Snapshot mô tả thời điểm kiểm tra, không khẳng định DB sẽ giữ nguyên sau khi worker tiếp tục chạy. Không sửa DB, nguồn SQLite hay cấu hình đã lưu trong lượt rà soát này.

Code đối chiếu:

- [Danh sách hành động và các trường config](../../../scripts/mock_platform/actions.json).
- [Worker: dữ liệu nền và cách áp tham số](../../../scripts/mock_platform/worker.py).
- [Handler: trường nào thực sự được ghi](../../../scripts/mock_platform/domain.py).
- [Import và kiểm tra định dạng config](../../../scripts/mock_platform/config_transfer.py).

## 3. Giới hạn chính của config hiện tại

Mỗi mã hành động chỉ có **một object `params`**. Worker ghép các giá trị mặc định với object này rồi dùng lại cho tất cả lượt của hành động đó trong kế hoạch.

- `count` là số lần/ngày thường.
- `special[ngày]` thay thế số lần cho ngày đó; không đổi `params` và không nhân tỷ lệ.
- `mode=all` xử lý toàn bộ đầu vào đủ điều kiện; không sinh thêm đầu vào để đủ quota.
- `seed` giúp tái lập những lựa chọn mà code có hỗ trợ; không tự biến giá trị cố định thành một phân bố.
- Chưa có danh sách biến thể, trọng số, nội suy chuỗi, profile thực thể hay tham số riêng theo ngày.
- Các mã hành động khác nhau có thể giữ các bộ tham số khác nhau. Ví dụ phiên guest và phiên registered có thể dùng hai thiết bị khác nhau. Đây chỉ tạo được một mức đa dạng hạn chế.

Có thể dùng cấu hình khác cho những giai đoạn/ngày tương lai khác nhau. Không chạy lại cùng một ngày bằng nhiều cấu hình vì checkpoint tuần tự đã chốt; kế hoạch/job đã snapshot cũng không tự nhận bản config vừa sửa.

**Thêm một ô `distribution` vào JSON/UI chưa đủ:** cần schema, validation và worker thực sự hiểu nó. Không dùng trường chưa được hỗ trợ để tạo cảm giác đã cấu hình thành công.

## 4. Rà soát đủ 27 bảng

“Config hiện tại” trong bảng dưới chỉ nói những tham số handler đang sử dụng; một giá trị áp cho toàn bộ lượt của cùng mã hành động. Độ đa dạng của kết quả còn phụ thuộc đối tượng đầu vào đủ điều kiện.

| Bảng — số dòng | Dữ liệu quan sát được | Config hiện tại làm được | Phần còn thiếu / cách xử lý |
|---|---|---|---|
| `categories` — 6 | Có cây danh mục; một `parent_id` NULL | Nhận danh mục mới qua đồng bộ append-only | Danh mục gốc NULL là hợp lệ; không tạo danh mục giả để tăng số lượng. |
| `products` — 149 | 9 seller, 5 category được dùng, 83 giá khác nhau; `cost_price`, `stock_item` đều NULL | Chọn sản phẩm cho hành động; có hành động sửa nội dung/phân loại theo quyền | Dữ liệu nguồn đã đa dạng. Muốn thêm sản phẩm thật thì cào rồi đồng bộ; không sửa giá/ID nguồn để làm đẹp. NULL thiếu nguồn không tự trở thành lỗi. |
| `sellers` — 9 | Tên có dấu vết nối chuỗi nhiều lần; điện thoại NULL; địa điểm HCM, hạng Normal | SEL-01 tên; SEL-02 email; SEL-03 địa điểm; MGR-01 hạng | Chưa có profile điện thoại/địa điểm hỗn hợp. Hạng hiện là kết quả được chỉ định, chưa tự tính từ hiệu suất. Không lặp sửa tên chỉ để tạo đa dạng. |
| `customers` — 338 | Tên khác nhau nhưng dạng mẫu; điện thoại giống nhau; ngày sinh/giới tính NULL; HCM/Member | GST-01 tỉnh; CUS-01 tên; CUS-02 địa điểm; SYS-03 hạng | Tên/điện thoại/demographic lúc tạo cần generator có config. Bootstrap đang cố định HCM/Member; hạng chưa có thuật toán tích lũy. |
| `customer_addresses` — 784 | Người nhận, điện thoại, phường, chi tiết địa chỉ lặp; district NULL; toàn bộ `is_default=false` | CUS-03 chọn khách, tỉnh và `value` cho chi tiết; CUS-04 chọn một địa chỉ của khách làm mặc định | Cần profile người nhận/điện thoại/địa phương và chính sách lưu/tái dùng địa chỉ. Checkout hiện tự tạo địa chỉ, không đọc địa chỉ mặc định. |
| `channels` — 3 | Web, App, Livestream; đều Digital | Chọn channel ở checkout và tạo phiên | Bộ tham chiếu hữu hạn đang hợp lý; không cần tạo nhiều tên khác nhau cho cùng một kênh. |
| `payment_methods` — 5 | COD, Momo, ZaloPay, Credit Card, Bank Transfer | Chọn `method` ở checkout | Đủ danh mục để thử nhiều phương thức; cùng một action chưa trộn được tỷ lệ. |
| `orders` — 688 | 2 kênh được dùng; session/campaign NULL; phí ship và giảm giá đều 0 | Checkout chọn method/channel/quantity | Liên kết hành trình, giảm giá, phí khách trả cần luồng nghiệp vụ; không sửa bằng cách random các tổng tiền. |
| `order_items` — 688 | Một dòng/đơn, quantity=1, discount=0 | Đổi quantity của sản phẩm được chọn | Nhiều dòng khác SKU/giỏ hàng và phân bổ giảm giá cần code; quantity>1 không đồng nghĩa nhiều dòng. |
| `payments` — 688 | Kết quả phụ thuộc checkout và xử lý thanh toán | Method tại checkout, PAY-01 `success_rate`; retry theo điều kiện | Không random độc lập số tiền/trạng thái. Luồng retry, thời hạn và hệ quả cần nâng cấp riêng. |
| `returns` — 0 | Chưa có dòng | Không thể dùng config hiện tại để tạo đủ luồng hoàn trả đúng nghiệp vụ | Cần triển khai điều kiện trả, nhận hàng, hoàn tiền và liên kết chứng từ; không điền giả để bảng có dữ liệu. |
| `product_reviews` — 150 | 93 đánh giá 5 sao, 57 đánh giá 4 sao; hai chuỗi bình luận | CUS-09 `rating`, `value`, chọn order item đủ điều kiện | Đổi được điểm/bình luận cố định. Muốn phân bố sao và nhiều mẫu bình luận trong một ngày cần profile. |
| `promotions` — 96 | Tên đều “Voucher mô phỏng”; 3 loại, đều Fixed Amount; giới hạn mỗi khách 1 | MKT-03/04, SHOP-MKT-01 chỉnh amount/min_order/limit/days và đối tượng liên quan | Tên, kiểu giảm và giới hạn mỗi khách chưa mở đầy đủ; cần code nếu muốn tùy chỉnh. Điều kiện áp dụng phải đi cùng ledger sử dụng. |
| `order_item_promotions` — 0 | Chưa ghi lượt áp voucher | Chưa có config giải quyết được một mình | Cần luồng áp dụng, phân bổ và kiểm soát lượt dùng; không tự chèn liên kết ngẫu nhiên. |
| `warehouses` — 1 | WH-DEMO, tên/địa chỉ thử nghiệm tại HCM | Chọn kho đã tồn tại cho một số hành động tồn kho | Bootstrap chưa nhận danh sách kho; thêm nhiều kho cần code dữ liệu nền và chính sách phân bổ tồn. |
| `inventory_levels` — 149 | Tồn thuộc một kho; tồn đầu cùng tham số chung | WH-01/02 chọn warehouse/product/quantity | Có thể thay lượng từng SKU qua hành động hợp lệ; chưa có profile tồn đầu theo nhóm/kho. WH-02 hiện không hỗ trợ điều chỉnh âm. |
| `inventory_movements` — 927 | Ledger phát sinh từ thao tác kho/đơn | Điều khiển đầu vào nhập/xuất theo hành động hỗ trợ | Phải bảo toàn giữ/xuất/nhập và khóa kho–SKU; không random ledger cho đa dạng. |
| `inventory_daily_balance` — 7.301 | Số dư ngày từ luồng tồn | Chạy chốt ngày và thay đổi đầu vào hợp lệ | Đây là kết quả tính toán, không cần form random số dư. |
| `carriers` — 1 | DEMO, “Vận chuyển mô phỏng” | Chưa có config tạo danh sách hoặc chọn carrier cụ thể | Cần dữ liệu nền nhiều carrier và selector theo điều kiện; SLA/routing là bước nghiệp vụ sau. |
| `shipments` — 667 | Phụ thuộc một kho/carrier và luồng giao | DSP-01 amount; CAR-03 success_rate | Không có lựa chọn carrier. Kho hiển thị ở DSP-01 chưa điều khiển chọn kho. Thất bại giao cần đủ hệ quả trước khi tăng tỷ lệ lỗi. |
| `marketing_campaigns` — 32 | Hai tên; toàn Brand Awareness và WEB; hai mức ngân sách | MKT-01 tên/budget/days, MKT-02 budget | Loại chiến dịch và kênh đích đang cố định; cần mở handler/config nếu muốn đổi. |
| `ad_spend_logs` — 49 | Hai cặp cost/clicks; impressions luôn clicks×100 | ADS-01 amount(cost), quantity(clicks), target(campaign) | Impressions/CTR cần code nhận hoặc sinh tham số hợp lệ; config hiện không đổi được tỷ lệ 1%. |
| `sessions` — 6.600 | Toàn Mobile; hai nguồn Organic/Direct; hai kênh; campaign NULL | GST/CUS-WEB-01 device/channel/traffic | Có thể đổi giá trị từng nhóm ngay; chưa có phân bố cùng action/ngày. Gắn campaign/hành trình mua cần code. |
| `page_events` — 18.497 | Năm loại sự kiện; order_id đều NULL | Chọn sản phẩm/phiên theo handler hỗ trợ | Thiếu nối checkout→order và lưu từ khóa; có lỗi phạm vi guest/registered đã phát hiện. Không sửa bằng đa dạng config. |
| `cart_items` — 1.506 | Phát sinh từ phiên và hành động giỏ | WEB-04 product/quantity | Cần checkout tiêu thụ đúng giỏ, giữ danh tính và trạng thái; quota không thay thế được quan hệ này. |
| `seller_commission_rates` — 1 | Category 9423, Normal, rate 0,05 | FIN-POL-01 category/tier/rate/start/end | Hỗ trợ một bộ chính sách mỗi action; count=5 không sinh năm category, mà lặp cùng policy và có thể bị chặn trùng kỳ. Cần form danh sách nếu muốn nạp ma trận chính sách. |
| `seller_payouts` — 0 | Chưa có đối soát/chi trả | Config hiện chưa tạo được trọn luồng | Cần tính từ giao dịch đủ điều kiện, hoàn tiền, hoa hồng, kỳ đối soát và duyệt/chi; không tạo số tiền ngẫu nhiên. |

## 5. Những trường config dễ gây hiểu nhầm

Đây là vấn đề code/UI cần sửa hoặc giải thích rõ, không phải người dùng nhập sai:

| Trường/hành động | Hành vi thực tế hiện tại | Hướng xử lý |
|---|---|---|
| DSP-01 `warehouse` | Không được dùng để chọn kho xuất; handler dùng kho đã giữ tồn trong runtime đơn | Hiển thị kho thực tế hoặc định nghĩa lại bước chọn kho; không đổi kho sau giữ tồn mà thiếu chuyển giữ. |
| CUS-WEB-01 `target` khách | Handler vẫn chọn khách với `target=""` | Áp lựa chọn khách và kiểm tra tồn tại/quyền sở hữu. |
| WEB-02 `value` từ khóa | Tạo sự kiện search nhưng không lưu từ khóa; schema `page_events` chưa có cột tương ứng | Chốt nơi lưu trước khi mở form có ý nghĩa. |
| AUT-WEB-01 channel/device/traffic | Handler chỉ chọn phiên mở để kết thúc, không dùng những giá trị này | Bỏ trường không có tác dụng hoặc triển khai bộ lọc đúng nghĩa. |
| AUT-WEB-02 product/quantity | Handler chọn giỏ Active của phiên đã đóng, không dùng các giá trị này | Bỏ trường không dùng hoặc định nghĩa bộ lọc. |
| CUS-06 method=COD | Registry cho chọn nhưng handler từ chối retry COD | Đồng bộ validation/UI với điều kiện handler. |
| GST/CUS-WEB-05/06 | Lựa chọn giỏ chưa lọc đúng phạm vi guest/registered | Sửa code; audit trước phát hiện 53 sự kiện guest gắn phiên có khách. Tắt hành động chỉ tránh phát sinh mới, không sửa lỗi. |

## 6. Có thể cải thiện ngay bằng config tới đâu?

Không cần sửa code để **đổi giá trị thử nghiệm** của những trường được hỗ trợ:

- Phiên: channel, device, traffic; chọn khác nhau cho mã guest và registered.
- Checkout: phương thức, kênh, quantity; dùng đầu vào hợp lệ và giữ đúng điều kiện thanh toán.
- Đánh giá: rating/bình luận cho order item đủ điều kiện.
- Khách/seller: tỉnh, tên/email được mở ở đúng hành động; thay hạng bằng chỉ định thử nghiệm.
- Kho: lượng nhập cho SKU/kho có thật; không thể tạo thêm kho bằng trường warehouse ID.
- Marketing: tên/ngân sách chiến dịch, hạn dùng/giá trị/ngưỡng voucher, cost/clicks.
- Hoa hồng: một category/tier/rate/kỳ hợp lệ.

Nhưng cấu hình mỗi hành động với một giá trị khác **chưa mô phỏng được cơ cấu hỗn hợp trong ngày**. Ví dụ đổi Mobile thành Desktop cho CUS-WEB-01 chỉ làm toàn bộ lượt mới của mã đó thành Desktop. Tăng count không làm rating, payment method hay province tự đa dạng hơn.

Không đề xuất tỷ lệ “chuẩn ngành” khi chưa có dữ liệu mục tiêu. Các tỷ lệ sau này là giả định do người dùng duyệt và cấu hình.

## 7. Phương án nâng cấp nhỏ nhất

### Bước A — Tận dụng config đang có và làm rõ UI

Giữ các bộ tham chiếu Web/App/Livestream và năm phương thức thanh toán. Hiển thị rõ “áp dụng một giá trị cho tất cả lượt của hành động”. Đánh dấu trường chưa có tác dụng; sửa các sai lệch handler/validation ở mục 5 trước khi dùng chúng để điều khiển dữ liệu.

Chưa thay cấu hình đang lưu hoặc sửa dữ liệu lịch sử chỉ vì báo cáo này.

### Bước B — Một cơ chế profile tham số dùng chung

Bổ sung một lớp chọn **bộ tham số theo trọng số** trong worker, cùng schema/validation/import/UI có version. Áp dụng đầu tiên cho các trường handler đã hỗ trợ: phiên, checkout, đánh giá, quảng cáo.

- Một profile gồm nhiều hàng; mỗi hàng là bộ tham số tương thích và trọng số. Ví dụ channel/device/traffic đi cùng nhau, thay vì chọn từng trường độc lập tạo tổ hợp không hợp lý.
- Trọng số điều khiển xác suất, không bảo đảm chính xác số lượt từng nhóm. Nếu cần quota chính xác từng nhóm phải có chế độ phân bổ riêng và hiển thị rõ.
- Chọn bộ tham số theo seed + action ID + namespace riêng, ghi quyết định vào kết quả và snapshot nội dung/revision profile vào kế hoạch/job. Không để sửa profile làm đổi job đã xếp.
- Config scalar cũ giữ nguyên hành vi; ngày đặc biệt vẫn chỉ thay quota trừ khi sau này chốt thêm thiết kế khác.
- Phải kiểm tra các tổ hợp bất hợp lệ, đầu vào đủ điều kiện, trọng số và field được handler hỗ trợ. Profile không được tự tạo đối tượng thiếu.

Như vậy chỉ mở một khả năng chung rồi thiết kế các bộ config; không viết một randomizer riêng cho từng hành động. Tuy nhiên profile không làm xuất hiện các trường handler chưa hỗ trợ như phone, ward, campaign_type hay impressions.

### Bước C — Dữ liệu nền và generator cho trường cố định

- Customer/address: generator dùng chung cho bootstrap, đăng ký, thêm địa chỉ và checkout; họ tên/điện thoại/địa phương có tính nhất quán, NULL có chủ đích. Tỉnh/phường không được ghép ngẫu nhiên độc lập.
- Warehouse/carrier: form danh sách dữ liệu nền, preview/validation khóa nhận diện, quan hệ tồn theo kho; bổ sung selector. Không đổi ID sản phẩm Tiki.
- Campaign/promotion/ad: mở đúng các trường cần dùng, kiểm tra điều kiện; không coi thêm tên đẹp là đã có nghiệp vụ áp voucher/attribution.
- Commission: nhập danh sách policy hợp lệ, không dùng số lần hành động thay cho số dòng cấu hình độc lập.

Cấu hình/profile lưu trong Control DB; các thực thể sinh ra nằm trong OLTP theo schema. Thuộc tính nghiệp vụ cần cho DW mà OLTP chưa biểu diễn phải được đề xuất schema riêng, không giấu toàn bộ trong metadata rồi coi là đã đầy đủ.

### Bước D — Các quan hệ nghiệp vụ là công việc riêng

Nhiều dòng/đơn, nối session→cart→order, voucher usage, trả hàng/hoàn tiền, đối soát và lịch giao qua ngày cần nâng cấp engine theo [kế hoạch nâng cấp](../plans/MOCK_ENGINE_UPGRADE_PLAN.md). Đa dạng config không thay thế được tính đúng của các luồng này.

## 8. Tiêu chí nghiệm thu

1. Trường UI cho chỉnh phải có hiệu lực và thấy được trong kết quả/preview; không còn trường trông có tác dụng nhưng bị bỏ qua.
2. Cùng seed, baseline và snapshot tái lập được lựa chọn; config cũ không đổi hành vi.
3. Một ngày có thể có nhiều bộ giá trị hợp lệ từ cùng một action khi profile đã được triển khai; quota ngày thường/ngày riêng vẫn đúng.
4. Địa chỉ thuộc đúng khách; guest có customer_id NULL hợp lệ; địa chỉ lịch sử của đơn không đổi theo hồ sơ mới.
5. Nhiều kho/carrier không phá giữ tồn, ledger, tuyến hợp lệ hoặc điều kiện giao/COD.
6. Không yêu cầu mọi trường khác nhau: tên trùng, điện thoại dùng chung, danh mục gốc NULL, mã tham chiếu lặp và dữ liệu nguồn chưa có là những trường hợp có thể đúng.
7. Không sửa tay tổng tiền, số dư, trạng thái hay FK để tạo vẻ đa dạng. Dữ liệu kết quả phải do hành động và hệ quả hợp lệ sinh ra.

Hướng đề xuất: **dùng config cho những trường đã hỗ trợ; bổ sung profile dùng chung và generator cho phần chưa hỗ trợ; sau đó điều khiển bằng config trên UI.** Chưa cần thay toàn bộ kiến trúc.
