#!/usr/bin/env bash
# Chạy một module ETL trong WSL bằng .venv của repo.
#   bash dw/etl/run.sh extract [--until YYYY-MM-DD]
# Log JSON được ghi thêm vào data/logs/etl.log.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p data/logs
mod=$1; shift
.venv/bin/python -m "dw.etl.$mod" "$@" 2>&1 | tee -a data/logs/etl.log
