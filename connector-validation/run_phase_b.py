#!/usr/bin/env python3
"""
Oura Connector Phase B — bounded multi-dataset backfill validation.

Approved purpose:
  - authenticate locally through the existing OAuth2 browser/passkey flow;
  - retrieve a bounded 30-day window for approved daily-scope datasets;
  - follow pagination with a hard page cap;
  - land each dataset separately in the canonical PHI raw repository with
    provenance + checksum metadata;
  - stop before normalization, insights, scheduling, token persistence,
    webhooks, or any Personal Health App work.

This must be run on the same computer as the browser used for Oura consent
because the redirect URI is http://localhost:8000/callback.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from oura_connector.config import ConfigError, load_config  # noqa: E402
from oura_connector.oauth_flow import OAuthError, run_authorization_code_flow  # noqa: E402
from oura_connector.oura_api import (  # noqa: E402
    PHASE_B_DATASETS,
    default_date_range,
    fetch_dataset_paginated,
)
from oura_connector.raw_landing import RawLandingError, land_raw_dataset  # noqa: E402
from oura_connector.secure_utils import SecretGuard  # noqa: E402

BACKFILL_DAYS = 30
MAX_PAGES_PER_DATASET = 20
DATASETS = (
    "daily_sleep",
    "sleep",
    "daily_readiness",
    "daily_activity",
)


def _print_header() -> None:
    print("\n" + "=" * 72)
    print("Oura Connector Phase B — bounded 30-day backfill validation")
    print("=" * 72)


def _print_dataset_result(name: str, result, landing=None) -> None:
    print(f"\n{name}")
    print(f"  endpoint: {result.endpoint}")
    print(f"  HTTP status: {result.http_status}")
    print(f"  records: {result.record_count}")
    print(f"  pages fetched: {result.pages_fetched}")
    if landing:
        print(f"  raw file: {landing.raw_file_path}")
        print(f"  metadata: {landing.metadata_file_path}")
        print("  checksum: YES")
    if result.error_message:
        print(f"  limitation: {result.error_message}")


def main() -> int:
    _print_header()

    try:
        config = load_config(PROJECT_ROOT)
    except ConfigError as exc:
        print(f"Configuration: FAIL — {exc}")
        return 1

    # Phase B deliberately remains on the validated daily scope. Expanding
    # to heartrate/workout/spo2Daily is a later scope-expansion decision.
    if config.scope != "daily":
        print("Configuration: FAIL — Phase B currently requires OURA_SCOPE=daily.")
        return 1

    try:
        tokens = run_authorization_code_flow(config)
    except OAuthError as exc:
        with SecretGuard(config.client_secret):
            print(f"OAuth: FAIL — {exc}")
        return 1

    print("OAuth: PASS")
    print(f"Granted scope: {tokens.scope_granted}")

    start_date, end_date = default_date_range(days=BACKFILL_DAYS)
    print(f"Bounded date range: {start_date} through {end_date}")
    print("Datasets: " + ", ".join(DATASETS))

    failures = []
    for dataset_name in DATASETS:
        if dataset_name not in PHASE_B_DATASETS:
            failures.append(f"{dataset_name}: not in approved dataset registry")
            continue

        with SecretGuard(tokens.access_token, tokens.refresh_token, config.client_secret):
            result = fetch_dataset_paginated(
                tokens.access_token,
                dataset_name,
                start_date,
                end_date,
                max_pages=MAX_PAGES_PER_DATASET,
            )

        if result.http_status != 200:
            _print_dataset_result(dataset_name, result)
            failures.append(f"{dataset_name}: HTTP/status {result.http_status}")
            continue

        try:
            landing = land_raw_dataset(
                vault_root=config.vault_root,
                dataset_name=dataset_name,
                endpoint=result.endpoint,
                start_date=start_date,
                end_date=end_date,
                scope_granted=tokens.scope_granted,
                records=result.records,
                pages_fetched=result.pages_fetched,
            )
        except RawLandingError as exc:
            _print_dataset_result(dataset_name, result)
            print(f"  landing: FAIL — {exc}")
            failures.append(f"{dataset_name}: raw landing failed")
            continue

        _print_dataset_result(dataset_name, result, landing)

    print("\n" + "-" * 72)
    if failures:
        print("PHASE B RESULT: PARTIAL / FAIL")
        for item in failures:
            print(f"  - {item}")
        print(
            "Do not normalize or treat this as a complete backfill. Resolve the "
            "failed dataset(s), then re-run the bounded validation."
        )
        return 1

    print("PHASE B RESULT: RETRIEVAL + RAW LANDING PASS")
    print(
        "Manual source-semantic verification is still required before the next "
        "project step. Confirm representative dates/records against Oura, with "
        "special attention to sleep-session boundaries, HRV, and resting heart "
        "rate fields in the detailed sleep dataset."
    )
    print(
        "STOP: no normalization, weekly insight generation, token persistence, "
        "incremental sync, webhook, scheduling, or app code has been executed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
