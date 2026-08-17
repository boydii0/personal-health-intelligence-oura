"""Deterministic Oura Step 2 normalizer for the validated sleep/RHR/HRV core."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

VERSION = "oura-core-normalizer-0.1"

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def sec_to_min(v):
    return None if v is None else round(v / 60.0, 3)

def normalize(sleep_doc, daily_doc, sleep_checksum, daily_checksum):
    long_sleep = [r for r in sleep_doc["data"] if r.get("type") == "long_sleep"]
    daily_by_day = {r["day"]: r for r in daily_doc["data"]}
    sleep_records, heart_records = [], []

    for r in sorted(long_sleep, key=lambda x: x["day"]):
        d = daily_by_day.get(r["day"])
        sleep_records.append({
            "day": r["day"],
            "source_sleep_record_id": r["id"],
            "source_daily_sleep_record_id": d["id"] if d else None,
            "bedtime_start": r["bedtime_start"],
            "bedtime_end": r["bedtime_end"],
            "sleep_type": r["type"],
            "sleep_algorithm_version": r.get("sleep_algorithm_version"),
            "total_sleep_minutes": sec_to_min(r.get("total_sleep_duration")),
            "time_in_bed_minutes": sec_to_min(r.get("time_in_bed")),
            "awake_minutes": sec_to_min(r.get("awake_time")),
            "deep_sleep_minutes": sec_to_min(r.get("deep_sleep_duration")),
            "light_sleep_minutes": sec_to_min(r.get("light_sleep_duration")),
            "rem_sleep_minutes": sec_to_min(r.get("rem_sleep_duration")),
            "latency_minutes": sec_to_min(r.get("latency")),
            "efficiency_percent": r.get("efficiency"),
            "average_breaths_per_minute": r.get("average_breath"),
            "oura_sleep_score": d.get("score") if d else None,
            "oura_sleep_score_contributors": d.get("contributors") if d else None,
            "vendor_score_flag": True,
            "data_quality_state": "trusted" if d else "partial",
            "provenance": {
                "raw_sleep_file": "sleep.json",
                "raw_sleep_sha256": sleep_checksum,
                "raw_daily_sleep_file": "daily_sleep.json",
                "raw_daily_sleep_sha256": daily_checksum,
            },
        })
        heart_records.append({
            "day": r["day"],
            "source_sleep_record_id": r["id"],
            "average_sleeping_heart_rate_bpm": r.get("average_heart_rate"),
            "lowest_sleeping_heart_rate_bpm": r.get("lowest_heart_rate"),
            "average_hrv_ms": r.get("average_hrv"),
            "data_quality_state": "trusted" if all(
                r.get(k) is not None for k in ("average_heart_rate", "lowest_heart_rate", "average_hrv")
            ) else "partial",
            "provenance": {"raw_sleep_file": "sleep.json", "raw_sleep_sha256": sleep_checksum},
        })

    missing_primary_days = sorted(set(daily_by_day) - {r["day"] for r in long_sleep})
    meta = {
        "schema_version": "0.1",
        "transformation_version": VERSION,
        "source": "Oura API V2",
        "session_selection_rule": "type == long_sleep",
        "source_sleep_record_count": len(sleep_doc["data"]),
        "selected_long_sleep_record_count": len(long_sleep),
        "source_daily_sleep_record_count": len(daily_doc["data"]),
        "missing_primary_sleep_days": missing_primary_days,
        "imputation_applied": False,
        "smoothing_applied": False,
        "ai_interpretation_applied": False,
    }
    return (
        {"metadata": {**meta, "dataset": "oura_sleep_core"}, "records": sleep_records},
        {"metadata": {**meta, "dataset": "oura_heart_core"}, "records": heart_records},
    )

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source-dir", required=True, type=Path)
    p.add_argument("--sleep-output", required=True, type=Path)
    p.add_argument("--heart-output", required=True, type=Path)
    args = p.parse_args()

    sleep_path = args.source_dir / "sleep.json"
    daily_path = args.source_dir / "daily_sleep.json"
    sleep_meta = json.loads((args.source_dir / "sleep.metadata.json").read_text())
    daily_meta = json.loads((args.source_dir / "daily_sleep.metadata.json").read_text())

    if sha256_file(sleep_path) != sleep_meta["checksum_sha256"]:
        raise RuntimeError("sleep.json checksum does not match source metadata")
    if sha256_file(daily_path) != daily_meta["checksum_sha256"]:
        raise RuntimeError("daily_sleep.json checksum does not match source metadata")

    sleep_core, heart_core = normalize(
        json.loads(sleep_path.read_text()),
        json.loads(daily_path.read_text()),
        sleep_meta["checksum_sha256"],
        daily_meta["checksum_sha256"],
    )
    args.sleep_output.parent.mkdir(parents=True, exist_ok=True)
    args.heart_output.parent.mkdir(parents=True, exist_ok=True)
    args.sleep_output.write_text(json.dumps(sleep_core, indent=2) + "\n")
    args.heart_output.write_text(json.dumps(heart_core, indent=2) + "\n")

if __name__ == "__main__":
    main()
