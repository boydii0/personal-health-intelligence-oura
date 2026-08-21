"""Incremental Oura normalization bridge for Phase C immutable source runs.

Consumes only PASS run manifests under:
Source Data/Oura/YYYY-MM-DD/<UTC-run-id>/

The existing normalized Oura cores are the historical seed. New Phase C
sleep/daily_sleep observations deterministically replace the same observation
day in the seed after checksum validation. No AI interpretation is applied.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VERSION = "oura-core-normalizer-0.2-phase-c-bridge"


@dataclass(frozen=True)
class SourceRun:
    run_dir: Path
    run_id: str
    retrieved_at_utc: str
    sleep_sha256: str
    daily_sleep_sha256: str
    sleep_records: list[dict[str, Any]]
    daily_sleep_records: list[dict[str, Any]]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_dataset(run_dir: Path, manifest: dict[str, Any], name: str) -> tuple[Path, str]:
    datasets = manifest.get("datasets", {})
    meta = datasets.get(name)
    if not isinstance(meta, dict):
        raise ValueError(f"PASS manifest missing dataset: {name}")
    raw_name = meta.get("raw_file")
    expected = meta.get("checksum_sha256")
    if not raw_name or not expected:
        raise ValueError(f"Manifest dataset {name} missing raw_file/checksum")
    path = run_dir / raw_name
    if not path.is_file():
        raise ValueError(f"Manifest raw file missing: {path}")
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(f"Checksum mismatch for {path.name}")
    return path, actual


def discover_pass_runs(source_root: Path) -> list[SourceRun]:
    runs: list[SourceRun] = []
    if not source_root.is_dir():
        raise ValueError(f"Oura source root not found: {source_root}")
    for manifest_path in sorted(source_root.glob("*/*/run_manifest.json")):
        run_dir = manifest_path.parent
        manifest = _load_json(manifest_path)
        if manifest.get("status") != "PASS":
            continue
        sleep_path, sleep_sha = _validate_dataset(run_dir, manifest, "sleep")
        daily_path, daily_sha = _validate_dataset(run_dir, manifest, "daily_sleep")
        sleep_doc = _load_json(sleep_path)
        daily_doc = _load_json(daily_path)
        runs.append(
            SourceRun(
                run_dir=run_dir,
                run_id=str(manifest.get("run_id") or run_dir.name),
                retrieved_at_utc=str(manifest.get("retrieved_at_utc") or ""),
                sleep_sha256=sleep_sha,
                daily_sleep_sha256=daily_sha,
                sleep_records=list(sleep_doc.get("data", [])),
                daily_sleep_records=list(daily_doc.get("data", [])),
            )
        )
    runs.sort(key=lambda r: (r.retrieved_at_utc, r.run_id))
    return runs


def _latest_records_by_id(
    runs: list[SourceRun], attr: str
) -> tuple[dict[str, dict[str, Any]], dict[str, SourceRun]]:
    records: dict[str, dict[str, Any]] = {}
    origins: dict[str, SourceRun] = {}
    for run in runs:
        for record in getattr(run, attr):
            rid = record.get("id")
            if rid:
                records[str(rid)] = record
                origins[str(rid)] = run
    return records, origins


def _daily_by_day(
    records: dict[str, dict[str, Any]], origins: dict[str, SourceRun]
) -> tuple[dict[str, dict[str, Any]], dict[str, SourceRun]]:
    by_day: dict[str, dict[str, Any]] = {}
    by_origin: dict[str, SourceRun] = {}
    for rid, record in records.items():
        day = record.get("day")
        if day:
            by_day[str(day)] = record
            by_origin[str(day)] = origins[rid]
    return by_day, by_origin


def _minutes(seconds: Any) -> Any:
    return None if seconds is None else round(seconds / 60, 3)


def _sleep_record(
    raw: dict[str, Any],
    daily: dict[str, Any],
    sleep_run: SourceRun,
    daily_run: SourceRun,
) -> dict[str, Any]:
    return {
        "day": raw["day"],
        "source_sleep_record_id": raw["id"],
        "source_daily_sleep_record_id": daily["id"],
        "bedtime_start": raw.get("bedtime_start"),
        "bedtime_end": raw.get("bedtime_end"),
        "sleep_type": raw.get("type"),
        "sleep_algorithm_version": raw.get("sleep_algorithm_version"),
        "total_sleep_minutes": _minutes(raw.get("total_sleep_duration")),
        "time_in_bed_minutes": _minutes(raw.get("time_in_bed")),
        "awake_minutes": _minutes(raw.get("awake_time")),
        "deep_sleep_minutes": _minutes(raw.get("deep_sleep_duration")),
        "light_sleep_minutes": _minutes(raw.get("light_sleep_duration")),
        "rem_sleep_minutes": _minutes(raw.get("rem_sleep_duration")),
        "latency_minutes": _minutes(raw.get("latency")),
        "efficiency_percent": raw.get("efficiency"),
        "average_breaths_per_minute": raw.get("average_breath"),
        "oura_sleep_score": daily.get("score"),
        "oura_sleep_score_contributors": daily.get("contributors"),
        "vendor_score_flag": daily.get("score") is not None,
        "data_quality_state": "trusted",
        "provenance": {
            "raw_sleep_file": str(sleep_run.run_dir / "sleep.json"),
            "raw_sleep_sha256": sleep_run.sleep_sha256,
            "raw_daily_sleep_file": str(daily_run.run_dir / "daily_sleep.json"),
            "raw_daily_sleep_sha256": daily_run.daily_sleep_sha256,
            "source_run_id": sleep_run.run_id,
        },
    }


def _heart_record(raw: dict[str, Any], sleep_run: SourceRun) -> dict[str, Any]:
    return {
        "day": raw["day"],
        "source_sleep_record_id": raw["id"],
        "average_sleeping_heart_rate_bpm": raw.get("average_heart_rate"),
        "lowest_sleeping_heart_rate_bpm": raw.get("lowest_heart_rate"),
        "average_hrv_ms": raw.get("average_hrv"),
        "data_quality_state": "trusted",
        "provenance": {
            "raw_sleep_file": str(sleep_run.run_dir / "sleep.json"),
            "raw_sleep_sha256": sleep_run.sleep_sha256,
            "source_run_id": sleep_run.run_id,
        },
    }


def refresh(
    seed_sleep: dict[str, Any],
    seed_heart: dict[str, Any],
    runs: list[SourceRun],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not runs:
        raise ValueError("No PASS Phase C Oura source runs found")

    sleep_records, sleep_origins = _latest_records_by_id(runs, "sleep_records")
    daily_records, daily_origins = _latest_records_by_id(runs, "daily_sleep_records")
    daily_by_day, daily_origin_by_day = _daily_by_day(daily_records, daily_origins)

    long_by_day: dict[str, dict[str, Any]] = {}
    long_origin_by_day: dict[str, SourceRun] = {}
    for rid, raw in sleep_records.items():
        if raw.get("type") != "long_sleep" or not raw.get("day"):
            continue
        day = str(raw["day"])
        long_by_day[day] = raw
        long_origin_by_day[day] = sleep_origins[rid]

    matched_days = sorted(set(long_by_day) & set(daily_by_day))
    missing_primary = sorted(set(daily_by_day) - set(long_by_day))

    sleep_updates = {
        day: _sleep_record(
            long_by_day[day],
            daily_by_day[day],
            long_origin_by_day[day],
            daily_origin_by_day[day],
        )
        for day in matched_days
    }
    heart_updates = {
        day: _heart_record(long_by_day[day], long_origin_by_day[day])
        for day in matched_days
    }

    merged_sleep = {r["day"]: r for r in seed_sleep.get("records", [])}
    merged_heart = {r["day"]: r for r in seed_heart.get("records", [])}
    merged_sleep.update(sleep_updates)
    merged_heart.update(heart_updates)

    run_ids = [r.run_id for r in runs]
    common = {
        "schema_version": "0.1",
        "transformation_version": VERSION,
        "source": "Oura API V2",
        "session_selection_rule": "type == long_sleep",
        "phase_c_pass_run_count": len(runs),
        "phase_c_run_ids": run_ids,
        "phase_c_latest_run_id": run_ids[-1],
        "phase_c_latest_retrieved_at_utc": runs[-1].retrieved_at_utc,
        "selected_long_sleep_record_count": len(long_by_day),
        "source_daily_sleep_record_count": len(daily_by_day),
        "missing_primary_sleep_days": missing_primary,
        "imputation_applied": False,
        "smoothing_applied": False,
        "ai_interpretation_applied": False,
    }
    sleep_doc = {
        "metadata": {
            **common,
            "source_sleep_record_count": len(sleep_records),
            "dataset": "oura_sleep_core",
        },
        "records": [merged_sleep[d] for d in sorted(merged_sleep)],
    }
    heart_doc = {
        "metadata": {
            **common,
            "source_sleep_record_count": len(sleep_records),
            "dataset": "oura_heart_core",
        },
        "records": [merged_heart[d] for d in sorted(merged_heart)],
    }
    return sleep_doc, heart_doc


def write_atomic(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)
