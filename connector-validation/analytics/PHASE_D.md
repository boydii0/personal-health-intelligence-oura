# Phase D — Oura Normalize + Insight Refresh Bridge

Status: **OWNER-APPROVED / IMPLEMENTED CANDIDATE / LOCAL WINDOWS VALIDATION PENDING**

## Purpose

Connect the validated Phase C immutable Oura source-run layout to the existing PHI normalized sleep/heart cores and deterministic baseline without changing the established health metric semantics.

## Source authority

Only Phase C folders with `run_manifest.json` status `PASS` are eligible:

```text
Source Data/Oura/YYYY-MM-DD/<UTC-run-id>/
```

The bridge verifies the manifest SHA-256 for `sleep.json` and `daily_sleep.json` before normalization.

## Historical continuity

The existing canonical files remain the historical seed:

- `Normalized Data/Sleep/oura_sleep_core_v0.1.json`
- `Normalized Data/Heart/oura_heart_core_v0.1.json`

Phase C observations replace the same observation day deterministically. Older seed days outside the Phase C snapshots remain preserved.

## Deterministic rules

- Only `sleep.type == long_sleep` is admitted to the sleep/heart core.
- A normalized sleep row requires a same-day `daily_sleep` record.
- Overlapping Phase C snapshots deduplicate by Oura source record ID; the newest PASS snapshot wins.
- Durations retain the validated v0.1 transform: source seconds → minutes rounded to 3 decimals.
- No imputation, smoothing, AI interpretation, clinical thresholds, or causal inference.
- A daily score without a matching long-sleep session is recorded as a missing-primary-sleep day and is not normalized.

## Validation commands

From `connector-validation` on the always-on Windows PC:

```powershell
py -m unittest discover -s analytics -p "test_refresh_oura_from_phase_c.py" -v
py run_phase_d_refresh.py --validate-only
```

The first command must pass all tests. The second must report `Refresh: PASS` and `Canonical write executed: NO`.

After owner inspection/approval of the validate-only output:

```powershell
py run_phase_d_refresh.py
```

This atomically replaces the canonical sleep core, heart core, and Oura baseline only after all source checks and baseline calculation succeed.

## Scheduling boundary

Do not schedule Phase D until manual publish PASS is validated. Proposed eventual cadence:

- 09:15 daily — normalization + baseline refresh, 15 minutes after the 09:00 source sync.
- 19:15 daily — normalization + baseline refresh, 15 minutes after the 19:00 source sync.
- Cross-source Weekly Insight remains a separate downstream task; it should not be generated twice daily.
- Step 8B Monthly Review remains a separate analytical implementation/gate.

## Controlled validation performed before owner run

A controlled no-write validation using the current canonical sleep/heart seed plus the latest Phase C PASS snapshot reproduced the established transform semantics. It produced 32 aligned normalized days through 2026-08-20. The 2026-08-21 `daily_sleep` record had no matching `long_sleep` in that source snapshot and was therefore correctly withheld from normalization. Baseline freshness was `fresh` at age 1 day.
