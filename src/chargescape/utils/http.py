"""Small, polite HTTP helpers with on-disk caching (no external deps beyond requests)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import requests

UA = "chargescape-london/0.1 (research; github portfolio project)"


def download(
    url: str, dest: Path, *, timeout: int = 120, retries: int = 3, headers: dict | None = None
) -> Path:
    """Download url to dest if dest does not exist. Returns dest."""
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    h = {"User-Agent": UA, **(headers or {})}
    last = None
    for attempt in range(retries):
        try:
            with requests.get(url, headers=h, timeout=timeout, stream=True) as r:
                r.raise_for_status()
                tmp = dest.with_suffix(dest.suffix + ".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
                tmp.rename(dest)
            return dest
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"failed to download {url}: {last}")


def get_json(
    url: str, params: dict | None = None, *, cache_dir: Path | None = None, timeout: int = 120
) -> Any:
    """GET JSON with optional file cache keyed by url+params."""
    key = hashlib.sha1((url + json.dumps(params or {}, sort_keys=True)).encode()).hexdigest()[:16]
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cp = cache_dir / f"{key}.json"
        if cp.exists():
            return json.loads(cp.read_text())
    r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if cache_dir is not None:
        cp.write_text(json.dumps(data))
    return data
