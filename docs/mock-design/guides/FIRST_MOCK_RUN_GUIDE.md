# Mock Studio: từ pull code đến lượt mock đầu tiên

Tài liệu dành cho người có kiến thức kỹ thuật, chạy trên **máy local mới** hoặc hai database mock còn trống. Mục tiêu: nhập sản phẩm thật từ SQLite crawler, tạo dữ liệu nền, import cấu hình, chạy **một ngày với 2 đơn COD**, rồi kiểm tra dữ liệu trong PostgreSQL.

Nếu môi trường đã có dữ liệu, không mặc định làm lại từ đầu hoặc xóa dữ liệu. Dùng ngày tiếp theo mà UI cho phép và kiểm tra checkpoint hiện tại. Các con số “2 đơn” bên dưới giả định database mới, không có job khác đã sinh dữ liệu.

## 1. Những gì cần có và những gì Git không mang sang

Chuẩn bị:

- Linux hoặc WSL2 với Bash. Windows native hiện chưa được hỗ trợ vì worker crawler dùng `fcntl`. macOS chưa được kiểm thử trong hướng dẫn này.
- Python **3.12** và khả năng tạo virtual environment; đây là phiên bản đã dùng để kiểm thử.
- Docker Engine/Desktop đang chạy và Docker Compose v2. Với WSL2, cần bật tích hợp Docker cho distro đang dùng.
- Git; trình duyệt có JavaScript. DBeaver là tùy chọn để xem database.
- Một SQLite đúng schema của `scripts/crawl_tiki.py`, hoặc kết nối tới Tiki để tự cào.

| Đi theo Git | Không đi theo Git |
|---|---|
| Code, schema, Compose, requirements, cấu hình mẫu JSON và tài liệu | `.venv`, file SQLite `.db`, Docker volume PostgreSQL, cấu hình đã lưu trên web, checkpoint và log local |

Tên cấu hình đã lưu trong database của đồng đội **không tự xuất hiện khi pull**. Hãy import file JSON từ repository hoặc file họ xuất trên UI. Không cần giống đường dẫn thư mục trên máy người viết code.

## 2. Pull commit mới nhất

Mở terminal trong repository đã clone:

```bash
git status --short
git branch --show-current
```

Lưu/commit hoặc xử lý thay đổi local của bạn trước nếu cần. Sau đó cập nhật nhánh `main`:

```bash
git switch main
git pull --ff-only origin main
git log -1 --oneline
```

`--ff-only` sẽ dừng nếu lịch sử local và remote phân kỳ; không tự reset/xóa thay đổi local để vượt lỗi. Nếu nhóm dùng nhánh khác, thay `main` bằng nhánh đã thống nhất.

Kiểm tra commit đã có các file cần thiết:

```bash
ls scripts/start_mock.sh scripts/requirements-mock.txt scripts/compose.mock.yaml
ls scripts/mock_platform/config/config_transfer.py scripts/mock_platform/web/config-transfer.js
ls docs/mock-design/examples/scenarios/first-run-cod.json
```

Nếu thiếu file, kiểm tra lại branch/commit hoặc hỏi người đẩy code. Lệnh pull chỉ lấy nội dung đã được commit và push.

> Mọi lệnh còn lại, trừ khi ghi khác, chạy từ **thư mục gốc repository**. Không dùng đường dẫn `/home/...` của máy người khác.

## 3. Cài thư viện Python

```bash
python3.12 --version
python3.12 -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements-mock.txt
```

Nếu máy chỉ có lệnh `python3`, kiểm tra phiên bản trước rồi thay `python3.12` bằng `python3`. Nếu venv đã tồn tại thì chỉ cần chạy lại lệnh cài requirements sau khi pull thay đổi dependency. Không bắt buộc activate venv vì các lệnh đều gọi Python bên trong `.venv`.

Các dependency chạy ứng dụng gồm requests, SQLAlchemy, psycopg, FastAPI và Uvicorn. Không cần Node.js để chạy web; frontend là JavaScript tĩnh được API phục vụ.

## 4. Khởi động PostgreSQL

### Cách mặc định: dùng Compose trong repository

```bash
docker compose version
docker compose -f scripts/compose.mock.yaml up -d --wait
docker compose -f scripts/compose.mock.yaml ps
```

Service `mock-postgres` cần ở trạng thái healthy. Lần đầu Docker cần tải image `postgres:15-alpine`.

| Thông số | Mặc định local |
|---|---|
| Host | `127.0.0.1` |
| Port trên máy | `55432` |
| User | `mock` |
| Password | `local_mock_only` |
| Database điều khiển | `mock_control` |
| Database nghiệp vụ | `mock_oltp` |
| Schema nghiệp vụ | `public` |

Compose tạo `mock_control`; script init tạo `mock_oltp` khi volume PostgreSQL được khởi tạo lần đầu. Chưa có dữ liệu nghiệp vụ chỉ vì container đã bật.

### Nếu dùng PostgreSQL có sẵn

Tạo **hai database riêng** cho mock và bảo đảm tài khoản có quyền tạo bảng/ghi dữ liệu trong đó. Export URL trong cùng terminal dùng để khởi động web:

```bash
export MOCK_CONTROL_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/mock_control'
export MOCK_BUSINESS_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/mock_oltp'
```

Thay USER/PASSWORD/host/port bằng cấu hình của bạn. Nếu mật khẩu có ký tự đặc biệt, URL-encode phần mật khẩu. Không dùng database chung có bảng không thuộc mô hình này. Hai URL phải trỏ **hai database khác tên**.

Script khởi động không tự đọc `.env`; dùng biến môi trường đã export hoặc công cụ nạp env của bạn. Nếu đổi `MOCK_POSTGRES_PASSWORD` khi tạo container lần đầu, phải đồng thời đặt hai URL ứng dụng tương ứng. Đổi biến môi trường không đổi mật khẩu của một volume PostgreSQL đã có.

### Khởi tạo bảng điều khiển một lần trước khi bật các tiến trình

```bash
.venv/bin/python - <<'PY'
from scripts.mock_platform.infrastructure.storage import Database

db = Database()
db.start_control()
print("Control DB đã sẵn sàng.")
db.control.dispose()
db.business.dispose()
PY
```

Bước này giúp khởi tạo Control DB tuần tự trên máy mới trước khi API và hai worker cùng khởi động. Chỉ tạo cấu trúc điều khiển, không tạo sản phẩm/đơn hàng.

## 5. Chuẩn bị SQLite crawler

Chọn **một** trong hai cách.

### Cách A: nhận SQLite đã cào từ đồng đội

Đặt bản SQLite tương thích tại:

```text
data/tiki_crawl.db
```

Đây là đường dẫn tương đối tính từ repository; có thể chọn vị trí khác rồi nhập đường dẫn đó ở UI. Không đặt một SQLite bất kỳ vào đây: cần các bảng do crawler hiện tại tạo như `products`, `product_raw`, `product_categories`, `product_checkpoints`.

Nếu SQLite gốc đang được ghi ở chế độ WAL, không chỉ copy riêng file `.db` đang hoạt động. Người cung cấp có thể dùng SQLite backup để xuất bản nhất quán, ví dụ chạy ở repository của họ:

```bash
.venv/bin/python - <<'PY'
import sqlite3
from pathlib import Path

source_path = Path("data/tiki_crawl.db").resolve()
output_path = Path("data/tiki_crawl_share.db").resolve()
with sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True) as source:
    with sqlite3.connect(output_path) as output:
        source.backup(output)
print(output_path)
PY
```

Chuyển `tiki_crawl_share.db` sang máy mới rồi dùng nó làm nguồn hoặc đổi tên thành `tiki_crawl.db`. Cách này không tạo sản phẩm giả và không sửa database nguồn.

### Cách B: tự cào bằng nút trên web

Trước tiên tạo **SQLite rỗng đúng schema** để UI nhận nguồn:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from scripts.crawl_tiki import open_database

path = Path("data/tiki_crawl.db")
conn = open_database(path)
conn.close()
print("SQLite crawler:", path.resolve())
PY
```

Lệnh chỉ tạo cấu trúc SQLite, **chưa gọi Tiki, chưa sinh sản phẩm và chưa đồng bộ OLTP**. Lát nữa, sau bước Thiết lập môi trường trên UI, bạn sẽ kích hoạt crawler.

Có thể dùng CLI thay UI nếu muốn:

```bash
.venv/bin/python scripts/crawl_tiki.py --category-ids 8322 --db data/tiki_crawl.db
```

`8322` là danh mục gốc Nhà Sách Tiki, không phải ID danh mục lá dùng trong chính sách hoa hồng. Crawler có thể mất thời gian và có thể bị API Tiki từ chối; không có cam kết mạng/API ngoài luôn sẵn sàng. Nếu đã dùng CLI để cào được sản phẩm thì không cần cào lại trên UI.

## 6. Bật web và hai worker

```bash
./scripts/start_mock.sh
```

Giữ terminal này mở, rồi vào [http://127.0.0.1:8765/](http://127.0.0.1:8765/).

Lệnh bật **ba tiến trình**:

| Tiến trình | Nhiệm vụ |
|---|---|
| API/web | Phục vụ UI, kiểm tra yêu cầu, lưu cấu hình và xếp job |
| Worker nghiệp vụ | Chạy đồng bộ, dữ liệu nền, mô phỏng và xóa OLTP khi người dùng yêu cầu |
| Worker crawler | Chạy crawler riêng, chỉ ghi SQLite nguồn |

**Khởi động server không tự cào, đồng bộ hoặc sinh dữ liệu mock.** Đóng tab không dừng worker. Ctrl+C trong terminal dùng để dừng ứng dụng.

Nếu port web đã dùng:

```bash
./scripts/start_mock.sh --port 8766
```

Sau đó mở port mới. Nếu dùng Python ở virtualenv khác, export `MOCK_PYTHON` trỏ tới executable đó trước khi chạy script.

## 7. Bản đồ UI và luồng dữ liệu

```mermaid
flowchart TD
    A[Pull code và cài dependency] --> B[PostgreSQL và SQLite nguồn]
    B --> C[Thiết lập môi trường]
    C --> D{SQLite đã có sản phẩm?}
    D -- Chưa --> E[Tổng quan: Cào Tiki]
    E --> F[Đồng bộ Tiki: kiểm tra và xem trước]
    D -- Có --> F
    F --> G[Thực hiện đồng bộ vào OLTP]
    G --> H[Thiết lập: Tạo dữ liệu nền]
    H --> I[Cấu hình: Import JSON và lưu]
    I --> J[Lập kế hoạch: Xem trước một ngày]
    J --> K[Bắt đầu mô phỏng]
    K --> L[Theo dõi: Hoàn tất]
    L --> M[Tổng quan / Lịch sử / DBeaver]
```

| Trang | Dùng để làm gì? | Khi nào ghi dữ liệu? |
|---|---|---|
| **Tổng quan** | Dashboard OLTP, kích hoạt/dừng crawler, xem trước/xác nhận xóa toàn bộ | Dashboard chỉ đọc. Nút cào ghi SQLite; nút xóa xếp job xóa OLTP sau xác nhận. |
| **Đồng bộ Tiki** | So sánh nguồn SQLite với OLTP, xem trước sản phẩm mới, nhập catalog | Nút Thực hiện đồng bộ mới xếp job ghi OLTP; chỉ append. |
| **Cấu hình kịch bản** | Chọn hành động của 6 hệ thống, số lần và tham số; nhập/xuất JSON | Lưu vào Control DB. Không tự chạy nghiệp vụ. |
| **Lập kế hoạch & Chạy** | Chọn cấu hình, ngày và kiểm tra kế hoạch | Xem trước lưu kế hoạch điều khiển; Bắt đầu mô phỏng mới xếp job nghiệp vụ. |
| **Theo dõi lượt chạy** | Trạng thái job, số hành động thành công/từ chối, pause/resume | Gửi lệnh cho worker; không tự tạo lượt chạy khác. |
| **Lịch sử & Dữ liệu** | Xem job, 50 dòng/bảng/trang, kiểm tra dữ liệu | Các thao tác xem và kiểm tra chỉ đọc. |
| **Thiết lập môi trường** | Chọn nguồn SQLite, ngày bắt đầu, seed; tạo bảng và dữ liệu nền | Chuẩn bị tạo cấu trúc; Tạo dữ liệu nền là job ghi OLTP riêng. |

Ba nơi lưu dữ liệu:

```text
Tiki API → SQLite crawler → [Đồng bộ chủ động, chỉ thêm] → mock_oltp.public
                                                            ↑
UI → API → mock_control (cấu hình, kế hoạch, job, checkpoint) → worker
```

Cào và đồng bộ là hai việc khác nhau. Mock dùng catalog đã đồng bộ; không ghi ngược vào SQLite. Dữ liệu sản phẩm đã có trong OLTP không bị cập nhật giá/tên chỉ vì crawler thay đổi nguồn.

## 8. Thao tác UI để chạy lượt đầu tiên

### Bước 1 — Thiết lập môi trường

Mở **Thiết lập môi trường** và nhập:

| Ô | Giá trị cho lượt thử | Ý nghĩa |
|---|---|---|
| Đường dẫn database crawler | Đường dẫn SQLite trên **máy đang chạy server** | Không phải đường dẫn trên máy đồng đội. Mặc định đã trỏ theo repository hiện tại. |
| Ngày bắt đầu mô phỏng | `2026-01-01` | Mốc đầu của đồng hồ mô phỏng, không phải ngày hiện tại của máy. |
| Seed (tái lập lựa chọn) | `42` | Giúp tái lập lựa chọn khi cùng dữ liệu ban đầu, lịch và cấu hình; không phải số khách hoặc số đơn. |
| Múi giờ | UTC+7 | Quy ước thời gian của môi trường mock. |

Bấm **Kiểm tra kết nối**, sau đó **Chuẩn bị môi trường**. Khi thành công, 27 bảng nghiệp vụ đã được tạo trong `mock_oltp`, nhưng chưa có sản phẩm hoặc đơn hàng.

Ngày bắt đầu và seed được cố định sau khi chuẩn bị môi trường; không đổi chúng để lách checkpoint. Chưa bấm Tạo dữ liệu nền ở bước này nếu catalog còn rỗng.

### Bước 2 — Nếu SQLite chưa có sản phẩm: cào Tiki

Bỏ qua bước này nếu dùng SQLite đã có dữ liệu.

1. Mở **Tổng quan**, bấm **Cào Tiki** để đến form.
2. Nhập ID danh mục gốc `8322`. Không để trống nếu chỉ muốn cào một danh mục; trống nghĩa là tất cả danh mục mặc định.
3. Giữ khoảng nghỉ **4–8 giây/request**; mã tiếp tục để trống cho lượt mới.
4. Bấm **Bắt đầu cào Tiki**, mở log để theo dõi.
5. Đợi có trang đã lưu sản phẩm. Có thể vào Đồng bộ Tiki để kiểm tra số sản phẩm nguồn.
6. Lượt đầu chỉ cần một ít sản phẩm hợp lệ. Nếu crawler còn chạy, có thể bấm **Dừng cào, giữ các trang đã lưu** sau khi đã có dữ liệu; không cần chờ cào hết danh mục.

Dừng chủ động có thể hiện trạng thái Đã hủy cho lượt cào; các trang đã commit vẫn dùng được. Chưa có sản phẩm mới trong OLTP chỉ vì cào xong. Nếu log báo HTTP 401/403 thì xử lý nguồn/API hoặc dùng SQLite đã cào; không tiếp tục bước mock khi nguồn vẫn rỗng.

### Bước 3 — Đồng bộ catalog từ SQLite vào OLTP

Mở **Đồng bộ Tiki**:

1. Bấm **Kiểm tra sản phẩm mới trong SQLite**. Nguồn phải có ít nhất một sản phẩm mới hợp lệ.
2. Nhập **Tối đa sản phẩm mới = 20** để giới hạn lượt thử; nếu nguồn ít hơn 20 thì nhập tất cả những sản phẩm hợp lệ có sẵn. `0` nghĩa là không giới hạn.
3. Giữ bật **Cho sản phẩm mới sẵn sàng bán trong mô phỏng**.
4. Bấm **Xem trước đồng bộ**, đọc số mới hợp lệ/đã có/lỗi.
5. Bấm **Thực hiện đồng bộ**.
6. Chờ job ở Theo dõi đạt **Hoàn tất** rồi mới làm tiếp.

Đồng bộ thêm sản phẩm, danh mục và người bán cần thiết. Không tạo tồn kho, khách, đơn hoặc thanh toán. ID/SKU thiếu, trùng hoặc chào bán xung đột bị báo lỗi/bỏ qua; không tự đổi mã để ép nhập. Nếu tất cả sản phẩm đều lỗi thì cần sửa/đổi nguồn đúng schema trước.

**Điều kiện để tiếp tục:** OLTP có ít nhất 1 sản phẩm đang bán, có giá hợp lệ và seller hoạt động. “Job đồng bộ hoàn tất” với 0 sản phẩm mới không tự bảo đảm điều kiện này.

### Bước 4 — Tạo dữ liệu nền

Quay lại **Thiết lập môi trường → Dữ liệu nền ban đầu**:

| Ô | Nhập | Tác dụng |
|---|---:|---|
| Số khách hàng nền | `20` | Tạo 20 tài khoản giả để có thể đặt hàng đăng nhập. Không phải 20 lượt truy cập hoặc 20 đơn. |
| Tồn đầu mỗi SKU | `30` | Nhập 30 sản phẩm cho mỗi SKU đã đồng bộ, có phiếu nhập trong ledger kho. Không phải tổng 30 sản phẩm cho cả catalog. |

Bấm **Tạo dữ liệu nền** và chờ **Hoàn tất**.

Bước này còn tạo các kênh bán, phương thức thanh toán, một kho và một carrier mô phỏng. Trên database mới, kho này có ID 1, phù hợp JSON mẫu. Bootstrap chạy một lần; không bấm lại để bổ sung hàng hoặc khách. Các nghiệp vụ nhập thêm sau đó phải qua hành động phù hợp.

### Bước 5 — Import cấu hình cho lượt đầu

Mở **Cấu hình kịch bản → Nhập / Xuất cấu hình JSON**:

1. Chọn file [examples/scenarios/first-run-cod.json](../examples/scenarios/first-run-cod.json) từ repository trên máy.
2. Tên mới có thể để trống, dùng tên trong file: **Lượt đầu tiên · 2 đơn COD · 1 ngày**.
3. Bấm **Kiểm tra & xem trước**.
4. Mở bảng xem hành động để đọc lại.
5. Bấm **Lưu thành cấu hình mới**.

Trên UI, nút **Mẫu cơ bản: 2 đơn COD** tải đúng `first-run-cod.json`; nút hành trình liên kết 2026 là bản đầy đủ khác. Nếu đang chỉnh sửa một cấu hình đã lưu, lưu hoặc hủy chỉnh sửa trước khi lưu bản import.

File này bật:

| Ai / hành động | Cấu hình | Dữ liệu chính bị tác động |
|---|---|---|
| Khách đăng nhập đặt hàng | 2 lần; COD, Web, số lượng 1 | orders, order_items, customer_addresses; giữ tồn |
| Xác nhận đơn | Tự xử lý đầu vào đủ điều kiện | orders |
| Tạo vận đơn | Tự xử lý; kho 1, chi phí vận chuyển 30.000 | shipments |
| Lấy hàng | Tự xử lý | shipments, inventory_levels, inventory_movements |
| Cập nhật đang vận chuyển | Tự xử lý | shipments |
| Báo giao hàng | Tự xử lý; thành công 100% | shipments, orders, order_items |
| Thu COD | Tự xử lý | payments |
| Đánh giá sản phẩm đã mua | 1 lần, 4 sao | product_reviews |
| Chốt tồn cuối ngày | 1 lần | inventory_daily_balance |

Các hành động khác mặc định tắt. Không bật `WH-03` thêm vào bộ này vì đường lấy hàng `CAR-01` đã thực hiện xuất kho.

**Cách đọc cấu hình:**

- **Bật hành động:** cho phép engine xét hành động đó trong lịch.
- **Số lần/ngày thường:** số yêu cầu engine thử thực hiện, không bảo đảm số thành công khi thiếu điều kiện.
- **Ngày đặc biệt:** giá trị riêng của ngày đó thay thế ngày thường, không cộng/nhân tự động.
- **Theo đầu vào:** xử lý những đối tượng đủ điều kiện đang có; không tự tạo đơn để đủ quota. Gặp hết đầu vào là kết quả bình thường.
- **Tham số/ID để trống:** các trường tùy chọn chọn đối tượng hợp lệ theo cơ chế của engine; không có nghĩa mọi trường bắt buộc đều được bỏ trống.
- **Bản nháp:** nội dung đang soạn. Cần lưu cấu hình trước khi lập kế hoạch.
- **Cấu hình đã lưu:** sửa được trực tiếp. Sau khi sửa phải xem trước kế hoạch mới; job đã xếp giữ snapshot cũ.

Để chỉnh file vừa nhập: chọn đúng bản trong **Bản cấu hình đang xem**, bấm **Chỉnh sửa cấu hình này**, chỉnh và **Lưu thay đổi**. Chỉ lưu cấu hình không tạo đơn.

### Bước 6 — Xem trước và chạy một ngày

Từ Tổng quan cấu hình, bấm **Lập kế hoạch với cấu hình này**, hoặc mở **Lập kế hoạch & Chạy** rồi chọn đúng tên cấu hình.

Nhập:

| Ô | Giá trị |
|---|---|
| Khoảng chạy nhanh | Một ngày |
| Ngày bắt đầu | `2026-01-01` trên môi trường mới ở hướng dẫn này |
| Ngày kết thúc | `2026-01-01` |
| Độ chậm quan sát | `0` ms; có thể tăng nếu muốn nhìn tiến trình chậm hơn |

Bấm **Xem trước kế hoạch**. Kế hoạch mẫu có 2 yêu cầu đặt hàng, 1 đánh giá, 1 chốt tồn và 6 hành động theo đầu vào. Con số yêu cầu theo số lượng không bao gồm toàn bộ số lần xử lý tự động.

Khi kiểm tra đúng, bấm **Bắt đầu mô phỏng**. Lúc này job mới thực sự được worker xử lý để ghi dữ liệu nghiệp vụ.

Không được nhảy ngày hoặc chạy lại ngày đã hoàn tất. Nếu UI báo ngày tiếp theo khác 01/01 thì môi trường đã có checkpoint; dùng ngày UI cho phép hoặc chủ động tạo môi trường riêng cho bài thử.

### Bước 7 — Theo dõi và hiểu kết quả

Ở **Theo dõi lượt chạy**:

| Trạng thái/kết quả | Ý nghĩa |
|---|---|
| Đang chờ | Job đã được lưu, worker chưa bắt đầu xử lý. |
| Đang chạy | Worker đang thực thi. |
| Hoàn tất | Job đã chạy xong; vẫn phải đọc số lần bị từ chối, không đồng nghĩa mọi hành động đã thành công. |
| Đã tạm dừng | Worker đã dừng ở điểm an toàn. Có thể tiếp tục cùng job. |
| Có lỗi / Bị gián đoạn | Cần đọc thông báo/log và đối chiếu; không tạo job khác để bỏ qua lỗi. |
| Không đủ điều kiện | Không có đối tượng hợp lệ, thiếu tồn hoặc thiếu đầu vào; không tính là ghi dữ liệu thành công. |
| Đã hết đầu vào đủ điều kiện | Kết thúc bình thường của một hành động chế độ tự xử lý. |

Có thể **Tạm dừng an toàn → Tiếp tục**. Hệ thống giữ tiến độ; job cũ tiếp tục với cấu hình snapshot ban đầu. Lượt xóa toàn bộ là transaction riêng, không hỗ trợ tạm dừng giữa chừng.

Checkpoint ngày chỉ tiến khi ngày đã xử lý và kiểm tra dữ liệu cuối ngày đạt. Đừng chỉ dựa vào ngày đang hiển thị ở một job còn chạy để kết luận ngày đó đã hoàn tất.

## 9. Xác nhận lượt đầu đã chạy đúng

### Trên UI

1. Vào **Lịch sử & Dữ liệu → Kiểm tra dữ liệu**. Các kiểm tra đã triển khai phải đạt.
2. Chọn lần lượt các bảng và xem bản ghi.
3. Quay **Tổng quan** xem số liệu đọc trực tiếp từ OLTP; dashboard tự làm mới mỗi 5 giây.

Trên database mới, đủ điều kiện như hướng dẫn và không có hành động bị từ chối, kết quả kỳ vọng:

| Dữ liệu | Kết quả |
|---|---|
| orders | 2 đơn, trạng thái Completed |
| order_items | 2 dòng hàng, mỗi dòng số lượng 1 |
| shipments | 2 vận đơn, trạng thái Delivered |
| payments | 2 thanh toán COD, trạng thái Success |
| product_reviews | 1 đánh giá |
| inventory_levels | Tồn thực giảm tổng 2 sản phẩm; tổng giữ tồn về 0 |
| inventory_daily_balance | Một dòng/SKU/kho cho ngày chạy, không phải chỉ 2 dòng theo số đơn |
| Checkpoint | Đã mock hết 01/01/2026; ngày tiếp theo là 02/01/2026 |

Giá trị tiền lấy từ sản phẩm thật được chọn, không có tổng tiền cố định cho bài thử. Phiên truy cập vẫn là 0 vì bài thử này chưa bật Analytics. Marketing, voucher, hoàn tiền và đối soát không được tạo chỉ để lấp đầy mọi bảng.

![Dashboard OLTP đọc dữ liệu nghiệp vụ](../screenshots/oltp-dashboard.png)

*Ảnh dashboard thật được cung cấp trong phiên làm việc, minh họa cách đọc giao diện. Ảnh chụp một môi trường đã có 310 đơn; đây không phải kết quả mong đợi của lượt thử 2 đơn trên máy mới.*

### Bằng DBeaver

Tạo kết nối **PostgreSQL**, điền thông số ở mục 4; database chọn **mock_oltp**. Mở schema **public**, refresh sau khi job hoàn tất. Kết nối database **mock_control** riêng nếu muốn xem metadata điều khiển; không nhầm hai nơi lưu dữ liệu.

Có thể chạy các truy vấn chỉ đọc:

```sql
SELECT order_status, COUNT(*) AS orders
FROM public.orders
GROUP BY order_status;

SELECT payment_status, COUNT(*) AS payments, SUM(paid_amount) AS paid_amount
FROM public.payments
GROUP BY payment_status;

SELECT o.order_code, o.order_status, o.final_amount,
       p.payment_status, s.shipment_status
FROM public.orders o
LEFT JOIN public.payments p ON p.order_id = o.id
LEFT JOIN public.shipments s ON s.order_code = o.order_code
ORDER BY o.id;

SELECT SUM(quantity_on_hand) AS on_hand,
       SUM(quantity_reserved) AS reserved,
       SUM(quantity_on_hand - quantity_reserved) AS available
FROM public.inventory_levels;
```

Truy vấn join là cách xem đơn của bài thử COD này; với kịch bản có nhiều lần thanh toán, một đơn có thể hiện nhiều dòng theo giao dịch. Không sửa/xóa trực tiếp bằng DBeaver khi worker đang chạy vì sẽ làm sai liên kết và bằng chứng phục hồi.

## 10. Dữ liệu nằm ở đâu, dừng và chạy tiếp thế nào?

| Dữ liệu | Vị trí mặc định |
|---|---|
| Sản phẩm/raw/checkpoint crawler | `data/tiki_crawl.db` hoặc file bạn chọn ở Thiết lập |
| Cấu hình, kế hoạch, job, snapshot, checkpoint mock | Database `mock_control`, bảng `control_records`, phân nhóm bằng `kind` |
| 27 bảng dữ liệu nghiệp vụ sinh ra | Database `mock_oltp`, schema `public` |
| Log crawler từ UI | `data/mock-platform/crawler/<job-id>.log` |
| File dữ liệu vật lý PostgreSQL | Docker named volume gắn tại `/var/lib/postgresql/data` trong container; không nằm trong Git |

Muốn xem tên volume trên máy bạn:

```bash
docker volume ls
```

Tên volume có thể mang tiền tố theo project Compose; không dùng đường dẫn volume của máy người khác.

Dừng ứng dụng bằng Ctrl+C. Có thể dừng container mà giữ dữ liệu:

```bash
docker compose -f scripts/compose.mock.yaml stop
```

Lần sau:

```bash
docker compose -f scripts/compose.mock.yaml up -d --wait
./scripts/start_mock.sh
```

Giữ cùng URL/database và SQLite. Không bootstrap lại. Đọc checkpoint trên UI rồi chạy từ ngày tiếp theo. Nếu job còn dang dở thì xử lý/tiếp tục job đó trước khi tạo lượt ghi mới.

Nếu muốn làm lại từ đầu: **Tổng quan → Chạy lại từ đầu → Xem trước dữ liệu sẽ xóa → nhập XOA TOAN BO → Xóa toàn bộ OLTP**. Thao tác xóa cả sản phẩm, seller, danh mục, khách nền và nghiệp vụ; đặt lại checkpoint. Nó giữ SQLite, thiết lập và cấu hình kịch bản. Sau khi hoàn tất phải **đồng bộ lại → bootstrap lại → xem trước kế hoạch mới → chạy**. Không có nút phục hồi tự động. Không dùng `docker compose down --volumes` như một bước khởi động thông thường.

## 11. Sau lượt đầu: dùng bộ lịch có biến thiên

Khi đã hiểu lượt COD nhỏ, có thể import [upgraded-linked-2026.json](../examples/scenarios/upgraded-linked-2026.json), hoặc tải bản đầy đủ từ UI. Xem [hướng dẫn và giới hạn v2](ENGINE_V2_UPGRADE_GUIDE.md).

- Lịch năm 2026 có ngày thường, cuối tuần, kỳ lương giả định và 4 ngày sale. Không tự đổi năm khi import.
- Có Analytics, Marketing, thanh toán trả trước và hủy quá hạn; số lượng lớn hơn bài thử đầu tiên.
- Nên thử từng ngày rồi chia tháng liên tục; bộ mẫu cả năm vượt giới hạn 100.000 yêu cầu theo số lượng cho một kế hoạch.
- Kiểm tra ID danh mục tài chính 9423 và kho 1 có phù hợp dữ liệu của bạn không. Nếu mẫu được áp dụng sau ngày tạo chính sách/chiến dịch đã định mà dữ liệu tương ứng chưa tồn tại, cần cấu hình ngày tạo phù hợp; import không tự bù lịch sử.
- Chưa mô phỏng đầy đủ delay nhiều ngày, liên kết đơn–phiên, áp voucher, hoàn tiền, hoàn kho sau giao thất bại hoặc tạo đối soát. Không dùng dữ liệu này để kết luận các nghiệp vụ đó đã hoàn chỉnh.

## 12. Xử lý các lỗi thường gặp

| Triệu chứng | Kiểm tra / xử lý |
|---|---|
| `.venv/bin/python: No such file` | Chưa tạo venv hoặc đang đứng sai thư mục. Làm lại mục 3. |
| `ModuleNotFoundError` | Dùng đúng Python và cài `scripts/requirements-mock.txt`. Nếu thiếu module thuộc repository như `config_transfer`, kiểm tra commit đã có đủ file mới. |
| `No module named fcntl` | Đang chạy Windows native. Chạy bằng Linux/WSL2. |
| `Permission denied` với shell script | Dùng `bash scripts/start_mock.sh`, hoặc kiểm tra quyền executable của file. |
| PostgreSQL connection refused / authentication failed | Kiểm tra container healthy, port, URL export và mật khẩu thật của volume. |
| Port 55432 đã được dùng | Kiểm tra service đang chiếm port; đổi mapping Compose và cả hai URL hoặc dùng PostgreSQL riêng. |
| `database mock_oltp does not exist` | Init script chỉ chạy khi volume mới. Nhờ người quản trị tạo database tương ứng hoặc dùng môi trường riêng; không xóa volume có dữ liệu chỉ để chạy lại init. |
| Lỗi khởi tạo bảng Control DB lúc bật lần đầu | Dừng các tiến trình app, chạy bước khởi tạo Control DB tuần tự ở mục 4, rồi bật lại. |
| Không tìm thấy database crawler | Nhập đường dẫn thực trên máy server; copy nguồn đúng cách hoặc tạo SQLite rỗng đúng schema theo mục 5. |
| Incompatible products schema / thiếu bảng | File SQLite không đúng phiên bản crawler hiện tại. Dùng nguồn tương thích; không tự sửa hàng loạt chỉ để vượt lỗi. |
| Cào hoàn tất/đã lưu nhưng OLTP chưa có sản phẩm | Cào chỉ ghi SQLite. Phải xem trước và Thực hiện đồng bộ. |
| HTTP 401/403 khi cào | Tiki từ chối request. Đọc log và kiểm tra nguồn/API; có thể dùng SQLite được đồng đội cung cấp. |
| Đồng bộ không có sản phẩm mới | Có thể toàn bộ ID đã có hoặc nguồn có lỗi SKU/chào bán/trường bắt buộc. Đọc thống kê và danh sách lỗi. |
| Job cứ Đang chờ | Kiểm tra worker nghiệp vụ còn chạy. Không chỉ khởi động API bằng lệnh `serve`. |
| Không có đối tượng hợp lệ / thiếu tồn | Kiểm tra sản phẩm đang bán, seller hoạt động, khách nền, tồn đầu và đầu vào từ bước trước. |
| Không đủ điều kiện khi đánh giá | Chưa có dòng hàng giao thành công của khách có tài khoản, hoặc đã được đánh giá. |
| Đơn Completed nhưng chưa có thanh toán COD | Kiểm tra có bật Trả kết quả thu COD và hành động này có chạy thành công không. |
| Kế hoạch hoặc preview hết hiệu lực | Dữ liệu/cấu hình/checkpoint đã thay đổi; tạo bản xem trước mới. |
| Không được nhảy ngày / chạy lại ngày | Dùng đúng Ngày tiếp theo được phép. Muốn chạy lại từ đầu phải dùng reset toàn bộ có xác nhận. |
| Còn job dang dở nên không tạo được job mới | Tiếp tục/hoàn tất hoặc xử lý lỗi job cũ; không sửa status/checkpoint trực tiếp để lách chặn. |
| Web thiếu nút mới hoặc script 404 | Kiểm tra commit đủ file; dừng/bật lại server sau thay đổi Python, rồi Ctrl+Shift+R để tải frontend mới. |

## 13. Các tài liệu liên quan

- [Rule đã chốt](../MOCK_SYSTEM_RULES.md).
- [Tổng quan, crawler và chức năng xóa dữ liệu](MOCK_OVERVIEW_CONTROLS.md).
- [Import JSON, lịch 2026 và giới hạn nghiệp vụ](REALISTIC_CONFIG_CURRENT_ENGINE.md).
- [Trạng thái triển khai](../reviews/MOCK_IMPLEMENTATION_STATUS.md).
- [README kỹ thuật](../../../scripts/mock_platform/README.md).
