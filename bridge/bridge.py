"""
APEX GCS — MAVLink ↔ WebSocket Bridge
======================================
Connects ArduPilot SITL (tcp:127.0.0.1:5760) to the browser cockpit
via a raw WebSocket on ws://localhost:5000.

Architecture:
  Browser cockpit  ←→  ws://localhost:5000  ←→  bridge.py  ←→  ArduPilot SITL:5760

Commands FROM browser (JSON):
  {"cmd":"ARM"}
  {"cmd":"DISARM"}
  {"cmd":"TAKEOFF","alt":10}
  {"cmd":"LAND"}
  {"cmd":"RTL"}
  {"cmd":"ESTOP"}
  {"cmd":"SET_MODE","mode":"LOITER"}
  {"cmd":"START_MISSION","waypoints":[{"lat":40.7128,"lng":-74.006,"alt":20},...]}

Telemetry TO browser (JSON) — matches ingestMavlink() keys:
  {"lat":40.7128,"lng":-74.006,"alt":15.2,"vx":1.2,"vy":0.3,"vz":-0.1,
   "pitch":-2.1,"roll":0.5,"hdg":183,"battery":82,"voltage":15.3,
   "current":12.4,"satellites":10,"hdop":1.1,"armed":true,"mode":"LOITER"}

Usage:
  python3 bridge.py                        # connects to SITL on localhost:5760
  python3 bridge.py --sitl /dev/ttyAMA0   # connects to real Pixhawk on Pi serial
  python3 bridge.py --sitl COM3            # Windows serial port
"""

import asyncio
import json
import math
import argparse
import sys
import threading
import time
from pymavlink import mavutil
import websockets

# ── Config ─────────────────────────────────────────────────────────────────────
WS_HOST = "localhost"
WS_PORT = 5000
TELEMETRY_HZ = 10          # send telemetry to browser 10×/sec
MAV_BAUD = 57600            # only used for real serial (Pi → Pixhawk)

# ArduCopter mode map
COPTER_MODES = {
    "STABILIZE": 0,  "ACRO": 1,     "ALT_HOLD": 2, "AUTO": 3,
    "GUIDED": 4,     "LOITER": 5,   "RTL": 6,      "CIRCLE": 7,
    "LAND": 9,       "DRIFT": 11,   "SPORT": 13,   "FLIP": 14,
    "AUTOTUNE": 15,  "POSHOLD": 16, "BRAKE": 17,   "THROW": 18,
    "AVOID_ADSB": 19,"GUIDED_NOGPS":20,"SMART_RTL":21,
}
# Reverse map for display
MODE_NAMES = {v: k for k, v in COPTER_MODES.items()}
# Short display names → match cockpit mode-btn labels
MODE_DISPLAY = {
    "STABILIZE": "STABILIZE", "ALT_HOLD": "ALT_HOLD",
    "LOITER": "LOITER",       "AUTO": "AUTO",
    "RTL": "RTL",             "GUIDED": "GUIDED",
    "LAND": "LAND",           "POSHOLD": "POSHOLD",
}

# ── State shared between MAVLink thread and WebSocket handler ──────────────────
_telem = {
    "lat": 0, "lng": 0, "alt": 0,
    "vx": 0, "vy": 0, "vz": 0,
    "pitch": 0, "roll": 0, "hdg": 0,
    "battery": 0, "voltage": 0, "current": 0,
    "satellites": 0, "hdop": 99,
    "armed": False, "mode": "STABILIZE",
    "connected": False,
}
_lock = threading.Lock()
_mav = None   # global MAVLink connection, set after connect
_connection_string = ""  # stored for auto-reconnect
# While set, the recv loop stops reading so mission upload can consume
# MISSION_REQUEST/MISSION_ACK messages itself (both threads share one link)
_upload_active = threading.Event()

# ── Geofence state ────────────────────────────────────────────────────────────
_fence_lat = 0.0
_fence_lng = 0.0
_fence_radius = 0.0


# ── MAVLink helpers ────────────────────────────────────────────────────────────

def mav_connect(connection_string):
    """Open MAVLink connection, wait for heartbeat."""
    global _mav, _connection_string
    _connection_string = connection_string
    print(f"[MAV] Connecting to {connection_string} ...")
    _mav = mavutil.mavlink_connection(connection_string, baud=MAV_BAUD)
    print("[MAV] Waiting for heartbeat (this may take ~10 s for SITL)...")
    _mav.wait_heartbeat(timeout=30)
    print(f"[MAV] Heartbeat received — system {_mav.target_system}, component {_mav.target_component}")
    with _lock:
        _telem["connected"] = True
    # Request data streams
    _mav.mav.request_data_stream_send(
        _mav.target_system, _mav.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1
    )


def mav_set_mode(mode_name):
    """Set flight mode by name."""
    mode_name = mode_name.upper()
    if mode_name not in COPTER_MODES:
        print(f"[MAV] Unknown mode: {mode_name}")
        return
    mode_id = COPTER_MODES[mode_name]
    _mav.mav.set_mode_send(
        _mav.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mode_id
    )
    print(f"[MAV] SET_MODE → {mode_name} ({mode_id})")


def mav_arm(arm=True):
    """Arm or disarm motors."""
    _mav.mav.command_long_send(
        _mav.target_system, _mav.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0,
        1 if arm else 0,  # param1: 1=arm, 0=disarm
        0, 0, 0, 0, 0, 0
    )
    print(f"[MAV] {'ARM' if arm else 'DISARM'} sent")


def mav_takeoff(alt_m):
    """Send guided takeoff to alt_m metres."""
    mav_set_mode("GUIDED")
    time.sleep(0.5)
    mav_arm(True)
    time.sleep(1.0)
    _mav.mav.command_long_send(
        _mav.target_system, _mav.target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        0,
        0, 0, 0, 0,       # params 1-4
        0, 0, alt_m        # lat, lng, alt
    )
    print(f"[MAV] TAKEOFF to {alt_m} m sent")


def mav_land():
    mav_set_mode("LAND")
    print("[MAV] LAND mode set")


def mav_rtl():
    mav_set_mode("RTL")
    print("[MAV] RTL mode set")


def mav_estop():
    """Emergency stop — disarm immediately regardless of state."""
    _mav.mav.command_long_send(
        _mav.target_system, _mav.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, 0,              # disarm
        21196,             # magic force-disarm param
        0, 0, 0, 0, 0
    )
    print("[MAV] ESTOP sent")


def mav_upload_mission(waypoints):
    """
    Upload a list of {lat, lng, alt} waypoints as a MAVLink mission.
    Inserts a TAKEOFF as item 0 and appends RTL at the end.
    Pauses the recv loop while active and answers whichever request flavour
    the autopilot uses (MISSION_REQUEST or MISSION_REQUEST_INT).
    Returns True on MISSION_ACK accepted.
    """
    frame = mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT
    first_alt = waypoints[0]["alt"] if waypoints else 20
    # (command, current, autocontinue, p1, p2, p3, p4, lat, lng, alt)
    items = [
        (mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, 1, 1, 0, 0, 0, 0, 0, 0, 0),   # dummy home
        (mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,  0, 1, 0, 0, 0, 0, 0, 0, first_alt),
    ]
    for wp in waypoints:
        items.append((
            mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, 0, 1,
            0,          # hold seconds
            2.0,        # acceptance radius (m)
            0, 0,
            wp["lat"], wp["lng"], wp["alt"]
        ))
    items.append((mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH, 0, 1, 0, 0, 0, 0, 0, 0, 0))

    count = len(items)
    _upload_active.set()
    time.sleep(0.1)  # let the recv loop finish its current read
    try:
        _mav.mav.mission_count_send(_mav.target_system, _mav.target_component, count)
        print(f"[MAV] Uploading {count} mission items...")

        for _ in range(count * 2 + 10):   # allow retransmit requests
            msg = _mav.recv_match(
                type=["MISSION_REQUEST", "MISSION_REQUEST_INT", "MISSION_ACK"],
                blocking=True, timeout=5
            )
            if msg is None:
                print("[MAV] Mission upload timed out")
                return False
            if msg.get_type() == "MISSION_ACK":
                ok = msg.type == mavutil.mavlink.MAV_MISSION_ACCEPTED
                print(f"[MAV] Mission upload ACK: {msg}")
                return ok
            seq = msg.seq
            if seq >= count:
                continue
            cmd, cur, auto, p1, p2, p3, p4, lat, lng, alt = items[seq]
            if msg.get_type() == "MISSION_REQUEST_INT":
                _mav.mav.mission_item_int_send(
                    _mav.target_system, _mav.target_component, seq, frame, cmd,
                    cur, auto, p1, p2, p3, p4,
                    int(lat * 1e7), int(lng * 1e7), alt
                )
            else:
                _mav.mav.mission_item_send(
                    _mav.target_system, _mav.target_component, seq, frame, cmd,
                    cur, auto, p1, p2, p3, p4,
                    lat, lng, alt
                )
        print("[MAV] Mission upload gave up — too many retransmits")
        return False
    finally:
        _upload_active.clear()


def mav_start_mission():
    """Start the uploaded mission (switch AUTO, send mission start)."""
    mav_set_mode("AUTO")
    _mav.mav.command_long_send(
        _mav.target_system, _mav.target_component,
        mavutil.mavlink.MAV_CMD_MISSION_START,
        0, 0, 0, 0, 0, 0, 0, 0
    )
    print("[MAV] Mission START sent")


def _upload_and_start(waypoints):
    """Upload a mission and start it only if the upload was accepted."""
    if mav_upload_mission(waypoints):
        time.sleep(0.5)
        mav_start_mission()
    else:
        print("[MAV] Mission NOT started — upload failed")


def mav_goto(lat, lng, alt_m):
    """Fly to a specific lat/lng/alt in GUIDED mode (click-to-fly)."""
    mav_set_mode("GUIDED")
    _mav.mav.set_position_target_global_int_send(
        0,                                                  # time_boot_ms
        _mav.target_system,
        _mav.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        0b0000111111111000,                                 # type_mask: position only
        int(lat * 1e7),                                     # lat (deg * 1e7)
        int(lng * 1e7),                                     # lng (deg * 1e7)
        alt_m,                                              # alt in metres (relative)
        0, 0, 0,                                            # vx, vy, vz (ignored)
        0, 0, 0,                                            # afx, afy, afz (ignored)
        0, 0                                                # yaw, yaw_rate (ignored)
    )
    print(f"[MAV] GOTO → lat={lat:.6f} lng={lng:.6f} alt={alt_m}m")


def mav_velocity(vx, vy, vz):
    """Send body-frame velocity command for joystick live control (GUIDED mode)."""
    _mav.mav.set_position_target_local_ned_send(
        0,                                                  # time_boot_ms
        _mav.target_system,
        _mav.target_component,
        mavutil.mavlink.MAV_FRAME_BODY_OFFSET_NED,
        0b0000111111000111,                                 # type_mask: velocity only
        0, 0, 0,                                            # x, y, z (ignored)
        vx, vy, vz,                                         # velocity m/s
        0, 0, 0,                                            # afx, afy, afz (ignored)
        0, 0                                                # yaw, yaw_rate (ignored)
    )


def _inside_fence(lat, lng):
    """Return True if the geofence is disabled or the drone is within fence_radius metres."""
    if _fence_radius == 0.0:
        return True
    dlat = math.radians(lat - _fence_lat)
    dlng = math.radians(lng - _fence_lng) * math.cos(math.radians(_fence_lat))
    dist = math.sqrt(dlat ** 2 + dlng ** 2) * 6371000  # Earth radius in metres
    return dist <= _fence_radius


# ── MAVLink receive loop (runs in background thread) ──────────────────────────

def mavlink_recv_loop():
    """
    Continuously reads MAVLink messages, updates _telem dict.
    Runs in a daemon thread — dies when the main process exits.
    Auto-reconnects after 10 consecutive errors.
    """
    global _mav
    print("[MAV] Receive loop started")
    _consecutive_errors = 0
    _last_fence_check = 0.0
    _have_sys_battery = False
    while True:
        try:
            if _upload_active.is_set():
                time.sleep(0.05)
                continue
            msg = _mav.recv_match(
                type=[
                    "GLOBAL_POSITION_INT",
                    "ATTITUDE",
                    "SYS_STATUS",
                    "BATTERY_STATUS",
                    "GPS_RAW_INT",
                    "HEARTBEAT",
                    "VFR_HUD",
                ],
                blocking=True, timeout=1.0
            )
            _consecutive_errors = 0  # reset on successful recv (even if msg is None)
            if msg is None:
                continue

            t = msg.get_type()
            _check_fence = False
            _fence_lat_snap = 0.0
            _fence_lng_snap = 0.0
            with _lock:
                if t == "HEARTBEAT":
                    armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                    mode_id = msg.custom_mode
                    _telem["armed"] = armed
                    _telem["mode"] = MODE_NAMES.get(mode_id, str(mode_id))

                elif t == "GLOBAL_POSITION_INT":
                    _telem["lat"]  = msg.lat  / 1e7
                    _telem["lng"]  = msg.lon  / 1e7
                    _telem["alt"]  = msg.relative_alt / 1000.0  # mm → m
                    _telem["vx"]   = msg.vx  / 100.0   # cm/s → m/s
                    _telem["vy"]   = msg.vy  / 100.0
                    _telem["vz"]   = msg.vz  / 100.0   # positive = down in MAVLink
                    _fence_lat_snap = _telem["lat"]
                    _fence_lng_snap = _telem["lng"]
                    _check_fence = True

                elif t == "ATTITUDE":
                    _telem["pitch"] = round(math.degrees(msg.pitch), 1)
                    _telem["roll"]  = round(math.degrees(msg.roll),  1)
                    _telem["hdg"]   = _telem.get("hdg", 0)  # from VFR_HUD

                elif t == "VFR_HUD":
                    _telem["hdg"] = msg.heading   # degrees 0-360

                elif t == "SYS_STATUS":
                    v = msg.voltage_battery / 1000.0       # mV → V
                    i = msg.current_battery  / 100.0       # cA → A
                    b = msg.battery_remaining               # %
                    if v > 0:   _telem["voltage"]  = round(v, 2)
                    if i >= 0:  _telem["current"]  = round(i, 1)
                    if b >= 0:
                        _telem["battery"] = b
                        _have_sys_battery = True

                elif t == "BATTERY_STATUS":
                    # Fallback if SYS_STATUS never reports battery (-1)
                    if not _have_sys_battery and msg.battery_remaining >= 0:
                        _telem["battery"] = msg.battery_remaining

                elif t == "GPS_RAW_INT":
                    _telem["satellites"] = msg.satellites_visible
                    _telem["hdop"]       = round(msg.eph / 100.0, 2)

            # Geofence check outside lock to avoid holding it during MAVLink send
            if _check_fence and not _inside_fence(_fence_lat_snap, _fence_lng_snap):
                now = time.time()
                if now - _last_fence_check > 5.0:
                    _last_fence_check = now
                    print(f"[MAV] WARNING: Drone outside geofence "
                          f"(lat={_fence_lat_snap:.6f}, lng={_fence_lng_snap:.6f}) — triggering RTL")
                    mav_rtl()

        except Exception as e:
            _consecutive_errors += 1
            print(f"[MAV] Recv error ({_consecutive_errors}): {e}")
            if _consecutive_errors >= 10:
                print("[MAV] Too many consecutive errors — attempting reconnect...")
                _consecutive_errors = 0
                try:
                    _mav.close()
                except Exception:
                    pass
                try:
                    mav_connect(_connection_string)
                except Exception as re:
                    print(f"[MAV] Reconnect failed: {re}")
            time.sleep(0.5)


# ── WebSocket server ───────────────────────────────────────────────────────────

CLIENTS = set()


async def ws_handler(websocket):
    """Handle one browser connection."""
    CLIENTS.add(websocket)
    remote = websocket.remote_address
    print(f"[WS] Client connected: {remote}")

    # Send current state immediately
    with _lock:
        snapshot = dict(_telem)
    await websocket.send(json.dumps(snapshot))

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
                await handle_command(msg)
            except json.JSONDecodeError:
                print(f"[WS] Bad JSON: {raw}")
            except Exception as e:
                print(f"[WS] Command error: {e}")
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        CLIENTS.discard(websocket)
        print(f"[WS] Client disconnected: {remote}")


async def handle_command(msg):
    """Dispatch a command dict from the browser to MAVLink."""
    global _fence_lat, _fence_lng, _fence_radius
    cmd = msg.get("cmd", "").upper()

    if not _mav:
        print(f"[WS] Command ignored — MAVLink not connected: {cmd}")
        return

    loop = asyncio.get_running_loop()

    if   cmd == "ARM":           mav_arm(True)
    elif cmd == "DISARM":        mav_arm(False)
    elif cmd == "TAKEOFF":
        # Blocking (sleeps ~1.5s) — run off the event loop so telemetry keeps flowing
        await loop.run_in_executor(None, mav_takeoff, float(msg.get("alt", 10)))
    elif cmd == "LAND":          mav_land()
    elif cmd == "RTL":           mav_rtl()
    elif cmd == "ESTOP":         mav_estop()
    elif cmd == "SET_MODE":      mav_set_mode(msg.get("mode", "LOITER"))
    elif cmd == "GOTO":
        mav_goto(float(msg.get("lat", 0)), float(msg.get("lng", 0)), float(msg.get("alt", 10)))
    elif cmd == "VELOCITY":
        mav_velocity(float(msg.get("vx", 0)), float(msg.get("vy", 0)), float(msg.get("vz", 0)))
    elif cmd == "SET_GEOFENCE":
        _fence_lat    = float(msg.get("lat",    0))
        _fence_lng    = float(msg.get("lng",    0))
        _fence_radius = float(msg.get("radius", 0))
        print(f"[WS] Geofence set: centre=({_fence_lat:.6f},{_fence_lng:.6f}) radius={_fence_radius}m")
    elif cmd == "CLEAR_GEOFENCE":
        _fence_radius = 0.0
        print("[WS] Geofence cleared")
    elif cmd == "START_MISSION":
        wps = msg.get("waypoints", [])
        if wps:
            # Upload blocks for seconds — run off the event loop
            await loop.run_in_executor(None, _upload_and_start, wps)
        else:
            print("[WS] START_MISSION — no waypoints")
    else:
        print(f"[WS] Unknown command: {cmd}")


async def telemetry_broadcast():
    """Push telemetry JSON to all connected browsers at TELEMETRY_HZ."""
    interval = 1.0 / TELEMETRY_HZ
    while True:
        await asyncio.sleep(interval)
        if not CLIENTS:
            continue
        with _lock:
            payload = json.dumps(_telem)
        dead = set()
        for ws in list(CLIENTS):
            try:
                await ws.send(payload)
            except Exception:
                dead.add(ws)
        CLIENTS.difference_update(dead)


async def main_async(connection_string):
    # Start WebSocket server
    print(f"[WS] Starting WebSocket server on ws://{WS_HOST}:{WS_PORT}")
    server = await websockets.serve(ws_handler, WS_HOST, WS_PORT)

    # Connect MAVLink in a thread (blocking I/O)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, mav_connect, connection_string)

    # Start MAVLink receive loop in daemon thread
    t = threading.Thread(target=mavlink_recv_loop, daemon=True)
    t.start()

    # Telemetry broadcast coroutine
    print(f"[OK] Bridge running — cockpit at ws://{WS_HOST}:{WS_PORT}")
    print("     Press Ctrl+C to stop.\n")
    await telemetry_broadcast()

    server.close()
    await server.wait_closed()


def main():
    global WS_PORT
    parser = argparse.ArgumentParser(description="APEX GCS MAVLink ↔ WebSocket Bridge")
    parser.add_argument(
        "--sitl",
        default="tcp:127.0.0.1:5760",
        help="MAVLink connection string. "
             "SITL default: tcp:127.0.0.1:5760  "
             "Pi serial: /dev/ttyAMA0  "
             "USB telemetry: /dev/tty.usbserial-XXXX"
    )
    parser.add_argument("--ws-port", type=int, default=WS_PORT, help="WebSocket port (default 5000)")
    args = parser.parse_args()

    WS_PORT = args.ws_port

    try:
        asyncio.run(main_async(args.sitl))
    except KeyboardInterrupt:
        print("\n[BRIDGE] Stopped.")


if __name__ == "__main__":
    main()
