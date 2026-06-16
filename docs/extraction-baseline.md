# Extraction Baseline — 2026-06-16

First measured accuracy of the rules-based extractors, on a **162-posting consensus gold set**
(stratified across all 4 ATS providers; each row independently labeled by **3 blind agents**,
majority vote). Inter-annotator agreement was high (level 88% unanimous / 100% majority; all
other fields 94–100% unanimous; 0 rows without a majority), so the gold is trustworthy.

Reproduce: `.venv/bin/python scripts/eval_extraction.py`

| Field | Metric | Baseline |
|---|---|---|
| level | accuracy | 0.815 |
| level | macro-F1 | 0.771 |
| sector | accuracy | 0.851 |
| city | accuracy | 0.772 |
| **country** | accuracy | **0.336** |
| comp | precision / recall / F1 | 0.755 / 1.000 / 0.860 |
| comp | value within 5% | 1.000 |
| **yoe** | F1 | **0.000** |

## Where to invest (Phase 2)
1. **country (0.34) — top priority.** Failure modes: gold labelers infer country from a known
   city ("San Francisco" → United States) but the extractor has no city→country gazetteer;
   ATS suffix formats ("Germany Locations", "3 Locations", "US-Remote") aren't parsed. Fix:
   city→country gazetteer + strip "Locations"/segment noise + handle "US"/"Remote" patterns.
2. **yoe (0.00) — under-measured + weak.** Only 2 gold positives, and descriptions were
   truncated to 1000 chars (often cutting the requirement). Fix: re-snapshot with full
   descriptions, enlarge the yoe-positive gold slice, then tune/expand the extractor.
3. **comp precision (0.755).** Recall and value accuracy are excellent; trim false positives
   (numbers misread as salary).
4. **level macro-F1 (0.771).** Add the company-ladder variants the gold exposed
   ("Member of Technical Staff", "Engineer II/III", "Associate"/segment vs seniority).

Regression thresholds are locked in `tests/test_extraction_quality.py` a margin below these;
Phase 2 must raise them as fields improve.
