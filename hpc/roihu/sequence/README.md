# Sequence CNN DEV submission v1

This package trains only on development labels ending before 2023-01-01. It
writes purged walk-forward out-of-fold barrier predictions, one GPU job for
each symbol and seed, then grades the fetched predictions on the laptop.
The default submission uses BTCUSDT and USATECHIDXUSD, three seeds each. The
[config](configs/dev_v1.json) includes all five supported symbols; set
`SYMBOLS=BTCUSDT,USATECHIDXUSD,USA500IDXUSD,XAUUSD,ETHUSDT` for all five once
the missing files in `bundle/missing.txt` have been produced. At packaging,
USA500 lacked `derived/bars_4h/USA500IDXUSD/2019-11.parquet`; ETH had 183
missing derived/feature/label files. The default BTC/NQ bundle has four
missing BTC 2017-12 warm-up derived/feature files. Those precede the configured
BTC start and the builder drops anchors without enough history.

## Laptop: ship code and the exact present inputs

Run from the project checkout with the production `data/` directory. Only the
CSC project **number** in the first command needs changing. `ship.sh` makes
`bundle/files.txt` (rsync paths), `bundle/manifest.tsv` (path and byte size),
and `bundle/missing.txt`; it prints the transfer size. It sends code and only
those listed files to project scratch on Roihu-GPU.

```bash
export CSC_PROJECT=2001234
uv sync
bash hpc/roihu/sequence/ship.sh
```

The current default two-symbol inventory is **654 files, 2,807,573,355 bytes
(2.61 GiB)**. The full five-symbol inventory is 2,142 present files,
7,110,463,526 bytes (6.62 GiB), with 309 missing paths. For Allas instead of
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
epoch with a width-eight CNN, and leaves outputs under `data/tmp/sequence-smoke/`.

```bash
uv sync --extra gpu
uv run python -m msd.research.sequence_train --data-root data --symbol BTCUSDT --output data/tmp/sequence-smoke/btc --smoke
uv run python -m msd.research.sequence_train --data-root data --symbol USATECHIDXUSD --output data/tmp/sequence-smoke/nq --smoke
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
