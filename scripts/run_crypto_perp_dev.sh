#!/bin/bash
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
work=data/venues/binance_perp
mkdir -p "$work/logs"
run_one() {
  name="$1"; shift
  /usr/bin/time -l -o "$work/logs/$name.time" nice -n 10 uv run "$@" >"$work/logs/$name.log" 2>&1 || {
    echo "$name" > "$work/FAILED"; return 1;
  }
}
run_one BTCUSDT python -m msd.processing.crypto_perp --symbol BTCUSDT || exit 1
run_one ETHUSDT python -m msd.processing.crypto_perp --symbol ETHUSDT || exit 1
run_one sanity python -m msd.research.crypto_perp_sanity || exit 1
run_one bundle python hpc/roihu/sequence/make_bundle.py --data-root data \
  --config hpc/roihu/sequence/configs/dev_v4.json \
  --output hpc/roihu/sequence/bundle_dev_v4 || exit 1
awk -F '\t' 'NR==1 || $1 ~ /^bars\/binance_um\/(BTCUSDT|ETHUSDT)\// || $1 ~ /^venues\/binance_perp\//' \
  hpc/roihu/sequence/bundle_dev_v4/manifest.tsv > hpc/roihu/sequence/bundle_dev_v4/delta_manifest.tsv
awk -F '\t' 'NR>1 {print $1}' hpc/roihu/sequence/bundle_dev_v4/delta_manifest.tsv \
  > hpc/roihu/sequence/bundle_dev_v4/delta_files.txt
date -u +%FT%TZ > "$work/DONE"
