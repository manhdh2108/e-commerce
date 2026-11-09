# Bước 09 — PLAN 6: Mart, drill-across và dashboard

> Ngày thực hiện: 08/11/2026 · Dữ liệu: batch 4 (hoàn tất đến hết 12/01/2026) · Kết quả: mart 21/21 kiểm thử đạt, dashboard 5/5 màn hình chạy, KPI = SQL độc lập
> Mã: [dw/sql/40_mart/401_mart.sql](../../dw/sql/40_mart/401_mart.sql), [dashboard/app.py](../../dashboard/app.py), B6 trong [dw/etl/load.py](../../dw/etl/load.py)
> Kiểm thử: [dw/tests/test_mart.sql](../../dw/tests/test_mart.sql), [dashboard/test_app.py](../../dashboard/test_app.py) · Bằng chứng: [evidence/09_mart_dashboard_check.txt](evidence/09_mart_dashboard_check.txt)

## 1. Mục tiêu

- **6.1** Tầng `mart`: một nơi định nghĩa KPI dùng chung; materialized view theo tháp phân tầng (M2 §3.2); trạng thái refresh để dashboard hiển thị thời điểm dữ liệu.
- **6.2** Drill-across: doanh thu × quảng cáo theo (tháng, kênh); doanh thu × tồn kho theo (sản phẩm, tháng) — giữ cả nhóm chỉ có một phía.
- **6.3** Dashboard Streamlit + Plotly 5 màn hình, mỗi bảng có nút xuất CSV, hiển thị đơn vị tiền, khoảng thời gian, thời điểm dữ liệu.

## 2. Đầu vào

- `dw.*` sau bước 08 (batch 4 SUCCESS): 1.195 dòng bán, 219.067 dòng tồn kho, 1 dòng quảng cáo tháng, dimension SCD, bridge, closure.
- `audit.*` (batch_log, batch_table_log, quarantine, dq_result, reconciliation) cho màn hình Chất lượng dữ liệu.
- Role chỉ đọc `dw_analyst` (bước 02) để dashboard không thể ghi vào kho.

## 3. Phân tích trước khi làm

- **MV chỉ lưu measure cộng được.** Số đơn / số khách là `COUNT(DISTINCT)` — chỉ đúng tại grain của MV; đặt hậu tố `_na` để người dùng không cộng lên grain cao hơn. Tỷ lệ, bình quân (AOV, CTR, tỷ lệ giảm giá…) tính trong view/dashboard từ tử và mẫu.
- **KPI theo kỳ tính trực tiếp từ fact atomic** (`v_kpi_period`, GROUPING SETS năm/quý/tháng) để số đơn cả năm là distinct cả năm, không phải tổng các tháng.
- **Tồn kho semi-additive:** tồn cuối tháng = ngày snapshot cuối của tháng; tồn bình quân = AVG theo ngày; không SUM qua ngày. Tháng chưa kết thúc (01/2026 mới đến 12/01) → ghi rõ ngày snapshot.
- **Drill-across phải FULL OUTER JOIN trên dimension dùng chung** (`month_key`, `channel_key`). Dữ liệu thật đã có đúng ca kiểm thử T5: kênh **App có doanh thu nhưng chưa có chi phí QC** (chiến dịch duy nhất là WEB) — INNER JOIN sẽ làm mất 152 triệu doanh thu App.
- **Doanh thu × tồn kho ghép bằng mã nghiệp vụ `product_id`**, không bằng `product_key` (một sản phẩm có thể có nhiều phiên bản SCD2 trong tháng).
- **Refresh chỉ sau batch SUCCESS (B6)**, `REFRESH … CONCURRENTLY` (mỗi MV có unique index) để dashboard vẫn đọc được trong lúc refresh. Refresh lỗi không hủy batch; `v_data_freshness.mart_stale` báo "dữ liệu cũ".
- Môi trường `.venv` (tạo bằng `uv`) chưa có Streamlit/Plotly/pandas → cài bằng `uv pip`, ghim phiên bản trong [dashboard/requirements.txt](../../dashboard/requirements.txt).

## 4. Cách thực hiện

```bash
# trong WSL, từ thư mục repo
~/.local/bin/uv pip install --python .venv/bin/python -r dashboard/requirements.txt
bash dw/sql/run_ddl.sh                         # đã thêm 40_mart/401_mart.sql (idempotent)
docker exec scripts-mock-postgres-1 psql -U dw_etl -d dwh -c "select * from mart.refresh_all(4)"   # lần đầu; sau đó load.py tự gọi
docker exec -i scripts-mock-postgres-1 psql -U dw_analyst -d dwh -f - < dw/tests/test_mart.sql
.venv/bin/python dashboard/test_app.py         # chạy 5 màn hình không cần trình duyệt
bash dashboard/run.sh                          # chạy nền → http://localhost:8501 (dừng: bash dashboard/run.sh stop)
```

### 4.1. Đối tượng trong `mart`

| Đối tượng | Loại | Grain / nội dung | Tầng |
|---|---|---|---|
| `kpi_definitions`, `v_kpi_definitions` | bảng/view | 24 KPI: công thức, nguồn, A/SA/NA, lỗi thường gặp, đơn vị | — |
| `mv_sales_day_product` | MV | ngày × sản phẩm (phiên bản) × seller × kênh; 12 measure cộng được | 2 |
| `mv_sales_month_category` | MV | tháng × danh mục lá × kênh | 3 |
| `mv_sales_month_channel` | MV | tháng × kênh (phía bán của drill-across); có doanh thu đơn gắn chiến dịch | 3 |
| `mv_sales_month_seller_tier` | MV | tháng × phiên bản seller: hạng/tỉnh/trạng thái **lúc bán** và **hiện tại** | 3 |
| `mv_sales_month_customer_region` | MV | tháng × tỉnh khách lúc mua × tỉnh hiện tại (khách vãng lai riêng) | 3 |
| `mv_inventory_month_product` | MV | tháng × product_id × kho: tồn cuối, tồn bình quân, dòng chảy, ngày hết hàng, giá trị ước tính | 3 |
| `mv_ads_month_channel` | MV | tháng × kênh (phía QC của drill-across) | 3 |
| `mv_promotion_month` | MV | tháng × voucher: giảm giá và doanh thu **phân bổ theo weight** của bridge | 3 |
| `v_kpi_period` | view | KPI năm / quý / tháng tính từ fact atomic (GROUPING SETS) | 3–4 |
| `v_drill_sales_ads` | view | FULL OUTER JOIN doanh thu × chi phí QC; `revenue_per_ad_cost`, CTR, CPC, cờ `missing_sales`/`missing_ads` | drill-across |
| `v_drill_sales_inventory` | view | FULL OUTER JOIN theo (product_id, tháng): số món hoàn tất vs xuất kho, tồn cuối, vòng quay, số ngày tồn | drill-across |
| `v_category_tree`, `v_data_freshness`, `v_dq_batch`, `v_quarantine_summary`, `v_unknown_keys` | view | hỗ trợ dashboard | — |
| `refresh_status`, `refresh_all(batch)` | bảng/hàm | refresh CONCURRENTLY 8 MV, ghi thời điểm, số dòng, giây | B6 |

Quyền: `dw_analyst` SELECT trên `mart` (và `bench` cho màn hình Hiệu năng).

### 4.2. B6 trong luồng ETL

`load.py` → sau khi batch **SUCCESS** và commit, gọi `mart.refresh_all(batch_id)` trong kết nối riêng; log `mart_refreshed` (số dòng từng MV) hoặc `mart_refresh_failed` (mart giữ bản cũ).

### 4.3. Dashboard ([dashboard/app.py](../../dashboard/app.py))

Đầu mọi màn hình: *Dữ liệu đến hết ngày*, *batch nạp gần nhất*, *thời điểm refresh mart*, *đơn vị VND (UTC+7)*; cảnh báo nếu mart cũ. Mọi bảng có nút **Xuất CSV** (UTF-8 BOM, mở được bằng Excel).

| Màn hình | Nội dung | Bộ lọc | Kỹ năng thể hiện |
|---|---|---|---|
| Tổng quan bán hàng | 8 KPI (doanh thu thuần, số đơn, số món, AOV, tỷ lệ voucher, số khách, tỷ trọng khách vãng lai, biên lãi ước tính); xu hướng; theo danh mục (cấp con của lựa chọn, qua closure); theo kênh; top 10 sản phẩm / seller; khuyến mãi phân bổ; định nghĩa KPI | Ngày, danh mục gốc → con, hạng seller lúc bán, kênh, có/không voucher | Drill-down Năm→Quý→Tháng→Ngày, gốc→lá; non-additive tính lại tại mỗi kỳ; bridge |
| Lịch sử thuộc tính (SCD) | Heatmap hạng lúc bán × hạng hiện tại; so doanh thu theo hai cách nhìn; tỉnh khách lúc mua vs hiện tại; tra cứu phiên bản SCD2 (seller/customer/product); bảng SCD3; treemap mini-dimension | Tháng | SCD2 vs SCD1, SCD3, mini-dimension |
| Đối soát vận hành | Doanh thu × chi phí QC (tháng–kênh) + cảnh báo nhóm một phía; doanh thu × tồn kho (sản phẩm–tháng): tồn cuối, giá trị ước tính, hai mốc thời gian bán, vòng quay | Tháng | Drill-across, semi-additive |
| Chất lượng dữ liệu | Danh sách batch; số dòng đọc/hợp lệ/WARN/cách ly/trùng theo bảng; lý do cách ly; đối soát; DQ có vi phạm; khóa 0/−1 | Ngày nạp, batch, giai đoạn, nguồn | Audit, quarantine, reconciliation |
| Hiệu năng | Kết quả BM (khi có `bench.bm_result`); thời gian refresh MV; dung lượng bảng/partition | Thí nghiệm | Bench (bước 10) |

## 5. Quá trình thực hiện (diễn biến thật)

| Giờ | Việc | Kết quả |
|---|---|---|
| 11:3x | Cài `streamlit 1.50.0`, `plotly 6.3.0`, `pandas 2.3.2` bằng `uv pip` | OK |
| 11:40 | Chạy `401_mart.sql` + `refresh_all(4)` | **Lỗi** `column reference "mv_name" is ambiguous` (tham số OUT trùng tên cột trong `ON CONFLICT`) |
| 11:41 | Thêm `#variable_conflict use_column` | 8 MV refresh trong ~3,5 s (mv_inventory_month_product 2,6 s, 18.257 dòng) |
| 11:42 | Gắn B6 vào `load.py`; chạy `test_mart.sql` bằng `dw_analyst` | **21/21 PASS** |
| 11:45 | Viết dashboard; sửa truy vấn "theo danh mục" (tách FROM/WHERE thay vì thay chuỗi) | — |
| 11:47 | `dashboard/test_app.py` | 5/5 màn hình không exception; KPI + bộ lọc khớp SQL |
| 11:49 | `bash dashboard/run.sh` | `/_stcore/health` = 200 từ Windows qua `localhost:8501` và IP WSL |

## 6. Kiểm tra kết quả

**Mart = truy vấn độc lập trên fact (21/21 PASS)** — trích:

| Kiểm tra | Mart | Độc lập |
|---|---:|---:|
| Σ net MV ngày×SP / tháng×danh mục / seller tier / tỉnh khách | 858.670.245 | 858.670.245 |
| Số đơn từng (tháng, kênh) sai lệch | 0 | 0 |
| Tồn cuối tháng (ngày snapshot cuối) | 5.669.671 | 5.669.671 |
| Σ giảm giá phân bổ qua bridge | 3.040.000 | 3.040.000 |
| Drill-across QC: Σ doanh thu / Σ chi phí | 858.670.245 / 2.932.996 | 858.670.245 / 2.932.996 |
| KPI tháng AOV | 828.033,02 | 828.033,02 |
| KPI năm: số đơn (distinct cả năm) | 1.037 | 1.037 |
| Mart không cũ | 0 | 0 |

**Drill-across thật (T01/2026):**

| Kênh | Doanh thu thuần | Số đơn | Chi phí QC | Doanh thu/chi phí | Ghi chú |
|---|---:|---:|---:|---:|---|
| Web | 706.525.701 | 752 | 2.932.996 | 240,89 | CTR 1,13% |
| App | 152.144.544 | 285 | — | — | `missing_ads = true` — vẫn giữ nhờ FULL OUTER JOIN |

**Dashboard (T5 phần giao diện):** 5/5 màn hình chạy không lỗi; "Doanh thu thuần" 858.670.245 đ, "Số đơn" 1.037, "AOV" 828.033 đ = SQL độc lập; chọn kênh Web → 706.525.701 đ = SQL độc lập. Màn hình SCD hiện thông báo "chưa có seller đổi hạng" (đúng với dữ liệu trước 30/01); màn hình Hiệu năng báo chờ BM ở bước 10.

## 7. Vấn đề & cách xử lý

| Vấn đề | Xử lý |
|---|---|
| `mv_name` mơ hồ trong hàm `refresh_all` (OUT param trùng tên cột) | `#variable_conflict use_column` |
| `.venv` không có pip (tạo bằng uv) | `~/.local/bin/uv pip install --python .venv/bin/python …`, ghim phiên bản |
| Số đơn/khách không cộng được qua grain | Hậu tố `_na` trong MV; KPI kỳ tính từ fact atomic; dashboard luôn tính lại `COUNT(DISTINCT)` theo bộ lọc |
| Tháng 01/2026 chưa kết thúc | Tồn cuối kỳ ghi rõ ngày snapshot; cảnh báo trên màn hình Đối soát |
| Chỉ 1 chiến dịch QC (WEB) đến 12/01 | Đúng dữ liệu nguồn (kịch bản QC đa kênh chạy từ 30/01); dùng làm ca T5 "kênh chỉ có một phía" |

## 8. Ảnh hưởng & bước tiếp theo

- Từ nay mỗi lần `load` SUCCESS sẽ tự refresh mart; dashboard đọc ngay dữ liệu mới (cache 5 phút).
- Mở dashboard: **http://localhost:8501** (WSL phải đang chạy; khởi động lại: `bash dashboard/run.sh`).
- **Tiếp theo:** bước 10 — thí nghiệm BM01 (MV vs truy vấn fact), BM02 (partition pruning), BM03 (index ghép) ghi vào `bench.bm_result` → màn hình Hiệu năng tự hiển thị (hạn 10/11). Bước 11 — kiểm thử T1–T7 (dùng lại `test_mart.sql`, `test_app.py`, `run_measure_tests.sh`, `test_scd_load.py`).
