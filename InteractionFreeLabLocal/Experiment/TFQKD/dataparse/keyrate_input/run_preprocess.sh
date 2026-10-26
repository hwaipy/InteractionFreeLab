#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${TFQKD_PYTHON:-/home/freespace/miniconda3/bin/python}"
export TFQKD_BATCH_OUTPUT="${TFQKD_BATCH_OUTPUT:-$SCRIPT_DIR/batch_output/20261026}"
export TFQKD_WORKERS="${TFQKD_WORKERS:-16}"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1
mkdir -p "$TFQKD_BATCH_OUTPUT/logs"
exec 9>"$TFQKD_BATCH_OUTPUT/.batch.lock"
if ! flock -n 9; then
    echo "A batch using this output directory is already running." >&2
    exit 1
fi
LOG="$TFQKD_BATCH_OUTPUT/logs/run_$(TZ=Asia/Shanghai date +%Y%m%d_%H%M%S).log"
ln -sfn "$(basename "$LOG")" "$TFQKD_BATCH_OUTPUT/logs/latest.log"
echo "Output: $TFQKD_BATCH_OUTPUT"
echo "Workers: $TFQKD_WORKERS"
echo "Log: $LOG"
"$PYTHON" -u "$SCRIPT_DIR/preprocess_batch.py" 2>&1 | tee -a "$LOG"
