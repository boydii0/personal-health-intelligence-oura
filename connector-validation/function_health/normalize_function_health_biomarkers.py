#!/usr/bin/env python3
"""Normalize owner-verified Function Health extraction rows into the PHI biomarker core.

Public code only. Never commit source PDFs, extracted personal health data, or normalized
personal health data to GitHub. This utility assumes owner verification has already occurred
outside GitHub and fails closed on conflicting repeated analyte occurrences.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "phi.function_health_biomarker_core.v0.1"
NORMALIZER_VERSION = "function-health-biomarker-normalizer-0.1"


class NormalizationError(ValueError):
    """Raised when trusted normalization would require guessing."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slugify(name: str) -> str:
    value = name.lower().replace("%", " percent ")
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def parse_result(value: str) -> dict[str, Any]:
    source = value.strip()
    compact = source.replace(",", "")
    censored = re.fullmatch(r"([<>]=?)\s*(-?\d+(?:\.\d+)?)", compact)
    if censored:
        return {
            "result_kind": "censored_numeric",
            "comparator": censored.group(1),
            "numeric_value": float(censored.group(2)),
            "categorical_value": None,
        }
    if re.fullmatch(r"-?\d+(?:\.\d+)?", compact):
        return {
            "result_kind": "numeric",
            "comparator": None,
            "numeric_value": float(compact),
            "categorical_value": None,
        }
    return {
        "result_kind": "categorical",
        "comparator": None,
        "numeric_value": None,
        "categorical_value": source,
    }


def normalize(
    extraction: dict[str, Any], collection_date: str, verified_at_utc: str
) -> dict[str, Any]:
    candidates = extraction.get("candidates") or []
    if not candidates:
        raise NormalizationError("no candidates")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", collection_date):
        raise NormalizationError("collection_date must be YYYY-MM-DD")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate["analyte_name_original"]].append(candidate)

    biomarkers: list[dict[str, Any]] = []
    for analyte_name in sorted(grouped):
        rows = grouped[analyte_name]
        signatures = {
            (
                row.get("result_text_original"),
                row.get("unit_original"),
                row.get("range_flag_original"),
            )
            for row in rows
        }
        if len(signatures) != 1:
            raise NormalizationError(f"conflicting repeated analyte: {analyte_name}")

        first = rows[0]
        parsed = parse_result(first["value_original"])
        biomarkers.append(
            {
                "biomarker_result_id": f"FH-{collection_date}-{slugify(analyte_name)}",
                "biomarker_key": slugify(analyte_name),
                "analyte_name_original": analyte_name,
                "collection_date": collection_date,
                "category_originals": sorted(
                    {row.get("category_original") for row in rows if row.get("category_original")}
                ),
                "result_text_original": first.get("result_text_original"),
                "value_original": first.get("value_original"),
                "unit_original": first.get("unit_original"),
                "range_flag_original": first.get("range_flag_original"),
                "reference_low_original": first.get("reference_low_original"),
                "reference_high_original": first.get("reference_high_original"),
                "reference_text_original": first.get("reference_text_original"),
                "value_normalized": first.get("value_original"),
                "unit_normalized": first.get("unit_original"),
                "normalization_operation": "identity_no_unit_conversion",
                **parsed,
                "verification_state": "verified",
                "verified_by": "owner",
                "verified_at_utc": verified_at_utc,
                "source_document_ref": first.get("source_document_ref"),
                "source_document_sha256": first.get("source_document_sha256"),
                "source_occurrence_count": len(rows),
                "source_occurrences": [
                    {
                        "candidate_row_id": row.get("candidate_row_id"),
                        "source_page": row.get("source_page"),
                        "category_original": row.get("category_original"),
                    }
                    for row in rows
                ],
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "normalizer_version": NORMALIZER_VERSION,
        "lab_panel": {
            "lab_panel_id": f"function_health_{collection_date}",
            "source_name": "Function Health",
            "collection_date": collection_date,
            "report_date": None,
            "panel_identity_original": None,
            "verification_state": "verified",
            "verified_by": "owner",
            "verified_at_utc": verified_at_utc,
        },
        "controls": {
            "owner_verified_all_candidate_rows": True,
            "unit_conversion": False,
            "numeric_reference_range_inference": False,
            "clinical_interpretation": False,
            "repeated_analytes_reconciled_only_when_value_unit_flag_identical": True,
        },
        "source_candidate_count": len(candidates),
        "normalized_biomarker_count": len(biomarkers),
        "reconciled_duplicate_occurrence_count": len(candidates) - len(biomarkers),
        "biomarkers": biomarkers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--collection-date", required=True)
    parser.add_argument("--verified-at-utc", required=True)
    args = parser.parse_args()

    extraction = json.loads(args.input_json.read_text(encoding="utf-8"))
    output = normalize(extraction, args.collection_date, args.verified_at_utc)
    output["source_extraction_sha256"] = sha256_file(args.input_json)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"PASS: {output['source_candidate_count']} verified candidates -> "
        f"{output['normalized_biomarker_count']} normalized biomarkers"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
