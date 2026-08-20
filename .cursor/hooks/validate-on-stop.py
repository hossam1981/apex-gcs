#!/usr/bin/env python3
"""Stop hook: if validate.py fails, keep the agent in a fix loop."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_lib import emit, read_event, run_validate


def main() -> int:
    event = read_event()
    status = str(event.get("status") or "")
    loop_count = int(event.get("loop_count") or 0)

    if status in {"aborted", "error"}:
        emit({})
        return 0

    ok, output = run_validate()
    if ok:
        emit({})
        return 0

    remaining = max(0, 3 - loop_count - 1)
    extra = (
        "This is the last auto-retry. Fix the failures and re-run the validator."
        if remaining == 0
        else f"Auto-retry remaining after this: {remaining}."
    )
    emit(
        {
            "followup_message": (
                "VALIDATE FAIL — do not stop. The code-not-breaking check failed.\n\n"
                f"{output}\n\n"
                "Fix the root cause, then run: python3 scripts/validate.py\n"
                "Only finish when it prints VALIDATE PASS.\n"
                "If the fail is [orphan] or [placeholder]: do NOT delete the function to go green. "
                "Tell the user what it might wire to, and ASK wire vs delete.\n"
                f"{extra}"
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
