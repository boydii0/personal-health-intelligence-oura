"""
Raw, lossless landing helpers for Oura connector validation.

Canonical target (relative to VAULT_ROOT):
  03_Areas/Health/Personal Health Repository/Source Data/Oura/<YYYY-MM-DD>/

Phase A writes daily_sleep.json + metadata. Phase B generalizes this to one
raw JSON + metadata sidecar per approved dataset while preserving the same
canonical path, checksum, provenance, and no-transformation guarantees.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CANONICAL_RELATIVE_PATH = Path("03_Areas") / "Health" / "Personal Health Repository" / "Source Data" / "Oura"


class RawLandingError(RuntimeError):
    pass


@dataclass(frozen=True)
class LandingResult:
    raw_file_path: str
    metadata_file_path: str
    checksum_sha256: str


def _extract_record_ids(parsed_body: dict) -> list:
    ids = []
    for record in parsed_body.get("data", []) if parsed_body else []:
        record_id = record.get("id")
        if record_id:
            ids.append(record_id)
    return ids


def _validate_vault_root(vault_root: str) -> Path:
    vault_path = Path(vault_root).expanduser()
    if not vault_path.exists() or not vault_path.is_dir():
        raise RawLandingError(
            f"VAULT_ROOT '{vault_root}' does not exist or is not a directory. "
            "Refusing to write raw data to an unverified location. Create/"
            "confirm the canonical vault root first, then re-run."
        )
    return vault_path


def land_raw_dataset(
    vault_root: str,
    dataset_name: str,
    endpoint: str,
    start_date: str,
    end_date: str,
    scope_granted: str,
    records: list,
    pages_fetched: int,
) -> LandingResult:
    """Land an aggregated Phase B dataset as a lossless JSON representation.

    The source records are not normalized or interpreted. The JSON envelope is
    intentionally simple and deterministic so checksums and reprocessing remain
    straightforward.
    """
    if not dataset_name or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_" for ch in dataset_name):
        raise RawLandingError("dataset_name must use lowercase letters, digits, or underscore only")

    vault_path = _validate_vault_root(vault_root)
    target_dir = vault_path / CANONICAL_RELATIVE_PATH / date_stamp()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RawLandingError(
            f"Could not create canonical landing folder under VAULT_ROOT: {exc}"
        ) from None

    raw_file = target_dir / f"{dataset_name}.json"
    metadata_file = target_dir / f"{dataset_name}.metadata.json"
    envelope = {"data": records}
    raw_body_bytes = json.dumps(envelope, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    try:
        raw_file.write_bytes(raw_body_bytes)
    except OSError as exc:
        raise RawLandingError(f"Could not write raw response file: {exc}") from None

    checksum = hashlib.sha256(raw_body_bytes).hexdigest()
    metadata = {
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source": "Oura API V2",
        "dataset_name": dataset_name,
        "endpoint": endpoint,
        "requested_start_date": start_date,
        "requested_end_date": end_date,
        "scope_granted": scope_granted,
        "source_record_ids": [r.get("id") for r in records if isinstance(r, dict) and r.get("id")],
        "record_count": len(records),
        "pages_fetched": pages_fetched,
        "checksum_sha256": checksum,
        "raw_file": raw_file.name,
        "transformation_applied": "none — source records preserved without normalization or interpretation",
    }

    try:
        metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    except OSError as exc:
        raise RawLandingError(f"Could not write metadata file: {exc}") from None

    return LandingResult(str(raw_file), str(metadata_file), checksum)


def land_raw_sample(
    vault_root: str,
    endpoint: str,
    start_date: str,
    end_date: str,
    scope_granted: str,
    raw_body_bytes: bytes,
    parsed_body: dict,
) -> LandingResult:
    """Phase A compatibility path preserving exact raw response bytes."""
    vault_path = _validate_vault_root(vault_root)
    target_dir = vault_path / CANONICAL_RELATIVE_PATH / date_stamp()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RawLandingError(
            f"Could not create canonical landing folder under VAULT_ROOT: {exc}"
        ) from None

    raw_file = target_dir / "daily_sleep.json"
    metadata_file = target_dir / "daily_sleep.metadata.json"
    try:
        raw_file.write_bytes(raw_body_bytes)
    except OSError as exc:
        raise RawLandingError(f"Could not write raw response file: {exc}") from None

    checksum = hashlib.sha256(raw_body_bytes).hexdigest()
    metadata = {
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source": "Oura API V2",
        "endpoint": endpoint,
        "requested_start_date": start_date,
        "requested_end_date": end_date,
        "scope_granted": scope_granted,
        "source_record_ids": _extract_record_ids(parsed_body),
        "record_count": len(parsed_body.get("data", [])) if parsed_body else 0,
        "checksum_sha256": checksum,
        "raw_file": raw_file.name,
        "transformation_applied": "none — lossless raw landing only",
    }
    try:
        metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    except OSError as exc:
        raise RawLandingError(f"Could not write metadata file: {exc}") from None

    return LandingResult(str(raw_file), str(metadata_file), checksum)


def date_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
