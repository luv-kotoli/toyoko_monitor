#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

source /home/yuxx/miniforge3/etc/profile.d/conda.sh
conda activate web

cd "$ROOT_DIR"

exec python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >>"$LOG_DIR/uvicorn.stdout.log" 2>>"$LOG_DIR/uvicorn.stderr.log"
