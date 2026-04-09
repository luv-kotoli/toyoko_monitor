#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
CONDA_PROFILE="/home/yuxx/miniforge3/etc/profile.d/conda.sh"
CONDA_ENV_NAME="web"
mkdir -p "$LOG_DIR"

if [[ ! -f "$CONDA_PROFILE" ]]; then
  echo "Conda init script not found: $CONDA_PROFILE" >&2
  echo "Update scripts/run_service.sh to match your local Miniforge/Conda installation path." >&2
  exit 1
fi

source "$CONDA_PROFILE"

if ! conda env list | awk 'NF && $1 !~ /^#/ {print $1}' | grep -qx "$CONDA_ENV_NAME"; then
  echo "Conda environment '$CONDA_ENV_NAME' was not found." >&2
  echo "Create it first with: conda create -n $CONDA_ENV_NAME python=3.12 -y" >&2
  exit 1
fi

conda activate "$CONDA_ENV_NAME"

cd "$ROOT_DIR"

exec python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >>"$LOG_DIR/uvicorn.stdout.log" 2>>"$LOG_DIR/uvicorn.stderr.log"
