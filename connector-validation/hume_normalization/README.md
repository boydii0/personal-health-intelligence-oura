# PHI Step 5B — Hume Body-Composition Normalization

Status: **IMPLEMENTED / LOCAL REPRODUCIBILITY VALIDATION REQUIRED**

This folder contains the deterministic Step 5B normalizer for the already validated Hume Health Connect export. It contains code/tests only; raw or normalized personal health data must never be committed to GitHub.

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

Normalized weight is rounded deterministically to **1 decimal place**. The source kilogram value is always preserved so the conversion is reversible/reproducible from source.

Body fat remains percent with the original value preserved.

## Output

Default canonical destination:

`03_Areas/Health/Personal Health Repository/Normalized Data/Body Composition/hume_body_composition_core_v0.1.json`

Every observation preserves:

- canonical metric name;
- direct source record ID;
- observation timestamp and zone offset;
- Hume/Health Connect source package;
- original value/unit;
- normalized value/unit;
- recording method and last-modified timestamp;
- trusted data-quality state.

The output also records source SHA-256, source query window, conversion factor, rounding rule, and explicit `imputation=false`, `smoothing=false`, `ai_interpretation=false`.

## Run

From this folder:

```powershell
python .\normalize_hume_body_composition.py <validated-source.json> <output.json>
```

## Test

```powershell
python -m unittest -v test_normalize_hume_body_composition.py
```

Tests use synthetic fixtures only and must not contain PHI.

## PASS gate

Step 5B is PASS only after:

1. unit tests pass;
2. the approved Step 5A source normalizes without error;
3. input/output source-count reconciliation is exact (30 → 30 for the approved validation set);
4. weight retains kg originals and normalizes to lb deterministically;
5. body fat remains percent;
6. canonical output is landed under `Normalized Data/Body Composition/`;
7. owner/local checkout reproduces the same normalized result/checksum;
8. no PHI is committed to GitHub.
