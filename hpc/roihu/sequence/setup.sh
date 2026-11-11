#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
if [[ "$(uname -m)" != aarch64 ]]; then
  echo 'Expected Roihu-GPU aarch64 environment' >&2
  exit 1
fi
# CSC's python-pytorch module provides the CUDA-enabled GH200 build.
module load python-pytorch/2.13
python3 -c 'import sys; assert sys.version_info >= (3, 12), sys.version'
python3 -m venv --system-site-packages .venv-roihu
./.venv-roihu/bin/python -m pip install -e .
./.venv-roihu/bin/python -c 'import torch, msd; print(torch.__version__)'
