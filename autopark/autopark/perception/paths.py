"""Project root and timestamps for perception modules that must import without torch (roi, costmap)."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_write_json(path, value) -> None:
    """Write JSON via a temporary file + rename so readers never see a truncated file."""
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)
