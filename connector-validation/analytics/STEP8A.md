# Step 8A — Cross-Source Weekly Insight

Status: implementation candidate; owner validation required before Step 8A PASS.

## Purpose

Generate a deterministic cross-source Weekly Insight using validated canonical PHI inputs without committing PHI to GitHub.

## Private canonical inputs

- Oura baseline core (`oura_baseline_core_v0.1.json`)
- Hume body-composition core (`hume_body_composition_core_v0.1.json`)
- Function Health verified biomarker core (`function_health_biomarker_core_v0.1.json`)
- owner-confirmed `Supplement Regimen - Current.md`
- owner-confirmed `Supplement Timeline.md`
- owner-confirmed `current_medications_v0.1.json`

These files remain in the private AI_Vault and are blocked by `.gitignore` rules. Only code, synthetic tests, and documentation belong in this repository.

## Generator

`generate_cross_source_weekly_insight.py`

The generator:

- uses the existing Oura 7-day vs trailing-28-day baseline as the backbone;
- aligns Hume trusted Weight and Body Fat observations by local measurement date;
- reports Hume coverage explicitly and never imputes missing observation days;
- treats the single verified Function Health panel as a static anchor only;
- treats supplement start/stop events as chronology, not proof of adherence or causation;
- uses medications as context only and excludes confirmations that postdate the weekly observation window;
- produces no diagnosis, clinical thresholds, treatment recommendation, medication change, or causal claim.

## Validation

Synthetic suite: `test_generate_cross_source_weekly_insight.py`

Controlled implementation validation: 9/9 synthetic tests PASS. A real-source canonical run is also required to be byte-for-byte reproducible before owner review.

## Owner gate

The generated Weekly Insight is a candidate until the owner validates the source windows/coverage, Hume calculations, intervention chronology, and non-causal/non-clinical boundaries. Step 8B Monthly Review must not begin until Step 8A is formally PASS.
