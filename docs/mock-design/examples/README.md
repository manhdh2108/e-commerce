# Cấu hình mẫu — chọn đúng nơi nhập

| Thư mục | Dùng ở đâu? | Nội dung |
|---|---|---|
| [scenarios/](scenarios/) | Tab **Cấu hình kịch bản → Nhập / Xuất cấu hình JSON** | Hành động, quota theo ngày, profile trọng số, tham số và độ trễ. |
| [settings/](settings/) | Tab **Thiết lập → Chính sách / Hồ sơ mô phỏng → Nhập thiết lập bằng JSON** | Ba chỉ số chính sách và hồ sơ họ tên, đầu số, địa phương, kho, carrier. |

- Bắt đầu với [bộ thiết lập đa dạng](settings/diverse-ecommerce.json), sau đó dùng [kịch bản liên kết v2](scenarios/upgraded-linked-2026.json).
- Nếu chỉ muốn điền ba ô chính sách, dùng [policy-only.json](settings/policy-only.json).
- Import thiết lập chỉ điền form sau khi xem trước; bạn phải bấm các nút **Lưu chính sách / Lưu hồ sơ** để lưu.
- Import kịch bản lưu một cấu hình hành động; không tự thay chính sách hoặc hồ sơ.
- Cả hai không tự cào, đồng bộ, tạo dữ liệu nền hoặc chạy mock.

[Hướng dẫn chi tiết thiết lập](settings/README.md) · [Hướng dẫn engine v2](../guides/ENGINE_V2_UPGRADE_GUIDE.md).
