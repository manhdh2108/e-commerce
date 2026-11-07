#!/usr/bin/env bash
# Start Mock Studio serve + worker and the resumable year pipeline, detached from the terminal.
# Run inside WSL:  bash scripts/mock_runner/start_all.sh
# Logs: data/logs/mock_{serve,worker,pipeline}.log . Safe to re-run: resumes from the last finished day.
cd "$(dirname "$0")/../.." || exit 1
mkdir -p data/logs
PY=.venv/bin/python
pgrep -f '[s]cripts.mock_platform serve' >/dev/null || setsid nohup $PY -m scripts.mock_platform serve --port 8765 >>data/logs/mock_serve.log 2>&1 < /dev/null &
pgrep -f '[s]cripts.mock_platform worker' >/dev/null || setsid nohup $PY -m scripts.mock_platform worker >>data/logs/mock_worker.log 2>&1 < /dev/null &
sleep 6
pgrep -f '[p]ipeline.py' >/dev/null || setsid nohup $PY -u scripts/mock_runner/pipeline.py >>data/logs/mock_pipeline.log 2>&1 < /dev/null &
sleep 2; pgrep -af '[m]ock_platform (serve|worker)|[p]ipeline.py' | cut -c1-100
