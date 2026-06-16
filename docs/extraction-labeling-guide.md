# Extraction Gold-Labeling Guide

Label each posting by reading its `title`, `description_text`, and `location_raw`. Output one
JSON object per input row, preserving `id`, `source`, `company_key`, `title`,
`description_text`, `location_raw`, `structured_salary`, and adding a `gold` object.

**Principle: label what the posting actually states. Never guess. Use the "unknown"/null
fallback when the posting doesn't say.**

## `gold` fields

### level  (string, required)
One of: `intern, entry, junior, mid, senior, staff, principal, lead, manager, director,
executive, unknown`.
- Judge the role's seniority from the title (and description if title is ambiguous).
- Map company-specific ladders to the closest rung: "Member of Technical Staff" → usually
  `mid` unless qualified ("Senior MTS" → `senior`); "MTS-3"/"E5"/"P4"/"IC4" → `senior`;
  "Engineer II"/"SDE II" → `mid`; "Engineer III" → `senior`; "Engineer I" → `entry`.
- "Senior Manager" → `manager` (management track wins over the senior modifier).
- No seniority signal at all (e.g. plain "Software Engineer") → `mid` ONLY if the description
  implies experience; otherwise `unknown`. Prefer `unknown` when genuinely unmarked.

### sector  (string or null)
The company's industry, one of the labels in `sectors.json` vocabulary (Software/SaaS, AI/ML,
Fintech, Banking/Finance, Insurance, Crypto/Web3, Healthcare, Biotech/Pharma,
Semiconductors/Hardware, Cybersecurity, Gaming, Media/Entertainment, E-commerce/Retail,
Consumer/Lifestyle, Telecom, Automotive/Mobility, Aerospace/Defense, Energy/Climate,
Logistics/SupplyChain, Education, RealEstate/PropTech, Consulting/Services,
Manufacturing/Industrial, Travel/Hospitality, Food/Beverage, Government/Public, Other).
Judge from the company, not the role. `null` only if you truly cannot tell.

### country / city  (string or null)
From `location_raw`. `country` = canonical country name ("United States", "United Kingdom",
"Germany"...). `city` = primary city if stated. Remote-only with no place → both `null`.
For multi-location ("Berlin / London"), use the FIRST. US "City, ST" → city + country
"United States".

### remote  (bool)
`true` if the posting is remote or hybrid; else `false`.

### salary  (object or null)
`{"min": <number|null>, "max": <number|null>, "currency": "USD"|..., "interval":
"year"|"hour"|"month"|"week"|"day"}` — ONLY if the posting states pay (in `structured_salary`
OR in the description text). Numbers are absolute (150000, not "150k"). `null` if no pay stated.
Do not infer from market norms.

### yoe  (object or null)
`{"min": <int|null>, "max": <int|null>}` — the required years of experience if stated
("5+ years" → {min:5,max:null}; "3-5 years" → {min:3,max:5}). `null` if not stated. Ignore
non-experience durations (vesting, "founded N years ago", tenure of benefits).

## Output format
Write JSONL (one object per line) to your assigned output path. Each line = the input row plus
the `gold` object. Do not reorder or drop rows.
