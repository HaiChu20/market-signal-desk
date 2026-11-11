"""SHA256 export inventory and post-transfer verification for the data lake."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import os
from pathlib import Path
import time

import pyarrow.parquet as pq

ROOT = Path("/Users/bfhach/Projects/market-signal-desk")
CATEGORIES = ("raw", "bars", "aux", "features", "labels", "levels", "events")
FIELDS = ("path", "bytes", "sha256", "category", "ts_min", "ts_max")
CHUNK = 8 * 1024**2


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def sidecar_digest(path: Path) -> str | None:
    sidecar = Path(str(path) + ".sha256")
    if not sidecar.exists():
        return None
    tokens = sidecar.read_text().split()
    if not tokens:
        return None
    value = tokens[0].lower()
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        return None
    return value


def ts_coverage(path: Path) -> tuple[str, str]:
    if path.suffix != ".parquet":
        return "", ""
    try:
        metadata = pq.read_metadata(path)
        names = metadata.schema.names
        if "ts" not in names:
            return "", ""
        index = names.index("ts")
        lows, highs = [], []
        for group_index in range(metadata.num_row_groups):
            stats = metadata.row_group(group_index).column(index).statistics
            if stats is None or not stats.has_min_max:
                return "", ""
            lows.append(stats.min)
            highs.append(stats.max)
        if not lows:
            return "", ""
        return str(min(lows)), str(max(highs))
    except (OSError, ValueError, IndexError):
        return "", ""


def scan(root: Path = ROOT, categories: tuple[str, ...] = CATEGORIES):
    for category in categories:
        directory = root / "data" / category
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.is_symlink() or path.name.startswith(".") or path.suffix == ".pem":
                continue
            minimum, maximum = ts_coverage(path)
            yield {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
                   "sha256": sidecar_digest(path) or digest_file(path), "category": category,
                   "ts_min": minimum, "ts_max": maximum}


def export(root: Path = ROOT, categories: tuple[str, ...] = CATEGORIES,
           dry_run: bool = False, output: Path | None = None) -> dict:
    started = time.monotonic()
    output = output or root / "data/manifest" / f"export_{datetime.now(timezone.utc):%Y%m%d}.csv"
    if output.exists() and not dry_run:
        raise FileExistsError(f"manifest already exists: {output}")
    count = bytes_total = 0
    if dry_run:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=FIELDS)
        writer.writeheader()
        manifest_bytes = len(buffer.getvalue().encode())
        for row in scan(root, categories):
            count += 1
            bytes_total += row["bytes"]
            buffer.seek(0); buffer.truncate(0)
            writer.writerow(row)
            manifest_bytes += len(buffer.getvalue().encode())
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        # The temporary file lives in this worktree; replacement into the data
        # lake is atomic on the shared local filesystem.
        scratch = Path("data/tmp/export_manifest")
        scratch.mkdir(parents=True, exist_ok=True)
        temp = scratch / f"{output.name}.part.{os.getpid()}"
        try:
            with temp.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                writer.writeheader()
                for row in scan(root, categories):
                    writer.writerow(row)
                    count += 1
                    bytes_total += row["bytes"]
            os.replace(temp, output)
        finally:
            temp.unlink(missing_ok=True)
        manifest_bytes = output.stat().st_size
    return {"files": count, "bytes": bytes_total, "seconds": time.monotonic() - started,
            "manifest_bytes": manifest_bytes, "manifest": str(output), "dry_run": dry_run}


def verify(root: Path, manifest: Path) -> dict:
    started = time.monotonic()
    checked = 0
    problems = []
    with manifest.open(newline="") as handle:
        for row in csv.DictReader(handle):
            relative = Path(row["path"])
            if relative.is_absolute() or ".." in relative.parts:
                problems.append(f"unsafe path: {row['path']}")
                continue
            path = root / relative
            if not path.is_file() or path.is_symlink():
                problems.append(f"missing: {row['path']}")
                continue
            if path.stat().st_size != int(row["bytes"]):
                problems.append(f"size mismatch: {row['path']}")
                continue
            # Verify actual bytes, never only a copied sidecar.
            if digest_file(path) != row["sha256"]:
                problems.append(f"SHA256 mismatch: {row['path']}")
                continue
            checked += 1
    return {"checked": checked, "problems": problems, "seconds": time.monotonic() - started}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--only", choices=CATEGORIES, action="append", help="Restrict to one or more categories")
    parser.add_argument("--dry-run", action="store_true", help="Hash and count without writing a manifest")
    parser.add_argument("--verify", action="store_true", help="Rehash files listed in an existing manifest")
    parser.add_argument("--manifest", type=Path, help="Manifest path for --verify or custom export output")
    args = parser.parse_args()
    if args.verify:
        if args.manifest is None:
            raise SystemExit("--verify requires --manifest")
        result = verify(args.root, args.manifest)
        print(result, flush=True)
        if result["problems"]:
            raise SystemExit(1)
    else:
        print(export(args.root, tuple(args.only) if args.only else CATEGORIES,
                     args.dry_run, args.manifest), flush=True)


if __name__ == "__main__":
    main()
