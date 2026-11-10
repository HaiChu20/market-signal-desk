"""Small public-archive downloader with HEAD planning and disk guard."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import shutil
from urllib.request import Request, urlopen

MIN_FREE_BYTES = 65 * 1024**3


def head_size(url: str) -> int:
    with urlopen(Request(url, method='HEAD'), timeout=30) as response:
        length = response.headers.get('Content-Length')
        if not length:
            raise OSError(f'archive has no Content-Length: {url}')
        return int(length)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url: str, target: Path, size: int, *, checksum_url: str | None = None) -> Path:
    """Resume a partial download; verify published SHA-256 when available."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(target.parent).free < MIN_FREE_BYTES + size:
        raise OSError('less than 65 GiB would remain after download')
    expected = None
    if checksum_url:
        with urlopen(checksum_url, timeout=30) as response:
            expected = response.read().decode().split()[0].lower()
    part = target.with_name(target.name + '.part')
    if not target.exists() or target.stat().st_size != size:
        offset = part.stat().st_size if part.exists() else 0
        request = Request(url, headers={'Range': f'bytes={offset}-'} if offset else {})
        with urlopen(request, timeout=90) as response:
            mode = 'ab' if offset and response.status == 206 else 'wb'
            with part.open(mode) as output:
                while chunk := response.read(1024 * 1024):
                    if shutil.disk_usage(target.parent).free < MIN_FREE_BYTES:
                        raise OSError('65 GiB free-space stop during download')
                    output.write(chunk)
        if part.stat().st_size != size:
            raise IOError(f'incomplete archive: {target}')
        part.replace(target)
    actual = _sha256(target)
    if expected and actual != expected:
        raise IOError(f'published checksum mismatch: {target}')
    sidecar = target.with_name(target.name + '.sha256')
    sidecar.write_text(f'{actual}  {target.name}\n')
    return target


def fetch_plan(items: list[tuple[str, Path, str | None]]) -> list[Path]:
    """HEAD every item before downloading, using at most two workers."""
    sizes = [head_size(url) for url, _, _ in items]
    print({'archives': len(items), 'compressed_bytes': sum(sizes),
           'items': [(str(path), size) for (_, path, _), size in zip(items, sizes)]}, flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(fetch, url, path, size, checksum_url=checksum)
                   for (url, path, checksum), size in zip(items, sizes)]
        return [future.result() for future in futures]
