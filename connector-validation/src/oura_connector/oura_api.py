"""
Oura API V2 helpers for bounded connector validation.

Phase A keeps the original 7-day daily_sleep helper. Phase B adds a bounded,
paginated date-range fetch for the approved daily-scope datasets only:
daily_sleep, sleep, daily_readiness, and daily_activity.

No token persistence, normalization, webhooks, scheduling, or medical
interpretation is implemented here.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta

API_BASE = "https://api.ouraring.com/v2"
DAILY_SLEEP_ENDPOINT = "/usercollection/daily_sleep"

PHASE_B_DATASETS = {
    "daily_sleep": "/usercollection/daily_sleep",
    "sleep": "/usercollection/sleep",
    "daily_readiness": "/usercollection/daily_readiness",
    "daily_activity": "/usercollection/daily_activity",
}


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


@dataclass(frozen=True)
class DatasetFetchResult:
    dataset_name: str
    endpoint: str
    start_date: str
    end_date: str
    http_status: int
    records: list
    pages_fetched: int
    error_message: str = ""

    @property
    def record_count(self) -> int:
        return len(self.records)


def default_date_range(days: int = 7) -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def _request_json(access_token: str, endpoint: str, params: dict[str, str]) -> ApiCallResult:
    query = urllib.parse.urlencode(params)
    url = f"{API_BASE}{endpoint}?{query}" if query else f"{API_BASE}{endpoint}"
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
                endpoint=endpoint,
                start_date=params.get("start_date", ""),
                end_date=params.get("end_date", ""),
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
            endpoint=endpoint,
            start_date=params.get("start_date", ""),
            end_date=params.get("end_date", ""),
            http_status=exc.code,
            raw_body_bytes=raw,
            parsed=parsed,
            error_message=f"HTTP {exc.code}: {raw.decode('utf-8', errors='replace')[:500]}",
        )
    except urllib.error.URLError as exc:
        return ApiCallResult(
            endpoint=endpoint,
            start_date=params.get("start_date", ""),
            end_date=params.get("end_date", ""),
            http_status=0,
            raw_body_bytes=b"",
            parsed={},
            error_message=f"Request failed: {exc.reason}",
        )


def fetch_daily_sleep(access_token: str, start_date: str, end_date: str) -> ApiCallResult:
    """Phase A compatibility helper: one bounded daily_sleep request."""
    return _request_json(
        access_token,
        DAILY_SLEEP_ENDPOINT,
        {"start_date": start_date, "end_date": end_date},
    )


def fetch_dataset_paginated(
    access_token: str,
    dataset_name: str,
    start_date: str,
    end_date: str,
    *,
    max_pages: int = 20,
) -> DatasetFetchResult:
    """Fetch one approved Phase B dataset across a bounded date range.

    Pagination is followed only up to max_pages. The result is an in-memory
    aggregate; the caller is responsible for lossless source landing.
    """
    if dataset_name not in PHASE_B_DATASETS:
        raise ValueError(
            f"Unsupported Phase B dataset '{dataset_name}'. Allowed: "
            + ", ".join(sorted(PHASE_B_DATASETS))
        )
    if max_pages < 1 or max_pages > 100:
        raise ValueError("max_pages must be between 1 and 100")

    endpoint = PHASE_B_DATASETS[dataset_name]
    records: list = []
    next_token = ""
    pages = 0

    while pages < max_pages:
        params = {"start_date": start_date, "end_date": end_date}
        if next_token:
            params["next_token"] = next_token
        result = _request_json(access_token, endpoint, params)
        pages += 1

        if result.http_status != 200:
            return DatasetFetchResult(
                dataset_name=dataset_name,
                endpoint=endpoint,
                start_date=start_date,
                end_date=end_date,
                http_status=result.http_status,
                records=records,
                pages_fetched=pages,
                error_message=result.error_message or "Non-200 response.",
            )

        records.extend(result.records)
        next_token = result.parsed.get("next_token") or ""
        if not next_token:
            break

    if next_token:
        return DatasetFetchResult(
            dataset_name=dataset_name,
            endpoint=endpoint,
            start_date=start_date,
            end_date=end_date,
            http_status=206,
            records=records,
            pages_fetched=pages,
            error_message=(
                f"Pagination stopped at configured max_pages={max_pages}; "
                "dataset is incomplete and must not be treated as a full backfill."
            ),
        )

    return DatasetFetchResult(
        dataset_name=dataset_name,
        endpoint=endpoint,
        start_date=start_date,
        end_date=end_date,
        http_status=200,
        records=records,
        pages_fetched=pages,
    )
