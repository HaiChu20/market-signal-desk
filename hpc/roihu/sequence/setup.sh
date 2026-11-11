#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
./hpc/roihu/setup.sh
uv sync --frozen --no-dev --extra gpu
./.venv/bin/python -c 'import torch; print(torch.__version__, torch.cuda.is_available())'
