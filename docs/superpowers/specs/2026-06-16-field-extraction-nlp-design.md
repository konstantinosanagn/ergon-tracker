# Robust Field Extraction + Evaluation (NLP) — Design Spec

**Date:** 2026-06-16
**Status:** Approved — ready for implementation planning
**Component:** `jobspine.extract` (+ eval harness, gold corpus)

## 1. Problem & motivation

jobspine enriches each posting with `level`, `sector`, structured `geo`, and (from some
providers) `salary`. These are currently heuristics:
- `level` — title regex in `enrich.py`
- `geo` — location-string regex in `enrich.py`
- `sector` — a static company→sector lookup table (`sectors.json`)
- `salary` — structured fields from Ashby/Lever only; Greenhouse/Workday bury comp in text
- `years_of_experience` — not extracted at all

These were validated against ~21 curated unit cases, **not** measured against a large, varied
real corpus. Real postings express these fields in many ways the current rules miss, e.g.:
- level: "Member of Technical Staff", "MTS-3", "P4", "E5", "Engineer III", "SDE II"
- comp: "$180k–$220k + equity", "£90,000", "OTE 250k", ranges inside prose
- YoE: "5+ years", "3-5 yrs", "minimum of seven years", "at least 8 years' experience"
- geo: "Remote (EMEA)", "Hybrid - 3 days NYC", "Bengaluru/Pune", "US-Remote"

**We do not know current precision/recall.** The goal is to make extraction *measurable*,
*regression-proof*, and *better* — escalating from rules to lightweight ML only where the data
shows rules plateau.

## 2. Constraints
- **Free / local only.** No paid APIs. Labeling is done in-session by agents.
- **Runtime stays dependency-light.** Core inference must remain pure-Python and fast. ML is
  training-time only, behind an optional `[ml]` extra; trained models ship as compact data
  files with pure-Python inference.
- **Live postings only** (unchanged); extraction operates on a posting's text/fields.

## 3. Decisions (from brainstorming)
1. **Measure first, then improve.**
2. Fields in scope: **job level, compensation, years-of-experience, geo (incl. country),
   sector.**
3. Labels: **agent-labeled GOLD set + weak/silver labels at scale.**
4. Model ceiling: **ladder, capped at classic ML** (linear models); DNN/transformer is a
   documented future option, not in scope.

## 4. Architecture

### 4.1 Extractor framework — `src/jobspine/extract/`
```
extract/
  base.py        # FieldExtractor protocol + registry + a RulesExtractor base
  level.py       # seniority
  comp.py        # salary range/currency/interval/equity from structured + text
  yoe.py         # years of experience (min/max) from text
  geo.py         # city/region/country/remote from location strings (+ text fallback)
  sector.py      # company -> sector (table-backed; eval its coverage/accuracy)
  models/        # shipped compact model artifacts (created in Phase 2, may stay empty)
```
- `FieldExtractor` protocol: `name: str`, `extract(self, posting: ExtractInput) -> Any`.
- `ExtractInput`: a light view over a posting — `title`, `description_text`, `location_raw`,
  `company_key`, `company_domain`, `structured_salary`. (Avoids coupling extractors to the
  full `JobPosting`.)
- A registry maps field name → active extractor. Each extractor MAY have a `rules` impl and an
  optional `ml` impl; selection is by availability of a shipped model artifact (graceful
  fallback to rules when absent).
- `enrich_in_place(job)` becomes a thin caller that runs the registry and writes results onto
  the `JobPosting` (`level`, `sector`, `locations`, and new `years_experience`). The current
  `enrich.py` logic moves into `extract/level.py` and `extract/geo.py`.

### 4.2 New model field
- Add `years_experience_min: int | None` and `years_experience_max: int | None` to
  `JobPosting`, plus `SearchQuery.min_years`/`max_years` filters (overlap semantics, like
  salary). Comp parsing from text augments the existing `salary` field when providers don't
  supply it.

### 4.3 Corpus & labeling
- `scripts/snapshot_corpus.py` — fetch ~3–5k real postings across all providers and a
  stratified spread of companies; write `data/corpus.jsonl` (fields: source, company_key,
  title, description_text, location_raw, structured_salary). Cached; re-runnable. NOT
  committed (large); a small committed sample backs unit tests.
- **Gold set:** agents fully-label a **stratified ~500-posting** subset (one posting → gold
  for every field) → `tests/data/gold.jsonl`. Stratified by provider and role family to cover
  the messy variants. Committed (compact: only the fields needed + gold labels). A labeling
  guide (`docs/extraction-labeling-guide.md`) defines each label precisely so agent labels are
  consistent.
- **Silver set:** rules/structured fields applied to the rest of the corpus → training data
  for Phase 2 (not committed).

### 4.4 Evaluation harness
- `scripts/eval_extraction.py` runs every extractor over `gold.jsonl` and prints a per-field
  report. Metrics:
  - **level** — accuracy, macro-F1, confusion matrix, UNKNOWN-rate
  - **comp** — presence precision/recall; value-within-tolerance accuracy (±5%)
  - **yoe** — presence precision/recall; exact-match; MAE on min-years
  - **geo** — country accuracy; city accuracy (normalized); remote-detection P/R
  - **sector** — accuracy; coverage (% non-Other) and % correct
- Output is a markdown/plain report; the baseline run (Phase 1 deliverable) tells us exactly
  where to invest.

### 4.5 The ladder (Phase 2, per field)
1. Refine the rules using gold-set failures.
2. Re-measure. If a field is below its target, train a linear model (scikit-learn:
   `LogisticRegression`/`LinearSVC` over `TfidfVectorizer` word + char n-grams) on the silver
   set, tuned/validated on a gold split.
3. **Export** the trained model to a compact artifact (vocabulary + weights as JSON/npz) and
   implement **pure-Python inference** (hashing/lookup + dot product) so runtime needs no
   sklearn/numpy. Ship the artifact under `extract/models/`.
4. Keep whichever (rules vs ML) scores higher on the gold set; record the choice.

## 5. Packaging
- `[ml]` optional extra → `scikit-learn` (+ `numpy`), used only by `scripts/train_*.py` and
  tests that retrain. Runtime imports neither.
- Model artifacts are data files included in the wheel (extend the existing force-include).

## 6. Testing
- Unit tests per extractor (rules behavior on tricky strings).
- **Gold regression tests** (`tests/test_extraction_quality.py`): assert each field's metric
  stays **≥ a locked threshold** computed from the baseline (e.g. `level_macro_f1 >= 0.80`).
  This is the durable stress test — accuracy cannot silently regress.
- Existing `test_enrich.py` cases migrate to the new extractor modules.

## 7. Phasing (one spec, two implementation phases)
- **Phase 1 — Measurement (do first):** extractor framework skeleton wrapping current logic +
  corpus snapshot tool + agent-labeled gold set + eval harness + **baseline report**. No
  accuracy work yet — just make it measurable.
- **Phase 2 — Improvement:** per-field rules→ML ladder, re-measure, ship best per field, lock
  regression thresholds. Add YoE field + comp-from-text + level variants + geo variants.

## 8. Out of scope (documented)
- DNN/transformer/embedding models (future; ceiling is classic ML).
- Skills/tech-stack extraction (separate future effort).
- Non-English postings (note as a known limitation; gold set is English-first).

## 9. Success criteria
- A reproducible eval harness + committed gold set exist.
- A baseline accuracy report for all five fields exists.
- Phase 2: each field meets or beats its baseline, with locked regression thresholds; runtime
  remains pure-Python and dependency-light.
