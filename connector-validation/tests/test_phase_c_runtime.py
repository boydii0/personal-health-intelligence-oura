from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oura_connector.config import OuraConfig
from oura_connector.oauth_flow import TokenResult
from oura_connector.runtime_api import DatasetFetchResult
from oura_connector.runtime_auth import ensure_fresh_token
from oura_connector.runtime_landing import RuntimeDataset, land_runtime_run
from oura_connector.runtime_lock import RuntimeLock, RuntimeLockError
from oura_connector.runtime_sync import execute_sync
from oura_connector.runtime_tokens import ProtectedTokenStore, TokenBundle, TokenStoreError


def fake_store(path: Path) -> ProtectedTokenStore:
    return ProtectedTokenStore(path, protect=lambda b: b[::-1], unprotect=lambda b: b[::-1])


def cfg(vault_root: str) -> OuraConfig:
    return OuraConfig(client_id="client", client_secret="secret", redirect_uri="http://localhost:8000/callback", scope="daily", vault_root=vault_root)


class PhaseCTests(unittest.TestCase):
    def test_token_store_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            store = fake_store(Path(td) / "tokens.dat")
            bundle = TokenBundle("a", "r", "2030-01-01T00:00:00+00:00", "extapi:daily")
            store.save(bundle)
            self.assertEqual(store.load(), bundle)
            self.assertNotIn(b'"access_token":"a"', (Path(td) / "tokens.dat").read_bytes())

    def test_token_store_rejects_incomplete_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            store = fake_store(Path(td) / "tokens.dat")
            with self.assertRaises(TokenStoreError):
                store.save(TokenBundle("", "r", "2030-01-01T00:00:00+00:00", "daily"))

    def test_ensure_fresh_token_does_not_refresh_valid_token(self):
        with tempfile.TemporaryDirectory() as td:
            store = fake_store(Path(td) / "tokens.dat")
            now = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)
            store.save(TokenBundle("a1", "r1", (now + timedelta(hours=1)).isoformat(), "extapi:daily"))
            calls = []
            bundle, refreshed = ensure_fresh_token(cfg(td), store, now=now, refresh_fn=lambda *_: calls.append(True))
            self.assertFalse(refreshed)
            self.assertEqual(bundle.access_token, "a1")
            self.assertEqual(calls, [])

    def test_refresh_rotation_is_persisted_immediately(self):
        with tempfile.TemporaryDirectory() as td:
            store = fake_store(Path(td) / "tokens.dat")
            now = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)
            store.save(TokenBundle("old-access", "old-refresh", (now - timedelta(seconds=1)).isoformat(), "extapi:daily"))

            def refresh(_config, refresh_token):
                self.assertEqual(refresh_token, "old-refresh")
                return TokenResult("new-access", "new-refresh", 3600, "extapi:daily")

            bundle, refreshed = ensure_fresh_token(cfg(td), store, now=now, refresh_fn=refresh)
            self.assertTrue(refreshed)
            self.assertEqual(bundle.refresh_token, "new-refresh")
            self.assertEqual(store.load().refresh_token, "new-refresh")

    def test_append_oriented_landing_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            datasets = {"daily_sleep": RuntimeDataset("daily_sleep", "/usercollection/daily_sleep", [{"id": "1"}], 1)}
            one = land_runtime_run(vault_root=td, start_date="2026-08-15", end_date="2026-08-21", scope_granted="extapi:daily", datasets=datasets, retrieved_at_utc="2026-08-21T10:00:00+00:00", run_id="run-one")
            two = land_runtime_run(vault_root=td, start_date="2026-08-15", end_date="2026-08-21", scope_granted="extapi:daily", datasets=datasets, retrieved_at_utc="2026-08-21T20:00:00+00:00", run_id="run-two")
            self.assertNotEqual(one.run_dir, two.run_dir)
            self.assertTrue(Path(one.run_dir, "daily_sleep.json").exists())
            self.assertTrue(Path(two.run_dir, "daily_sleep.json").exists())
            manifest = json.loads(Path(two.manifest_path).read_text())
            self.assertEqual(manifest["status"], "PASS")
            self.assertFalse(manifest["secrets_written_to_vault"])

    def test_runtime_lock_blocks_overlap_and_recovers_stale_lock(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "runtime.lock"
            first = RuntimeLock(path, stale_after_seconds=10)
            first.acquire()
            with self.assertRaises(RuntimeLockError):
                RuntimeLock(path, stale_after_seconds=10).acquire()
            first.release()
            path.write_text("stale")
            old = time.time() - 100
            os.utime(path, (old, old))
            second = RuntimeLock(path, stale_after_seconds=10)
            second.acquire()
            self.assertTrue(path.exists())
            second.release()

    def test_sync_honors_retry_after_then_succeeds(self):
        with tempfile.TemporaryDirectory() as td:
            store = fake_store(Path(td) / "tokens.dat")
            store.save(TokenBundle("access", "refresh", "2030-01-01T00:00:00+00:00", "extapi:daily"))
            attempts = {}
            sleeps = []

            def fetch(access, name, start, end, max_pages=20):
                attempts[name] = attempts.get(name, 0) + 1
                if name == "daily_sleep" and attempts[name] == 1:
                    return DatasetFetchResult(name, "/x", start, end, 429, [], 1, 2, "HTTP 429")
                return DatasetFetchResult(name, "/x", start, end, 200, [{"id": name}], 1)

            captured = {}
            def landing(**kwargs):
                captured.update(kwargs)
                class L:
                    run_id = "r"; run_dir = "d"; manifest_path = "m"; dataset_checksums = {}
                return L()

            result = execute_sync(cfg(td), store, fetch_fn=fetch, sleep_fn=lambda s: sleeps.append(s), landing_fn=landing)
            self.assertEqual(sleeps, [2])
            self.assertEqual(result.dataset_record_counts["daily_sleep"], 1)
            self.assertEqual(set(captured["datasets"]), {"daily_sleep", "sleep", "daily_readiness", "daily_activity"})

    def test_sync_401_forces_one_refresh_and_restarts_complete_run(self):
        with tempfile.TemporaryDirectory() as td:
            store = fake_store(Path(td) / "tokens.dat")
            store.save(TokenBundle("a1", "r1", "2030-01-01T00:00:00+00:00", "extapi:daily"))
            fetch_calls = []
            ensure_calls = []

            def ensure(_config, _store, force_refresh=False):
                ensure_calls.append(force_refresh)
                token = "a2" if force_refresh else "a1"
                return TokenBundle(token, "r2", "2030-01-01T00:00:00+00:00", "extapi:daily"), force_refresh

            def fetch(access, name, start, end, max_pages=20):
                fetch_calls.append((access, name))
                if access == "a1" and name == "sleep":
                    return DatasetFetchResult(name, "/x", start, end, 401, [], 1, None, "HTTP 401")
                return DatasetFetchResult(name, "/x", start, end, 200, [{"id": name}], 1)

            landed = []
            def landing(**kwargs):
                landed.append(kwargs)
                class L:
                    run_id = "r"; run_dir = "d"; manifest_path = "m"; dataset_checksums = {}
                return L()

            result = execute_sync(cfg(td), store, fetch_fn=fetch, sleep_fn=lambda _: None, landing_fn=landing, ensure_token_fn=ensure)
            self.assertTrue(result.auth_retry_used)
            self.assertEqual(ensure_calls, [False, True])
            self.assertEqual(len(landed), 1)
            self.assertIn(("a2", "daily_sleep"), fetch_calls)
            self.assertIn(("a2", "sleep"), fetch_calls)


if __name__ == "__main__":
    unittest.main()
