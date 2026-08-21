from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class RuntimeStatusError(RuntimeError):
    pass


def write_runtime_status(runtime_dir: Path, payload: dict) -> Path:
    """Write non-PHI operational status outside AI_Vault."""
    runtime_dir = Path(runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    status_path = runtime_dir / "last_status.json"
    document = {"updated_at_utc": datetime.now(timezone.utc).isoformat(), **payload}
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix="last_status.", suffix=".tmp", dir=runtime_dir, delete=False) as handle:
            temp_path = Path(handle.name)
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, status_path)
    except OSError as exc:
        if temp_path:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise RuntimeStatusError(f"Could not write runtime status: {exc}") from None
    return status_path
