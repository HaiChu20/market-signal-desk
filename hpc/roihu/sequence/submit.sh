#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
: "${CSC_PROJECT:?Set CSC_PROJECT to your CSC project number}"
SYMBOLS=${SYMBOLS:-BTCUSDT,USATECHIDXUSD,USA500IDXUSD,XAUUSD,ETHUSDT}
SEEDS=${SEEDS:-7,17,27}
IFS=, read -r -a symbols <<< "$SYMBOLS"
IFS=, read -r -a seeds <<< "$SEEDS"
count=$((${#symbols[@]} * ${#seeds[@]}))
mkdir -p logs reports/sequence
sbatch --account="project_${CSC_PROJECT}" --array="0-$((count-1))" \
  --export="ALL,SYMBOLS=${SYMBOLS},SEEDS=${SEEDS}" hpc/roihu/sequence/train.sbatch
