# Tham khảo lịch vận hành trước nâng cấp

> Tài liệu lịch sử cho generator đặt trực tiếp. Các file mẫu cũ đã được dọn theo yêu cầu; dùng [mẫu COD cơ bản](../examples/scenarios/first-run-cod.json) hoặc [kịch bản liên kết mới nhất](../examples/scenarios/upgraded-linked-2026.json) cho công việc hiện tại. Xem [hướng dẫn v2](ENGINE_V2_UPGRADE_GUIDE.md).

## 1. Mục tiêu và mức độ thực tế

Bộ này thay thế kịch bản thử 10 đơn cố định/ngày bằng lịch có biến thiên, xử lý thanh toán/đơn/kho theo dữ liệu đủ điều kiện và giảm các hành động quản trị phát sinh vô lý. Đây là **giả định mô phỏng cho một catalog nhỏ**, không phải thống kê lưu lượng Tiki hay tỷ lệ chuẩn của ngành thương mại điện tử.

Không thể dùng cấu hình để bổ sung những nghiệp vụ engine chưa có. Vì vậy một số nhánh được chủ động tắt, hoặc dùng giả định đơn giản có ghi rõ dưới đây. Không phải bộ mock đầy đủ mọi bảng hoặc mô phỏng toàn bộ một sàn thực tế.

## 2. Các file sử dụng

- JSON và CSV mẫu cũ đã được xóa khỏi thư viện. Có thể tạo lại ở thư mục riêng bằng generator bên dưới nếu cần nghiên cứu lịch cũ.
- Bộ sinh cấu hình OOP Python: `scripts/mock_platform/config/scenario.py`.

JSON có lịch riêng cho năm **2026**. Seed của môi trường vẫn điều khiển lựa chọn đối tượng/kết quả xử lý; lịch sản lượng đã được tính và ghi rõ trong JSON, không bị tính lại ngẫu nhiên mỗi lần chạy.

## 3. Nhập hoặc xuất cấu hình trên web

1. Mở **Cấu hình kịch bản → Nhập / Xuất cấu hình JSON**. Có ở cả chế độ Tổng quan và Chỉnh sửa.
2. Bấm **Tải mẫu vận hành 2026**, hoặc chọn file JSON có sẵn trên máy.
3. Có thể nhập tên mới; để trống thì dùng tên trong file.
4. Bấm **Kiểm tra & xem trước**. Đọc số hành động, cảnh báo về lịch ngày và mở bảng tổng hợp 6 hệ thống.
5. Bấm **Lưu thành cấu hình mới**. Hệ thống tạo mã cấu hình mới trong Control DB và chọn cấu hình đó để bạn xem/chỉnh sửa/lập kế hoạch.

Import không ghi đè cấu hình cũ, không thay bản nháp, không ghi OLTP, không đồng bộ Tiki và không tự chạy dữ liệu. Nếu đang chỉnh sửa một cấu hình đã lưu, phải lưu/hủy thay đổi trước khi lưu cấu hình nhập. Đổi file hoặc tên thì phải kiểm tra lại. Nút **Xuất cấu hình đang xem** tải một JSON có thể nhập lại, gồm thay đổi chưa lưu nếu bạn đang chỉnh sửa.

Hỗ trợ file tối đa **2 MiB**, UTF-8, có thể có BOM. Chấp nhận:

```json
{
  "format": "mock-studio-config",
  "format_version": 1,
  "name": "Kịch bản của tôi",
  "config": {
    "GST-01": {
      "enabled": true,
      "count": 3,
      "mode": "count",
      "special": {"2026-11-11": 12},
      "params": {"province": "Hà Nội"}
    }
  }
}
```

Cũng chấp nhận object ánh xạ mã hành động trực tiếp, không có lớp `config`; khi đó tên mặc định là “Cấu hình nhập từ JSON”. File ví dụ cũ có `name`, `version_id`, `config` được hỗ trợ: bỏ qua `version_id`, luôn tạo cấu hình mới. Hành động không có trong file mặc định tắt. Tham số không khai báo dùng mặc định của registry khi chạy; tham số kiểu số/lựa chọn để trống hoặc null được bỏ qua để dùng mặc định.

Từ chối JSON sai cú pháp, khóa lặp, NaN/Infinity, mã hành động không tồn tại, trường lạ, sai kiểu dữ liệu, ngày không đúng YYYY-MM-DD, số ngoài miền, số lượng dạng thập phân, chế độ không hỗ trợ và hành động chưa triển khai nhưng bị bật. Xem trước và lúc lưu đều kiểm tra lại phía server.

## 4. Điều kiện trước khi chạy mẫu

- Chuẩn bị môi trường với ngày bắt đầu mong muốn và seed; không đổi ngày bắt đầu của môi trường đã thiết lập chỉ bằng import.
- Đồng bộ catalog Tiki theo rule append-only, sản phẩm mới sẵn sàng bán, SKU hợp lệ.
- Khuyến nghị khởi đầu cho catalog hiện có khoảng 149 sản phẩm: **100 khách nền, 30 sản phẩm tồn đầu mỗi SKU**, kho mặc định ID **1**. Đây là giả định thử nghiệm; không tự ghi các giá trị này khi import.
- Dữ liệu nền hiện có không được tạo lại nếu đã bootstrap. Có thể tiếp tục với dữ liệu đang có; nếu muốn thử từ đầu thì dùng chức năng xóa toàn bộ đã xác nhận, đồng bộ và bootstrap lại. Không cần xóa dữ liệu chỉ để nhập cấu hình.
- Chính sách tài chính trong mẫu dùng danh mục **9423**, hạng **Normal**, 5%, hiệu lực 01/01–31/12/2026. ID này có trong catalog hiện tại nhưng phải sửa nếu catalog khác. Mẫu chỉ yêu cầu tạo chính sách vào **01/01/2026**, không giả định đã phủ hết danh mục/hạng seller.
- Khi bắt đầu giữa năm với môi trường trống: đặt thêm số lần 1 cho `FIN-POL-01` vào ngày bắt đầu nếu chưa có chính sách. Nếu đã có chính sách cùng phạm vi thì không tạo thêm vì sẽ chồng lấn. Tương tự, nếu chạy lần đầu giữa tháng và chưa có chiến dịch hiệu lực, đặt `MKT-01` số lần 1 ở ngày bắt đầu.

Với môi trường đã chạy hết **31/01/2026**, có thể dùng mẫu để **tiếp tục từ 01/02/2026**. Tháng Một giữ nguyên dữ liệu cũ; import không tái tạo lịch sử. Mẫu có chiến dịch mới ngày 01/02, còn chính sách tài chính tháng Một đang có được giữ.

## 5. Các hành động được cấu hình

| Hệ thống | Cách cấu hình | Lý do / giới hạn |
|---|---|---|
| Catalog & Người bán | Sửa mô tả 1 sản phẩm vào thứ Hai; cập nhật liên hệ 1 shop đầu tháng | Không đổi tên shop/sản phẩm hằng ngày; không khóa shop, đổi hạng, đổi phân loại tùy tiện. Giữ giá thật từ catalog. |
| Khách hàng | Đăng ký theo quy mô lưu lượng; thêm 1 địa chỉ vào thứ Tư | Hồ sơ và địa chỉ vẫn dùng dữ liệu thử nghiệm của engine. |
| Đặt hàng | Khoảng 25% lượt yêu cầu là khách vãng lai COD/Web, còn lại khách đăng nhập MoMo/App; 1 sản phẩm/số lượng 1 | Đây là cách tạo hai nhóm mà engine hỗ trợ, không có phân phối tùy chọn nhiều phương thức trong cùng hành động. |
| Thanh toán | Xử lý toàn bộ yêu cầu trả trước đủ điều kiện; tỷ lệ thành công **94%** | Là xác suất theo seed, không bảo đảm đúng 94% mỗi ngày. Đơn trả trước thất bại chờ xử lý quá hạn. |
| Hủy quá hạn | Tự xử lý đơn trả trước chưa trả tiền từ **2 ngày** trở lên | Không sinh retry hay hoàn tiền giả. Giữ tồn trước khi hủy; khi hủy mới giải phóng. |
| Xác nhận và giao vận | Tự xử lý đầu vào cho xác nhận đơn, tạo vận đơn, lấy hàng, đang giao, báo giao và thu COD | Không ép số vận đơn/thanh toán bằng quota độc lập khi không có đơn đủ điều kiện. |
| Kết quả giao hàng | **100% thành công** cho các vận đơn đã được xử lý | Cố ý để 100% vì engine chưa xử lý giao thất bại → hoàn kho/hoàn tiền/đóng nghĩa vụ. Đây là điểm chưa thực tế, không phải tỷ lệ giao hàng ngoài đời. |
| Kho | Mỗi ngày 1 lượt nhập 20 sản phẩm vào SKU được chọn; 2 ngày trước sale tăng lên 3 lượt; chốt tồn 1 lần cuối ngày | Không phải đặt hàng bổ sung theo nhu cầu/điểm tái đặt. Chỉ bật CAR-01, tắt WH-03 để tránh cấu hình hai đường cùng xuất kho cho một giai đoạn. |
| Đánh giá | Khoảng 1 lượt/6 yêu cầu đặt hàng; rating cố định **4** | Chỉ chọn dòng đã giao, khách có tài khoản, chưa đánh giá. Không giả định mọi người mua đều đánh giá; chưa tạo phân phối sao. |
| Marketing | Tạo 1 chiến dịch đầu tháng, ngân sách 3 triệu, hiệu lực 31 ngày; 1 báo cáo quảng cáo/ngày, 50.000 đồng, 60 clicks | Có thể chồng nhẹ hiệu lực hai chiến dịch khi sang tháng. Engine kiểm tra không vượt ngân sách; chưa mô phỏng ROI hay tác động lên mua hàng. |
| Voucher | Đầu tháng và ngày sale tạo 1 voucher sàn, freeship và shop; mức 20k/15k/10k, giá trị tối thiểu 200k/150k/100k, giới hạn 1.000, hiệu lực 7 ngày | Chỉ sinh định nghĩa voucher. Chưa áp vào đơn, chưa tiêu/hoàn lượt dùng. |
| Analytics | Tổng phiên = 15 × mục tiêu đặt hàng; 60% phiên khách vãng lai, 40% có tài khoản; xem hàng khoảng 2 lần/phiên; search khoảng nửa số phiên; số thêm giỏ khoảng 3 × mục tiêu đơn | Là các tổng lượng có tương quan do file cấu hình quy định, không phải phễu chuyển đổi thực sự được engine liên kết. |
| Đóng phiên/giỏ | Tự đóng phiên và đánh dấu giỏ còn hoạt động thành bỏ giỏ cuối ngày | Chưa có đường chuyển giỏ sang đã mua. Không được dùng số bỏ giỏ này để đo tỷ lệ bỏ giỏ thật. |
| Tài chính | Tạo một chính sách hoa hồng vào ngày đầu; tắt các hành động đối soát/chi tiền không có nguồn nghĩa vụ | Không bịa `seller_payouts` chỉ để lấp đầy bảng. |

Không bật các hành động `WEB-05/06` trong mẫu: checkout analytics chưa nối với đơn thực; ngoài ra handler chọn giỏ hiện chưa giới hạn đầy đủ theo nhóm khách ở hai hành động này. Không bật `VIS-01` cùng lượt xem analytics để tránh hai nguồn đếm xem hàng.

## 6. Lịch sản lượng

Thay vì thay engine, bộ sinh dùng khả năng `special[YYYY-MM-DD]` sẵn có để viết trước lịch:

- Mức nền theo thứ Hai → Chủ nhật: **16, 18, 19, 20, 22, 27, 24** lượt đặt hàng.
- Mỗi ngày có độ lệch cố định từ **−3 đến +3**, tính bằng hash ngày. Không thay đổi khi chạy lại bộ sinh cùng năm.
- Ngày 25–28: hệ số giả định **1,15** cho kỳ lương. Không coi đây là dữ liệu thị trường đã khảo sát.
- 8/8, 10/10, 11/11, 12/12: hệ số **4** trên mức nền có độ lệch của ngày đó. Hai ngày trước sale hệ số 1,5, ngày sau sale 1,4. Sale được ưu tiên khi các quy tắc trùng nhau.
- Chỉ số người dùng, phiên, xem hàng, giỏ và đánh giá được tính từ cùng mục tiêu để tổng lượng thay đổi đồng bộ. Không tự tăng mọi hành động quản trị, nhập kho, tạo chiến dịch hoặc đóng số dư theo hệ số sale.

Ví dụ 01–07/01 lần lượt **17, 23, 25, 26, 14, 20, 20** yêu cầu đặt hàng. Các ngày sale:

| Ngày | Tổng yêu cầu | COD khách vãng lai | MoMo khách đăng nhập |
|---|---:|---:|---:|
| 08/08/2026 | 108 | 27 | 81 |
| 10/10/2026 | 120 | 30 | 90 |
| 11/11/2026 | 64 | 16 | 48 |
| 12/12/2026 | 120 | 30 | 90 |

Toàn năm **8.224 yêu cầu đặt hàng**, không phải 8.224 đơn hoàn tất được bảo đảm. Checkout có thể bị từ chối do thiếu tồn/sản phẩm/khách; thanh toán thất bại không được hoàn tất như đơn thành công. Số đơn thực tế phải đọc từ OLTP và đối chiếu kết quả hành động.

Một hành động chỉ có một bộ tham số, ngày đặc biệt chỉ đổi **số lần**, không đổi giá trị tham số. Ví dụ không thể dùng riêng tỷ lệ thanh toán hay số lượng mỗi dòng hàng khác cho ngày sale chỉ bằng `special`.

## 7. Chạy theo tháng

Nên chạy thử 1–2 ngày, kiểm tra dữ liệu, rồi chia từng tháng liên tiếp. Bộ mẫu có khoảng **34.241–45.181 yêu cầu hành động theo số lượng/tháng**, chưa cộng số thực thi tự động. Số lượt thực thi lớn hơn kịch bản cũ; không coi đây là benchmark hiệu năng hay bảo đảm thời gian chạy.

Engine giới hạn 100.000 yêu cầu **theo số lượng** cho một kế hoạch. Vì mẫu toàn năm vượt ngưỡng đó, không chọn một lượt cả năm: chia tháng rồi chạy tiếp, không bỏ ngày. Các bước tự động có ngưỡng bảo vệ riêng, không được tính vào con số kế hoạch trên.

Ngoài năm 2026, `special` không còn áp dụng; engine sẽ quay về số ngày thường, không tự mở rộng lịch. Sinh file cho năm khác bằng:

```bash
.venv/bin/python -m scripts.mock_platform.config.scenario \
  --year 2027 --category-id 9423 \
  --output data/generated-scenarios/realistic-current-engine-2027.json
```

Lệnh chỉ tạo file JSON và CSV, không nhập cấu hình hay ghi OLTP.

## 8. Những điểm cấu hình không thể làm sát thực tế hơn

| Giới hạn của code hiện tại | Hệ quả đối với dữ liệu |
|---|---|
| Hành vi analytics và checkout độc lập | `orders.session_id`, `orders.campaign_id` không được liên kết; không có purchase event thật, không suy conversion/attribution theo phiên. |
| Các bước chạy theo khung giờ cố định trong một ngày | Không có phân phối giờ truy cập, độ trễ thanh toán, SLA giao 2–5 ngày hay hàng chờ giao qua nhiều ngày. Nhiều hành động cùng loại có cùng timestamp. |
| Chọn sản phẩm/khách chủ yếu ngẫu nhiên trong nhóm hợp lệ | Chưa có best seller, phân phối giá, người mua quay lại theo cohort, nhu cầu theo danh mục hoặc shop. Checkout chọn sản phẩm trước khi kiểm tồn, không tự chọn lại SKU khác khi hết hàng. |
| Mỗi checkout một SKU, một shop; tham số cố định | Không có giỏ nhiều sản phẩm/nhiều seller, tách kiện/đơn, phối trộn số lượng và phương thức thanh toán trong cùng một ngày cho cùng hành động. |
| Giao thất bại chưa có xử lý hệ quả đầy đủ | Không nên bật tỷ lệ thất bại giao hàng cho một kịch bản đóng vòng nghiệp vụ; chưa có hoàn hàng, giao lại, hoàn kho và hoàn tiền đi kèm. |
| Hủy giới hạn ở đơn chưa có vận đơn/chưa thanh toán thành công | Không có hủy sau trả tiền hoặc hủy một phần. Retry được hỗ trợ một phần nhưng thứ tự cố định khiến chưa thể tạo luồng retry nhiều lần có SLA; mẫu tắt retry. |
| Voucher chưa nối với checkout | `total_discount_amount`, `shipping_discount_amount` vẫn 0; `order_item_promotions` không được lấp bởi bộ mẫu. |
| Phí vận chuyển đơn đang là 0, chi phí vận đơn cố định | Không mô phỏng phí theo địa chỉ/cân nặng/kho/carrier, thuế, phụ phí hoặc lợi nhuận. `cost_price` sản phẩm chưa có cơ sở để tự điền. |
| Chưa sinh nghĩa vụ đối soát | `seller_payouts` vẫn rỗng; chính sách hoa hồng có dữ liệu không có nghĩa đã tính/thu/chi đúng dòng tiền. |
| Báo cáo quảng cáo chưa gắn traffic/đơn | Impressions = clicks × 100 trong code, tương đương CTR 1% cố định. Tạo chiến dịch không tự tăng traffic hoặc đơn; file cấu hình chỉ làm tổng lượng biến thiên theo lịch. |
| Giỏ chưa chuyển sang trạng thái đã mua | Tất cả giỏ còn hoạt động cuối ngày có thể bị đánh dấu Abandoned dù cùng khách có đơn riêng. Không thể phân tích tỷ lệ bỏ giỏ thực tế. |
| Sự kiện tìm kiếm không lưu từ khóa; chuỗi sự kiện chưa có logic đầy đủ | Không thể phân tích hành trình clickstream hoặc từ khóa tìm kiếm như dữ liệu sản xuất. |
| Một kho/carrier nền, nhập hàng ngẫu nhiên | Không có nhiều kho theo vùng, điều chuyển, mua bổ sung theo điểm tái đặt/lead time. |
| Hồ sơ và rating mẫu đơn giản | Địa chỉ/tên/điện thoại giả, nhóm địa lý cố định, đánh giá 4 sao; chưa có phân phối nhân khẩu/điểm sao hay độ trễ đánh giá. |
| Chỉ append catalog Tiki | Giá, `quantity_sold`, `review_count` nguồn là snapshot, không tự trở thành chỉ số tích lũy của giao dịch mock. Cần tổng hợp lại từ bảng nghiệp vụ khi phân tích. |
| Kiểm tra cuối ngày chỉ bao phủ những invariant đã triển khai | “Kiểm tra đạt” không phải chứng nhận mọi ràng buộc/nghiệp vụ của một sàn thực tế đều đầy đủ. |

Muốn vượt các giới hạn này cần nâng cấp engine/schema phù hợp, không chỉ đổi JSON. Bộ mẫu ưu tiên dữ liệu có liên kết và giải thích được trong phạm vi code đang có.
