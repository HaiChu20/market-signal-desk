#!/usr/bin/env bash
#SBATCH --job-name=msd-sequence
#SBATCH --partition=gpumedium
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --array=0-1
#SBATCH --output=logs/sequence-%A_%a.log
set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
mapfile -t symbols < <(printf '%s\n' BTCUSDT ETHUSDT)
symbol="${symbols[$SLURM_ARRAY_TASK_ID]}"
./.venv/bin/python -m msd.research.sequence_train \
  --data-root data --symbol "$symbol" \
  --start "${START:?Set START}" --end "${END:?Set END}" \
  --output "${OUTPUT_ROOT:?Set OUTPUT_ROOT}/$symbol" \
  --epochs "${EPOCHS:-20}" --seed "${SEED:-7}"
