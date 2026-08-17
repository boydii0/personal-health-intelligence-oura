"""
Phase 2 — one bounded Oura API V2 request.

Only implements GET /v2/usercollection/daily_sleep. No other endpoints, no
pagination auto-follow beyond reporting whether pagination was present, and
no retry/backoff (that belongs to a later, separately approved backfill
step, not this connectivity test).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta

API_BASE = "https://api.ouraring.com/v2"
DAILY_SLEEP_ENDPOINT = "/usercollection/daily_sleep"


@dataclass(frozen=True)
class ApiCallResult:
    endpoint: str
    start_date: str
    end_date: str
    http_status: int
    raw_body_bytes: bytes
    parsed: dict
    error_message: str = ""

    @property
    def records(self) -> list:
        return self.parsed.get("data", []) if self.parsed else []

    @property
    def pagination_present(self) -> bool:
        return bool(self.parsed.get("next_token")) if self.parsed else False


def default_date_range(days: int = 7) -> tuple:
    end = date.today()
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def fetch_daily_sleep(access_token: str, start_date: str, end_date: str) -> ApiCallResult:
    """access_token is used only to build the Authorization header for this
    single request. It is never logged or included in the returned result."""
    url = f"{API_BASE}{DAILY_SLEEP_ENDPOINT}?start_date={start_date}&end_date={end_date}"
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            status = response.status
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
            return ApiCallResult(
                endpoint=DAILY_SLEEP_ENDPOINT,
                start_date=start_date,
                end_date=end_date,
                http_status=status,
                raw_body_bytes=raw,
                parsed=parsed,
            )
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            parsed = {}
        return ApiCallResult(
            endpoint=DAILY_SLEEP_ENDPOINT,
            start_date=start_date,
            end_date=end_date,
            http_status=exc.code,
            raw_body_bytes=raw,
            parsed=parsed,
            error_message=f"HTTP {exc.code}: {raw.decode('utf-8', errors='replace')[:500]}",
        )
    except urllib.error.URLError as exc:
        return ApiCallResult(
            endpoint=DAILY_SLEEP_ENDPOINT,
            start_date=start_date,
            end_date=end_date,
            http_status=0,
            raw_body_bytes=b"",
            parsed={},
            error_message=f"Request failed: {exc.reason}",
        )
