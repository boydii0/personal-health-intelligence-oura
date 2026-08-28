# Step 8B — Deterministic Cross-Source Monthly Review

Status: **OWNER-APPROVED / IMPLEMENTED CANDIDATE / LOCAL WINDOWS VALIDATION PENDING**

## Purpose

Generate a deterministic Monthly Review focused on sustained trends, cross-source co-movement, intervention windows, data-quality gaps, and questions worth investigating.

## Canonical inputs

- Oura normalized sleep core
- Oura normalized heart core
- Hume normalized body-composition core
- Function Health verified biomarker core
- owner-confirmed supplement regimen and dated timeline
- owner-confirmed medication context

No PHI belongs in GitHub.

## Window policy

- Current window: latest 28 aligned trusted Oura sleep/heart days by calendar range.
- Prior comparison window: the immediately preceding 28 calendar days.
- A complete month-over-month comparison requires 28/28 trusted Oura sleep days and 28/28 trusted Oura heart days in the prior window.
- If the prior window is incomplete, prior-month deltas are withheld rather than calculated from a partial period.
- Hume observation counts remain explicit and missing days are never imputed.
- Function Health remains a static verified panel anchor until another verified panel exists.

## Co-movement

The candidate computes same-day Pearson coefficients between Hume Weight/Body Fat and Oura Total Sleep/Average HRV only when at least five paired observations exist. Coefficients are descriptive association signals only; they do not establish causation or clinical significance.

## Controls

- trusted canonical records only;
- no imputation or smoothing;
- no clinical thresholds;
- no diagnosis or treatment recommendation;
- no medication or supplement change;
- intervention chronology is not adherence proof;
- explicit data-quality limitations;
- deterministic investigation questions only.

## Candidate implementation

- branch: `step-8b-monthly-review`
- generator: `connector-validation/analytics/generate_cross_source_monthly_review.py`
- runner: `connector-validation/run_monthly_review.py`
- tests: `connector-validation/analytics/test_generate_cross_source_monthly_review.py`

## Local validation sequence

From `connector-validation` on the always-on Windows PC:

```powershell
py -m unittest discover -s analytics -p "test_generate_cross_source_monthly_review.py" -v
py run_monthly_review.py --validate-only
```

Expected controls:

- 8 synthetic tests PASS;
- `Review: PASS`;
- `Mode: validate-only`;
- output path under `Insights/Monthly/`;
- `Publish state: VALIDATE_ONLY`;
- `AI interpretation executed: NO`.

Only after owner validation of the candidate:

```powershell
py run_monthly_review.py
```

Expected publish state: `CREATED` (or `NOOP_IDENTICAL` on an identical rerun).

## Scheduling boundary

Do not schedule the Monthly Review until one manual publish PASS is owner-validated. The eventual cadence should be monthly and should run after the final Oura source + normalization refresh for the selected month-end operating date.
