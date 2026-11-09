#!/usr/bin/env bash
# Tạo lại cặp database demo từ bản sao của dữ liệu thật. Chạy trong WSL. Chạy lại = reset demo.
#   mock_oltp  --pg_dump (chỉ đọc)--> mock_oltp_demo
#   dwh        --pg_dump (bỏ bench)--> dwh_demo
# Chỉ DROP/CREATE hai database *_demo. Không ghi vào mock_oltp, mock_control, dwh.
# Dữ liệu nằm trong volume Docker (ổ D); không tạo file dump trung gian.
set -euo pipefail
C=scripts-mock-postgres-1
psql_() { docker exec -i "$C" psql -U mock -v ON_ERROR_STOP=1 -q "$@"; }

echo "== Xóa bản demo cũ (nếu có)"
psql_ -d postgres <<'SQL'
DROP DATABASE IF EXISTS mock_oltp_demo WITH (FORCE);
DROP DATABASE IF EXISTS dwh_demo WITH (FORCE);
CREATE DATABASE mock_oltp_demo OWNER mock ENCODING 'UTF8' TEMPLATE template0;
CREATE DATABASE dwh_demo OWNER dw_etl ENCODING 'UTF8' TEMPLATE template0;
REVOKE CONNECT ON DATABASE dwh_demo FROM PUBLIC;
GRANT CONNECT ON DATABASE dwh_demo TO dw_etl, dw_analyst;
GRANT CONNECT ON DATABASE mock_oltp_demo TO dw_reader;
ALTER ROLE dw_analyst IN DATABASE dwh_demo SET default_transaction_read_only = on;
SQL

echo "== Sao chép mock_oltp -> mock_oltp_demo"
docker exec "$C" sh -c "pg_dump -U mock -d mock_oltp | psql -U mock -d mock_oltp_demo -v ON_ERROR_STOP=1 -q -o /dev/null"

echo "== Sao chép dwh -> dwh_demo (bỏ schema bench)"
docker exec "$C" sh -c "pg_dump -U mock -d dwh --exclude-schema=bench | psql -U mock -d dwh_demo -v ON_ERROR_STOP=1 -q -o /dev/null"

psql_ -d postgres -At -c "SELECT datname, pg_size_pretty(pg_database_size(datname)) FROM pg_database WHERE datname LIKE '%\_demo' ORDER BY 1"
psql_ -d dwh_demo -At -c "SELECT 'Kho demo: batch ' || batch_id || ', dữ liệu đến ' || watermark_to FROM audit.batch_log WHERE status = 'SUCCESS' ORDER BY batch_id DESC LIMIT 1"
