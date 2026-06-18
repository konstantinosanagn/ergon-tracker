"""Download + verify + freshness-gate the published index snapshot."""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import urllib.request
from pathlib import Path

from .db import SCHEMA_VERSION

log = logging.getLogger("ergon_tracker.index")
_DEFAULT_BASE = "https://github.com/konstantinosanagn/ergon-tracker/releases/latest/download"


def _default_cache_dir() -> Path:
    return Path.home() / ".cache" / "ergon-tracker"


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310 - https/file only
        return r.read()


class IndexCache:
    def __init__(self, base_url: str | None = None, cache_dir: Path | None = None) -> None:
        self.base_url = (base_url or _DEFAULT_BASE).rstrip("/")
        self.cache_dir = Path(cache_dir or _default_cache_dir())
        self.db_path = self.cache_dir / "index.sqlite"
        self.local_manifest = self.cache_dir / "manifest.json"

    def ensure_fresh(self) -> Path | None:
        """Return a verified, schema-compatible index path, or None (caller live-falls-back)."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            remote = json.loads(_fetch(f"{self.base_url}/manifest.json"))
        except Exception as exc:  # noqa: BLE001
            log.warning("index manifest fetch failed (%s); using cache if present", exc)
            return self.db_path if self.db_path.exists() else None
        if int(remote.get("schema_version", -1)) != SCHEMA_VERSION:
            log.warning("index schema_version mismatch; live fallback")
            return None
        local = json.loads(self.local_manifest.read_text()) if self.local_manifest.exists() else {}
        if local.get("build_id") == remote.get("build_id") and self.db_path.exists():
            return self.db_path  # already current
        try:
            raw = gzip.decompress(_fetch(f"{self.base_url}/index.sqlite.gz"))
        except Exception as exc:  # noqa: BLE001
            log.warning("index download failed (%s)", exc)
            return self.db_path if self.db_path.exists() else None
        if hashlib.sha256(raw).hexdigest() != remote.get("sha256"):
            log.warning("index sha256 mismatch; rejecting download")
            return None
        tmp = self.db_path.with_suffix(".tmp")
        tmp.write_bytes(raw)
        tmp.replace(self.db_path)  # atomic
        self.local_manifest.write_text(json.dumps(remote))
        log.info("index updated to build %s (%d bytes)", remote.get("build_id"), len(raw))
        return self.db_path
