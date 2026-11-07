#!/usr/bin/env bash
# Stop pipeline, worker and server (inside WSL). Re-run start_all.sh to resume.
pkill -f '[p]ipeline.py'; pkill -f '[s]cripts.mock_platform (serve|worker|crawl-worker)'; echo stopped
