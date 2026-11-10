#!/usr/bin/env bash
#SBATCH --job-name=msd-train
#SBATCH --partition=gpumedium
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --array=0-2
#SBATCH --output=logs/train-%A_%a.log
set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
mapfile -t methods < <(printf '%s\n' sr_touch rsi2_mean_reversion liquidity_sweep)
# Training CLI is intentionally supplied by the training project when it exists.
: "${TRAIN_COMMAND:?Set TRAIN_COMMAND to the reviewed GPU trainer executable}"
"${TRAIN_COMMAND}" --method "${methods[$SLURM_ARRAY_TASK_ID]}" \
  --features data/features --events data/events --labels data/labels
