#!/usr/bin/env python3
"""Deterministically normalize validated Hume Health Connect body-composition data.

Public code only: never commit raw or normalized personal health data to GitHub.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "phi.hume_body_composition_core.v0.1"
NORMALIZER_VERSION = "hume-body-composition-v0.1"
EXPECTED_SOURCE_SCHEMA = "phi.health_connect_validation.v0.1"
DEFAULT_HUME_PACKAGE = "com.elink.fittrackhealth.pro"
KG_TO_LB = 2.2046226218487757
WEIGHT_DECIMALS = 1
ALLOWED_RECORD_TYPES = {"weight", "body_fat"}
METRIC_NAMES = {"weight": "weight", "body_fat": "body_fat_percentage"}
METRIC_ORDER = {"weight": 0, "body_fat": 1}


class NormalizationError(ValueError):
    """Raised when source data violates the trusted Step 5B contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require(record: dict[str, Any], field: str) -> Any:
    if field not in record or record[field] is None:
        raise NormalizationError(f"record missing required field: {field}")
    return record[field]


def _normalize_record(record: dict[str, Any], expected_package: str) -> dict[str, Any]:
    record_type = _require(record, "record_type")
    if record_type not in ALLOWED_RECORD_TYPES:
        raise NormalizationError(f"unexpected record_type: {record_type}")

    source_package = _require(record, "data_origin_package")
    if source_package != expected_package:
        raise NormalizationError(
            f"unexpected data_origin_package: {source_package}; expected {expected_package}"
        )

    value = float(_require(record, "value"))
    unit = _require(record, "unit")

    if record_type == "weight":
        if unit != "kg":
            raise NormalizationError(f"weight unit must be kg, got: {unit}")
        normalized_value = round(value * KG_TO_LB, WEIGHT_DECIMALS)
        normalized_unit = "lb"
    else:
        if unit != "percent":
            raise NormalizationError(f"body_fat unit must be percent, got: {unit}")
        normalized_value = value
        normalized_unit = "percent"

    source_record_id = str(_require(record, "record_id"))

    return {
        "metric_observation_id": f"hume:{record_type}:{source_record_id}",
        "metric": METRIC_NAMES[record_type],
        "source_record_id": source_record_id,
        "observed_at_utc": _require(record, "observed_at_utc"),
        "zone_offset": record.get("zone_offset"),
        "last_modified_at_utc": record.get("last_modified_at_utc"),
        "recording_method": record.get("recording_method"),
        "data_origin_package": source_package,
        "value_original": value,
        "unit_original": unit,
        "value_normalized": normalized_value,
        "unit_normalized": normalized_unit,
        "data_quality_state": "trusted",
    }


def normalize_document(
    source: dict[str, Any],
    *,
    source_file_name: str,
    source_sha256: str,
    expected_package: str = DEFAULT_HUME_PACKAGE,
) -> dict[str, Any]:
    if source.get("schema_version") != EXPECTED_SOURCE_SCHEMA:
        raise NormalizationError(
            f"source schema must be {EXPECTED_SOURCE_SCHEMA}, got: {source.get('schema_version')}"
        )
    if source.get("read_only") is not True:
        raise NormalizationError("source export must assert read_only=true")
    if source.get("network_transmission") is not False:
        raise NormalizationError("source export must assert network_transmission=false")

    records = source.get("records")
    if not isinstance(records, list):
        raise NormalizationError("source records must be a list")
    if source.get("record_count") != len(records):
        raise NormalizationError("source record_count does not match records length")

    source_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            raise NormalizationError("each source record must be an object")
        source_id = str(_require(record, "record_id"))
        if source_id in source_ids:
            raise NormalizationError(f"duplicate source record_id: {source_id}")
        source_ids.add(source_id)
        normalized.append(_normalize_record(record, expected_package))

    normalized.sort(
        key=lambda item: (
            item["observed_at_utc"],
            METRIC_ORDER["weight"] if item["metric"] == "weight" else METRIC_ORDER["body_fat"],
            item["source_record_id"],
        )
    )

    counts = {
        "weight": sum(1 for item in normalized if item["metric"] == "weight"),
        "body_fat_percentage": sum(
            1 for item in normalized if item["metric"] == "body_fat_percentage"
        ),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "normalizer_version": NORMALIZER_VERSION,
        "source": {
            "file_name": source_file_name,
            "sha256": source_sha256,
            "schema_version": source["schema_version"],
            "generated_at_utc": source.get("generated_at_utc"),
            "query_start_utc": source.get("query_start_utc"),
            "query_end_utc": source.get("query_end_utc"),
            "query_window_days": source.get("query_window_days"),
            "data_origin_package": expected_package,
            "validation_status": "PASS",
        },
        "normalization": {
            "canonical_weight_unit": "lb",
            "canonical_body_fat_unit": "percent",
            "kg_to_lb_factor": KG_TO_LB,
            "weight_rounding_decimals": WEIGHT_DECIMALS,
            "original_values_preserved": True,
            "imputation": False,
            "smoothing": False,
            "ai_interpretation": False,
        },
        "record_count": len(normalized),
        "record_counts_by_metric": counts,
        "records": normalized,
    }


def normalize_file(
    source_path: Path,
    output_path: Path,
    *,
    expected_package: str = DEFAULT_HUME_PACKAGE,
) -> dict[str, Any]:
    with source_path.open("r", encoding="utf-8") as handle:
        source = json.load(handle)

    result = normalize_document(
        source,
        source_file_name=source_path.name,
        source_sha256=sha256_file(source_path),
        expected_package=expected_package,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_json", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--expected-package", default=DEFAULT_HUME_PACKAGE)
    args = parser.parse_args()

    try:
        result = normalize_file(
            args.source_json,
            args.output_json,
            expected_package=args.expected_package,
        )
    except (OSError, json.JSONDecodeError, NormalizationError) as exc:
        parser.error(str(exc))
        return 2

    print(
        f"PASS: normalized {result['record_count']} records "
        f"({result['record_counts_by_metric']['weight']} weight, "
        f"{result['record_counts_by_metric']['body_fat_percentage']} body fat)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
