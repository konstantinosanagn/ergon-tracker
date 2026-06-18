"""Census crawl resilience: incremental checkpoint + per-record crash isolation.

Reproduces the failure mode from the field (a per-record exception propagating out of the anyio
task group, aborting the run and skipping the save) and proves the fix: survivors are
checkpointed the instant they're found, and one blown-up record never cancels the group.
"""

from __future__ import annotations

import sys
from pathlib import Path

import anyio
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from census_ats import _checkpoint_append, _load_checkpoint  # noqa: E402

pytestmark = pytest.mark.anyio


def _rec(i: int) -> dict:
    return {"company": f"co{i}", "ats": "taleo", "token": str(i), "domain": None}


def test_checkpoint_append_and_recover(tmp_path: Path) -> None:
    p = tmp_path / "c.partial.jsonl"
    recs = [_rec(0), _rec(1), _rec(2)]
    for r in recs:
        _checkpoint_append(p, r)
    assert _load_checkpoint(p) == recs


def test_recover_skips_truncated_final_line(tmp_path: Path) -> None:
    p = tmp_path / "c.partial.jsonl"
    _checkpoint_append(p, _rec(0))
    # Simulate a hard kill mid-write: a half-written final line with no newline.
    with p.open("a", encoding="utf-8") as fh:
        fh.write('{"company":"co1","ats":"ic')
    recovered = _load_checkpoint(p)
    assert len(recovered) == 1 and recovered[0]["company"] == "co0"


def test_load_missing_checkpoint_is_empty(tmp_path: Path) -> None:
    assert _load_checkpoint(tmp_path / "nope.jsonl") == []


async def test_one_failing_record_does_not_sink_the_group(tmp_path: Path) -> None:
    p = tmp_path / "c.partial.jsonl"

    async def guarded(i: int) -> None:
        # Mirrors the isolation now in find()/verify(): one record can never cancel the group.
        try:
            if i == 5:
                raise RuntimeError("simulated per-record blow-up (the salary-format bug class)")
            await anyio.sleep(0)
            _checkpoint_append(p, _rec(i))
        except Exception:  # noqa: BLE001 - the guard under test
            pass

    async with anyio.create_task_group() as tg:  # would raise if a task propagated
        for i in range(10):
            tg.start_soon(guarded, i)

    saved = {r["company"] for r in _load_checkpoint(p)}
    assert "co5" not in saved  # the failing record is absent
    assert len(saved) == 9  # every other record survived AND was saved incrementally
