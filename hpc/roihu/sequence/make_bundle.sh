#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
./.venv/bin/python hpc/roihu/sequence/make_bundle.py "$@"
