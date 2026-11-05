#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${MOCK_PYTHON:-.venv/bin/python}"
"$PYTHON" -m scripts.mock_platform worker &
worker_pid=$!
"$PYTHON" -m scripts.mock_platform crawl-worker &
crawler_pid=$!
trap 'kill "$worker_pid" "$crawler_pid" 2>/dev/null || true' EXIT INT TERM
"$PYTHON" -m scripts.mock_platform serve "$@"
