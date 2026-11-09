#!/usr/bin/env bash
# Chạy dashboard nền trong WSL (tách khỏi terminal) → mở http://localhost:8501 trên Windows.
#   bash dashboard/run.sh          # khởi động (bỏ qua nếu đang chạy)
#   bash dashboard/run.sh stop     # dừng
cd "$(dirname "$0")/.." || exit 1
mkdir -p data/logs
if [ "${1:-}" = "stop" ]; then pkill -f '[s]treamlit run dashboard/app.py' && echo stopped; exit 0; fi
pgrep -f '[s]treamlit run dashboard/app.py' >/dev/null && { echo "dashboard đang chạy: http://localhost:8501"; exit 0; }
setsid nohup .venv/bin/streamlit run dashboard/app.py --server.port 8501 --server.address 0.0.0.0 \
  --server.headless true --browser.gatherUsageStats false >> data/logs/dashboard.log 2>&1 < /dev/null &
sleep 4; pgrep -af '[s]treamlit run' | cut -c1-80; echo "http://localhost:8501"
