# Mock Studio

Ứng dụng local Python OOP, code dưới `scripts/mock_platform/`. Có 7 trang UI, 6 tab cấu hình, API và worker độc lập. Đầu ra PostgreSQL tách khỏi dữ liệu điều khiển.

## Khởi động

Chạy từ thư mục gốc repository:

```bash
uv pip install --python .venv/bin/python -r scripts/requirements-mock.txt
docker compose -f scripts/compose.mock.yaml up -d --wait
scripts/start_mock.sh
```

Mở [Mock Studio](http://127.0.0.1:8765/). Dừng ứng dụng bằng Ctrl+C; dữ liệu PostgreSQL vẫn được giữ trong Docker volume. Không dùng `down --volumes` nếu muốn giữ dữ liệu.

Hai tiến trình có thể chạy riêng:

```bash
.venv/bin/python -m scripts.mock_platform serve --port 8765
.venv/bin/python -m scripts.mock_platform worker
```

Đổi kết nối bằng `MOCK_CONTROL_URL` và `MOCK_BUSINESS_URL` trước khi chạy cả hai tiến trình. Các URL phải trỏ hai database khác nhau. Mặc định local:

- Control: `127.0.0.1:55432/mock_control`.
- Business: `127.0.0.1:55432/mock_oltp`.
- User: `mock`; mật khẩu local mặc định trong compose là `local_mock_only`. Nếu đổi `MOCK_POSTGRES_PASSWORD` lúc tạo volume, cập nhật cả hai URL tương ứng. Đổi biến môi trường không đổi mật khẩu của volume đã được tạo.

Database nghiệp vụ chưa tự tạo bảng khi chỉ mở ứng dụng. Người dùng chọn “Chuẩn bị môi trường” để tạo 27 bảng. Business DB chỉ có bảng nghiệp vụ; config/checkpoint/job nằm ở `mock_control.control_records`, phân nhóm bằng `kind` và khóa `id`. Đây là thiết kế lưu tài liệu JSON cho bản local, chưa phải toàn bộ các bảng vật lý gợi ý trong kế hoạch.

## Dùng lần đầu

1. **Thiết lập:** chọn ngày bắt đầu, seed và đường dẫn crawler. Kiểm tra kết nối, rồi chuẩn bị môi trường.
2. **Đồng bộ Tiki:** xem trước và nhập mới. Giá/bản ghi cũ không được sửa. SKU trùng/thiếu hoặc chào bán xung đột được báo lỗi. Hạ tầng crawler hiện chỉ lưu chào bán mới nhất theo product ID nên không thể phát hiện lịch sử chào bán đã bị nguồn ghi đè và không còn lưu.
3. **Thiết lập → Dữ liệu nền:** nhập số khách và tồn đầu/SKU. Chạy một lần, tạo kênh/phương thức, một kho/carrier thử nghiệm. Không tự làm khi sync.
4. **Cấu hình:** chọn hệ thống → nhóm → hành động. Nhập số ngày thường, các ngày đặc biệt và trường riêng. Số đặc biệt thay thế số thường. Lưu bản nháp hoặc phiên bản; cả hai không ghi Business DB.
5. **Lập kế hoạch:** chọn phiên bản và khoảng ngày từ checkpoint; xem trước rồi chạy.
6. **Theo dõi:** xem kết quả, gửi pause và resume. Tác vụ dang dở phải được hoàn tất trước khi xếp tác vụ ghi mới.
7. **Lịch sử:** xem dữ liệu phân trang, kiểm tra tiền/tồn/thời gian và các lỗi nghiệp vụ.

Các hành động hỗ trợ chế độ theo đầu vào có dropdown riêng. Chọn tự động thì quota thường/đặc biệt không áp dụng. Chỉ xử lý đối tượng hiện đủ điều kiện trong giai đoạn của ngày; không tạo thêm đầu vào để đủ việc. Bản đầu chưa mô phỏng độ trễ carrier/thanh toán theo nhiều ngày; thời điểm của từng giai đoạn trong ngày được engine sắp xếp cố định và hiển thị trong kết quả.

## Gói thử luồng COD

Sau khi đã có catalog và tồn đầu, đặt số ngày thường 2 cho mỗi hành động sau và bật chúng:

- `CUS-05`: đặt hàng đăng nhập, COD, số lượng 1.
- `ORD-01`: xác nhận đơn.
- `DSP-01`: tạo vận đơn.
- `CAR-01`: lấy hàng.
- `CAR-02`: đang giao.
- `CAR-03`: kết quả giao, tỷ lệ thành công 100%.
- `CAR-04`: thu COD.
- `AUT-WH-04`: chốt tồn cuối ngày, chỉ cần số lần 1.

Có thể chọn tự động xử lý cho các bước xử lý đơn/vận đơn. Cần có khách nền, sản phẩm đang bán và tồn kho. Lưu phiên bản rồi chạy một ngày. Nếu thiếu điều kiện, xem dòng kết quả bị từ chối; không có chuyện tăng tồn giả để đủ số đơn.

Bản đầu một sản phẩm và một shop/checkout; phí khách trả 0, chưa áp voucher. Đơn trả trước có thể chọn phương thức khác COD rồi bật `PAY-01` trước `ORD-01`. Hủy chỉ hỗ trợ trước có vận đơn và chưa thanh toán thành công; không làm mất nghĩa vụ hoàn tiền của đơn đã thu.

## DBeaver

Tạo kết nối PostgreSQL host `127.0.0.1`, port `55432`, database `mock_oltp`, user/password như trên. Mở schema `public`, refresh sau các transaction để xem dữ liệu. Kết nối `mock_control` riêng nếu muốn xem điều khiển. Không sửa Business DB bằng DBeaver trong lúc worker hoạt động vì sẽ làm sai bằng chứng phục hồi.

## Kiểm thử

```bash
.venv/bin/python -m pytest scripts/mock_platform/tests -q
```

Bộ test mặc định dùng hai SQLite riêng trong thư mục tạm. Test PostgreSQL tạo database kiểm thử riêng và dọn sau test; tài khoản cần quyền tạo database:

```bash
MOCK_TEST_POSTGRES='postgresql+psycopg://mock:local_mock_only@127.0.0.1:55432/mock_control' .venv/bin/python -m pytest scripts/mock_platform/tests -q
```

Đã kiểm tra append-only, không ghi khi preview, quota đặc biệt, pipeline COD, thanh toán trả trước, hai DB tách biệt, chặn nhảy ngày, pause/resume, chống gửi lặp, xung đột SKU, kiểm tra chủ sản phẩm và phục hồi sau target commit. Không phải benchmark cả năm/hàng triệu dòng.

## Phần còn giới hạn

Xem [trạng thái triển khai](../../docs/mock-design/MOCK_IMPLEMENTATION_STATUS.md). Các hành động chưa có quy tắc dữ liệu đầy đủ được giữ trên UI, tắt và giải thích lý do. Không coi có form là toàn bộ nghiệp vụ đã hoàn tất.

Bản local chưa có authentication nhiều người dùng. Chỉ bind localhost, kiểm tra Host/Origin. Không mở cổng ứng dụng ra mạng công cộng. Bản đầu không có xóa/reset qua UI, distributed worker, sửa schema cũ tự động hoặc hiệu năng đã benchmark quy mô lớn.
