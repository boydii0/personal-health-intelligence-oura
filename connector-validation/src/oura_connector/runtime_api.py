from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from email.utils import parsedate_to_datetime

API_BASE = "https://api.ouraring.com/v2"

PHASE_C_DATASETS = {
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
    retry_after_seconds: int | None = None
    error_message: str = ""

    @property
    def records(self) -> list:
        return self.parsed.get("data", []) if self.parsed else []


@dataclass(frozen=True)
class DatasetFetchResult:
    dataset_name: str
    endpoint: str
    start_date: str
    end_date: str
    http_status: int
    records: list
    pages_fetched: int
    retry_after_seconds: int | None = None
    error_message: str = ""

    @property
    def record_count(self) -> int:
        return len(self.records)


def default_date_range(days: int = 7) -> tuple[str, str]:
    if days < 1 or days > 30:
        raise ValueError("days must be between 1 and 30")
    end = date.today()
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def _parse_retry_after(headers) -> int | None:
    if not headers:
        return None
    raw = headers.get("Retry-After")
    if not raw:
        return None
    raw = raw.strip()
    if raw.isdigit():
        return max(0, int(raw))
    try:
        when = parsedate_to_datetime(raw)
        now = parsedate_to_datetime(headers.get("Date")) if headers.get("Date") else None
        if now:
            return max(0, int((when - now).total_seconds()))
    except Exception:
        return None
    return None


def _request_json(access_token: str, endpoint: str, params: dict[str, str]) -> ApiCallResult:
    query = urllib.parse.urlencode(params)
    url = f"{API_BASE}{endpoint}?{query}" if query else f"{API_BASE}{endpoint}"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
            return ApiCallResult(endpoint, params.get("start_date", ""), params.get("end_date", ""), response.status, raw, parsed, _parse_retry_after(response.headers))
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            parsed = {}
        return ApiCallResult(endpoint, params.get("start_date", ""), params.get("end_date", ""), exc.code, raw, parsed, _parse_retry_after(exc.headers), f"HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError) as exc:
        reason = getattr(exc, "reason", "timeout/network error")
        return ApiCallResult(endpoint, params.get("start_date", ""), params.get("end_date", ""), 0, b"", {}, None, f"Request failed: {reason}")
    except json.JSONDecodeError:
        return ApiCallResult(endpoint, params.get("start_date", ""), params.get("end_date", ""), 502, b"", {}, None, "Oura returned invalid JSON.")


def fetch_dataset_paginated(access_token: str, dataset_name: str, start_date: str, end_date: str, *, max_pages: int = 20) -> DatasetFetchResult:
    if dataset_name not in PHASE_C_DATASETS:
        raise ValueError(f"Unsupported Phase C dataset '{dataset_name}'. Allowed: " + ", ".join(sorted(PHASE_C_DATASETS)))
    if max_pages < 1 or max_pages > 100:
        raise ValueError("max_pages must be between 1 and 100")

    endpoint = PHASE_C_DATASETS[dataset_name]
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
            return DatasetFetchResult(dataset_name, endpoint, start_date, end_date, result.http_status, records, pages, result.retry_after_seconds, result.error_message or "Non-200 response.")
        records.extend(result.records)
        next_token = result.parsed.get("next_token") or ""
        if not next_token:
            break

    if next_token:
        return DatasetFetchResult(dataset_name, endpoint, start_date, end_date, 206, records, pages, None, f"Pagination stopped at configured max_pages={max_pages}; dataset is incomplete.")
    return DatasetFetchResult(dataset_name, endpoint, start_date, end_date, 200, records, pages)
