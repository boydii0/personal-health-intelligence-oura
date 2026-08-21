from __future__ import annotations

import ctypes
import json
import os
import tempfile
from ctypes import wintypes
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class TokenBundle:
    access_token: str
    refresh_token: str
    expires_at_utc: str
    scope_granted: str

    def expires_at(self) -> datetime:
        value = self.expires_at_utc
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class TokenStoreError(RuntimeError):
    pass


class ProtectedTokenStore:
    """Atomic protected token store. Production uses Windows DPAPI."""

    def __init__(self, path: Path, protect: Callable[[bytes], bytes], unprotect: Callable[[bytes], bytes]) -> None:
        self.path = Path(path)
        self._protect = protect
        self._unprotect = unprotect

    def exists(self) -> bool:
        return self.path.exists()

    def save(self, bundle: TokenBundle) -> None:
        if not bundle.access_token or not bundle.refresh_token:
            raise TokenStoreError("Refusing to persist an incomplete OAuth token bundle.")
        payload = json.dumps(asdict(bundle), separators=(",", ":"), sort_keys=True).encode("utf-8")
        protected = self._protect(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent, delete=False) as handle:
                temp_path = Path(handle.name)
                handle.write(protected)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        except OSError as exc:
            if temp_path:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise TokenStoreError(f"Could not atomically persist OAuth tokens: {exc}") from None

    def load(self) -> TokenBundle:
        if not self.path.exists():
            raise TokenStoreError("No persisted Oura runtime token bundle exists. Run Phase C authorization first.")
        try:
            protected = self.path.read_bytes()
            payload = self._unprotect(protected)
            data = json.loads(payload.decode("utf-8"))
            bundle = TokenBundle(**data)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise TokenStoreError(f"Could not load persisted OAuth token bundle: {exc}") from None
        if not bundle.access_token or not bundle.refresh_token:
            raise TokenStoreError("Persisted OAuth token bundle is incomplete.")
        return bundle


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob_from_bytes(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    blob = _DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _dpapi_protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise TokenStoreError("Windows DPAPI token storage is available only on Windows.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(_DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DATA_BLOB)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    in_blob, _buffer = _blob_from_bytes(data)
    out_blob = _DATA_BLOB()
    ok = crypt32.CryptProtectData(ctypes.byref(in_blob), "PHI Oura Runtime", None, None, None, 0x1, ctypes.byref(out_blob))
    if not ok:
        raise TokenStoreError("Windows DPAPI failed to protect OAuth token data.")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out_blob.pbData, wintypes.HLOCAL))


def _dpapi_unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise TokenStoreError("Windows DPAPI token storage is available only on Windows.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DATA_BLOB)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    in_blob, _buffer = _blob_from_bytes(data)
    out_blob = _DATA_BLOB()
    ok = crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0x1, ctypes.byref(out_blob))
    if not ok:
        raise TokenStoreError("Windows DPAPI failed to unprotect OAuth token data.")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out_blob.pbData, wintypes.HLOCAL))


def default_runtime_dir() -> Path:
    override = os.environ.get("OURA_RUNTIME_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    if os.name != "nt":
        raise TokenStoreError("Phase C production token persistence requires Windows DPAPI.")
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        raise TokenStoreError("LOCALAPPDATA is unavailable; cannot determine secure runtime directory.")
    return Path(local_app_data) / "PHI" / "OuraRuntime"


def default_windows_token_store() -> ProtectedTokenStore:
    if os.name != "nt":
        raise TokenStoreError("Phase C production token persistence requires Windows.")
    return ProtectedTokenStore(default_runtime_dir() / "tokens.dat", protect=_dpapi_protect, unprotect=_dpapi_unprotect)
