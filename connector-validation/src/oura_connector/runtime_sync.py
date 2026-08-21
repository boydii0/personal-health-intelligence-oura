from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from .config import OuraConfig
from .runtime_api import DatasetFetchResult, default_date_range, fetch_dataset_paginated
from .runtime_auth import ensure_fresh_token
from .runtime_landing import RuntimeDataset, RuntimeLandingResult, land_runtime_run
from .runtime_tokens import ProtectedTokenStore

DATASETS = ("daily_sleep", "sleep", "daily_readiness", "daily_activity")


class RuntimeSyncError(RuntimeError):
    pass


class RuntimeUnauthorized(RuntimeSyncError):
    pass


@dataclass(frozen=True)
class RuntimeSyncResult:
    start_date: str
    end_date: str
    token_refreshed: bool
    auth_retry_used: bool
    dataset_record_counts: dict[str, int]
    landing: RuntimeLandingResult


def _fetch_with_retry(access_token: str, dataset_name: str, start_date: str, end_date: str, *, fetch_fn: Callable[..., DatasetFetchResult] = fetch_dataset_paginated, sleep_fn: Callable[[float], None] = time.sleep, max_attempts: int = 3) -> DatasetFetchResult:
    result = None
    for attempt in range(1, max_attempts + 1):
        result = fetch_fn(access_token, dataset_name, start_date, end_date, max_pages=20)
        if result.http_status == 200:
            return result
        if result.http_status == 401:
            raise RuntimeUnauthorized(f"{dataset_name}: Oura returned HTTP 401.")
        retryable = result.http_status == 0 or result.http_status == 429 or 500 <= result.http_status <= 599
        if not retryable or attempt == max_attempts:
            break
        if result.http_status == 429 and result.retry_after_seconds is not None:
            delay = min(max(result.retry_after_seconds, 1), 300)
        else:
            delay = (5, 15, 30)[min(attempt - 1, 2)]
        sleep_fn(delay)
    assert result is not None
    raise RuntimeSyncError(f"{dataset_name}: retrieval failed with status {result.http_status} after {max_attempts} attempt(s).")


def _retrieve_all(access_token: str, start_date: str, end_date: str, *, fetch_fn: Callable[..., DatasetFetchResult], sleep_fn: Callable[[float], None]) -> dict[str, DatasetFetchResult]:
    results = {}
    for name in DATASETS:
        results[name] = _fetch_with_retry(access_token, name, start_date, end_date, fetch_fn=fetch_fn, sleep_fn=sleep_fn)
    return results


def execute_sync(config: OuraConfig, store: ProtectedTokenStore, *, overlap_days: int = 7, fetch_fn: Callable[..., DatasetFetchResult] = fetch_dataset_paginated, sleep_fn: Callable[[float], None] = time.sleep, landing_fn: Callable[..., RuntimeLandingResult] = land_runtime_run, ensure_token_fn=ensure_fresh_token) -> RuntimeSyncResult:
    if overlap_days < 2 or overlap_days > 14:
        raise RuntimeSyncError("overlap_days must be between 2 and 14.")

    bundle, refreshed = ensure_token_fn(config, store)
    start_date, end_date = default_date_range(days=overlap_days)
    auth_retry_used = False
    try:
        results = _retrieve_all(bundle.access_token, start_date, end_date, fetch_fn=fetch_fn, sleep_fn=sleep_fn)
    except RuntimeUnauthorized:
        # Force one refresh, persist the rotated token, then restart all four datasets.
        bundle, _ = ensure_token_fn(config, store, force_refresh=True)
        refreshed = True
        auth_retry_used = True
        try:
            results = _retrieve_all(bundle.access_token, start_date, end_date, fetch_fn=fetch_fn, sleep_fn=sleep_fn)
        except RuntimeUnauthorized:
            raise RuntimeSyncError("Oura returned HTTP 401 after one forced token refresh. Interactive reauthorization is required.") from None

    runtime_datasets = {name: RuntimeDataset(name, result.endpoint, result.records, result.pages_fetched) for name, result in results.items()}
    landing = landing_fn(vault_root=config.vault_root, start_date=start_date, end_date=end_date, scope_granted=bundle.scope_granted, datasets=runtime_datasets)
    return RuntimeSyncResult(start_date, end_date, refreshed, auth_retry_used, {name: result.record_count for name, result in results.items()}, landing)
