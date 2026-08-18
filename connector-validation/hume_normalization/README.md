# PHI Step 5B — Hume Body-Composition Normalization

Status: **COMPLETE / PASS — 2026-08-18**

This folder contains the deterministic Step 5B normalizer for the validated Hume Health Connect export. It contains code/tests only; raw or normalized personal health data must never be committed to GitHub.

## Scope

Trusted input is limited to the Step 5A export contract:

- `WeightRecord` represented as `record_type = weight`, unit `kg`;
- `BodyFatRecord` represented as `record_type = body_fat`, unit `percent`;
- `data_origin_package = com.elink.fittrackhealth.pro`;
- Step 5A validation export schema `phi.health_connect_validation.v0.1`;
- read-only export with network transmission disabled.

The normalizer fails closed for unexpected source packages, record types, units, duplicate record IDs, count mismatches, or authority-contract changes.

## Weight unit policy

The source value remains unchanged as `value_original` / `unit_original = kg`.

The canonical normalized/display unit is **pounds (`lb`)**, per owner preference:

`lb = kg × 2.2046226218487757`

Normalized weight is rounded deterministically to **1 decimal place**. The source kilogram value is always preserved so the conversion remains traceable and reproducible.

Body fat remains percent with the original value preserved.

## Validated result

- synthetic tests: **7/7 PASS**;
- approved source: **30 records**;
- normalized output: **30 records** — 15 Weight + 15 Body Fat;
- source SHA-256: `2ff0a87076481f659c679d507d1dfd9ae45296e2a652c3c3c1b838fea4a243ed`;
- normalized SHA-256: `8958c65d615960d0fb55f78ba14905ccbffb2c14567a73e2dd8efcf13a24c80d`;
- local/controlled reproducibility: **PASS**;
- imputation: **NO**;
- smoothing: **NO**;
- AI interpretation: **NO**.

Canonical output lives outside GitHub at:

`03_Areas/Health/Personal Health Repository/Normalized Data/Body Composition/hume_body_composition_core_v0.1.json`

Step 5B and Step 5 overall are complete. The governed roadmap proceeds to Step 6 Function Health PDF extraction / human verification / biomarker normalization.
