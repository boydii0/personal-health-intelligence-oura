# PHI Step 6 - Function Health Data PDF Extraction

Status: **IMPLEMENTED / OWNER VERIFICATION REQUIRED**

This folder contains the deterministic candidate-row extractor for the Function Health "Data" PDF export used in PHI Step 6. It contains code and synthetic tests only. Source PDFs and extracted personal health data must never be committed to GitHub.

## Scope

The extractor:

- reads a Function Health `Data` PDF through Poppler `pdftotext -layout`;
- preserves source section, analyte label, Function range flag, result text, value text, unit text and page provenance;
- preserves repeated analytes as separate source occurrences;
- excludes the `Daily Metrics` section from the lab candidate set;
- marks every candidate `unverified`;
- does not infer collection dates, panel identity, numeric reference ranges or clinical meaning;
- performs no unit normalization, clinical interpretation or deduplication.

## Run

```powershell
python .\extract_function_health_data.py <source.pdf> <candidate-output.json>
```

Requirements: Python 3 and Poppler `pdftotext` available on `PATH`.

## Test

```powershell
python -m unittest -v test_extract_function_health_data.py
```

Tests use synthetic fixtures only.

## Governance gate

Candidate extraction is not trusted biomarker admission. The source PDF remains canonical and every parsed row remains unverified until the owner completes the Step 6 side-by-side verification gate. Missing source facts such as collection date or numeric reference-range boundaries must remain missing rather than being guessed.
