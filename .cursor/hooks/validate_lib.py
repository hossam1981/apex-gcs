"""Shared helpers for APEX GCS validate hooks."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATE = ROOT / "scripts" / "validate.py"
WATCHED_SUFFIXES = {".py", ".html", ".sh", ".sdf", ".mdc", ".json"}
WATCHED_TOP = {"bridge", "files", "scripts", ".cursor"}


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()


def read_event() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def is_watched_file(file_path: str) -> bool:
    if not file_path:
        return False
    path = Path(file_path).resolve()
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return False
    if path.suffix.lower() not in WATCHED_SUFFIXES:
        return False
    parts = rel.parts
    # Do not re-enter the hook when the hook files themselves are edited.
    if len(parts) >= 2 and parts[0] == ".cursor" and parts[1] == "hooks":
        return False
    return bool(parts) and parts[0] in WATCHED_TOP


def run_validate(max_output: int = 3500) -> tuple[bool, str]:
    if not VALIDATE.is_file():
        return False, "missing scripts/validate.py — restore it, then re-run."
    python = sys.executable or "python3"
    result = subprocess.run(
        [python, str(VALIDATE)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    output = (result.stdout or "") + (result.stderr or "")
    output = output.strip() or f"validate.py exited {result.returncode} with no output"
    if len(output) > max_output:
        output = output[:max_output] + "\n…(truncated)"
    return result.returncode == 0, output
