# Đánh giá các bảng Fact — Đề xuất "Kho dữ liệu cho sàn TMĐT đa người bán"

Nguồn: `DeXuat_KhoDuLieu_TMDT.pdf` (mục 4.1, 4.2, 5 — Bảng 6, 7, 8, 9).

Nhận định chung: 3 fact (`Fact_Order_Item`, `Fact_Inventory_Snapshot`,
`Fact_Ad_Spend`) được phân loại đúng mẫu Kimball (transaction / periodic
snapshot / periodic), đo lường additive / semi-additive / non-additive được
xử lý đúng nguyên tắc. Các vấn đề dưới đây là những điểm **cần làm rõ hoặc bổ
sung** trước khi triển khai ETL, không phải lỗi thiết kế nền tảng.

---

## 1. `Fact_Order_Item`

### Vấn đề

`Date_Key` của fact chưa được chốt rõ: grain quy định "một dòng sản phẩm
trong một đơn hàng **giao thành công**", nhưng tài liệu không nói `Date_Key`
lấy theo ngày đặt hàng hay ngày giao thành công. Hai cách tính cho ra kết quả
"doanh thu theo tháng" khác nhau — đây là câu hỏi nghiệp vụ số 1 của đề tài,
nên sự mơ hồ này ảnh hưởng trực tiếp tới tính đúng của toàn bộ dashboard.

### Cách cải thiện

Thêm vào mục 4.1, ngay dưới Bảng 6:

> *"Date_Key của Fact_Order_Item lấy theo ngày đơn hàng chuyển trạng thái
> Completed (ngày giao thành công), không phải ngày đặt hàng. Ngày đặt hàng
> (`order_date`) được lưu như một thuộc tính degenerate để tham chiếu, không
> có vai trò dimension riêng do ngoài phạm vi giao vận thật."*

Ở tầng nguồn OLTP, dùng cột `item_status` trên `order_items` làm điều kiện lọc:
ETL nạp các dòng `Fulfilled` và `Returned` của đơn `Completed`, bỏ dòng
`Cancelled`. Hàng hoàn sau khi giao được ghi nhận riêng ở `Fact_Return`, nên
doanh số đã bán không bị mất.

---

## 2. `Fact_Inventory_Snapshot`

### Vấn đề 2.1 — Thiếu lịch sử giá vốn cho `inventory_value`

`inventory_value` cần đơn giá vốn tại **đúng thời điểm snapshot**, nhưng
Bảng 8 chỉ liệt kê SCD loại 2 cho Product ở "giá niêm yết, danh mục" — không
có giá vốn. Nếu dùng giá vốn hiện tại để tính giá trị tồn kho cho các ngày
quá khứ thì kết quả sẽ sai.

**Cách cải thiện:** sửa dòng Product trong Bảng 8 thành:

> Product: ... SCD 2 (giá niêm yết, **giá vốn**, danh mục); SCD 1 (tên sai)

### Vấn đề 2.2 — Không có `Seller_Key`, chưa nêu giả định về kho

Fact không có `Seller_Key` trong ma trận bus. Với mô hình "đa người bán", nếu
seller tự quản kho riêng (self-fulfilled) thay vì kho do sàn vận hành, câu
hỏi "tồn kho theo người bán" không trả lời được trực tiếp. Tài liệu chưa nêu
rõ giả định này.

**Cách cải thiện:** thêm vào mục 4.2:

> *"Giả định: toàn bộ kho trong phạm vi đề tài do sàn vận hành (fulfillment
> center), không mô phỏng kho riêng của từng người bán. Muốn biết tồn kho
> theo người bán, suy ra gián tiếp qua Product → Seller."*

Nếu nhóm muốn mô hình thực tế hơn và còn thời gian, có thể thêm `Seller_Key`
trực tiếp vào fact và cập nhật Bảng 7 — coi là phần mở rộng, không bắt buộc.

### Vấn đề 2.3 — Chưa rõ nguồn sinh snapshot hằng ngày

Grain "sản phẩm – kho – ngày" bắt buộc phải dựng lại được tồn kho ở **mọi
ngày trong quá khứ**. OLTP thật chỉ giữ trạng thái hiện tại
(`quantity_on_hand`), không đủ để tái tạo lịch sử nếu không có sổ cái giao
dịch kho.

**Cách cải thiện:** thêm vào Bảng 4 (Nguồn dữ liệu), dòng "Kho vận":

> Tồn kho cuối ngày theo kho (dựng từ sổ cái giao dịch kho
> `inventory_movements`: nhập/xuất/điều chỉnh, replay theo ngày)

Ở tầng nguồn OLTP, bổ sung bảng `inventory_movements`
(`warehouse_id, product_id, movement_type, quantity_change, movement_date`)
làm nguồn để ETL replay ra snapshot từng ngày.

---

## 3. `Fact_Ad_Spend`

### Vấn đề

Không có vấn đề nghiêm trọng. Tài liệu đã tự nêu đúng giới hạn: fact không có
`Product_Key`/`Seller_Key` nên chi phí quảng cáo không tự phân bổ xuống sản
phẩm/người bán được. Grain tháng (tách riêng `Dim_Month` khỏi `Dim_Date`) là
lựa chọn hợp lý vì nguồn marketing chỉ có độ chi tiết tháng.

### Cách cải thiện (tuỳ chọn, không bắt buộc)

Nếu nhóm muốn mở rộng, có thể định nghĩa thêm một **quy tắc phân bổ** (vd.
theo tỷ trọng doanh thu sản phẩm/seller trong cùng tháng–kênh) để tính chi
phí quảng cáo quy đổi xuống sản phẩm — nhưng phải ghi rõ đây là ước lượng,
không phải chi phí thực, để không gây hiểu nhầm nhân quả.

---

## 4. Vấn đề chung cho cả 3 fact — Bridge khuyến mãi

### Vấn đề

Bảng 9 quy định điều kiện đúng của Bridge khuyến mãi là "Tổng weight mỗi
nhóm = 1", nhưng không định nghĩa rõ **"nhóm"** là gì: theo từng
`order_item_id`, hay tách riêng theo loại voucher (sàn / seller)? Nếu không
chốt công thức, các thành viên code ETL khác nhau có thể hiểu khác nhau.

### Cách cải thiện

Thay điều kiện đúng của Bridge trong Bảng 9 bằng ví dụ cụ thể:

> *"Nhóm = toàn bộ voucher áp dụng trên một `order_item` (không tách theo
> loại sàn/seller). Ví dụ: dòng hàng dùng 1 voucher sàn giảm 20.000đ và 1
> voucher seller giảm 10.000đ, `discount_amount` gốc = 30.000đ →
> `weighting_factor` lần lượt là 20.000/30.000 = 0,667 và 10.000/30.000 =
> 0,333, tổng = 1."*

---

## 5. Tổng hợp mức ưu tiên

| # | Vấn đề | Fact liên quan | Mức độ |
|---|---|---|---|
| 1 | `Date_Key` chưa chốt (ngày đặt vs ngày giao) | Fact_Order_Item | Bắt buộc |
| 2 | Thiếu SCD2 cho `cost_price` | Fact_Inventory_Snapshot | Bắt buộc |
| 3 | Thiếu nguồn `inventory_movements` để dựng snapshot | Fact_Inventory_Snapshot | Bắt buộc |
| 4 | Công thức "nhóm" trong Bridge khuyến mãi chưa rõ | Fact_Order_Item | Bắt buộc |
| 5 | Giả định kho do sàn vận hành chưa nêu | Fact_Inventory_Snapshot | Nên làm |
| 6 | Quy tắc phân bổ chi phí quảng cáo xuống sản phẩm | Fact_Ad_Spend | Tuỳ chọn / mở rộng |
