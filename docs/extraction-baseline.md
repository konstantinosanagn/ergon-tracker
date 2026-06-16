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
| city | accuracy | 0.772 → **0.798** |
| **country** | accuracy | 0.336 → **0.877** (Phase 2: city→country gazetteer) |
| comp | precision / recall / F1 | 0.74 / 0.98 / 0.844 |
| comp | value within 5% | 0.926 |
| **yoe** | F1 | 0.000 → **0.932** (exact 0.98, MAE 0.0) |

## Principle: deterministic-first
Exhaust deterministic methods — gazetteers, dictionaries, rules — before reaching for ML/NLP.
The country fix below is the model: a city→country lookup beat the problem outright, no NLP.

## Where to invest (Phase 2)
1. **country (0.34) — DONE → 0.877.** Added a deterministic 2,925-city `cities.json`
   gazetteer (GeoNames-sourced) + noise stripping ("Germany Locations"→Germany, "US-Remote",
   "3 Locations", metro/bay-area) + full US state names. Pure lookup, zero NLP.
2. **yoe (0.00) — DONE → 0.932.** Not an extractor bug: head-truncation to 1000 chars hid
   ~97% of YoE statements (median JD ~4.7k chars; 794/820 cues lay beyond char 1000). Fix was
   a measurement fix — `cue_windows()` keeps ±250 chars around each year/experience/salary cue
   (compact + signal-preserving), gold re-labeled on the windows. 55 yoe positives now.
3. **comp precision (0.755).** Recall and value accuracy are excellent; trim false positives
   (numbers misread as salary).
4. **level macro-F1 (0.771).** Add the company-ladder variants the gold exposed
   ("Member of Technical Staff", "Engineer II/III", "Associate"/segment vs seniority).

Regression thresholds are locked in `tests/test_extraction_quality.py` a margin below these;
Phase 2 must raise them as fields improve.
