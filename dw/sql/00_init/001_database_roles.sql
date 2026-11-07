-- PLAN 1.1 — Database kho và các role. Chạy trên database `postgres` bằng superuser `mock`.
-- Idempotent: chạy lại không lỗi. Mật khẩu chỉ dùng cho môi trường local.
--   psql -U mock -d postgres -v ON_ERROR_STOP=1 -f 001_database_roles.sql

-- 1. Role
DO $$
BEGIN
  -- ETL đọc nguồn OLTP: chỉ SELECT trên mock_oltp
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_reader') THEN
    CREATE ROLE dw_reader LOGIN PASSWORD 'dw_reader_local';
  END IF;
  -- ETL ghi kho: sở hữu các schema trong dwh
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_etl') THEN
    CREATE ROLE dw_etl LOGIN PASSWORD 'dw_etl_local';
  END IF;
  -- Nhà phân tích / dashboard: chỉ đọc dw, mart (đề xuất Bảng 3)
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_analyst') THEN
    CREATE ROLE dw_analyst LOGIN PASSWORD 'dw_analyst_local';
  END IF;
END $$;

-- ETL cần đọc nguồn → dw_etl kế thừa quyền của dw_reader
GRANT dw_reader TO dw_etl;

-- 2. Database kho (CREATE DATABASE không chạy được trong DO/transaction → dùng \gexec)
SELECT 'CREATE DATABASE dwh OWNER dw_etl ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'dwh') \gexec

-- Chỉ các role kho được kết nối dwh
REVOKE CONNECT ON DATABASE dwh FROM PUBLIC;
GRANT CONNECT ON DATABASE dwh TO dw_etl, dw_analyst;

-- Nhà phân tích luôn ở phiên chỉ đọc trong dwh (cần superuser nên đặt ở đây, không ở 003)
ALTER ROLE dw_analyst IN DATABASE dwh SET default_transaction_read_only = on;
