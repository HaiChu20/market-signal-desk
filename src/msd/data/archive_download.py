"""Small, bounded, verified streaming downloads for public data archives."""
from __future__ import annotations

import hashlib
import os
import random
import shutil
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

MIN_FREE_BYTES = 15 * 1024**3
CHUNK = 8 * 1024**2
HEADERS = {"User-Agent": "MarketSignalDesk/0.1"}


def remote_size(url: str) -> int | None:
    try:
        with urlopen(Request(url, headers=HEADERS, method="HEAD"), timeout=60) as response:
            value = response.headers.get("Content-Length")
            return int(value) if value else None
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


def stream_archive(url: str, target: Path, expected: int | None = None,
                   expected_sha: str | None = None, retries: int = 5,
                   disk_path: Path | None = None) -> str | None:
    """Return SHA256, None on 404; a sidecar certifies a complete local file."""
    sidecar = Path(str(target) + ".sha256")
    if target.exists() and sidecar.exists():
        digest = sidecar.read_text().split()[0].lower()
        if len(digest) == 64 and (expected is None or target.stat().st_size == expected) and (expected_sha is None or digest == expected_sha):
            return digest
    target.parent.mkdir(parents=True, exist_ok=True)
    disk_path = disk_path or target.parent
    last: Exception | None = None
    scratch = Path("data/tmp/free_downloaders")
    scratch.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        tmp = scratch / f"{target.name}.part.{os.getpid()}"
        try:
            size_hint = expected or 0
            if shutil.disk_usage(disk_path).free - size_hint < MIN_FREE_BYTES:
                raise OSError("free disk would drop below 15 GiB")
            digest = hashlib.sha256()
            size = 0
            with urlopen(Request(url, headers=HEADERS), timeout=120) as response, tmp.open("wb") as out:
                length = response.headers.get("Content-Length")
                response_size = int(length) if length else None
                if expected is not None and response_size is not None and expected != response_size:
                    raise ValueError(f"HEAD size {expected} != Content-Length {response_size}")
                while chunk := response.read(CHUNK):
                    size += len(chunk)
                    if size % (256 * 1024**2) < CHUNK and shutil.disk_usage(disk_path).free < MIN_FREE_BYTES:
                        raise OSError("free disk below 15 GiB")
                    out.write(chunk)
                    digest.update(chunk)
            if expected is not None and size != expected or response_size is not None and size != response_size:
                raise ValueError(f"downloaded size {size} differs from expected size")
            actual = digest.hexdigest()
            if expected_sha is not None and actual != expected_sha:
                raise ValueError("SHA256 mismatch")
            os.replace(tmp, target)
            side_tmp = scratch / f"{target.name}.sha256.part.{os.getpid()}"
            side_tmp.write_text(f"{actual}  {target.name}\n")
            os.replace(side_tmp, sidecar)
            return actual
        except HTTPError as error:
            if error.code == 404:
                return None
            last = error
        except OSError as error:
            if "15 GiB" in str(error):
                raise
            last = error
        except (ValueError, TimeoutError) as error:
            last = error
        finally:
            tmp.unlink(missing_ok=True)
        if attempt + 1 < retries:
            time.sleep(min(60, 2**attempt) + random.random())
    raise RuntimeError(f"{target.name}: {type(last).__name__}: {last}")
