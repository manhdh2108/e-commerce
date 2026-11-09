#!/usr/bin/env bash
# PLAN 7.3 bước 6: tạm dừng mock khi đo (đóng băng worker bằng SIGSTOP — engine không có watchdog heartbeat,
# job vẫn RUNNING và chạy tiếp từ đúng chỗ khi SIGCONT), đo, rồi cho mock chạy lại (kể cả khi bench lỗi).
#   bash bench/run.sh            # setup + run
#   bash bench/run.sh run        # chỉ đo lại (dữ liệu bench đã có)
cd "$(dirname "$0")/.." || exit 1
mkdir -p data/logs bench/results
resume() { pkill -CONT -f '[s]cripts.mock_platform worker' && echo "mock worker: tiếp tục (SIGCONT)"; }
trap resume EXIT
pkill -STOP -f '[s]cripts.mock_platform worker' && echo "mock worker: tạm dừng (SIGSTOP) lúc $(date +%T)"
sleep 3
.venv/bin/python -m bench.run_bench "${1:-all}" "${@:2}" 2>&1 | tee -a data/logs/bench.log
