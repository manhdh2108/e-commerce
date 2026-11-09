# Nền code của quybruno và main sau tích hợp DW

Đã fetch origin và kiểm tra ngày 08/11/2026. Giờ trong bảng là +07:00. Đây là lịch sử commit, không phải thời điểm xác nhận người viết thực hiện git pull.

## Kết luận có bằng chứng

`git merge-base origin/main origin/quybruno` trả về **19c09913f3ffcea0545070ee0f03793c004a802d**, commit **update: ảnh dữ liệu schema**, tạo lúc **05/11/2026 21:44:42**.

Commit **edbfb8b** (ET) của quybruno được tạo lúc **08/11/2026 00:30:38** và có đúng một parent là **19c0991**. Không có merge/rebase chứa bốn commit nâng cấp main bên dưới trong ancestry của quybruno đang công khai.

Do đó có thể kết luận: **quybruno chưa tích hợp đầy đủ lịch sử main sau nền 19c0991**. Không thể xác định “người đó đã pull chính xác lúc 21:44:42 ngày 05/11” hoặc “chưa từng pull/fetch/copy code mới”: timestamp là lúc commit được tạo; reflog trên máy người khác không có ở đây, và code có thể được copy, checkout file, cherry-pick một phần hoặc xử lý stash.

## Bốn commit main còn thiếu trong ancestry của quybruno

| Commit | Thời điểm tạo | Thay đổi quan trọng đã kiểm tra trong diff |
|---|---|---|
| b45f6d5 | 05/11/2026 23:39:00 | Nâng engine 33 bảng, migration, liên kết checkout/giỏ/đơn, chính sách/profile, đối soát; tổ chức lại tài liệu. |
| 922fb12 | 05/11/2026 23:45:37 | Dọn config cũ, phân loại bộ mẫu/đầy đủ, cập nhật nhập/xuất và kiểm tra. |
| 04b0201 | 06/11/2026 15:12:56 | Nâng cơ chế config thực thể/hành vi/thời gian; sửa tính thực tế; refactor package thành application/config/engine/infrastructure/interfaces/integrations/diagnostics/resources. |
| 20d3a2f | 06/11/2026 18:07:35 | Bộ cấu hình khoảng 1.000 lượt đặt/ngày thường và hướng dẫn quy mô vừa; cập nhật bộ khoảng 100 lượt/ngày. |

Không suy nội dung chỉ từ tiêu đề commit: đã đọc diff. Đặc biệt 04b0201 mang cả nâng cấp code lớn, dù tiêu đề chỉ là “config mới”.

## Vì sao code quybruno trông có cả phần mới lẫn cũ?

Nhánh vẫn dùng module phẳng `scripts/mock_platform/domain.py`, `storage.py`, `worker.py` của nền cũ, nhưng thêm `engine/actors.py`, `engine/finance.py`, `engine/selection.py` dựa trên code mới. Những marker đã commit ghi đồng thời đường dẫn cũ và đường dẫn mới, với nhãn Updated upstream/Stashed changes.

Đó là bằng chứng source bị pha trộn, không phải một bản engine cũ thuần túy và cũng chưa phải bản main mới hoàn chỉnh. Không đủ căn cứ tái dựng thao tác Git trên máy tác giả hoặc quy trách nhiệm một thao tác cụ thể.

Main đã rename/refactor file; Git có thể nhận diện rename khi merge, nhưng không thể tự giải quyết những khác biệt nghiệp vụ và code đang dở. Đây là nguyên nhân hợp lý của sáu conflict đã ghi trong báo cáo review trước.

## Main hiện tại sau PR DW

Sau fetch:

- origin/main: **031c3b7**, PR #3, tạo 08/11/2026 **20:22:27**.
- Commit đưa DW vào: **98725d2**, dựa trên **20d3a2f**.
- So sánh `20d3a2f..origin/main` cho scripts/mock_platform, start_mock.sh, compose.mock.yaml và docs/mock-design: **không có khác biệt**.
- So sánh thư mục dw giữa origin/quybruno và origin/main: **giống nhau**.
- Phần mock hỏng trên quybruno chưa đi vào main qua PR này. Code DW được lấy sang; điều này không xác nhận DW đã chạy đúng hoặc các vấn đề review đã được sửa.
- Việc lấy file DW sang một commit mới không làm edbfb8b trở thành ancestor của main. merge-base với quybruno vẫn là 19c0991; đây là kết quả đúng, không phải dấu hiệu merge DW thất bại.
- Checkout local hiện là integrate/dw-only ở 98725d2; main local vẫn 20d3a2f, chậm hai commit so với origin/main. Phân tích sau merge phải dùng origin/main hoặc main local đã cập nhật.

## Nền tổ chức code nên dùng

1. Dùng main hiện tại (031c3b7 tại thời điểm kiểm tra) làm nền tiếp tục phát triển, không lấy cây thư mục quybruno làm chuẩn.
2. Giữ package mock hiện tại trong scripts/mock_platform, crawler riêng và Control/Business DB tách biệt. Giữ dw riêng cho lớp kho dữ liệu; không chuyển ETL vào engine mock để né import conflict.
3. Sửa đường dẫn tài liệu DW về cấu trúc docs/data-model/warehouse hiện có; sửa các link sau khi chuyển, không giữ hai bản tài liệu cùng nội dung làm nguồn chuẩn cạnh tranh nhau.
4. Với code mock của quybruno chưa nhận: tách ý tưởng sửa finance và tối ưu, port từng thay đổi lên module mới, có test và benchmark. Không copy lại ba module phẳng hoặc merge lại toàn commit ET mà không kiểm soát.
5. Profile dw-lite/dw-scd và runner là phần tùy chọn chưa có trong PR DW; chỉ nhận khi có nhu cầu và đã sửa các vấn đề trong báo cáo trước. Giữ bộ cấu hình quy mô vừa trên main.
6. Người tiếp tục làm DW nên bắt đầu nhánh mới từ main hiện tại hoặc cập nhật nhánh phát triển trên nền đó trước khi sửa. Ghi commit nền trong báo cáo/test để tránh nhầm “code đã chạy ở máy tác giả” với “code đúng phiên bản hiện tại”.

Tham khảo [review chi tiết trước tích hợp](QUY_BRANCH_MERGE_REVIEW_2026-11-08.md) cho danh sách file, lỗi và tiêu chí kiểm chứng. Báo cáo trước mô tả thời điểm chưa tích hợp DW; không dùng trạng thái trước đó để suy rằng main hiện tại cũng chứa các file conflict.

Chưa checkout, merge, reset, chỉnh code hoặc truy cập/sửa DB trong lần xác minh lịch sử này. Chỉ fetch, đọc lịch sử/diff và ghi báo cáo.
