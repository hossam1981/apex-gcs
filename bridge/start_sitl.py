"""
APEX GCS — Start ArduPilot SITL + Bridge in one command
=========================================================
Run:  python3 start_sitl.py

What it does:
  1. Downloads the ArduCopter SITL binary (first run only, ~10 MB)
  2. Launches SITL at CVS HQ New York (40.7128, -74.0060)
  3. Waits for SITL TCP port 5760 to open
  4. Starts bridge.py connected to that SITL

Then open the cockpit in Chrome:
  http://localhost:5500/drone-cockpit.html

The cockpit's WebSocket already points to ws://192.168.4.1:5000 (Pi).
For SITL on your Mac you need to update the WS_URL in the cockpit:
  ws://localhost:5000
(instructions printed at startup below)
"""

import subprocess
import sys
import time
import socket
import os
import signal
import threading

# ── SITL home location — CVS pharmacy area (New York) ────────────────────────
HOME_LAT  = 40.7128
HOME_LON  = -74.0060
HOME_ALT  = 0
HOME_HDG  = 0

SITL_TCP_PORT = 5760
SITL_TIMEOUT  = 30   # seconds to wait for SITL to open its port

# ── Paths ─────────────────────────────────────────────────────────────────────
THIS_DIR   = os.path.dirname(os.path.abspath(__file__))
BRIDGE_PY  = os.path.join(THIS_DIR, "bridge.py")


def wait_for_port(host, port, timeout=SITL_TIMEOUT):
    """Block until a TCP port is open (SITL ready) or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return False


def stream_output(proc, prefix):
    """Print subprocess stdout/stderr with a prefix label."""
    for line in iter(proc.stdout.readline, b""):
        print(f"[{prefix}] {line.decode(errors='replace').rstrip()}")


def main():
    print("=" * 56)
    print("  APEX GCS — SITL + Bridge Launcher")
    print("=" * 56)

    # ── Step 1: Start SITL via dronekit-sitl ──────────────────────────────────
    print("\n[1/3] Starting ArduPilot SITL (ArduCopter)...")
    print(f"      Home: lat={HOME_LAT}, lon={HOME_LON}, alt={HOME_ALT}")

    try:
        import dronekit_sitl
    except ImportError:
        print("\n[ERROR] dronekit-sitl not installed.")
        print("        Run:  pip3 install dronekit-sitl")
        sys.exit(1)

    sitl = dronekit_sitl.start_default(lat=HOME_LAT, lon=HOME_LON)
    connection_str = sitl.connection_string()
    print(f"      SITL ready at: {connection_str}")

    # dronekit-sitl also opens TCP:5760
    print(f"\n[2/3] Waiting for SITL TCP port {SITL_TCP_PORT}...", end="", flush=True)
    if not wait_for_port("127.0.0.1", SITL_TCP_PORT):
        print(" TIMEOUT")
        print("[ERROR] SITL did not open port 5760 in time. Check dronekit-sitl install.")
        sitl.stop()
        sys.exit(1)
    print(" OK")

    # ── Step 2: Print cockpit URL ──────────────────────────────────────────────
    print("\n[2b] Cockpit WS_URL already set to ws://localhost:5000 ✓")

    # ── Step 3: Start bridge ───────────────────────────────────────────────────
    print(f"\n[3/3] Starting MAVLink bridge → tcp:127.0.0.1:5760")
    bridge_proc = subprocess.Popen(
        [sys.executable, BRIDGE_PY, "--sitl", "tcp:127.0.0.1:5760"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1
    )

    # Stream bridge output in background thread
    t = threading.Thread(target=stream_output, args=(bridge_proc, "BRIDGE"), daemon=True)
    t.start()

    print("\n" + "=" * 56)
    print("  ✅  Everything is running!")
    print("=" * 56)
    print("""
  Opening cockpit in Chrome...
    http://localhost:5500/drone-cockpit.html

  In the cockpit, set the URL box to:
    ws://localhost:5000
  then click Connect.

  Press Ctrl+C here to stop everything.
""")

    # Auto-open Chrome with the cockpit
    import subprocess as _sp
    _sp.Popen(["open", "-a", "Google Chrome", "http://localhost:5500/drone-cockpit.html"])

    # ── Keep running until Ctrl+C ──────────────────────────────────────────────
    try:
        bridge_proc.wait()
    except KeyboardInterrupt:
        print("\n[LAUNCHER] Stopping...")
        bridge_proc.terminate()
        sitl.stop()
        print("[LAUNCHER] Done. SITL and bridge stopped.")


if __name__ == "__main__":
    main()
