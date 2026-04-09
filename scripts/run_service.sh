#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
CONDA_ENV_NAME="${TOYOKO_MONITOR_CONDA_ENV:-web}"
CONDA_PROFILE="${TOYOKO_MONITOR_CONDA_SH:-}"
mkdir -p "$LOG_DIR"

if [[ -z "$CONDA_PROFILE" ]]; then
  if [[ -n "${CONDA_EXE:-}" ]]; then
    CONDA_PROFILE="$(cd "$(dirname "${CONDA_EXE}")/.." && pwd)/etc/profile.d/conda.sh"
  elif command -v conda >/dev/null 2>&1; then
    CONDA_PROFILE="$(conda info --base)/etc/profile.d/conda.sh"
  else
    for candidate in \
      "$HOME/miniforge3/etc/profile.d/conda.sh" \
      "$HOME/mambaforge/etc/profile.d/conda.sh" \
      "$HOME/miniconda3/etc/profile.d/conda.sh" \
      "$HOME/anaconda3/etc/profile.d/conda.sh"
    do
      if [[ -f "$candidate" ]]; then
        CONDA_PROFILE="$candidate"
        break
      fi
    done
  fi
fi

if [[ -z "$CONDA_PROFILE" || ! -f "$CONDA_PROFILE" ]]; then
  echo "Conda init script not found: $CONDA_PROFILE" >&2
  echo "Set TOYOKO_MONITOR_CONDA_SH to your conda.sh path if auto-detection fails." >&2
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
