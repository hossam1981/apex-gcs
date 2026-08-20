#!/usr/bin/env python3
"""
APEX GCS — fast “did we break the app?” checks.

Run from anywhere:
  python3 scripts/validate.py

Exit 0 = pass. Exit 1 = fail (prints every problem).
Does NOT start SITL, Gazebo, or a real drone.
"""
from __future__ import annotations

import ast
import py_compile
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
from code_graph import check_paths  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "bridge"
FILES = ROOT / "files"
COCKPIT = FILES / "drone-cockpit.html"
BRIDGE_PY = BRIDGE / "bridge.py"

REQUIRED_HTML_IDS = (
    "arm-pill",
    "arm-btn",
    "mode-pill",
    "waypoint-list",
    "wp-count",
)
REQUIRED_JS_FNS = (
    "connectDrone",
    "sendCmd",
    "ingestMav",
    "toggleArm",
    "takeoff",
    "rtl",
    "emergencyStop",
    "addWaypoint",
    "planRoute",
)
REQUIRED_CMDS = (
    "ARM",
    "DISARM",
    "TAKEOFF",
    "LAND",
    "RTL",
    "ESTOP",
    "SET_MODE",
    "GOTO",
    "VELOCITY",
    "START_MISSION",
    "SET_GEOFENCE",
    "CLEAR_GEOFENCE",
)

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


class IdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name == "id" and value:
                self.ids.add(value)


def check_python_files() -> None:
    py_files = sorted(BRIDGE.glob("*.py"))
    if not py_files:
        fail(f"no Python files under {BRIDGE}")
        return
    for path in py_files:
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as e:
            fail(f"{path.relative_to(ROOT)}: cannot read ({e})")
            continue
        try:
            ast.parse(source, filename=str(path))
        except SyntaxError as e:
            fail(f"{path.relative_to(ROOT)}:{e.lineno}: syntax error: {e.msg}")
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as e:
            fail(f"{path.relative_to(ROOT)}: compile failed: {e.msg}")


def check_shell_scripts() -> None:
    for path in sorted(BRIDGE.glob("*.sh")):
        try:
            result = subprocess.run(
                ["bash", "-n", str(path)],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            fail("bash not found — cannot syntax-check .sh files")
            return
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip() or "bash -n failed"
            fail(f"{path.relative_to(ROOT)}: {detail}")


def check_sdf_worlds() -> None:
    worlds = sorted((BRIDGE / "worlds").glob("*.sdf"))
    if not worlds:
        fail("missing bridge/worlds/*.sdf")
        return
    for path in worlds:
        try:
            ET.parse(path)
        except ET.ParseError as e:
            fail(f"{path.relative_to(ROOT)}: invalid SDF/XML: {e}")


def check_cockpit_html() -> str:
    if not COCKPIT.is_file():
        fail("missing files/drone-cockpit.html")
        return ""
    html = COCKPIT.read_text(encoding="utf-8", errors="replace")
    parser = IdCollector()
    try:
        parser.feed(html)
    except Exception as e:  # noqa: BLE001 — report parse issues, keep going
        fail(f"files/drone-cockpit.html: HTML parse error: {e}")
    for html_id in REQUIRED_HTML_IDS:
        if html_id not in parser.ids:
            fail(f"files/drone-cockpit.html: missing required id='{html_id}'")
    for fn in REQUIRED_JS_FNS:
        if not re.search(rf"function\s+{re.escape(fn)}\s*\(", html):
            fail(f"files/drone-cockpit.html: missing JS function {fn}()")
    index = FILES / "index.html"
    if not index.is_file():
        fail("missing files/index.html")
    return html


def extract_cockpit_cmds(html: str) -> set[str]:
    found: set[str] = set()
    for match in re.finditer(r"cmd\s*:\s*'([A-Z_]+)'", html):
        found.add(match.group(1))
    for match in re.finditer(r"cmd\s*:\s*arming\s*\?\s*'([A-Z_]+)'\s*:\s*'([A-Z_]+)'", html):
        found.update(match.groups())
    return found


def extract_bridge_cmds(source: str) -> set[str]:
    return set(re.findall(r'cmd\s*==\s*"([A-Z_]+)"', source))


def check_placeholders_and_orphans() -> None:
    """Stubs, broken onclick chains, and unused functions."""
    targets = sorted(BRIDGE.glob("*.py")) + sorted(FILES.glob("*.html"))
    for finding in check_paths(targets, ROOT):
        fail(finding.format())


def check_command_contract(html: str) -> None:
    if not BRIDGE_PY.is_file():
        fail("missing bridge/bridge.py")
        return
    source = BRIDGE_PY.read_text(encoding="utf-8")
    bridge_cmds = extract_bridge_cmds(source)
    cockpit_cmds = extract_cockpit_cmds(html) if html else set()
    for cmd in REQUIRED_CMDS:
        if cmd not in bridge_cmds:
            fail(f"bridge/bridge.py: missing handler for cmd '{cmd}'")
        if html and cmd not in cockpit_cmds:
            fail(f"files/drone-cockpit.html: never sends cmd '{cmd}'")


def main() -> int:
    if not ROOT.joinpath("bridge").is_dir() or not ROOT.joinpath("files").is_dir():
        fail(f"expected bridge/ and files/ under {ROOT}")
    else:
        check_python_files()
        check_shell_scripts()
        check_sdf_worlds()
        html = check_cockpit_html()
        check_command_contract(html)
        check_placeholders_and_orphans()

    if errors:
        print("VALIDATE FAIL")
        for item in errors:
            print(f"  - {item}")
        print(f"\n{len(errors)} problem(s). Fix these, then re-run: python3 scripts/validate.py")
        if any("[orphan]" in item or "[placeholder]" in item for item in errors):
            print("Orphan/placeholder: report what it might wire to, then ASK before deleting.")
        return 1

    print("VALIDATE PASS")
    print("  syntax, cockpit IDs, MAVLink cmds, placeholders, orphans, handler sequence")
    return 0


if __name__ == "__main__":
    sys.exit(main())
