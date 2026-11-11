# Sequence CNN DEV submission v2

This package trains only on development labels ending before 2023-01-01. It
writes purged walk-forward out-of-fold barrier predictions, one GPU job for
each symbol and seed, then grades the fetched predictions on the laptop.
The default submission uses all five symbols in the
[v2 config](configs/dev_v2.json), with three seeds each. BTC and ETH add
causal flow features from 2020 onward. The immutable [v1 config](configs/dev_v1.json)
remains runnable by setting `CONFIG_PATH=hpc/roihu/sequence/configs/dev_v1.json`
for both `ship.sh` and `submit.sh`; its hash and inputs are unchanged.

## Laptop: ship code and the exact present inputs

Run from the project checkout with the production `data/` directory. Only the
CSC project **number** in the first command needs changing. `ship.sh` makes
`bundle/files.txt` (rsync paths), `bundle/manifest.tsv` (path and byte size),
`bundle/missing.txt`, `bundle/coverage.json`, and `bundle/stale.txt`; it prints
the transfer size. It sends code and only
those listed files to project scratch on Roihu-GPU.

```bash
export CSC_PROJECT=2001234
uv sync
bash hpc/roihu/sequence/ship.sh
```

The v2 five-symbol inventory is **2,237 files, 8,531,143,626 bytes (7.95 GiB)**,
with no missing files. `ship.sh` refuses any missing DEV
input, absent production4 completion marker, stale production4 output, or DEV
year with less than 80% anchor coverage. It checks the per-symbol chain-done
marker and each `data/tmp/stage9p4_{SYM}_{YEAR}.json` result. Since that result
is written *after* the year's bars and labels, the freshness lower bound is
its mtime minus the recorded `runtime_seconds` and a 60-second clock margin.
Raw source bars are historical inputs and are exempt from this derived-output
freshness check.

Per-year anchor coverage (eligible resolved label anchors retained by the
time, ATR and window-history gates):

| Symbol | DEV years | Coverage by year |
|---|---|---|
| BTCUSDT | 2020–2022 | 100%, 100%, 100% |
| ETHUSDT | 2020–2022 | 100%, 100%, 100% |
| USATECHIDXUSD | 2019–2022 | 99.9%, 100%, 100%, 100% |
| USA500IDXUSD | 2019–2022 | 99.9%, 100%, 100%, 100% |
| XAUUSD | 2008–2022 | 96.2% in 2008, 100% in every year 2009–2022 |

For BTC and ETH, the bundle also gates every selected flow column at least
80% non-NaN coverage over 2020–2022. The selected dense inputs include their
spot and UM coverage flags; BTC also includes its Bybit coverage flag. A
missingness channel is added before dense zero imputation, so unavailable data
does not become indistinguishable from a covered minute with zero activity.
Depth and tick features are excluded because they have no DEV history. The
bundle reads no 2023+ flow files and therefore does not depend on the ongoing
2024+ Bybit flow rebuild.

For Allas instead of
rsync, upload the same `bundle/files.txt` paths under the same `data/` relative
paths; see [CSC object storage](https://docs.csc.fi/data/Allas/).

## Roihu-GPU: setup and submit

```bash
ssh roihu-gpu.csc.fi "cd /scratch/project_${CSC_PROJECT}/${USER}/market-signal-desk && bash hpc/roihu/sequence/setup.sh && CSC_PROJECT=${CSC_PROJECT} bash hpc/roihu/sequence/submit.sh"
```

`setup.sh` loads CSC's CUDA-enabled `python-pytorch/2.13`, makes a system-site
virtual environment and installs this package. Each array task requests one
GH200 GPU on `gpumedium`, 16 CPUs, 64 GiB, and 24 hours. The job checks that
CUDA is available before loading data. Slurm sends `USR1` three minutes before
timeout; the trainer checkpoints and the script requeues. The default checkpoint
interval is 100 optimizer steps. A requeued task resumes the exact fold, epoch,
and batch order. Change `SYMBOLS` and `SEEDS` as comma-separated environment
variables before `submit.sh`; every seed must appear in the JSON config.

## Monitor, fetch, grade

```bash
ssh roihu-gpu.csc.fi "squeue -u ${USER}; sacct -u ${USER} --format=JobID,State,Elapsed,ExitCode | tail"
bash hpc/roihu/sequence/fetch.sh
uv run python -m msd.research.grade_sequence --input reports/sequence --data-root data
```

Fetch after the array is complete. The grade CLI writes `grade/summary.json`
and a DEV report card for each symbol/seed/config hash. It applies
`decision.choose`, then the one-position gate (`label_end_ts + 1 minute`),
then the existing random-direction benchmark. Treat smoke or DEV numbers as
research diagnostics; the protocol grades only the later held-out Test period.
The output includes per-fold `oof.parquet`, `model.pt`, `resume.pt`,
`metrics.json`, and `config_sha256.txt`.

## Local CPU smoke

The following reads two 2021 months, selects two anchors per day, trains one
epoch with a width-eight CNN and the v2 BTC flow inputs, and leaves outputs
under `data/tmp/sequence-smoke/`.

```bash
uv sync --extra gpu
uv run python -m msd.research.sequence_train --data-root data --config hpc/roihu/sequence/configs/dev_v2.json --symbol BTCUSDT --output data/tmp/sequence-smoke/btc --smoke
uv run python -m msd.research.grade_sequence --input data/tmp/sequence-smoke --data-root data
```

## CSC settings and verification status

[CSC's Roihu job script guide](https://docs.csc.fi/computing/running/creating-job-scripts-roihu/)
confirms `gpumedium` and `--gres=gpu:gh200:1`. [CSC's PyTorch page](https://docs.csc.fi/apps/pytorch/)
confirms `python-pytorch/2.13` on Roihu-GPU and its CUDA support.
[Partition limits](https://docs.csc.fi/computing/running/batch-job-partitions/)
allow 36 hours and 212 GiB per reserved GPU on `gpumedium`.
**Unverified on Roihu:** the exact Python minor version and whether its module
wrapper supports the `venv --system-site-packages` path in `setup.sh`, the
project scratch quota, and the requeue signal delivery. The script checks Python
>=3.12 and CUDA before training. No Roihu connection or job was made here.
