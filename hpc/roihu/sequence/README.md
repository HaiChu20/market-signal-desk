# Sequence CNN on Roihu

Scripts only; these commands are for a synced Roihu checkout with existing
`data/bars/binance_spot`, `data/derived/bars_{15m,1h,4h}`, `data/features`,
and `data/labels` inputs. The loader currently uses Binance spot 1m bars, so
submit BTCUSDT/ETHUSDT tasks only until a 1m source loader is added for indices.
The template requests one GH200 GPU per array task on `gpumedium` (aarch64,
RHEL 9). Confirm current CSC module names and Slurm GPU syntax before use.

```bash
cd /path/to/market-signal-desk
bash hpc/roihu/sequence/setup.sh
mkdir -p logs reports/sequence
START=2021-01-01 END=2022-01-01 OUTPUT_ROOT=reports/sequence \
  sbatch --array=0-1 hpc/roihu/sequence/train.sbatch
```

`END` is exclusive and must be at most `2023-01-01`. Each output directory
contains fold checkpoints, early-stop loss, calibration thresholds and a DEV
report card. No Test or Final data is read by the CLI.
