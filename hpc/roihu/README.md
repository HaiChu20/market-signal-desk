# Roihu job templates

These are scripts only. They do not connect to CSC or transfer data. Roihu GH200 nodes are aarch64/RHEL 9. Confirm CSC's current module names, partition limits, and GPU resource syntax before submission. Run from a synced project checkout; create `logs/` first. `setup.sh` expects an available aarch64 `uv` and Rust toolchain, installs frozen production dependencies, and builds the PyO3 extension locally.

`rsync-files.txt` lists derived inputs and outputs to transfer: bars, derived bars, features, labels, levels, and events. It intentionally excludes `data/raw`. For rsync, filter comments and pass the remaining entries with `--files-from`. Keep the destination data paths identical to the local project. These paths may not all exist before the pipeline runs.

`features.sbatch` fans out by symbol and needs `START_YEAR` and `END_YEAR`. Its pipeline call performs feature, level, event and label work, so it also needs source bars under `data/bars`. `train.sbatch` fans out by the three currently implemented pilot methods. There is no reviewed GPU training CLI or model yet; set `TRAIN_COMMAND` when one is available. Do not treat the template as a trained-model result. Both templates request `gpumedium`; switch to `gpularge` if a reviewed run needs it.
