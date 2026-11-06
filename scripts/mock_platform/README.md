# Mock Studio

Ứng dụng local Python OOP, code dưới `scripts/mock_platform/`. Có 7 trang UI, 6 tab cấu hình, API và worker độc lập. Đầu ra PostgreSQL tách khỏi dữ liệu điều khiển.

Người mới dùng: [Hướng dẫn đầy đủ từ pull đến lượt mock đầu tiên](../../docs/mock-design/guides/FIRST_MOCK_RUN_GUIDE.md), có ảnh dashboard, cấu hình 2 đơn COD và hướng dẫn từng trang UI.

## Cấu trúc source

```text
scripts/mock_platform/
├── __main__.py          # Điểm chạy serve / worker / crawl-worker / status
├── application/         # Điều phối use case, job, snapshot và thao tác dữ liệu
├── config/              # Kiểm tra/import config, profile, policy, sinh mẫu
├── engine/              # Thực thi hành động, actor, selector và workflow nghiệp vụ
├── infrastructure/      # Kết nối DB, transaction, migration và index
├── integrations/        # Kích hoạt/theo dõi crawler Tiki độc lập
├── interfaces/          # HTTP API và phục vụ giao diện
├── diagnostics/         # Kiểm tra dữ liệu và audit chỉ đọc
├── resources/           # Registry hành động, schema, mặc định và SQL khởi tạo
├── web/                 # HTML, CSS, JavaScript của UI
└── tests/               # Kiểm thử Python và JavaScript
```

Luồng chính: CLI/API gọi `application`; worker thực thi các workflow trong `engine` và ghi dữ liệu qua `infrastructure`. `config` chịu trách nhiệm định dạng và kiểm tra cấu hình; `resources` cung cấp đường dẫn tài nguyên tập trung, không phụ thuộc thư mục chạy lệnh. Crawler thật vẫn ở `scripts/crawl_tiki.py`; `integrations/crawler.py` chỉ điều phối tiến trình đó.

Thêm bộ sinh thuộc tính hoặc quy tắc config trong `config`; thêm rule hành động trong `engine`; thêm endpoint trong `interfaces`. Không đặt module nghiệp vụ mới ở thư mục gốc package. Việc gom package không đổi database, dữ liệu, API hay lệnh `scripts/start_mock.sh`.

Các module Python nội bộ đã chuyển đường dẫn; mã bên ngoài nếu import trực tiếp cần cập nhật, ví dụ `scripts.mock_platform.application.service.PlatformService` và `scripts.mock_platform.infrastructure.storage.Database`. Các lệnh công cụ hiện hành:

```bash
.venv/bin/python -m scripts.mock_platform.diagnostics.audit --help
.venv/bin/python -m scripts.mock_platform.infrastructure.migrations --help
.venv/bin/python -m scripts.mock_platform.infrastructure.indexes --help
.venv/bin/python -m scripts.mock_platform.config.scenario --help
```

Kế hoạch đã preview trước khi thay source cần preview lại theo fingerprint mới. Job/lịch sử đã hoàn tất được giữ nguyên.

## Nâng cấp engine v2

Xem [hướng dẫn v2](../../docs/mock-design/guides/ENGINE_V2_UPGRADE_GUIDE.md) trước khi chạy trên DB cũ: preview/apply migration, giữ dữ liệu lịch sử, cấu hình mới và các giả định chính sách. Mẫu mới tải trong tab Cấu hình hoặc [file JSON](../../docs/mock-design/examples/scenarios/upgraded-linked-2026.json).

## Khởi động

Chạy từ thư mục gốc repository:

```bash
uv pip install --python .venv/bin/python -r scripts/requirements-mock.txt
docker compose -f scripts/compose.mock.yaml up -d --wait
scripts/start_mock.sh
```

Mở [Mock Studio](http://127.0.0.1:8765/). Dừng ứng dụng bằng Ctrl+C; dữ liệu PostgreSQL vẫn được giữ trong Docker volume. Không dùng `down --volumes` nếu muốn giữ dữ liệu.

Ba tiến trình có thể chạy riêng:

```bash
.venv/bin/python -m scripts.mock_platform serve --port 8765
.venv/bin/python -m scripts.mock_platform worker
.venv/bin/python -m scripts.mock_platform crawl-worker
```

Đổi kết nối bằng `MOCK_CONTROL_URL` và `MOCK_BUSINESS_URL` trước khi chạy các tiến trình. Các URL phải trỏ hai database khác nhau. Mặc định local:

- Control: `127.0.0.1:55432/mock_control`.
- Business: `127.0.0.1:55432/mock_oltp`.
- User: `mock`; mật khẩu local mặc định trong compose là `local_mock_only`. Nếu đổi `MOCK_POSTGRES_PASSWORD` lúc tạo volume, cập nhật cả hai URL tương ứng. Đổi biến môi trường không đổi mật khẩu của volume đã được tạo.

Database nghiệp vụ chưa tự tạo bảng khi chỉ mở ứng dụng. Người dùng chọn “Chuẩn bị môi trường” để tạo 33 bảng (27 bảng gốc và 6 bảng nghiệp vụ bổ sung). Business DB chỉ có bảng nghiệp vụ; config/checkpoint/job nằm ở `mock_control.control_records`, phân nhóm bằng `kind` và khóa `id`. Đây là thiết kế lưu tài liệu JSON cho bản local, chưa phải toàn bộ các bảng vật lý gợi ý trong kế hoạch.

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

V2 giữ chế độ đặt trực tiếp và bổ sung checkout từ phiên/giỏ nhiều dòng, tách shop, phí giao có cấu hình, voucher và nghĩa vụ hoàn riêng. Hủy toàn bộ trước lấy hàng có thể tạo refund cho khoản đã thu. Mẫu COD tối thiểu vẫn dùng chế độ trực tiếp; mẫu mới và các chính sách nằm trong hướng dẫn v2.

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

Xem [trạng thái triển khai](../../docs/mock-design/reviews/MOCK_IMPLEMENTATION_STATUS.md). Các hành động chưa có quy tắc dữ liệu đầy đủ được giữ trên UI, tắt và giải thích lý do. Không coi có form là toàn bộ nghiệp vụ đã hoàn tất.

Bản local chưa có authentication nhiều người dùng. Chỉ bind localhost, kiểm tra Host/Origin. Không mở cổng ứng dụng ra mạng công cộng. Bản local chưa có distributed worker, sửa schema cũ tự động hoặc hiệu năng đã benchmark quy mô lớn. Xóa toàn bộ qua UI được mô tả trong hướng dẫn bên dưới.

## Xem cấu hình bằng tên hành động

Sau khi tải lại web, mở **Cấu hình kịch bản → Tổng quan cấu hình**. Chọn **Bản nháp đang chỉnh sửa** hoặc một phiên bản đã lưu trong ô **Bản cấu hình đang xem**. Màn này tổng hợp cả 6 hệ thống: người/tiến trình thực hiện, tên hành động, số ngày thường, từng ngày đặc biệt và các tham số mở rộng. Hành động tắt có mục riêng; mã nội bộ chỉ hiện khi mở **Chi tiết kỹ thuật**.

Chọn cấu hình đã lưu rồi bấm **Chỉnh sửa cấu hình này** để sửa trực tiếp. Đổi hành động/tham số và bấm **Lưu thay đổi**: cập nhật đúng cấu hình đang chọn, giữ nguyên mã cấu hình, không bắt tạo một bản mới. Có thể **Hủy chỉnh sửa** nếu chưa muốn lưu. Bản nháp riêng không bị ghi đè. Nút **Lập kế hoạch với cấu hình này** chuyển đúng cấu hình đang xem sang bước lập kế hoạch. Xem/sửa cấu hình không tự chạy mô phỏng.

Preview kế hoạch và kết quả chạy hiển thị tên hệ thống/nhóm/tên hành động thay cho chuỗi mã. Bộ kiểm tra hiển thị có thể chạy độc lập, không cần PostgreSQL và không khởi động browser:

```bash
node scripts/mock_platform/tests/test_presentation.cjs
```

### Sửa cấu hình đã dùng để chạy

Mỗi kế hoạch giữ bản chụp cấu hình lúc xem trước. Sau khi lưu thay đổi, kế hoạch chưa được đưa vào job sẽ hết hiệu lực và phải xem trước lại. Job đã xếp, đang chạy hoặc đang tạm dừng vẫn sử dụng bản chụp cũ; tiếp tục job không đổi giữa chừng sang thông số mới. Lịch sử nội bộ giữ các lần sửa trong Control DB. Nếu hai cửa sổ cùng sửa một cấu hình, cửa sổ lưu sau phải tải lại để tránh đè mất thay đổi; nội dung đang nhập vẫn được giữ khi báo xung đột.

## Tổng quan, cào Tiki và xóa để chạy lại

Xem [hướng dẫn Tổng quan và điều khiển dữ liệu](../../docs/mock-design/guides/MOCK_OVERVIEW_CONTROLS.md). Nút cào chỉ ghi SQLite; thao tác đồng bộ vẫn riêng. Xóa toàn bộ có bước xem trước/xác nhận và bao gồm cả catalog OLTP, giữ SQLite và cấu hình.

## Nhập / xuất cấu hình JSON

Tại Cấu hình kịch bản, mở **Nhập / Xuất cấu hình JSON** để chọn file, kiểm tra/xem trước rồi lưu thành cấu hình mới. Có nút tải mẫu 2026 và xuất cấu hình đang xem. File tối đa 2 MiB. Import không tự chạy dữ liệu hoặc ghi đè cấu hình cũ. Xem [hướng dẫn, giả định và giới hạn của bộ mẫu](../../docs/mock-design/guides/REALISTIC_CONFIG_CURRENT_ENGINE.md).
