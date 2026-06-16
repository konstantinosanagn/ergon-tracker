"""Finalize the 500-row gold run: combine reused vote#1 (data/judge3/vote1.jsonl) with the two
new votes (data/judge3/out_*.jsonl) into a 3-vote consensus, evaluate, and persist artifacts to
runs/<date>-gold-500/.

    .venv/bin/python scripts/finalize_run500.py --run-id wf_9fbe86f0-ce9
"""

from __future__ import annotations

import json
import subprocess
import sys
import tarfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from eval_extraction import evaluate  # noqa: E402

J3 = ROOT / "data" / "judge3"
GOLD = ROOT / "tests" / "data" / "gold.jsonl"
RUNS = ROOT / "runs"
FIELDS = ["level", "sector", "country", "city", "remote", "salary", "yoe"]


def _arg(flag: str, default: str) -> str:
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def _key(v: object) -> str:
    return json.dumps(v, sort_keys=True)


def main() -> None:
    now = datetime.now(timezone.utc)
    run_id = _arg("--run-id", "unknown")
    run_dir = RUNS / f"{now.strftime('%Y-%m-%d')}-gold-500"
    run_dir.mkdir(parents=True, exist_ok=True)

    inputs: dict[str, dict] = {}
    for f in J3.glob("assign_*.jsonl"):
        for line in f.read_text().split("\n"):
            if line.strip():
                r = json.loads(line)
                inputs[r["id"]] = r

    votes: dict[str, list[dict]] = defaultdict(list)
    for line in (J3 / "vote1.jsonl").read_text().split("\n"):
        if line.strip():
            r = json.loads(line)
            votes[r["id"]].append(r["gold"])  # reused vote #1
    out_files = sorted(J3.glob("out_*.jsonl"))
    for f in out_files:
        for line in f.read_text().split("\n"):
            if line.strip():
                r = json.loads(line)
                if r.get("id") and isinstance(r.get("gold"), dict):
                    votes[r["id"]].append(r["gold"])

    agree_full: Counter[str] = Counter()
    agree_maj: Counter[str] = Counter()
    nomaj: Counter[str] = Counter()
    coverage: Counter[int] = Counter()
    final: list[dict] = []
    for jid, inp in inputs.items():
        gs = votes.get(jid, [])
        coverage[len(gs)] += 1
        if len(gs) < 2:
            continue
        gold: dict = {}
        for field in FIELDS:
            vals = [g.get(field) for g in gs]
            cnt = Counter(_key(v) for v in vals)
            top, topn = cnt.most_common(1)[0]
            if topn == len(vals):
                agree_full[field] += 1
            if topn >= 2:
                agree_maj[field] += 1
                gold[field] = json.loads(top)
            else:
                nomaj[field] += 1
                chosen = vals[0]
                for v in vals:
                    if v not in (None, "unknown", ""):
                        chosen = v
                        break
                gold[field] = chosen
        final.append(
            {
                "id": jid,
                "source": inp.get("source"),
                "company_key": inp.get("company_key"),
                "title": inp.get("title"),
                "description_text": inp.get("description_windows"),
                "location_raw": inp.get("location_raw"),
                "structured_salary": inp.get("structured_salary"),
                "gold": gold,
            }
        )

    GOLD.write_text("".join(json.dumps(r, ensure_ascii=True) + "\n" for r in final))
    report = evaluate(final)
    n = max(1, len(final))
    agg = {
        "postings_labeled": len(final),
        "vote_coverage": dict(coverage),
        "agreement_unanimous": {f: round(agree_full[f] / n, 4) for f in FIELDS},
        "agreement_majority": {f: round(agree_maj[f] / n, 4) for f in FIELDS},
        "no_majority": {f: nomaj[f] for f in FIELDS},
        "positives": {
            f: sum(1 for r in final if r["gold"].get(f))
            for f in ("sector", "country", "city", "salary", "yoe")
        },
    }
    try:
        sha = (
            subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT)
            .decode()
            .strip()
        )
    except Exception:  # noqa: BLE001
        sha = "unknown"
    meta = {
        "run_id": run_id,
        "label": "gold-500",
        "finished_at": now.isoformat(),
        "git_sha": sha,
        "labeler_model": "sonnet",
        "votes_per_posting": 3,
        "vote1_source": "reused from stopped run wf_d2892da5-5bb",
        "postings_labeled": len(final),
    }
    (run_dir / "run.json").write_text(json.dumps(meta, indent=2) + "\n")
    (run_dir / "agreement.json").write_text(json.dumps(agg, indent=2) + "\n")
    (run_dir / "eval.json").write_text(json.dumps(report, indent=2) + "\n")
    (run_dir / "gold.jsonl").write_text(GOLD.read_text())
    if out_files:
        with tarfile.open(run_dir / "judge_raw.tar.gz", "w:gz") as tar:
            tar.add(J3 / "vote1.jsonl", arcname="vote1.jsonl")
            for f in out_files:
                tar.add(f, arcname=f.name)

    log = RUNS / "RUNS.md"
    line = (
        f"- **{now.strftime('%Y-%m-%d')} gold-500** (`{run_id}`, sonnet, 3-vote; vote1 reused): "
        f"{len(final)} postings — level {report['level_macro_f1']:.2f} F1 · "
        f"country {report['country_accuracy']:.2f} · city {report['city_accuracy']:.2f} · "
        f"comp {report['comp_f1']:.2f} F1 · yoe {report['yoe_f1']:.2f} F1 → `runs/{run_dir.name}/`\n"
    )
    log.write_text((log.read_text() if log.exists() else "# Labeling / eval runs\n\n") + line)

    print(json.dumps({"meta": meta, "eval": report, "agreement": agg}, indent=2))


if __name__ == "__main__":
    main()
