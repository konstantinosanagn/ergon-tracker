"""Download + verify + freshness-gate the published index snapshot.

Works two ways:
* **Anonymous** (public repo): fetch assets from the stable release download URL.
* **Token-auth** (private repo or rate-limit relief): if a GitHub token is present in the env
  (``ERGON_GH_TOKEN`` / ``GITHUB_TOKEN`` / ``GH_TOKEN``) and we're talking to github.com, resolve
  assets via the GitHub API and download them authenticated. This lets a private repo still serve
  the index to token-holders; a public repo needs no token (the intended zero-friction path).

Any failure returns the cached copy if present, else ``None`` (caller live-falls-back).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .db import SCHEMA_VERSION

log = logging.getLogger("ergon_tracker.index")
_REPO = "konstantinosanagn/ergon-tracker"
_TAG = "index-latest"
_DEFAULT_BASE = f"https://github.com/{_REPO}/releases/download/{_TAG}"


def _default_cache_dir() -> Path:
    return Path.home() / ".cache" / "ergon-tracker"


def _token() -> str | None:
    return (
        os.environ.get("ERGON_GH_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
    )


def _get(url: str, *, token: str | None = None, accept: str | None = None) -> bytes:
    req = urllib.request.Request(url)  # noqa: S310 - https/file only
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if accept:
        req.add_header("Accept", accept)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


class IndexCache:
    def __init__(
        self,
        base_url: str | None = None,
        cache_dir: Path | None = None,
        repo: str = _REPO,
        tag: str = _TAG,
    ) -> None:
        self.base_url = (base_url or _DEFAULT_BASE).rstrip("/")
        self.cache_dir = Path(cache_dir or _default_cache_dir())
        self.repo = repo
        self.tag = tag
        self.db_path = self.cache_dir / "index.sqlite"
        self.local_manifest = self.cache_dir / "manifest.json"

    def _make_fetch(self) -> Callable[[str], bytes]:
        """Return ``fetch(asset_name) -> bytes`` using token-auth API if available, else anonymous."""
        token = _token()
        if token and self.base_url.startswith("https://github.com"):
            api = f"https://api.github.com/repos/{self.repo}/releases/tags/{self.tag}"
            rel = json.loads(_get(api, token=token, accept="application/vnd.github+json"))
            assets = {a["name"]: a["url"] for a in rel.get("assets", [])}
            return lambda name: _get(assets[name], token=token, accept="application/octet-stream")
        return lambda name: _get(f"{self.base_url}/{name}")

    def ensure_fresh(self) -> Path | None:
        """Return a verified, schema-compatible index path, or None (caller live-falls-back)."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            fetch = self._make_fetch()
            remote = json.loads(fetch("manifest.json"))
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
            raw = gzip.decompress(fetch("index.sqlite.gz"))
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
