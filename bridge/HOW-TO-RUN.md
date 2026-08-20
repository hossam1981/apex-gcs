# APEX GCS — How to Run

---

## 🎮 Option A — Gazebo 3D Visual Simulator (Recommended)

A real 3D world you fly through — buildings, trees, CVS pharmacy, landing pad.
The drone moves in 3D space. You see it from chase-cam or FPV.

### One-time setup (~20 min, downloads ~1 GB)
```bash
cd /Users/hossamelnaggar/Downloads/drone/bridge
./setup_gazebo.sh
```
Installs: Gazebo Harmonic, ArduPilot source, Gazebo plugin. Takes ~20 min first time.

### Every time you want to fly
```bash
cd /Users/hossamelnaggar/Downloads/drone/bridge
./start_gazebo.sh
```
Opens: Gazebo 3D window + ArduPilot SITL + WebSocket bridge

Then open the cockpit at `http://localhost:5500/drone-cockpit.html`, set URL to `ws://localhost:5000`, click Connect.

**You now have two views simultaneously:**
- **Gazebo window** — 3D chase-cam / FPV of the drone flying
- **APEX GCS cockpit** — telemetry, map, mission control

### What's in the 3D world
| Object | Description |
|---|---|
| 🏢 CVS Pharmacy | Red building in center with rooftop landing pad (yellow H) |
| 🏢 3 Office buildings | Various heights around the block |
| 🌳 4 Trees | On sidewalks |
| 📦 Delivery package | Sits on ground near CVS |
| 🚁 Iris drone | Spawns ready to arm |
| ☁️ Sky + clouds | Moving clouds, directional sun with shadows |
| 💨 Wind | Light random wind enabled |

---

## 🖥️ Option B — Basic SITL (no 3D visuals)

### What it is

## What is this and why do we need it?

The cockpit (drone-cockpit.html) is a browser app. Real ArduPilot drones speak
MAVLink — a protocol the browser can't talk to directly. This bridge fills that gap:

```
Chrome cockpit  ←→  bridge.py (ws://localhost:5000)  ←→  ArduPilot SITL (:5760)
```

- **SITL** = Software In The Loop. A real ArduPilot running on your Mac as a program,
  with no physical drone needed. All flight logic (modes, PID, GPS, battery) is real.
- **bridge.py** = translates MAVLink ↔ WebSocket so the browser can talk to it.
- When the real drone arrives, only one line changes — the bridge target switches from
  `localhost:5760` (SITL) to the Raspberry Pi serial port. The cockpit stays the same.

---

## Three things that run (in order)

| # | What | Port | Started by |
|---|------|------|-----------|
| 1 | ArduPilot SITL (fake drone) | `:5760` | `start_sitl.py` |
| 2 | Python MAVLink bridge | `:5000` | `start_sitl.py` |
| 3 | HTTP server (cockpit page) | `:5500` | VS Code / already running |

---

## How to start

### One-time setup (run once ever)
```bash
cd /Users/hossamelnaggar/Downloads/drone/bridge
./setup.sh
```
Downloads ArduCopter SITL binary and installs Python packages.

### Every time you want to fly
```bash
cd /Users/hossamelnaggar/Downloads/drone/bridge
python3 start_sitl.py
```
This starts SITL + bridge in one command. Leave this terminal open.

### Open the cockpit
1. Go to `http://localhost:5500/drone-cockpit.html` in Chrome
2. Find the connection URL box — change it to: `ws://localhost:5000`
3. Click **Connect**
4. You should see live battery %, GPS satellites, and attitude — all from real ArduPilot

---

## How to stop
Press `Ctrl+C` in the terminal running `start_sitl.py`. Both SITL and bridge stop cleanly.

---

## When the real drone arrives
```bash
# Instead of start_sitl.py, run bridge.py directly pointed at the Pi:
python3 bridge.py --sitl /dev/ttyAMA0

# And change the cockpit URL box back to:
ws://192.168.4.1:5000
```
That's the only change needed. Everything else stays the same.

---

## Is this a real drone?

No — not yet. What you're seeing now is **SITL** (Software In The Loop).
It's ArduPilot running as a program on your Mac, pretending to be a real drone.
Think of it like a flight simulator — the numbers are real ArduPilot math and logic,
but there's no physical drone.

### The 3 stages of this project

| Stage | What's connected | Status |
|---|---|---|
| 🖥️ **Now** | SITL on your Mac (fake drone) | ✅ Done |
| 📦 **When hardware arrives** | Real Pixhawk via Raspberry Pi | Just change the URL |
| 🚁 **Final** | Real drone flying outdoors | Full delivery POC |

The good news: you just proved the whole system works end-to-end.
When the real drone arrives, you change **one thing** — the WebSocket URL
from `ws://localhost:5000` → `ws://192.168.4.1:5000` (the Pi on the drone).
The cockpit stays exactly the same.

### What the cockpit shows right now (SITL data, not fake sim)

| Where | What you see | What it means |
|---|---|---|
| Top bar | 🟢 Connected | Live ArduPilot data flowing |
| Top bar | LOITER / STABILIZE | Real flight mode from ArduPilot |
| Top bar | GPS 10 sats | Real ArduPilot GPS simulation |
| Left panel | TELEMETRY 9 HZ | Data arriving 9× per second |
| Left panel | Pitch / Roll | Real IMU attitude from ArduPilot |
| Left panel | BATTERY 99% | Real ArduPilot battery model |
| Left panel | Voltage 12.6V | Real voltage reading |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `dronekit-sitl not found` | Run `pip3 install dronekit-sitl` |
| `websockets not found` | Run `pip3 install websockets` |
| Port 5000 already in use | Kill old bridge: `lsof -i :5000` then `kill <PID>` |
| Cockpit shows "Disconnected" | Make sure `start_sitl.py` is running and URL is `ws://localhost:5000` |
| SITL timeout | Wait 30 s — first run downloads binary, takes longer |
