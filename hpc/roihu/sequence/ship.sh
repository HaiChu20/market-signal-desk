#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
: "${CSC_PROJECT:?Set CSC_PROJECT to your CSC project number}"
SYMBOLS=${SYMBOLS:-BTCUSDT,USATECHIDXUSD,USA500IDXUSD,XAUUSD,ETHUSDT}
DATA_ROOT=${DATA_ROOT:-data}
remote="roihu-gpu.csc.fi:/scratch/project_${CSC_PROJECT}/${USER}/market-signal-desk"
./.venv/bin/python hpc/roihu/sequence/make_bundle.py \
  --data-root "$DATA_ROOT" --symbols "$SYMBOLS"
ssh roihu-gpu.csc.fi "mkdir -p /scratch/project_${CSC_PROJECT}/${USER}/market-signal-desk/data"
rsync -az --exclude=.git --exclude=.venv --exclude=.cao --exclude=data \
  ./ "$remote/"
rsync -az --files-from=hpc/roihu/sequence/bundle/files.txt \
  "$DATA_ROOT/" "$remote/data/"
