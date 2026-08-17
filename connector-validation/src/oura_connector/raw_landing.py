"""
Phase 3 — land ONE raw, lossless sample under the canonical PHI repository
path. No transformation or normalization happens here.

Canonical target (relative to VAULT_ROOT):
  03_Areas/Health/Personal Health Repository/Source Data/Oura/<YYYY-MM-DD>/
    daily_sleep.json           <- exact bytes returned by the Oura API
    daily_sleep.metadata.json  <- provenance: retrieved_at, source, endpoint,
                                  requested date range, source record ids,
                                  sha256 checksum of the raw file

If the vault root does not exist or is not writable, this module raises
RawLandingError rather than inventing an alternate persistent location, per
governance. The caller is responsible for stopping and reporting the
constraint to the user.
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


def land_raw_sample(
    vault_root: str,
    endpoint: str,
    start_date: str,
    end_date: str,
    scope_granted: str,
    raw_body_bytes: bytes,
    parsed_body: dict,
) -> LandingResult:
    vault_path = Path(vault_root).expanduser()
    if not vault_path.exists() or not vault_path.is_dir():
        raise RawLandingError(
            f"VAULT_ROOT '{vault_root}' does not exist or is not a directory. "
            "Refusing to write raw data to an unverified location. Create/"
            "confirm the canonical vault root first, then re-run."
        )

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
        "raw_file": str(raw_file.name),
        "transformation_applied": "none — lossless raw landing only",
    }

    try:
        metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    except OSError as exc:
        raise RawLandingError(f"Could not write metadata file: {exc}") from None

    return LandingResult(
        raw_file_path=str(raw_file),
        metadata_file_path=str(metadata_file),
        checksum_sha256=checksum,
    )


def date_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
