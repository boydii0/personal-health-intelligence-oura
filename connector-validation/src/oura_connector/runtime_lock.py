from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path


class RuntimeLockError(RuntimeError):
    pass


@dataclass
class RuntimeLock:
    path: Path
    stale_after_seconds: int = 7200

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        if self.path.exists():
            try:
                age = now - self.path.stat().st_mtime
            except OSError as exc:
                raise RuntimeLockError(f"Could not inspect runtime lock: {exc}") from None
            if age <= self.stale_after_seconds:
                raise RuntimeLockError(f"Another Oura runtime may already be active; lock exists at {self.path}.")
            try:
                self.path.unlink()
            except OSError as exc:
                raise RuntimeLockError(f"Could not clear stale runtime lock: {exc}") from None
        payload = json.dumps({"pid": os.getpid(), "created_at_epoch": now}).encode("utf-8")
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            raise RuntimeLockError(f"Another Oura runtime acquired the lock concurrently at {self.path}.") from None
        except OSError as exc:
            raise RuntimeLockError(f"Could not create runtime lock: {exc}") from None
        try:
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)

    def release(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False
