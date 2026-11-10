#!/usr/bin/env bash
#SBATCH --job-name=msd-features
#SBATCH --partition=gpumedium
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --array=0-4
#SBATCH --output=logs/features-%A_%a.log
set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
mapfile -t symbols < <(printf '%s\n' USATECHIDXUSD USA500IDXUSD XAUUSD BTCUSDT ETHUSDT)
./.venv/bin/python -m msd.processing.pipeline --symbol "${symbols[$SLURM_ARRAY_TASK_ID]}" \
  --start-year "${START_YEAR:?Set START_YEAR}" --end-year "${END_YEAR:?Set END_YEAR}"
