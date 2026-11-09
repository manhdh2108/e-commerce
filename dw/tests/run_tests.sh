#!/usr/bin/env bash
# Chạy bộ kiểm thử tổng hợp T1–T7 trong WSL bằng .venv của repo (PLAN mục 8).
#   bash dw/tests/run_tests.sh            # đầy đủ (~5 phút, gồm nạp lại batch SUCCESS mới nhất để kiểm T3)
#   bash dw/tests/run_tests.sh --quick    # chỉ kiểm thử đọc, ~20 giây
#   bash dw/tests/run_tests.sh --only T4,T6
# Kết quả cũng được ghi thêm vào data/logs/test.log; mã thoát ≠ 0 nếu có FAIL.
cd "$(dirname "$0")/../.." || exit 1
mkdir -p data/logs
.venv/bin/python -m dw.tests.run_tests "$@" 2>&1 | tee -a data/logs/test.log
exit "${PIPESTATUS[0]}"
