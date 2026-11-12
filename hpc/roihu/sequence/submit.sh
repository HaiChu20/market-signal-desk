#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
: "${CSC_PROJECT:?Set CSC_PROJECT to your CSC project number}"
SYMBOLS=${SYMBOLS:-BTCUSDT,USATECHIDXUSD,USA500IDXUSD,XAUUSD,ETHUSDT}
SEEDS=${SEEDS:-7,17,27}
CONFIG_PATH=${CONFIG_PATH:-hpc/roihu/sequence/configs/dev_v3.json}
IFS=, read -r -a symbols <<< "$SYMBOLS"
IFS=, read -r -a seeds <<< "$SEEDS"
count=$((${#symbols[@]} * ${#seeds[@]}))
mkdir -p logs reports/sequence
# Slurm splits --export values on commas, so pass the lists through the environment.
export SYMBOLS SEEDS CONFIG_PATH
sbatch --account="project_${CSC_PROJECT}" --array="0-$((count-1))" \
  --export=ALL hpc/roihu/sequence/train.sbatch
