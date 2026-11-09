#!/usr/bin/env bash
# Chạy ETL thật (extract -> transform -> load) từ mock_oltp_demo sang dwh_demo. Chạy trong WSL.
#   bash demo/03_run_etl.sh [--until YYYY-MM-DD]   (mặc định 2026-01-22)
# Biến môi trường chỉ áp dụng cho các lệnh trong script này.
set -euo pipefail
cd "$(dirname "$0")/.."
UNTIL=2026-01-22
[ "${1:-}" = "--until" ] && UNTIL=$2

export DW_SOURCE_URL="postgresql://dw_reader:dw_reader_local@127.0.0.1:55432/mock_oltp_demo"
export DW_TARGET_URL="postgresql://dw_etl:dw_etl_local@127.0.0.1:55432/dwh_demo"

PY=.venv/bin/python
$PY -m dw.etl.extract --until "$UNTIL"
BATCH=$(docker exec scripts-mock-postgres-1 psql -U mock -d dwh_demo -At -c "SELECT max(batch_id) FROM audit.batch_log")
echo "== Batch demo: $BATCH"
$PY -m dw.etl.transform --batch "$BATCH"
$PY -m dw.etl.load --batch "$BATCH"
docker exec scripts-mock-postgres-1 psql -U mock -d dwh_demo -c "SELECT batch_id, status, watermark_from, watermark_to FROM audit.batch_log ORDER BY batch_id DESC LIMIT 2"
