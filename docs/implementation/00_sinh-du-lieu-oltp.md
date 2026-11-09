# 00 — Sinh dữ liệu OLTP bằng Mock Studio (tiền đề của kho dữ liệu)

| | |
|---|---|
| Ngày thực hiện | 07/11/2026 |
| Trạng thái | 🔄 Đang chạy nền (sinh dần từng ngày mô phỏng, đích 31/12/2026) |
| Liên quan PLAN | Mục 0 (Hiện trạng); đề xuất Bảng 14, giai đoạn 2 "Sinh dữ liệu" |

## 1. Mục tiêu

Tạo một bộ dữ liệu OLTP **mới, sạch, tái lập được** làm nguồn cho kho dữ liệu: sản phẩm thật từ crawler Tiki, các bảng nghiệp vụ còn lại do Mock Studio mô phỏng theo luật của nhóm ([MOCK_SYSTEM_RULES.md](../mock-design/MOCK_SYSTEM_RULES.md)), trải đủ năm 2026 để có mùa vụ.

## 2. Đầu vào

| Thành phần | Giá trị |
|---|---|
| Crawler Tiki | `data/tiki_crawl.db` — 3.532 sản phẩm, 5 danh mục gốc; WSL đọc bản sao `data/tiki_crawl_share.db` (journal_mode=DELETE) vì file gốc là WAL |
| Engine | Mock Studio v2, `scripts/mock_platform/` (33 bảng nghiệp vụ) |
| Hồ sơ thực thể & chính sách | [medium-ecommerce.json](../mock-design/examples/settings/medium-ecommerce.json) (21 nhóm actor, 6 kho, 5 hãng vận chuyển, quy tắc tồn kho) |
| Kịch bản | [dw-lite-2026.json](../mock-design/examples/scenarios/dw-lite-2026.json) (01/01–29/01), [dw-scd-2026.json](../mock-design/examples/scenarios/dw-scd-2026.json) (từ 30/01, xem bước 01) |
| Tham số | seed 42, ngày bắt đầu 01/01/2026, 10.000 khách nền |
| Hạ tầng | Postgres 15 trong Docker (`scripts-mock-postgres-1`, cổng 55432); Mock Studio chạy trong WSL Ubuntu-20.04 |

## 3. Phân tích trước khi làm

1. **Dữ liệu cũ bị xóa theo yêu cầu.** Volume Postgres (gồm `mock_oltp` và `mock_control`) được tạo lại. SQLite crawler giữ nguyên.
2. **Khối lượng của các kịch bản có sẵn** (số hành động theo kế hoạch):

   | Kịch bản | Hành động/ngày | Cả năm | Ước tính ở tốc độ gốc 3,5 hành động/giây |
   |---|---:|---:|---:|
   | `medium-linked-2026` (~1.000 đơn/ngày) | 51.777 | 18,9 triệu | ~1.500 giờ |
   | `upgraded-linked-2026` (~100 đơn/ngày) | 7.591 | 2,77 triệu | ~220 giờ |

   Cả hai đều không khả thi. **95% hành động là clickstream** (xem/tìm kiếm), trong khi đề xuất (Bảng 2) xếp phân tích clickstream ngoài phạm vi.
3. **Profile engine** (cProfile trên worker) chỉ ra các điểm nghẽn, tính trên mỗi hành động:
   - `actors.bind` tải toàn bộ 10.000 khách (mọi cột) để chọn người thực hiện có trọng số, chiếm **68% thời gian**;
   - `UnitOfWork.rows()` nạp lại cả bảng trong mỗi transaction;
   - `page_events` bị quét toàn bộ ở `AUT-WEB-01` và `*-WEB-06`, nên càng chạy lâu càng chậm (độ phức tạp bậc hai);
   - `saleable()` truy vấn seller riêng cho từng sản phẩm (~480 truy vấn/hành động);
   - `clean()` chuyển mỗi dòng qua `json.dumps`/`json.loads`;
   - ping kết nối ở mỗi lần lấy connection; Postgres chờ ghi đĩa ở mỗi commit.

## 4. Cách thực hiện

### 4.1. Kịch bản rút gọn clickstream

Tạo `dw-lite-2026.json` từ `upgraded-linked-2026.json` bằng cách nhân số lần của các hành động quan sát, kể cả ngày đặc biệt:

| Hành động | Hệ số |
|---|---|
| `GST-WEB-01`, `CUS-WEB-01` (bắt đầu phiên) | × 0,5 |
| `GST-WEB-02`, `CUS-WEB-02` (tìm kiếm) | × 0,3 |
| `GST-WEB-03`, `CUS-WEB-03` (xem sản phẩm) | × 0,3 |

Giữ nguyên giỏ hàng (`WEB-04/05/06`), đặt hàng (`GST-02`, `CUS-05`) và toàn bộ luồng xử lý đơn, kho, vận chuyển, tài chính, marketing. Kết quả là 3.212 hành động/ngày theo kế hoạch (cả năm 1,17 triệu), chưa tính các hành động chế độ "theo đầu vào".

### 4.2. Tối ưu engine, giữ nguyên kết quả

| File | Thay đổi |
|---|---|
| `engine/actors.py` | `sampling_frame()`: chỉ đọc `id` + cột trọng số; cache theo md5 fingerprint `(id, field)` của tập ứng viên |
| `infrastructure/storage.py` | `SharedTableCache`: ảnh bảng đã commit dùng chung giữa các transaction, chỉ hợp nhất sau commit, bỏ khi rollback, xóa đầu mỗi ngày; `one()` tra theo vị trí; `clean()` đi đường nhanh cho dòng chỉ có giá trị vô hướng; `RuntimeState` dùng cache runtime của worker (lưu dạng JSON text); bỏ `pool_pre_ping` |
| `application/worker.py` | Gắn 2 cache trên, cập nhật cache runtime sau khi Control DB commit |
| `engine/domain.py` | `page_events` truy vấn theo `session_id` (có index) thay vì quét cả bảng; `saleable()` đọc bảng seller một lần |
| `engine/selection.py` | Chọn sản phẩm không có bộ lọc: dùng ảnh bảng `products` |
| Postgres | `ALTER SYSTEM SET synchronous_commit = off` (chỉ áp dụng cho môi trường local) |

### 4.3. Chạy tự động, tách khỏi phiên làm việc

Các script trong [scripts/mock_runner/](../../scripts/mock_runner/):
- `start_all.sh`: dùng `setsid nohup` để chạy serve, worker và `pipeline.py`;
- `pipeline.py`: tự làm prepare → nhập settings → đồng bộ catalog → tạo dữ liệu nền → nhập kịch bản → lập kế hoạch và chạy từng đợt, mỗi đợt ≤ 95.000 hành động (giới hạn engine là 100.000/lượt). Có thể chạy lại bất kỳ lúc nào, nó nối tiếp từ checkpoint.

```bash
# trong WSL
bash "/mnt/d/PTIT/KÌ 1 năm 4/DATA WAREHOUSE/e-commerce/scripts/mock_runner/start_all.sh"
# dừng
bash ".../scripts/mock_runner/stop_all.sh"
```

Log ở `data/logs/mock_{serve,worker,pipeline}.log`.

## 5. Quá trình thực hiện

| Giờ (07/11) | Diễn biến |
|---|---|
| 13:56 | Bật Docker; container cũ không khởi động được (bind-mount từ WSL) → `docker compose down -v` rồi `up`, tạo lại volume sạch |
| 13:58–14:04 | Lần dựng 1: đồng bộ 3.532 sản phẩm, 481 seller, 49 danh mục; tạo nền 10.000 khách, 6 kho, 18.254 dòng tồn |
| 14:05 | Chạy thử ngày 01/01 (kịch bản ~100 đơn): **3,5 hành động/giây** → profile |
| 14:15 | Tối ưu 1 (`actors`): **~10 hành động/giây** trên `CUS-WEB-01` |
| 14:40–15:20 | Tối ưu 2 (cache bảng, `page_events`); kiểm chứng tương đương (mục 6) |
| 15:54 | Dựng lại lần 3 trên dữ liệu đầy đủ (3.532 sản phẩm, 10.000 khách): chỉ **2,2 hành động/giây** → profile lại: `saleable()` và `clean()` |
| 16:24 | Tối ưu 3, dựng lại lần 4, chạy chính thức từ 01/01 |
| 17:02 | Xong ngày 01/01 (ngày lễ, 8.544 hành động theo kế hoạch): 296 đơn, 2.469 phiên |
| 18:17 | **Máy bị tắt** (Windows event 1074) → mọi tiến trình dừng |
| 20:23 | Khởi động lại bằng `start_all.sh`, nối tiếp từ ngày 06/01 |
| 21:48 | Xong tới 10/01: 1.210 đơn, 6 đổi trả |

Trong quá trình chạy đã xóa và dựng lại 4 lần. Lý do: engine kiểm tra fingerprint của code (`EngineContract`), nên sau mỗi lần sửa code thì job cũ không chạy tiếp được.

Tốc độ thực tế hiện tại: ngày thường mất ~15–20 phút; ngày lễ ~38 phút.

## 6. Kiểm tra kết quả

**Tương đương với code gốc.** Script `eq_run.py` chạy cùng một quy trình trên code gốc (git worktree tại HEAD) và code đã tối ưu, dùng 2 cặp DB riêng (400 sản phẩm, 2.000 khách, kịch bản dw-lite thu nhỏ còn 10%), rồi so md5 của từng bảng:

| Lượt | Code gốc | Code tối ưu | Kết quả |
|---|---|---|---|
| 2 ngày | 1.473 thành công / 19 từ chối, 331 s | 1.473 / 19, 187 s | **33/33 bảng giống hệt** |
| 20 ngày (có đổi trả, hoàn tiền, đối soát seller) | 9.531 / 120, 2.029 s | 9.531 / 120, 956 s | **33/33 bảng giống hệt** |

**Tính nhất quán của dữ liệu đang sinh** (kiểm tra ngày 07/11):
- `order_items.net_amount = quantity × unit_price − discount_amount`: đúng 100%;
- `orders.final_amount = Σ net + shipping_fee − shipping_discount_amount`: đúng ở 1.013/1.013 đơn;
- replay `inventory_movements` = `inventory_daily_balance`: đúng 100%;
- Σ `order_item_promotions` = `order_items.discount_amount`: đúng ở 171/171 dòng.

## 7. Vấn đề & cách xử lý

| Vấn đề | Xử lý |
|---|---|
| Container Postgres không khởi động sau khi máy khởi động lại (bind-mount qua WSL) | Bật WSL trước, hoặc tạo lại bằng compose từ Windows. Đã đặt `restart: unless-stopped` |
| `start_mock.sh` có ký tự xuống dòng CRLF nên chạy lỗi trong WSL; đường dẫn tiếng Việt bị hỏng khi truyền qua PowerShell | Dùng script viết bằng LF (`scripts/mock_runner/*.sh`) |
| Tiến trình nền gắn với phiên làm việc bị dừng khi phiên kết thúc | `setsid nohup` trong WSL |
| Máy tắt/ngủ làm dừng mô phỏng | Chạy lại `start_all.sh` là nối tiếp. Sau khi máy ngủ dậy, `pipeline.py` tự resume job `FAILED`/`INTERRUPTED`, tối đa 30 lần |
| Bộ test pytest của Mock Studio có 1 test chạy > 13 phút ở cả code gốc lẫn code tối ưu | Thay bằng kiểm chứng tương đương trực tiếp (mục 6) |

Giới hạn còn lại:
- `products.cost_price` để trống (engine cố ý không điền);
- tháng 1 gần như không có thay đổi dimension, và quảng cáo chỉ có kênh WEB (xử lý ở bước 01);
- clickstream đã được rút gọn.

## 8. Ảnh hưởng & bước tiếp theo

- Các file engine đã sửa (**chưa commit**): `application/worker.py`, `engine/actors.py`, `engine/domain.py`, `engine/selection.py`, `infrastructure/storage.py`.
- File mới: `scripts/mock_runner/*`, `docs/mock-design/examples/scenarios/dw-lite-2026.json`.
- Theo dõi tiến độ: http://127.0.0.1:8765/api/overview (`last_day`).
- Bước tiếp theo: [01 — Cấu hình mock cho SCD và quảng cáo đa kênh](01_buoc-1.0_cau-hinh-mock-scd.md).

---

## 9. Sự cố 07/11/2026 23:14 — lỗi logic engine khi đối soát seller (ngày mô phỏng 14/01)

**Hiện tượng.** Job mô phỏng chuyển `FAILED` ở ngày 14/01. Log worker:

```
psycopg.errors.UniqueViolation: duplicate key value violates unique constraint
"seller_payouts_seller_id_period_start_period_end_key"
DETAIL: Key (seller_id, period_start, period_end)=(1, 2026-01-04, 2026-01-14) already exists.
```

Pipeline tự resume (cơ chế chống ngủ máy), nhưng lỗi này tất định nên lần nào cũng hỏng. Pipeline đã được dừng tay.

**Chẩn đoán** (phân biệt lỗi engine gốc với lỗi do phần tối ưu cache):
- 14/01 là ngày đầu tiên luồng đối soát `FIN-REC-01` chạy (38 kỳ, đều có `period_end = 14/01`), vì thời gian giữ tiền là 10 ngày.
- Kỳ 18 của seller 1 (Tiki Trading, rất nhiều đơn) chỉ chứa dòng 109, hoàn tất 04/01 lúc 03:10. Dòng 279 cùng seller hoàn tất 04/01 lúc 11:08, **chỉ hết thời gian giữ tiền sau** lượt đối soát đầu. Lượt `FIN-REC-01` kế tiếp trong cùng ngày gom dòng 279 và tạo kỳ mới với **cùng** `period_start = 04/01`, `period_end = 14/01`.
- Tập dòng "đã đối soát" được đọc **đúng** (dòng 109 bị loại, dòng 279 chưa có trong kỳ nào), nên không phải do cache. Đây là lỗi logic của engine gốc: không chặn việc tạo hai kỳ cho cùng seller, cùng ngày kết thúc. Lượt kiểm chứng 20 ngày trước đó (400 sản phẩm, 87 seller) không gặp vì không có seller nào nhiều đơn như vậy.

**Sửa** (`scripts/mock_platform/engine/finance.py`, `FIN-REC-01`): seller đã có kỳ kết thúc trong ngày thì không được chọn lại trong ngày đó. Dòng đủ điều kiện muộn hơn sẽ vào kỳ của ngày hôm sau. Mỗi seller có tối đa 1 kỳ cho mỗi ngày kết thúc, nên ràng buộc duy nhất không còn bị vi phạm.

**Hệ quả và xử lý:**
- Đổi code engine làm đổi fingerprint (`EngineContract`), nên job cũ không chạy tiếp được. Đã xóa `mock_oltp`/`mock_control` và sinh lại từ đầu lúc 23:15. **Database kho `dwh` giữ nguyên.**
- Engine tất định (seed 42) và luồng đối soát chưa chạy trước 14/01, nên dữ liệu 01/01–13/01 sinh lại phải **giống hệt** bản cũ. Sẽ kiểm chứng bằng cách trích lại `--until 2026-01-13` và so checksum với batch 1 của kho.
- Tạo lại `mock_oltp` làm mất quyền `dw_reader`. Đã cấp lại (`002_source_grants.sql`) và cho `pipeline.py` tự cấp lại sau bước chuẩn bị (`grant_dw_reader`).
- Thời gian mất: ~3,5 giờ sinh dữ liệu (13 ngày mô phỏng chạy lại).

## 10. Sự cố 08/11/2026 00:27–07:00 — máy ngủ + đổi nhánh git giữa lúc đang sinh dữ liệu

**Triệu chứng (07:01):** job `run` ở trạng thái `FAILED` tại ngày mô phỏng 05/01 (đã xong 27.541 hành động), tiến trình `pipeline.py` đã chết, log trong `data/logs/` không cập nhật từ 00:27.

**Nguyên nhân (đã kiểm chứng):**
1. **00:26–00:30, thao tác git:** `git stash -u` trên `main` → checkout nhánh `quybruno` → commit "ET". Thư mục làm việc bị thay bằng bản engine cũ hơn (cấu trúc phẳng `scripts/mock_platform/{domain,storage,worker}.py` còn **marker xung đột** `<<<<<<<`). Các file log (đã bị commit vào nhánh) cũng bị git ghi đè, nên tiến trình đang chạy ghi vào file cũ và không còn đọc được log. `core.autocrlf=true` biến các file `.sh` thành CRLF, khiến bash không chạy được.
2. **00:43–07:00, máy vào Modern Standby** (Event Log Kernel-Power 506/507). WSL bị treo; khi máy thức dậy, kết nối DB của job bị đứt → `FAILED`.

**Khôi phục, không mất dữ liệu đã sinh:**
- Không động vào thư mục và nhánh `quybruno` của người dùng. Tạo **git worktree riêng** `D:/PTIT/mock_run` = `main@20d3a2f` + `git stash apply stash@{0}` (đúng phiên bản engine đã sinh các ngày 01–04; pull `main` lúc 13:49 ngày 07/11, trước lần sinh lại lúc 23:15).
- Kiểm fingerprint `EngineContract` (sha256 của 26 file engine) so với kế hoạch đang chạy: `f76e4a3f…`. Bản dựng lại chỉ khớp khi tất cả file dùng CRLF, trừ `engine/domain.py`, `application/worker.py`, `infrastructure/storage.py` dùng LF. Đã chuẩn hóa 3 file này về LF, nên **nội dung code giống hệt hôm qua**.
- Worktree: `pipeline.py` dùng `REPO = parents[2]`, còn `start_all.sh` dùng `.venv` của repo chính. Khởi động serve + worker từ worktree; worker nhận lại job `7afa944a…` và chạy tiếp từ receipts (không áp dụng trùng hành động). Sau đó mới bật `pipeline.py`. Lưu ý: nếu job ở trạng thái FAILED mà bật pipeline trước, pipeline sẽ lập chunk mới đè lên ngày đang dở.
- **Kết quả (07:13):** ngày 05/01 hoàn tất, đang chạy 06/01, không có lỗi mới.

**Phòng ngừa:**
- Không đổi nhánh, stash hoặc pull trong thư mục repo chính khi Mock đang chạy. Mock hiện chạy từ `D:/PTIT/mock_run`, log ở `D:/PTIT/mock_run/data/logs/`.
- Tắt sleep (Settings → Power → *When plugged in, put my device to sleep: Never*) và cắm sạc. Khóa màn hình (Win + L) thì an toàn.
- Log worker cũ của đợt chạy đêm 07/11: `data/logs/mock_worker_20261107.log` (repo chính).
