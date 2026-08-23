from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

CANONICAL_RELATIVE_PATH = Path("03_Areas") / "Health" / "Personal Health Repository" / "Source Data" / "Oura"
WORKER_VERSION = "oura-phase-c-runtime-0.1"


class RuntimeLandingError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeDataset:
    dataset_name: str
    endpoint: str
    records: list
    pages_fetched: int


@dataclass(frozen=True)
class RuntimeLandingResult:
    run_id: str
    run_dir: str
    manifest_path: str
    dataset_checksums: dict[str, str]


def _validate_vault_root(vault_root: str) -> Path:
    vault_path = Path(vault_root).expanduser()
    if not vault_path.exists() or not vault_path.is_dir():
        raise RuntimeLandingError(f"VAULT_ROOT '{vault_root}' does not exist or is not a directory. Refusing to write Oura data to an unverified location.")
    return vault_path


def make_run_id(now: datetime | None = None) -> str:
    value = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return value.strftime("%Y%m%dT%H%M%S%fZ")


def local_operational_day(now: datetime | None = None) -> str:
    """Return the machine-local calendar day used only for outer-folder partitioning.

    UTC remains authoritative for run identity and retrieval provenance.  The
    outer YYYY-MM-DD folder answers which local operating day the scheduled
    collection belongs to, so an evening Central-time run after 00:00 UTC
    remains grouped with the same local day's morning run.
    """
    value = now or datetime.now().astimezone()
    if value.tzinfo is None:
        raise RuntimeLandingError("Operational-day timestamp must be timezone-aware.")
    return value.date().isoformat()


def _write_bytes_fsync(path: Path, payload: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _write_json_fsync(path: Path, payload: dict) -> None:
    raw = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")
    _write_bytes_fsync(path, raw)


def land_runtime_run(*, vault_root: str, start_date: str, end_date: str, scope_granted: str, datasets: Mapping[str, RuntimeDataset], retrieved_at_utc: str | None = None, run_id: str | None = None, operational_now: datetime | None = None) -> RuntimeLandingResult:
    """Publish one complete, append-oriented Phase C retrieval run."""
    if not datasets:
        raise RuntimeLandingError("At least one dataset is required for a runtime landing.")
    vault_path = _validate_vault_root(vault_root)
    retrieved_at = retrieved_at_utc or datetime.now(timezone.utc).isoformat()
    rid = run_id or make_run_id()
    day = local_operational_day(operational_now)
    day_dir = vault_path / CANONICAL_RELATIVE_PATH / day
    day_dir.mkdir(parents=True, exist_ok=True)
    staging = day_dir / f".staging-{rid}"
    final_dir = day_dir / rid
    if staging.exists() or final_dir.exists():
        raise RuntimeLandingError(f"Runtime run_id already exists: {rid}")

    dataset_checksums: dict[str, str] = {}
    manifest_datasets: dict[str, dict] = {}
    try:
        staging.mkdir(parents=False)
        for name in sorted(datasets):
            dataset = datasets[name]
            if name != dataset.dataset_name:
                raise RuntimeLandingError(f"Dataset map key mismatch for {name}.")
            if not name or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_" for ch in name):
                raise RuntimeLandingError(f"Invalid dataset name: {name}")

            raw_bytes = json.dumps({"data": dataset.records}, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            checksum = hashlib.sha256(raw_bytes).hexdigest()
            raw_name = f"{name}.json"
            meta_name = f"{name}.metadata.json"
            _write_bytes_fsync(staging / raw_name, raw_bytes)
            metadata = {
                "retrieved_at_utc": retrieved_at,
                "source": "Oura API V2",
                "runtime_version": WORKER_VERSION,
                "mode": "phase-c-overlap-poll",
                "dataset_name": name,
                "endpoint": dataset.endpoint,
                "requested_start_date": start_date,
                "requested_end_date": end_date,
                "scope_granted": scope_granted,
                "record_count": len(dataset.records),
                "pages_fetched": dataset.pages_fetched,
                "source_record_ids": [r.get("id") for r in dataset.records if isinstance(r, dict) and r.get("id")],
                "checksum_sha256": checksum,
                "raw_file": raw_name,
                "transformation_applied": "none — source records preserved without normalization or interpretation",
            }
            _write_json_fsync(staging / meta_name, metadata)
            dataset_checksums[name] = checksum
            manifest_datasets[name] = {"record_count": len(dataset.records), "pages_fetched": dataset.pages_fetched, "checksum_sha256": checksum, "raw_file": raw_name, "metadata_file": meta_name}

        manifest = {
            "schema_version": "0.1",
            "runtime_version": WORKER_VERSION,
            "run_id": rid,
            "status": "PASS",
            "retrieved_at_utc": retrieved_at,
            "operational_day_local": day,
            "requested_start_date": start_date,
            "requested_end_date": end_date,
            "scope_granted": scope_granted,
            "datasets": manifest_datasets,
            "secrets_written_to_vault": False,
            "normalization_executed": False,
            "scheduling_executed": False,
        }
        _write_json_fsync(staging / "run_manifest.json", manifest)
        staging.rename(final_dir)
    except Exception as exc:
        try:
            if staging.exists():
                shutil.rmtree(staging)
        except OSError:
            pass
        if isinstance(exc, RuntimeLandingError):
            raise
        raise RuntimeLandingError(f"Runtime landing failed before publication: {exc}") from None

    return RuntimeLandingResult(rid, str(final_dir), str(final_dir / "run_manifest.json"), dataset_checksums)
