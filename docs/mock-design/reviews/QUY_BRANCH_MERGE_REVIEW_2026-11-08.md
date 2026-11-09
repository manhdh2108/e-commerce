# Rà soát nhánh quy trước khi tích hợp vào main

Ngày rà soát: 08/11/2026. Báo cáo là phương án tích hợp, chưa sửa code nghiệp vụ và chưa merge.

## 1. Trạng thái Git và phạm vi đã đối chiếu

- Checkout hiện tại: `quy`, commit `edbfb8b` (ET), trùng `origin/quybruno` đang lưu ở local.
- `main` và `origin/main` đang cùng commit `20d3a2f` (config quy mô vừa khoảng 1.000 lượt đặt/ngày).
- Điểm chung: `19c0991`. Nhánh quy có một commit mới; main có bốn commit sau điểm chung, bao gồm nâng cấp engine và tổ chức lại thư mục.
- Đối chiếu các ref local trên; không fetch hoặc khẳng định remote chưa có commit khác.
- Khi bắt đầu rà soát working tree sạch, index không có unmerged entries và không có MERGE_HEAD: chưa có phiên merge đang dở.
- Dùng `git merge-tree --write-tree main HEAD` để kiểm tra kết quả tích hợp mà không checkout/merge vào working tree.
- Có 71 file khác so với điểm chung: 26 file DW, 21 tài liệu/config, 13 log/PID/output, 6 file engine mock và 4 file runner, cùng CLAUDE.md.

### Sáu file sẽ conflict khi tích hợp

| File theo cấu trúc main | Loại conflict | Cách xử lý đề xuất |
|---|---|---|
| scripts/mock_platform/application/worker.py | content, từ worker.py cũ | Giữ worker của main; tối ưu cache phải được port và kiểm chứng riêng. |
| scripts/mock_platform/infrastructure/storage.py | content, từ storage.py cũ | Giữ storage main, không thay bằng file cũ bị dở. |
| scripts/mock_platform/engine/domain.py | content, từ domain.py cũ | Giữ domain main; chỉ port tối ưu có kiểm chứng. |
| scripts/mock_platform/engine/actors.py | add/add | Main đã có file này từ đợt nâng cấp; không ghép hai file thành một hoặc giữ cả hai. |
| scripts/mock_platform/engine/selection.py | add/add | Giữ bộ lọc, ownership, thời gian và preference của main. |
| scripts/mock_platform/engine/finance.py | add/add | Lấy main làm nền, port có chọn lọc phần chống lập trùng đối soát. |

Các đường dẫn gốc mà nhánh quy sửa là `scripts/mock_platform/{domain,storage,worker}.py`. Main đã chuyển sang engine/infrastructure/application. Không khôi phục ba module phẳng này vào bản sau merge.

## 2. Lỗi chặn chạy cần xử lý trước

### P0 — Dấu conflict đã nằm trong commit

Ba file `scripts/mock_platform/domain.py`, `storage.py`, `worker.py` chứa nguyên văn `<<<<<<< Updated upstream`, `=======`, `>>>>>>> Stashed changes`. Đây không chỉ là Git báo conflict trong một phiên merge: dấu conflict đã được commit vào nhánh.

Đã kiểm tra cú pháp bằng ast.parse: cả ba file không parse được. Các marker ghi cả đường dẫn cũ và đường dẫn sau refactor, phù hợp với việc trộn bản trước/sau tổ chức lại thư mục. Chưa đủ bằng chứng để kết luận thao tác Git cụ thể đã gây ra điều này.

Hệ quả: không thể dùng checkout hiện tại làm bản chạy chuẩn hoặc xác nhận số liệu benchmark của code hiện tại. Không chỉ xóa ba dấu phân cách rồi coi là đã sửa xong.

### P1 — Bản storage/worker đang ghép thiếu cơ chế

- `storage.py:278`: constructor UnitOfWork chỉ khởi tạo changes/cache nhưng các nhánh mới gọi positions và row_cache; SharedTableCache.merge cũng dùng positions. Chọn phần code mới trong conflict vẫn thiếu khởi tạo và một phần implementation hiện có ở main.
- `storage.py:326`: header prefetch_by bị ghép vào thân truy vấn dùng biến id cũ; không phải implementation hoàn chỉnh tương đương main.
- `worker.py:20`: gọi SharedTableCache trong khi các import đang conflict. Import mới của một file ở đường dẫn cũ cũng không khớp package hiện tại.

Giải pháp là port trên bản main hoàn chỉnh, không vá tiếp từ ba file phẳng đang hỏng.

## 3. Các thay đổi mock: nên giữ gì, sửa gì?

### 3.1. Finance: lỗi thực sự đáng sửa, nhưng bản vá có thay đổi nghiệp vụ

`engine/finance.py:147–171` loại seller đã có payout cùng period_end trước khi tạo payout mới. Main có unique `(seller_id, period_start, period_end)` và unique order_item_id trong payout_items.

Điểm tốt: xử lý tình huống dòng khác của cùng seller đủ điều kiện muộn hơn trong ngày, tránh lặp insert cùng khóa kỳ. Mô tả sự cố ngày mô phỏng 14/01 hợp lý với cấu trúc code và constraint.

Điểm phải hiểu đúng:

- Đây không phải tối ưu thuần túy. Từ sau bản vá, một seller tối đa một payout cho cùng ngày kết thúc, kể cả khi hai kỳ có period_start khác nhau.
- Dòng đủ điều kiện sau payout đầu phải chờ kỳ tiếp theo. Tổng tiền cuối cùng có thể bằng nhau nhưng ngày đối soát/chi tiền có thể khác.
- Nếu người dùng giữ cố định tham số end của kỳ, những dòng đến muộn không tự được xử lý chỉ vì đã sang ngày mô phỏng tiếp theo: end vẫn cũ và seller vẫn bị loại.
- Việc chặn không phân biệt Pending/Approved/Paid. Cần kiểm tra đủ ba trạng thái hiện được workflow hỗ trợ; không tự thêm trạng thái hoặc cơ chế lập lại kỳ ngoài hợp đồng hiện có.

Đề xuất: lấy main làm nền; định nghĩa rõ cutoff/kỳ đối soát và tính idempotent. Giữ payout đã chốt bất biến; dòng đến muộn chuyển kỳ kế tiếp trong trường hợp end tự chạy theo ngày. Không tự thêm dòng vào payout đã Approved/Paid. Trường hợp explicit end phải trả lý do rõ ràng thay vì chỉ báo hết đối tượng. Nếu muốn cho phép nhiều kỳ/ngày thì cần mô hình khóa kỳ khác, không bỏ constraint để hết lỗi.

Kiểm chứng bắt buộc: cùng seller, hai dòng đủ điều kiện vào hai thời điểm trong ngày; lặp request; resume; explicit end; Pending/Approved/Paid; ngày sau thu nhận dòng còn lại; tổng ledger và tiền chi đúng. Chưa tái hiện tình huống finance bằng job/DB trong lần rà soát này.

### 3.2. Tăng tốc: hướng đáng giữ, chưa có cơ sở nhận nguyên trạng

| Thay đổi | Giá trị | Vấn đề trước khi nhận |
|---|---|---|
| clean() có nhánh nhanh cho bản ghi phẳng | Bớt serialize JSON cho từng dòng | Kiểm tra tương đương Decimal/date/null/lồng nhau; không làm thay đổi chuẩn hóa của manifest. |
| UnitOfWork.one() dùng vị trí theo ID | Tránh tìm tuyến tính trong bảng cache | Đồng bộ vị trí sau insert/update/delete; cần port trên implementation main đầy đủ. |
| SharedTableCache giữa các transaction | Giảm đọc lại các bảng | Phải xử lý rollback, recovery, reset, ghi qua đường khác, pause/resume và đổi job; không chỉ dựa vào xóa cache đầu ngày. |
| RuntimeState dùng runtime_cache của worker | Giảm truy vấn Control | Chỉ phản ánh effect đã commit; kiểm chứng crash giữa Business commit và Control finish, giá trị thiếu và cập nhật metadata. |
| selection dùng ảnh products đã cache | Giảm quét catalog bằng SQL lặp lại | Giữ đúng filters, scope/ownership, eligibility, thời gian, preferences và thứ tự ID. |
| actors đọc id + trường sampling thay vì toàn dòng | Giảm dữ liệu truyền | PostgreSQL vẫn COUNT + ordered string_agg + MD5 trên cả tập mỗi lần; vẫn có chi phí quét/sắp xếp. Cần benchmark. |
| Bỏ pool_pre_ping | Bớt kiểm tra kết nối | Dễ lỗi kết nối cũ sau DB restart/máy sleep, trong khi runner chủ yếu xử lý chính tình huống này. Đề xuất giữ main cho đến khi đo được và có cơ chế thay thế. |

Không có test mới cho các thay đổi này trong diff nhánh. Các log chạy hoặc phát biểu “33 bảng giống hệt” không thay thế được kiểm chứng trên bản code đã giải conflict, đặc biệt main đã có engine/config khác bản chung.

Tối ưu không cần thiết để đưa lớp DW vào repo. Có thể giữ main ở lần tích hợp DW đầu, rồi đưa tối ưu thành thay đổi riêng sau khi đo CPU, thời gian SQL, số query, bộ nhớ và thời gian chạy. Không thêm if/else cho từng bộ dữ liệu để tăng tốc.

## 4. Hai config DW

Đã dùng bộ kiểm tra nhập của main trong bản sao tạm biệt lập để kiểm tra cả hai JSON. Cả hai hợp lệ về cấu hình; mọi actor_pool đang bật khớp role của hồ sơ medium trên main. Điều này không có nghĩa chúng chạy được với engine cũ đang checkout.

### dw-lite-2026.json

- So với `main:examples/scenarios/upgraded-linked-2026.json`, chỉ đổi sáu hành động: GST/CUS-WEB-01, 02, 03.
- WEB-01 giảm khoảng 0,5; WEB-02/03 giảm khoảng 0,3, có làm tròn số. Giảm cả mặc định và lịch ngày.
- Quota đặt hàng không tăng: ngày thường trung bình **100,2 lượt**, khoảng **57–177**. Không phải config quy mô vừa 1.000 lượt/ngày.
- Không tự viết lại giá/ID sản phẩm Tiki. Giảm số session/view làm tăng tỷ lệ chuyển đổi nhìn thấy trên dashboard, kể cả khi số yêu cầu đặt hàng không đổi; số thành công vẫn có thể khác do nguồn phiên/giỏ.

Đề xuất giữ làm profile **DW chạy nhẹ**, không thay thế config vận hành chính hoặc config medium. Đưa vào `docs/mock-design/examples/scenarios/dw/`, ghi rõ baseline và khác biệt; tránh để người dùng nhầm “tối ưu” với cùng dữ liệu nhưng chạy nhanh hơn.

### dw-scd-2026.json

Kế thừa bản nhẹ, bật thêm:

| Mã | Hành động / lượng yêu cầu |
|---|---|
| SYS-03 | Xét/đổi hạng khách, 25 lần/ngày; có Member/Silver/Gold/Platinum. |
| CUS-02 | Đổi tỉnh khách, 3 lần/ngày. |
| MGR-01 | Xét hạng seller, 1 lần/ngày. |
| SEL-03 | Chuyển tỉnh seller, mỗi 4 ngày một lần. |
| MGR-02 | Khóa seller vào bốn ngày cụ thể trong năm. |
| SEL-01 | Đổi tên shop, mỗi 10 ngày một lần, bắt đầu sau mốc chuyển. |
| MKT-01 | Mỗi đợt tạo ba chiến dịch WEB/APP/LIVESTREAM, ngân sách 12 triệu/chiến dịch, 31 ngày. |
| ADS-01 | Mặc định tối đa 4 yêu cầu báo cáo/ngày, còn phụ thuộc chiến dịch đủ điều kiện và ngân sách. |

Hướng dùng hành động nghiệp vụ sẵn có qua config để có biến động đầu vào DW là phù hợp. Nhưng không được hiểu mock đang thực hiện SCD1/2/3: mock cập nhật OLTP hiện tại; DW phải quan sát/lưu lịch sử và xử lý SCD.

Các điểm cần sửa/ghi rõ:

1. Mốc 30/01 nằm trong runner, không phải hàng rào của JSON. Nhập trực tiếp dw-scd và chạy trước 30/01 vẫn có các count 25/3/1 hoạt động. Cần biến lịch áp dụng thành cấu hình rõ ràng hoặc tạo special=0 trước mốc cho các hành động mới, không dựa vào tên file.
2. Đổi hạng ngẫu nhiên là kịch bản kích thích thay đổi để thử DW, không phải chính sách xếp hạng theo chi tiêu thực tế. 25 yêu cầu không bảo đảm 25 lần đổi giá trị vì có thể chọn trùng hoặc giữ hạng.
3. Khóa seller không có lịch khôi phục trong bộ này. Với ít seller, bốn lần khóa có thể làm giảm đáng kể catalog bán được. Phải giới hạn theo quy mô hoặc tách thành ca kiểm thử có chủ đích.
4. Dòng reason “Vi phạm chính sách mô phỏng” là dấu vết thử nghiệm trong dữ liệu nghiệp vụ; thay bằng lý do nghiệp vụ phù hợp nếu dùng profile vận hành. Dấu vết nguồn/test vẫn giữ trong Control/metadata phục vụ truy vết.
5. Chính sách hoa hồng chỉ có Normal/Preferred/Mall; không thêm Platinum cho seller. Platinum ở config này là hạng **khách**, không được trộn hai danh mục.
6. Thông tin thay đổi nhiều lần sẽ không trở thành lịch sử đầy đủ nếu chỉ extract một snapshot sau khi mock đã chạy xa. Cần lịch extract/CDC phù hợp.

Giữ config này như profile **kiểm chứng thay đổi dimension**, không làm mặc định của mọi người hoặc âm thầm thay bộ 1.000 lượt/ngày.

### Lỗi vị trí file

Nhánh commit hai JSON ở ngay `docs/mock-design/examples/`. Runner và make_dw_scd_config lại đọc/ghi từ `examples/scenarios/`. Hồ sơ `examples/settings/medium-ecommerce.json` mà runner dùng cũng không có trong cây commit nhánh quy (có trên main). Clone riêng nhánh hiện tại sẽ thiếu các đường dẫn này ngay cả sau khi sửa Python conflict.

## 5. Runner: có ích nhưng cần thiết kế lại trước khi dùng chung

Giá trị nên giữ: chia ngày thành chunk dưới giới hạn quota, giữ checkpoint, không để chunk vượt mốc đổi cấu hình, dùng API thay vì ghi thẳng bảng nghiệp vụ.

Các vấn đề cụ thể:

- `pipeline.py:9`: hard-code đường dẫn WSL `/mnt/d/PTIT/KÌ 1 năm 4/DATA WAREHOUSE/e-commerce`; chọn nguồn tiki_crawl_share.db cũng cố định.
- `pipeline.py:12–15`: năm, ngày đầu/cuối, seed, hồ sơ, kịch bản và mốc chuyển nằm trong code. Mâu thuẫn mục tiêu người dùng điều khiển bằng config.
- `pipeline.py:48–49`: tự resume PAUSED, kể cả người dùng vừa chủ động tạm dừng bằng UI. `stop_all.sh` chỉ là dừng process, không tạo trạng thái tạm dừng nghiệp vụ bền vững.
- `pipeline.py:50–58`: resume cả lỗi nghiệp vụ và lỗi kết nối; reset retry counter ngay khi thấy RUNNING nên lỗi lặp có thể tiếp tục nhiều hơn giới hạn được mô tả.
- `pipeline.py:22–29`: lặp lại HTTP request sau timeout. `new_job` có request_key ổn định trong từng lần gọi, đây là điểm đúng; nhưng cả vòng chạy sau khi khởi động lại chưa có định danh pipeline bền vững. POST khác cũng không tự trở thành idempotent chỉ vì gọi lại.
- `pipeline.py:69–73`: tiếp quản mọi job active trong overview, không chỉ job của chính pipeline; FAILED/INTERRUPTED từ phiên trước lại không được nhận ở vòng leftover dù wait_job có nhánh xử lý.
- `pipeline.py:79`: chỉ kiểm tra có actors, không xác nhận profile/hash/config có đúng bộ pipeline yêu cầu.
- `pipeline.py:98–103`: kiểm tra counts thay cho marker/receipt hoàn tất sync/bootstrap; có customers không đồng nghĩa bootstrap đúng yêu cầu, có một product không đồng nghĩa đã sync mọi sản phẩm mới.
- `pipeline.py:110`: tìm version bằng tên, có thể dùng cấu hình đã chỉnh trên UI nhưng giữ nguyên tên; cần ID + revision/hash và snapshot.
- `pipeline.py:84–97`: cấp quyền DW bằng tài khoản mock nằm trong runner sinh dữ liệu, bắt mọi exception rồi bỏ qua. Cấp quyền thuộc bước khởi tạo/tích hợp DW, cần báo lỗi rõ nếu bắt buộc, không trộn với engine.
- `start_all.sh` mở server/worker rồi chạy luôn pipeline đến cuối năm. Không nên khiến lệnh mở web vô tình tự sinh dữ liệu.
- `start_all.sh` không chạy crawl-worker như launcher main; `stop_all.sh` pkill theo pattern rộng, có thể dừng process của checkout khác.
- Hai module Python runner chạy tác dụng phụ ở top-level; nên chuyển thành lớp điều phối/CLI có main guard, theo quy ước Python OOP của dự án.

Đề xuất tách `start web` và `run pipeline`. Runner chỉ hoạt động khi người dùng chọn, có tham số/JSON nguồn, range, seed, profile, lịch version, chunk limit và retry. Lưu pipeline/job ID; tôn trọng PAUSED; chỉ resume tự động những lỗi tạm thời đã phân loại và trong phạm vi job của nó. Dùng PID/lock theo checkout hoặc quản lý process hiện có. Không mặc định chạy pipeline từ launcher chung.

`make_dw_scd_config.py` không phải file thừa về chức năng, nhưng đường dẫn sai với file đã commit và có thể lệch bản JSON được nhập. Chọn một nguồn chuẩn: giữ JSON làm artifact nhập UI, còn builder có tham số và kiểm tra output tái lập được; hoặc giữ builder và sinh JSON ở quy trình rõ ràng. Không duy trì hai bản khác nhau không được kiểm tra.

## 6. DW/ETL: nên nhận, với ranh giới và giới hạn rõ ràng

### Nội dung mới đáng giữ

- `dw/sql/00_init/`: database dwh, role đọc nguồn/ghi kho/đọc dashboard, tách quyền.
- `dw/sql/20_stg/`, `30_dw/`, `50_audit/`: staging chuẩn hóa, dimension/fact/bridge, metadata, batch log, chất lượng và cách ly.
- `dw/etl/extract.py`: đọc OLTP bằng role read-only, một PostgreSQL snapshot REPEATABLE READ; COPY sang raw theo batch, checksum và trạng thái EXTRACTED.
- `dw/etl/transform.py` và mappings: chuẩn hóa/ánh xạ, DQ, loại trùng, cách ly, đối chiếu số dòng.
- `dw/etl/inject_test_errors.py`: chèn lỗi vào batch TEST_ERRORS của raw, **không ghi vào OLTP**. Đây là công cụ thử DQ có chủ đích, không phải file thừa.
- `dw/tools/export_dictionary.py`, tài liệu M1/M2/M3, kế hoạch và bằng chứng triển khai: giữ để review DW.

Các script DW dùng psycopg có trong scripts/requirements-mock.txt; không kết luận thiếu dependency chỉ vì requirements.txt gốc mới ghi requests. Nên có entrypoint cài đặt/tài liệu DW rõ ràng khi tách sử dụng.

### Những việc cần chốt/sửa trước khi gọi là DW chạy hoàn chỉnh

1. **Snapshot nhất quán không phải snapshot đúng cuối ngày.** Extract lấy last_day qua API trước transaction, trong khi worker có thể đang ghi ngày kế tiếp. Các dimension FULL lấy current state, các row giao dịch cũng có thể đã đổi sau watermark_to. Ví dụ muốn đọc hết 29/01 nhưng khách đã đổi hạng trong 30/01: raw có thể mang hạng mới. Nếu cần as-of watermark, dừng/điều phối writer tại ranh giới an toàn cho tới khi snapshot nguồn được thiết lập, hoặc xây cơ chế CDC/lịch sử nguồn; không dùng WHERE updated_at <= cutoff để giả khôi phục phiên bản cũ bị ghi đè.
2. **SCD chưa được triển khai Load.** Có DDL và hash chuẩn bị nhưng không có load dimension/fact trong nhánh; README implementation cũng ghi bước 08 đang chờ. Không giới thiệu nhánh như đã hoàn tất SCD1/2/3, mart và pipeline E2E.
3. **Lịch sử bị mất nếu extract quá thưa.** Hai lần snapshot không tái tạo được mọi lần đổi hạng/tỉnh/tên đã xảy ra giữa chúng. Cần xác định yêu cầu lấy lịch sử quan sát hay đầy đủ sự kiện rồi thiết kế nhịp extract/CDC tương ứng.
4. `extract.py:172`: watermark từ max SUCCESS chưa loại TEST_ERRORS. Khi có Load, phải loại batch thử và quản lý stream nguồn; không để batch inject/rerun tùy ý đẩy tiến độ production. Hiện chỉ EXTRACTED/TRANSFORMED nên chưa tự tiến watermark SUCCESS, phù hợp với việc Load còn thiếu nhưng dễ khiến extract lặp từ mốc đầu.
5. `config.py:16`, `transform.py:126–129`: mốc watermark và ngày tính tuổi cố định năm 2026. Đưa baseline/as-of vào cấu hình hoặc batch contract; không cố định máy/năm trong logic chung.
6. `map_channel.csv` ánh xạ WEB/APP/LIVESTREAM sang ID 1/2/3. Hồ sơ môi trường có thể đổi thứ tự/tập channel. Nên ánh xạ qua natural code/name vào raw.channels, không giả ID luôn tương ứng.
7. DDL SCD2 đang dùng độ hạt DATE, unique `(business_id, valid_from)`. Nếu cần nhiều thay đổi cùng ngày thì phải định nghĩa gom cuối ngày hoặc nâng độ chính xác; tránh tuyên bố lưu đầy đủ thay đổi trong ngày.
8. DQ tính row_number trước loại lỗi: nếu bản rn=1 mới nhất sai và rn=2 hợp lệ, bản hợp lệ cũng bị loại trùng. Cần chốt “giữ phiên bản mới nhất dù lỗi thì cách ly cả khóa” hay “giữ bản hợp lệ mới nhất”; code/comment hiện tại chưa làm rõ.
9. Đây là kiểm tra source code, chưa chạy DDL/Extract/Transform vào PostgreSQL hiện có. Các file evidence là bằng chứng do nhánh cung cấp, chưa tái xác minh. Không chạy inject_test_errors hoặc run_init chỉ để rà soát vì chúng ghi DB.

Ranh giới phải giữ: crawler → SQLite; sync do người dùng yêu cầu và append-only vào OLTP; mock ghi OLTP; ETL chỉ đọc OLTP và ghi dwh. Không để DW sửa sản phẩm/giá/ID Tiki hoặc cập nhật trực tiếp Control checkpoint của mock.

## 7. File thừa hoặc tài liệu cần dọn khi tích hợp

| Nhóm | Phương án |
|---|---|
| Toàn bộ 13 file data/logs/* trong diff, gồm .log/.out/crawl_pids.txt | Bỏ khỏi bản tích hợp, thêm ignore data/logs/. Log/PID của máy cá nhân không là mã nguồn; PID không mang sang máy khác được. Không xóa log local trong lần review này. |
| domain.py/storage.py/worker.py phẳng cũ | Không phục hồi vào main; giữ cấu trúc engine/infrastructure/application hiện tại. |
| File scenarios cũ có trên nhánh nhưng main đã xóa/chuyển trước đó | Không khôi phục khi giải conflict. Chúng không phải nội dung mới của commit quy; diff HEAD với main có thể gây nhầm. |
| CLAUDE.md | Nội dung nói generator/DW chưa triển khai, chưa có test, 27 bảng và tài liệu cũ là nguồn chuẩn: sai với main hiện tại. Loại hoặc viết lại; không dùng làm quy định lấn át docs/mock-design/MOCK_SYSTEM_RULES.md. |
| docs/DW_BUILD_PLAN.md, M1/M2/M3 ở docs root | Nội dung có ích, vị trí chưa khớp link implementation đang trỏ docs/data-model/warehouse/. Chuyển thống nhất và sửa link, không để nhiều bản cùng tên ở các nơi. |
| docs/implementation/ và evidence | Giữ như nhật ký/bằng chứng của máy/commit đã chạy; ghi nguồn và giới hạn tái lập, không coi trạng thái ✅ là chứng nhận main sau merge. |
| Hai config dw-lite/dw-scd | Không thừa về mục đích; tách thư mục/profile DW và sửa đường dẫn, không ghi đè hai bộ config vận hành. |
| pipeline/start_all/stop_all | Không nhận nguyên trạng vào đường khởi động mặc định; refactor thành công cụ tùy chọn hoặc để lần tích hợp sau. |

## 8. Phương án tích hợp đề xuất

### Đợt A — Đưa DW vào trên nền main, bảo toàn mock

1. Ghi lại hai commit đầu nhánh và sao lưu DB nếu chuẩn bị chạy thử/migrate; merge code không tự merge dữ liệu PostgreSQL/SQLite hay checkpoint từ máy người viết.
2. Khi bắt đầu thực hiện, tạo nhánh tích hợp từ main mới nhất đã fetch. Main local đang kiểm tra là 20d3a2f; phải đối chiếu lại ref lúc đó.
3. Tích hợp commit quy trên nhánh trung gian. Với sáu conflict, dùng main làm nền theo bảng mục 1; không dùng một lệnh chọn toàn bộ ours/theirs cho mọi file.
4. Nhận DW/SQL/mappings/docs, sửa paths/link/config mốc thời gian và vấn đề ranh giới snapshot; không nhận runtime logs/PID, không phục hồi module mock cũ.
5. Đưa hai profile DW vào thư mục rõ ràng; giữ nguyên bộ đầy đủ/medium và launcher hiện tại. Không tự chọn profile theo ngày trong engine.
6. Port bản sửa finance đã làm rõ kỳ/cutoff, kèm kiểm thử riêng. Nếu chưa chốt semantics thì tách commit/PR finance, không lẫn trong commit thêm DW.

### Đợt B — Tối ưu engine

Port từng tối ưu đo được trên main, giữ seed/thứ tự chọn đối tượng/rule/manifest. Chạy so sánh trước/sau cùng nguồn, seed, config và khoảng ngày; ghi số query, elapsed và RSS. Cache phải có cơ chế cập nhật/vô hiệu hóa và kiểm thử failure/recovery, không chỉ kiểm chứng một lượt thành công.

### Đợt C — Công cụ điều phối tùy chọn

Refactor runner theo mục 5. Các mốc, profile, nguồn và giới hạn đi vào JSON/CLI. Launcher web chỉ khởi động dịch vụ; thao tác sinh dữ liệu phải do người dùng gọi rõ ràng. Cấp quyền DW thuộc bước init, không thuộc hàm sinh dữ liệu.

## 9. Tiêu chí trước merge vào main

- Không còn marker conflict; mọi Python module parse/import được, shell syntax hợp lệ.
- Không còn import module phẳng hoặc đường dẫn /mnt/d cá nhân; không có bản cũ đè module main.
- Test mock của main chạy lại trên SQLite và PostgreSQL biệt lập; test UI liên quan còn pass. Không dùng DB đang có dữ liệu để làm test destructive.
- Finance có các test nêu tại mục 3.1, đặc biệt không làm job crash vì unique và không bỏ mất dòng chưa đối soát.
- Tối ưu có so sánh kết quả hợp lệ/không hợp lệ, business rows, timestamps, ledger, checkpoint, receipts/manifest khi lỗi/resume; không chỉ so số dòng. Cache không phản ánh thay đổi rollback.
- JSON nhập được, mọi actor role đúng; chạy nhỏ trước 30/01 và sau mốc chứng minh hiệu lực rõ ràng và dữ liệu khác biệt có chủ đích.
- DW đọc bằng dw_reader, thử ghi vào OLTP phải bị từ chối; ETL ghi đúng dwh, không SQLite crawler/Control.
- Extract được kiểm chứng tại ranh giới ngày trong lúc có writer; TEST_ERRORS không tiến watermark chính; chạy lại không trùng dữ liệu/fact khi Load được bổ sung.
- Khoản nào chưa triển khai (Load/SCD/mart) phải ghi rõ; không đánh dấu hoàn thành toàn hệ thống.

## 10. Những gì đã thực sự kiểm tra trong lần rà soát

- Đọc diff 71 file theo nhóm; đối chiếu trực tiếp sáu thay đổi mock với bản main và đọc runner, config, ETL/DDL/mappings/docs liên quan.
- Tính conflict bằng merge-tree: đúng sáu file nêu ở mục 1. Không tạo phiên merge hoặc thay đổi index/checkout.
- Parse các Python script của nhánh: phát hiện ba file mock lỗi cú pháp; Python trong dw parse được. Năm script shell runner/DW qua kiểm tra bash -n. Các kiểm tra này không kiểm chứng SQL/runtime.
- Xuất bản main vào thư mục tạm ngoài repo, dùng validator thật và SQLite Control tạm để kiểm tra hai config DW + actor roles; không ghi DB của người dùng.
- Tính lại quota ngày thường và xác định đúng sáu hành động traffic bị giảm so với profile khoảng 100 lượt/ngày trên main.
- Chưa chạy đầy đủ tests, benchmark, UI, migration hay pipeline; chưa xác minh DB/log do người viết cung cấp. Không kết luận “tăng tốc mà dữ liệu giống hệt” khi chưa có kiểm chứng này.

**Khuyến nghị:** tích hợp phần DW có chọn lọc trên main; giữ kiến trúc/config mock hiện tại. Sửa finance và tối ưu thành các thay đổi có bằng chứng riêng. Không merge nguyên commit ET rồi coi việc xóa dấu conflict là hoàn tất.
