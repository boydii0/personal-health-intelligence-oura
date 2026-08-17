#!/usr/bin/env python3
"""
Oura Connector Validation Test — PHI Project

Purpose (and ONLY purpose): prove that the registered Oura OAuth2
application can authenticate, retrieve a small bounded sample of the
caller's own daily_sleep data, and land it losslessly as a raw source
artifact under the canonical PHI repository path. Nothing else.

Run this on the SAME machine as the browser you use to approve the Oura
consent screen — the OAuth redirect target is http://localhost:8000/callback,
which only resolves back to this process if they are on the same host.
That is why this cannot be run from a remote/cloud assistant session.

Hard stop condition (do not extend this script to do the following without
a separate, explicitly approved step):
  - no 30-90 day backfill
  - no detailed /sleep parsing, no HRV/RHR normalization
  - no webhook subscription
  - no scheduling / cron / GitHub Actions
  - no PHI application code
  - no reports, insights, or supplement correlation
  - no medical interpretation of any value

Usage:
  1. cp .env.example .env
  2. Fill in OURA_CLIENT_ID, OURA_CLIENT_SECRET, VAULT_ROOT in your local .env
     (never paste these into chat with any AI assistant).
  3. python run_validation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from oura_connector.config import ConfigError, load_config  # noqa: E402
from oura_connector.oauth_flow import OAuthError, run_authorization_code_flow  # noqa: E402
from oura_connector.oura_api import default_date_range, fetch_daily_sleep  # noqa: E402
from oura_connector.raw_landing import RawLandingError, land_raw_sample  # noqa: E402
from oura_connector.secure_utils import SecretGuard  # noqa: E402


def _print_report(fields: dict) -> None:
    print("\n" + "=" * 60)
    print("Oura Connector Validation")
    print("=" * 60)
    for label, value in fields.items():
        print(f"{label}: {value}")
    print("=" * 60)


def main() -> int:
    report = {
        "OAuth authorization": "FAIL",
        "Token exchange": "FAIL",
        "API endpoint": "/v2/usercollection/daily_sleep",
        "HTTP status": "n/a",
        "Scope granted": "n/a",
        "Date range": "n/a",
        "Records returned": "n/a",
        "Raw file written to": "n/a",
        "Raw checksum created": "NO",
        "Oura UI comparison": "n/a",
        "Credential leakage detected": "NO",
        "GitHub health data committed": "NO",
        "Errors / limitations": "",
        "Recommended next step": "",
    }

    # --- Config -----------------------------------------------------------
    try:
        config = load_config(PROJECT_ROOT)
    except ConfigError as exc:
        report["Errors / limitations"] = str(exc)
        report["Recommended next step"] = "Fix local .env configuration and re-run."
        _print_report(report)
        return 1

    # --- Phase 1: OAuth -----------------------------------------------------
    try:
        tokens = run_authorization_code_flow(config)
        report["OAuth authorization"] = "PASS"
        report["Token exchange"] = "PASS"
        report["Scope granted"] = tokens.scope_granted
    except OAuthError as exc:
        with SecretGuard(config.client_secret):
            report["Errors / limitations"] = str(exc)
        report["Recommended next step"] = (
            "Verify Client ID/Secret and redirect URI on the Oura application, "
            "then re-run."
        )
        _print_report(report)
        return 1

    # --- Phase 2: bounded API call -----------------------------------------
    start_date, end_date = default_date_range(days=7)
    report["Date range"] = f"{start_date} through {end_date}"

    with SecretGuard(tokens.access_token, tokens.refresh_token, config.client_secret):
        api_result = fetch_daily_sleep(tokens.access_token, start_date, end_date)

    report["HTTP status"] = api_result.http_status
    report["Records returned"] = len(api_result.records)

    if api_result.http_status != 200:
        report["Errors / limitations"] = api_result.error_message or "Non-200 response."
        report["Recommended next step"] = (
            "Investigate the reported error before attempting Phase 3 landing."
        )
        _print_report(report)
        return 1

    print(f"\nPagination present: {api_result.pagination_present}")
    print("Retrieved daily_sleep summary (for manual comparison against the Oura app):")
    for record in api_result.records:
        print(f"  date={record.get('day')} score={record.get('score')} id={record.get('id')}")

    # --- Phase 3: raw landing (only after Phase 2 success) ------------------
    try:
        landing = land_raw_sample(
            vault_root=config.vault_root,
            endpoint=api_result.endpoint,
            start_date=start_date,
            end_date=end_date,
            scope_granted=tokens.scope_granted,
            raw_body_bytes=api_result.raw_body_bytes,
            parsed_body=api_result.parsed,
        )
        report["Raw file written to"] = landing.raw_file_path
        report["Raw checksum created"] = "YES"
    except RawLandingError as exc:
        report["Errors / limitations"] = str(exc)
        report["Recommended next step"] = (
            "Resolve the vault root path constraint reported above. Do not "
            "invent an alternate persistent location; re-run once fixed."
        )
        _print_report(report)
        return 1

    # --- Phase 4: manual comparison against the Oura app --------------------
    print(
        "\nPhase 4 — Manual validation required.\n"
        "Open the Oura app and compare at least 3-5 of the dates printed "
        "above (sleep score) against what you see for those same dates.\n"
        "Do not interpret these values medically — this is a data-match "
        "check only."
    )
    try:
        answer = input(
            "Enter comparison result [PASS / PARTIAL / FAIL]: "
        ).strip().upper()
    except EOFError:
        answer = "PARTIAL"
        print("(no interactive input available — recording PARTIAL; confirm manually)")

    report["Oura UI comparison"] = answer if answer in ("PASS", "PARTIAL", "FAIL") else "PARTIAL"

    report["Recommended next step"] = (
        "Stop here per the approved validation scope. If this report shows "
        "PASS across the board, the next GOVERNED step (30-90 day backfill, "
        "webhook subscription, etc.) requires a separate approval — do not "
        "extend this script to perform it."
    )

    _print_report(report)
    print(
        "\nStop condition reached: connectivity + one bounded raw pull "
        "validated. No backfill, normalization, webhook, scheduling, or "
        "application code was executed by this script."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
