#!/usr/bin/env bash
set -euo pipefail

# Run on a Roihu login node after syncing the repository. No credentials used.
if [[ "$(uname -m)" != aarch64 ]]; then
  echo 'Expected aarch64 GH200 environment' >&2
  exit 1
fi
module load rust 2>/dev/null || true
if ! command -v uv >/dev/null; then
  echo 'Install uv for aarch64 from the CSC software stack before continuing' >&2
  exit 1
fi
uv sync --frozen --no-dev
uvx --from maturin==1.16.0 maturin develop --release --manifest-path rust/msd_kernels/Cargo.toml
python -c 'import msd._msd_kernels; print("Rust extension ready")'
