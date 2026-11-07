#!/usr/bin/env bash
# Chạy toàn bộ bước khởi tạo (PLAN 1.1) trong container Postgres của Mock Studio.
# Dùng từ Git Bash / WSL:  bash dw/sql/00_init/run_init.sh
set -euo pipefail
cd "$(dirname "$0")"
C=${PG_CONTAINER:-scripts-mock-postgres-1}
psql_in() { docker exec -i "$C" psql -v ON_ERROR_STOP=1 "$@"; }

psql_in -U mock   -d postgres  < 001_database_roles.sql
psql_in -U mock   -d mock_oltp < 002_source_grants.sql
psql_in -U dw_etl -d dwh       < 003_schemas.sql
echo "init done"
