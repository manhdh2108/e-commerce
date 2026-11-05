# Hướng dẫn Tổng quan, crawler và chạy lại dữ liệu

## Mở web

Tại thư mục gốc repository:

```bash
./scripts/start_mock.sh
```

Mở http://127.0.0.1:8765/ và chọn **Tổng quan**. Script chỉ bật API, worker nghiệp vụ và worker crawler; không tự cào, đồng bộ hoặc sinh dữ liệu. Nếu đang chạy bản cũ, dừng bằng Ctrl+C rồi chạy lại lệnh trên. Dùng Ctrl+Shift+R để lấy JavaScript mới.

## Dashboard OLTP

Đọc trực tiếp Business DB (`mock_oltp`, schema `public` với thiết lập mặc định), tự làm mới mỗi 5 giây:

- Số đơn, khách hàng, phiên truy cập, tổng số dòng trên 27 bảng.
- Giá trị toàn bộ đơn, giá trị đơn hoàn tất, tổng thanh toán thành công, chi phí quảng cáo. Giá trị toàn bộ đơn có cả đơn hủy/chưa thanh toán; các chỉ số này không phải lợi nhuận.
- Biểu đồ 30 **ngày có đơn gần nhất**, nhóm theo ngày tạo đơn mô phỏng. Mở “Xem số liệu từng ngày” để đọc giá trị chính xác. Không tự thêm các ngày không có đơn vào biểu đồ.

Theo yêu cầu tinh gọn giao diện, dashboard giữ 8 ô thống kê chính; không hiển thị các khối trạng thái, tồn kho, vận đơn/đánh giá, khuyến mãi, giỏ hàng, hoa hồng và đối soát. Dữ liệu này vẫn có thể xem tại Lịch sử & Dữ liệu.

Catalog bao gồm dữ liệu đã đồng bộ từ Tiki; khách hàng gồm cả khách nền và khách sinh thêm. Số liệu trên dashboard là trạng thái hiện có của OLTP. Lịch sử Control DB sau thao tác xóa không được cộng vào dashboard.

## Cào Tiki, chưa đồng bộ

1. Bấm **Cào Tiki** trên đầu Tổng quan để tới form.
2. Có thể nhập ID danh mục gốc, cách nhau bằng dấu phẩy; để trống dùng tất cả 26 danh mục của crawler. Ví dụ `8322` là Nhà Sách Tiki. Khoảng nghỉ mặc định 4–8 giây/request như CLI hiện có.
3. Nếu cần tiếp tục một lượt cào gián đoạn, nhập mã `crawl_run_id` từ log. Để trống ID danh mục khi muốn dùng lại toàn bộ danh mục của lượt đó.
4. Bấm **Bắt đầu cào Tiki**. Tiến trình riêng gọi `scripts/crawl_tiki.py`, ghi vào SQLite đã chọn ở Thiết lập. Trang hiển thị trạng thái, thời điểm bắt đầu/kết thúc và log.
5. Có thể **Dừng cào, giữ các trang đã lưu**. Crawler hiện tại lưu checkpoint theo trang. Dừng/khởi động lại không xóa những trang đã commit.
6. Sang **Đồng bộ Tiki** để kiểm tra dữ liệu mới. Cào thành công không tự nhập OLTP.

Đóng tab không dừng crawler. Dừng toàn bộ server bằng Ctrl+C sẽ gửi tín hiệu dừng tới worker crawler và tiến trình con. Nếu worker bị mất đột ngột, hệ thống không tự khởi chạy lại lượt cào đó; kiểm tra log và mã tiếp tục trước khi kích hoạt lượt mới. Một worker crawler chạy trên cùng máy; đây không phải hàng đợi phân tán nhiều máy. Tránh chạy CLI crawler khác cùng nguồn khi crawler UI đang chạy.

Log: `data/mock-platform/crawler/<job-id>.log` (không đưa vào Git). Metadata lượt cào nằm trong Control DB, nhóm `crawl_jobs`. Crawler có thể bị Tiki từ chối truy cập hoặc gặp lỗi mạng; UI hiển thị lỗi từ crawler, không coi mọi lượt được kích hoạt là thành công.

## Kiểm tra nguồn ở tab Đồng bộ Tiki

- Xem **Đồng bộ thành công gần nhất** theo thời gian thực, tách biệt ngày mô phỏng. Sau xóa toàn bộ, lịch sử cũ vẫn còn nhưng không được tính là lần đồng bộ của dữ liệu hiện tại.
- Bấm **Kiểm tra sản phẩm mới trong SQLite**: đếm tổng sản phẩm nguồn, ID chưa có trong OLTP, số mới hợp lệ, ID đã có và các lỗi.
- Đếm theo **ID sản phẩm**, không so tổng dòng của hai database (SQLite có thêm raw/checkpoint/bảng phụ). ID chưa có có thể chưa đủ điều kiện nhập nếu thiếu/trùng SKU, chào bán xung đột hoặc thiếu trường bắt buộc.
- Kiểm tra này chỉ đọc; không gọi API Tiki, không lưu preview đồng bộ, không ghi OLTP.
- Muốn nhập: dùng **Xem trước đồng bộ → Thực hiện đồng bộ** như trước. Quy tắc append-only vẫn giữ nguyên.

## Xóa toàn bộ để chạy lại

1. Tại Tổng quan, bấm **Chạy lại từ đầu** để tới phần xóa.
2. Bấm **Xem trước dữ liệu sẽ xóa**, xem tổng và số dòng từng bảng.
3. Nhập chính xác `XOA TOAN BO`, rồi bấm **Xóa toàn bộ OLTP**.
4. Theo dõi job đến **Hoàn tất**. Không có nút khôi phục tự động.

Xóa mọi bản ghi của 27 bảng, gồm cả catalog và dữ liệu nền. Không xóa SQLite crawler, cấu hình kịch bản hoặc thiết lập ngày bắt đầu/seed. Checkpoint quay về chưa chạy ngày nào; kế hoạch và preview cũ hết hiệu lực. Các lượt cũ giữ lịch sử để đối chiếu và không thể tiếp tục ghi sau reset. Các manifest kỹ thuật có ảnh dữ liệu trước/sau để xử lý sự cố, không phải tính năng phục hồi cho người dùng.

Chặn xóa nếu còn job ghi đang chạy/chờ; hãy hoàn tất hoặc tạm dừng trước. Job đã tạm dừng/có lỗi có thể bị hủy bởi reset. Nếu dữ liệu thay đổi sau xem trước, phải xem trước lại. Xóa OLTP trong một transaction theo thứ tự khóa ngoại; lỗi giữa chừng sẽ rollback. Nếu OLTP đã commit nhưng cập nhật Control DB bị gián đoạn, tiếp tục job reset để worker đối chiếu manifest và hoàn tất checkpoint.

Sau xóa:

1. **Đồng bộ Tiki**: xem trước và nhập lại catalog từ SQLite.
2. **Thiết lập môi trường**: tạo lại khách nền, kho và tồn đầu.
3. **Cấu hình kịch bản**: dùng cấu hình đã giữ hoặc chỉnh sửa.
4. **Lập kế hoạch & Chạy**: xem trước mới, bắt đầu từ ngày bắt đầu đã thiết lập.

Không hỗ trợ xóa dữ liệu từ một ngày trở về trước rồi giữ các ngày sau vì có thể phá liên kết giữa đơn, khách, kho, thanh toán và dữ liệu lịch sử.
