-- PLAN 1.1 — Các schema logic theo đề xuất mục 3. Chạy trên database `dwh` bằng `dw_etl`.
--   psql -U dw_etl -d dwh -v ON_ERROR_STOP=1 -f 003_schemas.sql

CREATE SCHEMA IF NOT EXISTS raw;    -- bản trích nguyên trạng từng batch, chỉ INSERT
CREATE SCHEMA IF NOT EXISTS stg;    -- dữ liệu đã chuẩn hóa, ánh xạ mã, gắn cờ kiểm tra
CREATE SCHEMA IF NOT EXISTS dw;     -- dimension, fact, bridge
CREATE SCHEMA IF NOT EXISTS mart;   -- view / materialized view phục vụ báo cáo
CREATE SCHEMA IF NOT EXISTS audit;  -- lịch sử nạp, cách ly lỗi, đối soát, chất lượng dữ liệu
CREATE SCHEMA IF NOT EXISTS bench;  -- biến thể cho thí nghiệm hiệu năng (không phục vụ báo cáo)

COMMENT ON SCHEMA raw   IS 'Bản trích nguyên trạng từ mock_oltp / tiki_crawl theo batch_id; bất biến (chỉ INSERT).';
COMMENT ON SCHEMA stg   IS 'Dữ liệu đã chuẩn hóa kiểu, ánh xạ mã (IR-01..07), gắn dq_status; làm mới theo batch.';
COMMENT ON SCHEMA dw    IS 'Kho dữ liệu: dimension (SCD1/2/3, mini-dimension, cây danh mục), fact, bridge.';
COMMENT ON SCHEMA mart  IS 'View/Materialized View, định nghĩa KPI dùng chung cho dashboard.';
COMMENT ON SCHEMA audit IS 'batch_log, quarantine, dq_result, reconciliation, data_dictionary.';
COMMENT ON SCHEMA bench IS 'Bản sao/biến thể dữ liệu cho BM01–BM03; không ảnh hưởng mart.';

-- Không ai ngoài chủ sở hữu tạo đối tượng trong public
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- dw_analyst: chỉ đọc dw và mart (kể cả bảng tạo sau này)
GRANT USAGE ON SCHEMA dw, mart TO dw_analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA dw, mart TO dw_analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA dw   GRANT SELECT ON TABLES TO dw_analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA mart GRANT SELECT ON TABLES TO dw_analyst;
-- dashboard cần xem trạng thái batch và lỗi (màn hình Chất lượng dữ liệu)
GRANT USAGE ON SCHEMA audit TO dw_analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA audit TO dw_analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit GRANT SELECT ON TABLES TO dw_analyst;

-- (ALTER ROLE dw_analyst ... read_only nằm ở 001 vì cần superuser)
ALTER DATABASE dwh SET search_path = dw, mart, public;
ALTER DATABASE dwh SET timezone = 'Asia/Ho_Chi_Minh';
