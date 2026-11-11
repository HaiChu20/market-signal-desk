# Data transfer: local lake → Allas and Roihu

Run these commands from the project root after the relevant downloaders finish. Replace `CSC_USER`, `project_XXXXXX`, and `BUCKET` with your assigned values. Those account and bucket values have **not been verified** for this project.

## 1. Inventory the files

```bash
uv run python -m msd.data.export_manifest --dry-run
uv run python -m msd.data.export_manifest
```

The second command creates `data/manifest/export_YYYYMMDD.csv`. It records relative path, byte size, SHA256, category, and cheap Parquet `ts` bounds. Keep a copy outside the transfer destination. To create separate verification inventories for the two destinations, use `--only raw --manifest data/manifest/raw_YYYYMMDD.csv` and repeat `--only` for the derived categories with a different output name. The exporter will not overwrite an existing manifest.

## 2. Upload raw archives from the workstation to Allas

CSC documents [local `allas-conf` setup and the `s3allas:` rclone remote](https://docs.csc.fi/data/Allas/using_allas/rclone_local/). Install `rclone` and CSC's local `allas_conf` helper as described there, then configure the S3 connection interactively:

```bash
source allas_conf -u CSC_USER -p project_XXXXXX -m S3
rclone lsd s3allas:
rclone mkdir s3allas:BUCKET
rclone copy data/raw s3allas:BUCKET/market-signal-desk/data/raw --progress --transfers 4
rclone copyto data/manifest/raw_YYYYMMDD.csv s3allas:BUCKET/market-signal-desk/data/manifest/raw_YYYYMMDD.csv
rclone check data/raw s3allas:BUCKET/market-signal-desk/data/raw --size-only
```

Use the bucket assigned to your CSC project; its name is **unverified** here. `rclone check --size-only` is a transfer check, not a SHA256 proof. For a full post-transfer verification, restore the raw tree to a separate local or Roihu directory and run `uv run python -m msd.data.export_manifest --verify --root RESTORE_ROOT --manifest raw_YYYYMMDD.csv`. The tool rehashes actual files and does not trust copied sidecars.

CSC also provides `module load allas`, `allas-conf`, `a-put`, and `a-list` on Roihu, but [its `a-put` documentation](https://docs.csc.fi/data/Allas/using_allas/a_commands/) says a directory is packed into one tar object. Use `rclone copy` above for the many raw archives so individual files remain addressable. The [Roihu rclone guide](https://docs.csc.fi/data/Allas/using_allas/rclone/) describes the S3 remote created by `allas-conf`.

## 3. Sync derived data to Roihu scratch

CSC documents `/scratch/<project>` as the shared project scratch path and notes that [default scratch quota is 250 GiB](https://docs.csc.fi/computing/disk/); confirm your actual quota before transfer. CSC's [rsync guide](https://docs.csc.fi/data/moving/rsync/) uses `roihu-cpu.csc.fi` and `-P` to retain partial transfers. Roihu access requires the user's CSC SSH setup; this account's access has **not been verified**.

```bash
ssh CSC_USER@roihu-cpu.csc.fi 'mkdir -p /scratch/project_XXXXXX/market-signal-desk'
rsync -aP --dry-run --relative data/bars/ data/aux/ data/derived/ data/features/ data/labels/ data/levels/ data/events/ CSC_USER@roihu-cpu.csc.fi:/scratch/project_XXXXXX/market-signal-desk/
rsync -aP --relative data/bars/ data/aux/ data/derived/ data/features/ data/labels/ data/levels/ data/events/ CSC_USER@roihu-cpu.csc.fi:/scratch/project_XXXXXX/market-signal-desk/
rsync -aP --relative data/manifest/ CSC_USER@roihu-cpu.csc.fi:/scratch/project_XXXXXX/market-signal-desk/
```

On Roihu, from a checkout containing this script and with its Python environment installed, verify the derived-only manifest against `/scratch/project_XXXXXX/market-signal-desk`. A full manifest that includes raw files will not verify against a scratch tree containing only derived data.

```bash
uv run python -m msd.data.export_manifest --verify --root /scratch/project_XXXXXX/market-signal-desk --manifest /scratch/project_XXXXXX/market-signal-desk/data/manifest/derived_YYYYMMDD.csv
```

For later compute jobs, CSC lists the [Roihu CPU and GPU partitions](https://docs.csc.fi/computing/running/batch-job-partitions/). `gpumedium` has a 36-hour limit; `gpularge` requires a scalability test. Verify the project's partition access and current limits before submitting the templates in this directory.
