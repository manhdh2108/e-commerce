# Các bộ cấu hình hiện hành

Mỗi loại giữ một mẫu cơ bản, một bản đầy đủ và một bản quy mô vừa được bổ sung theo yêu cầu. Có tổng cộng sáu file JSON; README và hướng dẫn không phải file cấu hình.

| Loại | Mẫu cơ bản | Bản đầy đủ mới nhất | Nhập ở đâu? |
|---|---|---|---|
| Kịch bản hành động | [first-run-cod.json](scenarios/first-run-cod.json) | [upgraded-linked-2026.json](scenarios/upgraded-linked-2026.json) | Tab **Cấu hình kịch bản → Nhập / Xuất cấu hình JSON** |
| Chính sách / Hồ sơ | [policy-only.json](settings/policy-only.json) | [diverse-ecommerce.json](settings/diverse-ecommerce.json) | Tab **Thiết lập → Nhập thiết lập bằng JSON** |

Import thiết lập: kiểm tra → điền form → bấm **Lưu chính sách / Lưu hồ sơ** tương ứng. Import kịch bản: xem trước → lưu một cấu hình hành động. Cả hai không tự cào, đồng bộ, bootstrap, chạy mock hay thay dữ liệu OLTP hiện có.

Bộ quy mô vừa: [medium-ecommerce.json](settings/medium-ecommerce.json) và [medium-linked-2026.json](scenarios/medium-linked-2026.json). Mục tiêu khoảng 1.000 lượt đặt/ngày thường. Đọc [hướng dẫn quy mô vừa](MEDIUM_SCALE.md) trước khi nhập.

[Hướng dẫn thiết lập](settings/README.md) · [Hướng dẫn engine v2](../guides/ENGINE_V2_UPGRADE_GUIDE.md).

Bản đầy đủ mới nhất khai báo 21 nhóm tác động, phân bố thuộc tính/tồn đầu, lịch tương đối theo phiên và lookup tham số theo điều kiện. Đọc [hướng dẫn engine cấu hình](../guides/CONFIG_DRIVEN_ENGINE_GUIDE.md) trước khi nhập. Để áp hồ sơ cho seller mới, lưu thiết lập trước lần đồng bộ đầu tiên; không ghi đè seller đã có.

Bản mới sau rà soát có 52 hành động bật, 20 bộ địa phương ở bốn thành phố, năm carrier, lịch theo trọng số và các nhánh retry/hủy/từ chối. Xem [hướng dẫn vận hành 2026](../guides/REALISTIC_OPERATIONS_2026.md) để biết semantics, giới hạn và cách dùng trên DB đã có dữ liệu.
