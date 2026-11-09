#!/usr/bin/env bash
# Kiểm thử measure (PLAN 4.8.7): so fact với OLTP gốc (độc lập ETL) + quy tắc công thức trên kho.
#   bash dw/tests/run_measure_tests.sh            # cửa sổ = watermark_to của batch SUCCESS mới nhất
set -uo pipefail
cd "$(dirname "$0")"
PG="docker exec -i scripts-mock-postgres-1 psql -U mock -q"
UNTIL=$($PG -d dwh -Atc "SELECT max(watermark_to) FROM audit.batch_log WHERE status = 'SUCCESS'")
echo "Cửa sổ kiểm: dữ liệu hoàn tất đến hết $UNTIL"
SRC=$(mktemp); DW=$(mktemp)
$PG -d mock_oltp -v until="$UNTIL" -f - < measure_src.sql > "$SRC" 2>&1
$PG -d dwh -f - < measure_dw.sql > "$DW" 2>&1
echo
echo "== A. So từng dòng kết quả: OLTP gốc (tính lại) vs kho"
fail=0
while IFS= read -r a && IFS= read -r b <&3; do
  if [ "$a" == "$b" ]; then echo "OK   $a"; else echo "DIFF nguồn: $a"; echo "     kho  : $b"; fail=$((fail+1)); fi
done < "$SRC" 3< "$DW"
[ "$(wc -l < "$SRC")" == "$(wc -l < "$DW")" ] || { echo "DIFF số dòng kết quả khác nhau"; fail=$((fail+1)); }
echo "→ $fail khác biệt"
rm -f "$SRC" "$DW"
echo
echo "== B. Quy tắc measure trên kho"
$PG -d dwh -P pager=off -f - < measure_rules.sql 2>&1
exit $fail
