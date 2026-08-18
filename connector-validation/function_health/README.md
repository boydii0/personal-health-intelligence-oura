# PHI Step 6 - Function Health Extraction and Biomarker Normalization

Status: **COMPLETE / PASS**

This folder contains the deterministic Function Health `Data` PDF candidate extractor and the owner-verified biomarker normalizer used in PHI Step 6. It contains code and synthetic tests only. Source PDFs, extracted PHI, verified PHI, and normalized biomarker outputs must never be committed to GitHub.

## Candidate extraction

The extractor:

- reads a Function Health `Data` PDF through Poppler `pdftotext -layout`;
- preserves source section, analyte label, Function range flag, result text, value text, unit text and page provenance;
- preserves repeated analytes as separate source occurrences;
- excludes the `Daily Metrics` section from the lab candidate set;
- marks every candidate `unverified`;
- does not infer collection dates, panel identity, numeric reference ranges or clinical meaning;
- performs no unit normalization, clinical interpretation or deduplication.

Run:

```powershell
python .\extract_function_health_data.py <source.pdf> <candidate-output.json>
```

## Trusted biomarker normalization

After owner verification occurs outside GitHub, the normalizer:

- requires an explicit collection date;
- preserves original value text, units, Function range flags and source-document checksum;
- deterministically parses numeric, censored-numeric (for example `<10`) and categorical results;
- performs no unit conversion and does not invent numeric reference ranges;
- reconciles repeated analyte occurrences only when result text, unit and Function range flag are identical;
- fails closed when repeated occurrences conflict;
- preserves every reconciled source occurrence as provenance;
- emits only `verified` normalized biomarker records.

Run:

```powershell
python .\normalize_function_health_biomarkers.py <verified-extraction.json> <biomarker-output.json> --collection-date YYYY-MM-DD --verified-at-utc <UTC timestamp>
```

## Tests

```powershell
python -m unittest -v test_extract_function_health_data.py
python -m unittest -v test_normalize_function_health_biomarkers.py
```

Synthetic fixtures only.

## Validated Step 6 result

Private controlled execution completed outside GitHub:

- candidate extractor synthetic tests: PASS;
- biomarker normalizer synthetic tests: 7/7 PASS;
- owner verified all 127 extracted laboratory candidates;
- owner confirmed blood collection date: 2026-08-04;
- 127 verified source occurrences deterministically reconciled into 118 normalized biomarker records;
- 9 repeated source occurrences were reconciled only because their source result/unit/range flag matched exactly;
- no unit conversion, numeric reference-range inference or clinical interpretation occurred;
- source PDF and all PHI artifacts remain in the canonical private PHI repository, not GitHub.
