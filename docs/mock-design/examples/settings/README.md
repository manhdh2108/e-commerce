# Thiết lập chính sách và hồ sơ bằng JSON

## Dùng trên UI

1. Vào **Thiết lập**, tìm khối **Nhập thiết lập bằng JSON** phía trên Chính sách mô phỏng.
2. Chọn file hoặc dán JSON.
3. Bấm **Kiểm tra & xem trước**: xem các giá trị chính sách, số hồ sơ và thông báo phạm vi áp dụng.
4. Bấm **Điền vào biểu mẫu**: các ô tương ứng bên dưới được điền. Lúc này **chưa lưu** và có thể sửa tiếp.
5. Bấm **Lưu chính sách cho kế hoạch mới** và/hoặc **Lưu hồ sơ mô phỏng** theo các phần đã nhập.

File chỉ có chính sách sẽ giữ nguyên các ô hồ sơ. File chỉ có hồ sơ sẽ giữ nguyên các ô chính sách. File sai không điền hoặc lưu một phần. Sửa nội dung JSON sau khi xem trước thì phải kiểm tra lại trước khi điền.

## Các mẫu

| File | Nội dung |
|---|---|
| [diverse-ecommerce.json](diverse-ecommerce.json) | Đầy đủ chính sách và hồ sơ đa dạng theo các trường generator hiện hỗ trợ. |
| [policy-only.json](policy-only.json) | Chỉ ba ô chính sách, không thay hồ sơ thực thể. |
| [medium-ecommerce.json](medium-ecommerce.json) | Hồ sơ cho quy mô khoảng 1.000 lượt đặt/ngày; dùng cùng kịch bản medium. Xem [hướng dẫn](../MEDIUM_SCALE.md). |

Bộ đa dạng gồm **32 họ × 64 tên = tối đa 2.048 tổ hợp tên**, **30 đầu số**, **24 bộ địa phương ở 3 thành phố**, **6 kho**, **5 carrier**. Tên không phải khóa; có thể trùng tên/điện thoại và ID khách vẫn riêng.

Địa phương, địa chỉ, kho và carrier là dữ liệu tổng hợp có tên mô phỏng. District để NULL có chủ đích; không giả rằng đây là địa giới hiện hành. Tên các carrier không tạo ra khác biệt SLA/biểu cước/phạm vi vận chuyển: engine hiện chưa có những chính sách đó.

Mẫu giữ ba thành phố mà form hành động hiện hỗ trợ: TP. Hồ Chí Minh, Hà Nội, Đà Nẵng. Tám bộ địa phương mỗi thành phố giúp đa dạng địa chỉ trong khi vẫn khớp province mà kịch bản đăng ký/thêm địa chỉ truyền vào. Không tự mở thêm tỉnh trong registry hành động.

Chính sách mẫu: **7 ngày** yêu cầu trả, **10 ngày** giữ tiền trước đối soát, **3 lần** giao tối đa. Đây là giả định thử nghiệm có thể chỉnh, không phải chính sách Tiki. Thời gian giữ tiền phải dài hơn cửa sổ trả.

Ba giá trị chính sách là giá trị chung, không phải danh sách phân bố theo khách/ngày. Muốn đa dạng phương thức thanh toán, thiết bị, sao đánh giá hoặc quota ngày sale, cấu hình trong [scenarios/](../scenarios/). Không thêm các khóa tỷ lệ, phí hoàn hay SLA chưa được code hỗ trợ vào file này.

## Lưu ý về DB đã có dữ liệu

- Lưu thiết lập ở Control DB, không cập nhật hồ sơ/địa chỉ đã sinh hoặc ghi sang SQLite crawler.
- Kế hoạch/job đã có giữ snapshot; đơn đã tạo giữ chính sách đã chốt. Hãy lập kế hoạch mới để dùng thiết lập vừa lưu.
- Kho/carrier được tạo khi bootstrap môi trường mới. Import sau bootstrap không tạo thêm hoặc sửa master đang có trong OLTP.
- Tồn nền là **mỗi SKU tại mỗi kho**: mẫu 6 kho, chọn tồn 100 nghĩa tổng 600 đơn vị mỗi SKU khi bootstrap. Import không tự điền số khách hay tồn đầu, không tự bootstrap.
- Không cần reset để thử nhập/điền form. Chỉ reset khi chủ động muốn xóa toàn bộ dữ liệu và bắt đầu lại.

## Định dạng

File đầy đủ hoặc một phần dùng envelope:

```json
{
  "format": "mock-studio-settings",
  "format_version": 1,
  "name": "Tên bộ thiết lập",
  "business_policy": {
    "return_window_days": 7,
    "payout_hold_days": 10,
    "max_delivery_attempts": 3
  }
}
```

Thêm `entity_profile` nếu cần; xem file đầy đủ để biết chính xác sáu danh sách và các trường được hỗ trợ. Có thể bỏ `business_policy` khi chỉ nhập hồ sơ. Không chấp nhận khóa lạ hoặc mã kho/carrier trùng.

Nếu chỉ nhập chính sách, cũng chấp nhận object trực tiếp như `policy-only.json`:

```json
{
  "return_window_days": 7,
  "payout_hold_days": 10,
  "max_delivery_attempts": 3
}
```

API `POST /api/settings-imports/preview`, body `{"text": "...nội dung JSON..."}`, chỉ kiểm tra/trả dữ liệu để điền form. Giới hạn 2 MiB, từ chối JSON lặp khóa/số không hợp lệ. Việc lưu tiếp tục dùng `PUT /api/business-policy` và `PUT /api/entity-profile`.
