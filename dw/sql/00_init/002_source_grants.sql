-- PLAN 1.1 — Quyền CHỈ ĐỌC trên nguồn OLTP cho ETL. Chạy trên database `mock_oltp` bằng `mock`.
--   psql -U mock -d mock_oltp -v ON_ERROR_STOP=1 -f 002_source_grants.sql
-- Nguyên tắc: ETL không bao giờ ghi vào mock_oltp (engine Mock Studio đang ghi và đối chiếu manifest).

GRANT CONNECT ON DATABASE mock_oltp TO dw_reader;
GRANT USAGE ON SCHEMA public TO dw_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dw_reader;
-- Bảng engine tạo sau này (nếu có) cũng tự cấp SELECT
ALTER DEFAULT PRIVILEGES FOR ROLE mock IN SCHEMA public GRANT SELECT ON TABLES TO dw_reader;
-- Chặn mọi quyền ghi (phòng trường hợp có GRANT nhầm trước đó)
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM dw_reader;
-- Truy vấn ETL không được giữ khóa lâu làm chậm engine
ALTER ROLE dw_reader SET statement_timeout = '10min';
ALTER ROLE dw_reader SET default_transaction_read_only = on;
