#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
: "${CSC_PROJECT:?Set CSC_PROJECT to your CSC project number}"
mkdir -p reports/sequence
rsync -az "roihu-gpu.csc.fi:/scratch/project_${CSC_PROJECT}/${USER}/market-signal-desk/reports/sequence/" \
  reports/sequence/
