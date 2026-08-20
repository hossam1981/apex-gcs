#!/usr/bin/env python3
"""After each Agent/Tab file edit, run the project validator and inject failures."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_lib import emit, is_watched_file, read_event, run_validate


def main() -> int:
    event = read_event()
    file_path = str(event.get("file_path") or "")
    if not is_watched_file(file_path):
        emit({})
        return 0

    ok, output = run_validate(max_output=2000)
    if ok:
        emit({})
        return 0

    emit(
        {
            "additional_context": (
                "VALIDATE FAIL after this file edit. Do not continue as if the app is fine.\n"
                f"File: {file_path}\n\n"
                f"{output}\n\n"
                "Fix the failure now, then the next edit will re-run python3 scripts/validate.py.\n"
                "If this is [orphan] or [placeholder]: do NOT delete the function. ASK the user wire vs delete."
            )
        }
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        emit({})
        raise SystemExit(0)
