#!/usr/bin/env bash
#SBATCH --job-name=msd-sequence
#SBATCH --partition=gpumedium
#SBATCH --gres=gpu:gh200:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --requeue
#SBATCH --signal=USR1@180
#SBATCH --output=logs/sequence-%A_%a.log
set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
module load python-pytorch/2.13
./.venv-roihu/bin/python -c 'import torch; assert torch.cuda.is_available(), "CUDA torch unavailable in project venv"'
IFS=, read -r -a symbols <<< "${SYMBOLS:?Set comma-separated SYMBOLS}"
IFS=, read -r -a seeds <<< "${SEEDS:?Set comma-separated SEEDS}"
seed_count=${#seeds[@]}
index=${SLURM_ARRAY_TASK_ID}
symbol=${symbols[$((index / seed_count))]}
seed=${seeds[$((index % seed_count))]}
config=${CONFIG_PATH:-hpc/roihu/sequence/configs/dev_v3.json}
config_sha=$(sha256sum "$config" | cut -d' ' -f1)
output="reports/sequence/${config_sha}/${symbol}/seed_${seed}"
mkdir -p "$output"
set +e
srun ./.venv-roihu/bin/python -m msd.research.sequence_train \
  --data-root data --config "$config" \
  --symbol "$symbol" --seed "$seed" --output "$output"
result=$?
set -e
if [[ "$result" -eq 99 ]]; then
  scontrol requeue "$SLURM_JOB_ID"
  exit 0
fi
exit "$result"
