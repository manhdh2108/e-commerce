#!/usr/bin/env bash
# Tạo/cập nhật cấu trúc kho (PLAN 4 + audit). Idempotent. Chạy sau 00_init/run_init.sh.
#   bash dw/sql/run_ddl.sh
set -euo pipefail
cd "$(dirname "$0")"
C=${PG_CONTAINER:-scripts-mock-postgres-1}
for f in 20_stg/201_stg.sql 30_dw/301_dim_date.sql 30_dw/302_dimensions.sql 30_dw/303_facts.sql 50_audit/501_audit.sql 50_audit/502_dictionary_metadata.sql 50_audit/503_batch_status.sql 40_mart/401_mart.sql 40_mart/402_consistency.sql; do
  echo "== $f"
  docker exec -i -e PGOPTIONS=--client-min-messages=warning "$C" psql -q -U dw_etl -d dwh -v ON_ERROR_STOP=1 < "$f"
done
echo "ddl done"
