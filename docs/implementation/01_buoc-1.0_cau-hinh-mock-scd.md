# 01 — PLAN 1.0: Cấu hình mock cho SCD và quảng cáo đa kênh

| | |
|---|---|
| Ngày thực hiện | 07/11/2026, 22:00–22:30 |
| Trạng thái | ✅ Xong. Áp dụng từ ngày mô phỏng **25/01/2026** (đổi từ 30/01 ngày 08/11, xem §10). Dự kiến ban đầu: **30/01/2026** (khi đợt 1 kết thúc, dự kiến ~04:00–05:00 08/11) |
| Liên quan PLAN | Mục 1.0; khoảng trống G2, G3, G7 |
| Liên quan đề xuất | M2 "Lịch sử chính xác" (SCD 1, 2, minh họa 3), T4; drill-across doanh thu–quảng cáo theo tháng–kênh (mục 6) |

## 1. Mục tiêu

Kịch bản đang chạy (`dw-lite-2026`) gần như không tạo thay đổi thuộc tính dimension: sau 6 ngày có 0 sản phẩm, 0 khách và 1 seller thay đổi. Chi phí quảng cáo thì chỉ có ở kênh WEB. Bước này tạo một phiên bản cấu hình mới để từ 30/01 dữ liệu nguồn có:
- thay đổi để minh họa **SCD1, SCD2, SCD3** và mini-dimension;
- **chi phí quảng cáo cho cả 3 kênh** Web / App / Livestream.

Ràng buộc: **không sửa code engine**. Engine kiểm tra fingerprint code; đổi code thì phải sinh lại dữ liệu từ đầu.

## 2. Đầu vào

- Kịch bản [dw-lite-2026.json](../mock-design/examples/scenarios/dw-lite-2026.json) (91 hành động).
- Hồ sơ thực thể `medium-ecommerce.json` với 21 nhóm actor.
- Định nghĩa hành động `scripts/mock_platform/resources/actions.json` và code xử lý `engine/domain.py`.
- Trạng thái lúc làm: mô phỏng đã xong tới 11/01; đợt 1 chạy tới 29/01.

## 3. Phân tích trước khi làm

Đọc trực tiếp code xử lý từng hành động, không dựa vào nhãn trên giao diện:

| Hành động | Code thực sự làm gì | Quyết định |
|---|---|---|
| `SYS-03` Xét hạng thành viên | `customers.membership_tier = new_tier` (gán tier chỉ định, không xét theo chi tiêu) | ✅ Bật, dùng variants để tier ngẫu nhiên có trọng số |
| `CUS-02` Đổi nơi cư trú | `customers.province = city = province` | ✅ Bật. Danh sách chỉ có TP.HCM, Hà Nội, Đà Nẵng (thiếu Cần Thơ) |
| `CUS-01` Đổi thông tin cá nhân | `full_name = value or full_name cũ` | ❌ Để trống thì không đổi gì; điền giá trị thì mọi khách bị đặt **cùng một tên**. Bỏ |
| `MGR-01` Xét hạng người bán | `sellers.tier = tier` | ✅ Bật (SCD2 + SCD3 hạng seller) |
| `MGR-02` Khóa người bán | `sellers.status = Suspended`, mọi sản phẩm của shop `is_active = false` | ✅ Bật thưa (4 lần/năm) |
| `SEL-01` Đổi tên shop | `shop_name = value or "<tên cũ> · <4 ký tự>"` (tự sinh) | ✅ Bật (SCD1) |
| `SEL-02` Đổi liên hệ shop | Sinh email mới | Giữ như cũ (đã bật, 12 lần/năm) |
| `SEL-03` Đổi địa điểm | `sellers.province = city = province` | ✅ Bật (SCD2 tỉnh seller) |
| `SEL-04` Sửa tên sản phẩm | `name = value or name cũ` | ❌ Cùng vấn đề như `CUS-01`. Bỏ |
| `CAT-01` Chấp thuận chuyển danh mục | Chỉ xử lý yêu cầu do `SEL-08` tạo; `SEL-08` gán **một** danh mục cố định cho mọi sản phẩm | ❌ Không thực tế. Bỏ |
| `MKT-01` Tạo chiến dịch | `target_channel_code = campaign_channel` ∈ `WEB`/`APP`/`LIVESTREAM` | ✅ 3 chiến dịch mỗi đợt, mỗi kênh một chiến dịch |
| `ADS-01` Báo cáo quảng cáo | Chọn chiến dịch đang chạy chưa có báo cáo trong ngày; **từ chối nếu tổng chi vượt `budget_amount`** | ✅ Tăng ngân sách và số lần mỗi ngày |

Hai phát hiện quan trọng:
1. **Ngân sách cũ (3.000.000đ trong 31 ngày) cạn sau khoảng 10 ngày**, vì chi trung bình ~316.000đ/ngày. Tháng 1 vì thế chỉ có ~10 ngày có chi phí quảng cáo. Ngân sách mới là 12.000.000đ cho 31 ngày.
2. **Mã kênh thật của engine là `WEB`/`APP`/`LIVESTREAM`**, không phải `MOBILE_APP`/`LIVE` như [OLTP_SCHEMA.md §10](../data-model/oltp/OLTP_SCHEMA.md). Quy tắc IR-03 trong PLAN đã được sửa để nhận cả hai bộ mã.

Nhóm actor đúng vai trò (lấy theo `roles` trong hồ sơ thực thể):

| Hành động | Nhóm actor |
|---|---|
| `SYS-03` | `orders-team-8` (Tiến trình tự động của hệ thống) |
| `CUS-02` | `customers` |
| `MGR-01`, `MGR-02` | `catalog-team-3` (Nhân viên quản lý người bán) |
| `SEL-01`, `SEL-03` | `sellers` |

## 4. Cách thực hiện

### 4.1. Script sinh cấu hình (để tái lập)

[scripts/mock_runner/make_dw_scd_config.py](../../scripts/mock_runner/make_dw_scd_config.py) đọc `dw-lite-2026.json` rồi ghi `dw-scd-2026.json`:

| Hành động | Cấu hình |
|---|---|
| `SYS-03` | 25 lần/ngày; variants `new_tier`: Member 2, Silver 5, Gold 3, Platinum 1 (trọng số) |
| `CUS-02` | 3 lần/ngày; variants tỉnh: TP.HCM 4, Hà Nội 4, Đà Nẵng 2 |
| `MGR-01` | 1 lần/ngày; variants `tier`: Preferred 5, Normal 3, Mall 2 |
| `SEL-03` | 1 lần mỗi 4 ngày (từ 30/01); variants tỉnh như trên |
| `MGR-02` | 16/03, 15/06, 15/09, 15/12 |
| `SEL-01` | 1 lần mỗi 10 ngày (từ 02/02) |
| `MKT-01` | `variant_mode: cycle`, 3 variants (WEB · Brand Awareness, APP · Retargeting, LIVESTREAM · Livestream Show); `amount` 12.000.000, `days` 31; mỗi ngày đặc biệt (ngày 1 hằng tháng và các ngày đôi) chạy 3 lần → lần lượt WEB, APP, LIVESTREAM |
| `ADS-01` | 4 lần/ngày (mỗi chiến dịch đang chạy tối đa 1 báo cáo/ngày) |

Variants được chọn bằng hash của `seed` + `action_id` (`ParameterProfiles.resolve`), độc lập với RNG nghiệp vụ, nên vẫn tái lập được.

```bash
python scripts/mock_runner/make_dw_scd_config.py
```

### 4.2. Kiểm tra và lưu vào Mock Studio

1. `POST /api/config-imports/preview` với nội dung file: bước này chỉ kiểm tra, không lưu.
2. `POST /api/config-imports`: lưu thành phiên bản cấu hình mới.
3. `POST /api/plans` cho ngày `next_day`: chỉ lập kế hoạch, **không chạy**, để engine kiểm tra từng `actor_pool` đúng vai trò và chạy preflight.

### 4.3. Cho pipeline tự chuyển kịch bản theo ngày

Sửa [pipeline.py](../../scripts/mock_runner/pipeline.py):

```python
SCHEDULE = [("2026-01-01", "dw-lite-2026.json"), ("2026-01-30", "dw-scd-2026.json")]
```

- `version_for(day)`: chọn kịch bản có hiệu lực tại `day` (tự import nếu chưa có) và trả về ngày cuối của kịch bản đó.
- Mỗi đợt không vượt qua ngày chuyển kịch bản. Đợt 1 vốn đã kết thúc đúng 29/01, nên đợt 2 bắt đầu 30/01 bằng `dw-scd-2026`.
- Chỉ khởi động lại **tiến trình pipeline**. Worker và job đang chạy không bị ảnh hưởng.

## 5. Quá trình thực hiện (output thật)

```
written ...\docs\mock-design\examples\scenarios\dw-scd-2026.json
preview status 200
{'name': 'DW 2026 · SCD + quảng cáo đa kênh (áp dụng từ 30/01)', 'config': 91, 'warnings': [
  'Lịch ngày cụ thể trong file được giữ nguyên, không tự đổi năm hoặc dời theo ngày nhập.',
  'Một số ngày trong file trước ngày chạy tiếp 2026-01-12; chúng không làm chạy lại dữ liệu cũ.',
  'Nhập cấu hình chỉ lưu Control DB. Không tự đồng bộ, tạo dữ liệu nền hoặc chạy mock.'], 'summary': 7}
planned/day avg 3245 max 14086

import 201 {'id': '4401328b-f736-4c7d-9e26-045412e54e8e', 'revision': 1,
            'name': 'DW 2026 · SCD + quảng cáo đa kênh (áp dụng từ 30/01)'}
plan check 200 []          # preflight rỗng = không có lỗi vai trò/tham số
```

Khởi động lại pipeline lúc ~22:16:

```
1104 .venv/bin/python -m scripts.mock_platform worker
1105 .venv/bin/python -m scripts.mock_platform serve --port 8765
1508 .venv/bin/python -u scripts/mock_runner/pipeline.py
... leftover-run RUNNING day 2026-01-12 ... AUT-WH-04 · Chốt số dư cuối ngày
```

Khối lượng: trung bình 3.245 hành động/ngày theo kế hoạch, so với 3.212 của dw-lite (chỉ thêm ~1%), nên tốc độ sinh dữ liệu gần như không đổi.

## 6. Kiểm tra kết quả

| Tiêu chí | Kết quả |
|---|---|
| Cấu hình hợp lệ theo validator của Mock Studio | ✅ preview 200, 91 hành động |
| Nhóm actor đúng vai trò, preflight không lỗi | ✅ `plan check 200 []` |
| Không đổi code engine (job đang chạy vẫn tiếp tục) | ✅ job đợt 1 vẫn RUNNING sau khi khởi động lại pipeline |
| Áp dụng đúng từ 30/01 | ⏳ Kiểm tra khi đợt 2 bắt đầu: log pipeline phải có `chunk plan 2026-01-30 -> … version DW 2026 · SCD + quảng cáo đa kênh` |

Truy vấn cần chạy sau khi mô phỏng qua khoảng 05/02 để xác nhận dữ liệu thay đổi thật:

```sql
-- seller đổi hạng/tỉnh/tên (SCD1/2/3)
select count(*) filter (where updated_at::date >= '2026-01-30') from sellers;
-- khách đổi hạng/tỉnh
select count(*) filter (where updated_at::date >= '2026-01-30') from customers;
-- quảng cáo theo kênh
select channel_code, count(*), sum(cost_amount) from ad_spend_logs group by 1;
select target_channel_code, count(*) from marketing_campaigns group by 1;
```

## 7. Vấn đề & cách xử lý

| Vấn đề | Xử lý |
|---|---|
| Không có hành động đổi giá sản phẩm; chuyển danh mục không thực tế | `Dim_Product` không có SCD2 giá/danh mục từ nguồn. Logic SCD2 vẫn cài, kiểm thử bằng ca có kiểm soát ở `stg`. SCD3 chuyển sang **hạng seller** (G7) |
| `SYS-03` gán hạng ngẫu nhiên, không theo chi tiêu (có thể xuống hạng) | Ghi giới hạn này trong báo cáo; mini-dimension của DW tự tính bucket chi tiêu từ fact |
| `CUS-02`/`SEL-03` chỉ có 3 tỉnh để chọn | Đủ để minh họa SCD2; ghi giới hạn |
| Tháng 1 không có thay đổi dimension và quảng cáo đa kênh | Tháng 1 là giai đoạn "trước thay đổi", dùng để đối chiếu với giai đoạn sau |
| Lệnh chạy bị ngắt giữa chừng một lần | Chạy lại; script ghi file theo kiểu idempotent, import kiểm tra tên trước để không tạo phiên bản trùng |
| Bước `plan check` tạo một bản ghi plan thừa trong `mock_control` | Không ảnh hưởng (plan chưa được đưa vào job) |

## 8. Ảnh hưởng & bước tiếp theo

File thay đổi:
- mới: `scripts/mock_runner/make_dw_scd_config.py`, `docs/mock-design/examples/scenarios/dw-scd-2026.json`;
- sửa: `scripts/mock_runner/pipeline.py` (`SCHEDULE`, `version_for`);
- sửa PLAN: mục 1.0, IR-03, `map_channel`, G2/G3, `dim_product`, lịch mục 10.

Bước tiếp theo: **02 — PLAN 1.1, khởi tạo database `dwh`, role chỉ đọc, các schema `raw/stg/dw/mart/audit/bench`.**

## 10. Cập nhật 08/11/2026: chuyển sớm sang kịch bản SCD từ 25/01

**Lý do:** cần dữ liệu SCD thật sớm hơn để chuẩn bị demo. Các mốc 30/01 ở các mục trên là thiết kế ban đầu; mốc đang có hiệu lực là bảng dưới.

| Hành động | Lịch ban đầu | Lịch hiện tại |
|---|---|---|
| `SYS-03`, `CUS-02`, `MGR-01` | Từ 30/01 | Từ **25/01** |
| `SEL-03` tỉnh seller | Mỗi 4 ngày từ 30/01 | Mỗi 4 ngày từ **25/01** |
| `SEL-01` tên shop | Mỗi 10 ngày từ 02/02 | Mỗi 10 ngày từ **26/01** |
| `MGR-02` khóa seller | 16/03, 15/06, 15/09, 15/12 | **Thêm 27/01** để demo có ca thật |
| `MKT-01` quảng cáo đa kênh | Từ 01/02 | Không đổi |
| `ADS-01` | 4 lượt/ngày từ 30/01 | 4 lượt/ngày từ **25/01** |

**Cách làm:** API chỉ có `pause`/`resume`, không đổi được kế hoạch của job đang chạy, nên kế hoạch được sửa trực tiếp trong `mock_control`:

1. Dừng `pipeline.py` (vì nó tự resume job đang `PAUSED`), tạm dừng job, sao lưu kế hoạch.
2. Sinh lại `dw-scd-2026.json`, nạp vào Mock Studio và lập một kế hoạch thử để engine chạy preflight.
3. Ghi cấu hình mới vào `config_snapshot` của kế hoạch đang chạy. Ngày 24/01 đang dở được giữ đúng số lượng cũ bằng cách đặt `special["2026-01-24"]`.
4. Resume job và khởi động lại pipeline. Sửa `SCHEDULE` trong `pipeline.py` thành `("2026-01-25", "dw-scd-2026.json")`.

Code engine không đổi nên `EngineContract` vẫn khớp. Không chèn SCD vào ngày 24/01 vì ngày đó đã chạy dở: thay đổi mới có thể mang giờ sớm hơn các hành động đã chạy.

**Bằng chứng:** [evidence/01_chuyen-kich-ban-scd-25-01.txt](evidence/01_chuyen-kich-ban-scd-25-01.txt).

**Hệ quả cần ghi trong báo cáo:**
- Dữ liệu 01/01–24/01 sinh theo `dw-lite-2026`, từ 25/01 theo `dw-scd-2026`.
- Đây là thao tác ngoài luồng chuẩn của Mock Studio. Muốn tái lập đúng lượt sinh này thì phải áp dụng đúng mốc chuyển trên.
- Lần khóa seller 27/01 là bổ sung cho demo, không thuộc lịch nghiệp vụ ban đầu.
