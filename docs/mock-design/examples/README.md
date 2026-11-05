# Bốn file cấu hình hiện hành

Mỗi loại giữ một mẫu cơ bản và một bản đầy đủ mới nhất. Các file JSON/CSV kịch bản cũ đã được dọn; README và hướng dẫn không phải file cấu hình.

| Loại | Mẫu cơ bản | Bản đầy đủ mới nhất | Nhập ở đâu? |
|---|---|---|---|
| Kịch bản hành động | [first-run-cod.json](scenarios/first-run-cod.json) | [upgraded-linked-2026.json](scenarios/upgraded-linked-2026.json) | Tab **Cấu hình kịch bản → Nhập / Xuất cấu hình JSON** |
| Chính sách / Hồ sơ | [policy-only.json](settings/policy-only.json) | [diverse-ecommerce.json](settings/diverse-ecommerce.json) | Tab **Thiết lập → Nhập thiết lập bằng JSON** |

Import thiết lập: kiểm tra → điền form → bấm **Lưu chính sách / Lưu hồ sơ** tương ứng. Import kịch bản: xem trước → lưu một cấu hình hành động. Cả hai không tự cào, đồng bộ, bootstrap, chạy mock hay thay dữ liệu OLTP hiện có.

[Hướng dẫn thiết lập](settings/README.md) · [Hướng dẫn engine v2](../guides/ENGINE_V2_UPGRADE_GUIDE.md).
