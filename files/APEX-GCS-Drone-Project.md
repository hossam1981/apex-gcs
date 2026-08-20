# APEX GCS — CVS Drone Delivery POC
### Complete Project Documentation & Setup Guide
*Conversation export — June 2026*

---

## TABLE OF CONTENTS
1. [Project Overview](#project-overview)
2. [Autonomy Stack](#autonomy-stack)
3. [Hardware & Sensors](#hardware--sensors)
4. [Control Interface](#control-interface)
5. [Recommended Drone Hardware](#recommended-drone-hardware)
6. [Complete Hardware List](#complete-hardware-list)
7. [CVS Drone Delivery Context](#cvs-drone-delivery-context)
8. [Delivery POC Focus](#delivery-poc-focus)
9. [Software Sync Plan](#software-sync-plan)
10. [Step-by-Step Beginner Setup Guide](#step-by-step-beginner-setup-guide)

---

## Project Overview

A browser-based drone cockpit (APEX GCS) built in a single HTML file, designed to:
- Control a drone in real time via a browser cockpit
- Detect objects autonomously (people, deer, cars, etc.) using AI camera detection
- Fly pre-planned autonomous routes based on battery capacity
- Alert the operator with bounding boxes when targets are detected
- Eventually support smart autonomous delivery for CVS pharmacy

The system is designed to work with **any cheap ArduPilot-compatible drone** and a Raspberry Pi companion computer.

---

## Autonomy Stack

**Choice: Custom Python + MAVLink (no ROS)**

**Why:** Lightweight, runs on a $35 Raspberry Pi Zero 2W. ROS is overkill for a single drone — it adds 2GB overhead and complexity you don't need unless running a robot arm or swarm.

The full communication chain:
```
Browser Cockpit
     ↕ WebSocket
  Pi (onboard)
     ↕ MAVLink serial
  Flight Controller (ArduPilot)
     ↕ PWM/DShot
  Motors
```

---

## Hardware & Sensors

**Sensors: Camera + GPS only (to start)**
- **Cheap USB/CSI camera** → YOLO object detection on-device or streamed to browser
- **Built-in GPS** (any ArduPilot FC has one) → waypoint navigation
- **FC IMU** (accelerometer/gyro/baro) → already in every $40 flight controller

No LiDAR needed for outdoor aerial scanning. Add later if obstacle avoidance indoors is needed.

---

## Control Interface

**Companion computer onboard (Raspberry Pi)**

The Pi onboard runs three things:
1. MAVLink bridge (talks to the flight controller)
2. Python WebSocket server (talks to the browser cockpit)
3. YOLO inference process (AI object detection)

The browser becomes the GCS over WiFi or 4G.

**Why this stack:** Total hardware cost under $80, works with any cheap drone, no cloud needed, fully hackable.

---

## Recommended Drone Hardware

### 🥇 Best Overall: Holybro S500 + Pixhawk 6C (~$350 total)
Frame, motors, ESC all pre-matched. The Pixhawk 6C is the current gold standard for ArduPilot — solid IMU, great community support. Plug in a Raspberry Pi 4 via UART, flash ArduCopter, done. This is exactly the hardware the cockpit stack is designed for.

### 🥈 Budget Option: DJI F450 Frame + Pixhawk 2.4.8 clone (~$150–180)
The F450 ARF kit comes with frame, 4 motors, 4 ESCs, and propellers — you add the flight controller and battery. The Pixhawk 2.4.8 is a cheap clone but fully ArduPilot-compatible and fine for a POC. Only downside: clone sensors drift more in wind.

### 🥉 Fastest Start: Holybro X500 v2 Kit (~$250)
Comes almost fully assembled. Great if you want to skip the build and jump straight to software.

### Companion Computer (add to any of the above)
Raspberry Pi 4 (2GB) — ~$45. Straps to the frame, talks to the Pixhawk over UART, runs Python bridge + YOLO detection + WebSocket server all at once.

### ⚠️ What to Avoid
- **DJI consumer drones** (Mavic, Mini) — locked ecosystem, no MAVLink, no companion computer slot
- **Betaflight FCs** — Betaflight supports MAVLink only for telemetry, cannot execute commands for autonomous flight

---

## Complete Hardware List

### 🚁 Frame & Propulsion
- Holybro S500 frame kit (includes arms, landing gear)
- 4x 2216 880KV brushless motors (usually included)
- 4x 20A ESCs (usually included)
- 4x 1045 propellers (2 CW + 2 CCW)

### 🧠 Flight Controller
- Holybro Pixhawk 6C (ArduPilot)
- GPS + compass module (M8N or M9N — usually bundled)
- Power module (voltage/current sensor)
- Buzzer + safety switch

### 🖥️ Companion Computer
- Raspberry Pi 4 (2GB minimum, 4GB recommended)
- MicroSD card 32GB+ (Class 10)
- Pi Camera Module v2 OR USB webcam (1080p)
- UART-to-USB cable (Pi ↔ Pixhawk serial connection)
- Small heatsink + fan for the Pi

### 🔋 Power
- 4S LiPo battery 4000–5000mAh (14.8V)
- LiPo balance charger (iMAX B6 or similar)
- XT60 connectors + power splitter
- Battery strap + foam pad

### 📡 Radio & Comms
- RC transmitter 6+ channel (FlySky FS-i6 is cheap and works)
- RC receiver (matching brand)
- 4G USB dongle OR WiFi hotspot (for long-range GCS link)
- Telemetry radio pair optional (SiK 915MHz) — useful as backup

### 🔧 Assembly & Misc
- M3 screws + standoffs kit
- Zip ties + velcro straps
- Double-sided foam tape (vibration dampening for FC)
- Heat shrink tubing
- Soldering iron + solder
- Loctite threadlocker
- Multimeter

### 💻 Ground Station (laptop/PC)
- Any modern browser (Chrome recommended)
- The APEX GCS cockpit HTML file
- Python 3 + `pymavlink` + `dronekit` installed
- Optional: second screen for map + camera split view

### Estimated Total Cost

| Tier | ~Cost |
|---|---|
| Budget (clones) | $250–300 |
| Mid (Holybro S500 kit) | $380–450 |
| With 4G long-range | +$40–60 |

---

## CVS Drone Delivery Context

CVS already has skin in this game:
- CVS partnered with UPS Flight Forward to deliver prescription medicines by drone to retirement communities in Florida using the Matternet M2 system
- CVS Health is now working with SkyfireAI, piloting drone operations for disaster response and supply chain resilience

Those are enterprise-scale, FAA-certified, expensive programs. This POC is different — it's an **internal dev tool** that proves the concept on cheap hardware before CVS spends millions.

---

## Delivery POC Focus

**The delivery problem at CVS is concrete:**
- Prescriptions to elderly/mobility-limited customers
- Same-day OTC delivery (cold medicine, insulin, test kits)
- Disaster/emergency supply drops when roads are blocked
- Last-mile from store to customer within ~5 mile radius

**Software layer to build (in your lane as app dev analyst):**
1. **Payload Management** — arm release trigger via MAVLink servo command, weight sensor on hook
2. **Address-to-GPS resolver** — customer enters address → converts to landing coordinates
3. **Safe Landing Zone detection** — camera + CV checks drop zone is clear before release
4. **Chain of custody** — photo confirmation at drop, timestamp, customer notification
5. **Geofence enforcement** — hard no-fly zones around airports, hospitals, schools
6. **Return-to-pharmacy** — drone automatically flies back after drop, battery-aware

---

## Software Sync Plan

### What connects the HTML cockpit to your real drone

**Step 1 — Flash ArduCopter onto the Pixhawk**
Download Mission Planner (Windows) or QGroundControl (any OS), plug in Pixhawk via USB, flash ArduCopter firmware.

**Step 2 — Install the Pi bridge**
```bash
pip install pymavlink dronekit flask flask-socketio
```

**Step 3 — Wire Pi to Pixhawk**
```
Pi GPIO Pin 8  (TX) → Pixhawk TELEM2 RX
Pi GPIO Pin 10 (RX) → Pixhawk TELEM2 TX
Pi Ground           → Pixhawk Ground
```
Set in Mission Planner: `SERIAL2_PROTOCOL = 2`, `SERIAL2_BAUD = 921`

**Step 4 — Connect laptop to Pi**
Pi creates a WiFi hotspot. Open cockpit in Chrome at `http://192.168.4.1:5000`

### Sync Test Checklist (before first flight)
- [ ] Attitude indicator moves when you tilt the drone by hand
- [ ] GPS coordinates update on the map
- [ ] Battery voltage reads correctly
- [ ] ARM button arms the motors (props off for safety)
- [ ] Waypoint upload triggers mission in QGroundControl too (cross-verify)
- [ ] RTL command brings drone back in sim first (SITL test)

### Recommended: Run SITL First (simulate everything on your laptop)
```bash
pip install dronekit-sitl
dronekit-sitl copter --home=40.7128,-74.0060,0,0
```
This spins up a fake Pixhawk on your machine. Point the cockpit at `localhost:5760` and everything works — arm, fly waypoints, RTL — zero risk of crashing a $400 drone.

---

## Step-by-Step Beginner Setup Guide

### THE BIG PICTURE
You're building 3 things that talk to each other:
```
Your Browser (cockpit) ↔ Raspberry Pi (brain) ↔ Pixhawk (drone nervous system) ↔ Motors
```
Everything in the HTML file is ready. You just need to connect the physical pieces.

---

### PHASE 1 — Buy & Unbox
**⏱ Time: 1-2 weeks (shipping)**

1. Order the hardware list above
2. When it arrives, don't connect anything yet
3. Lay everything out on a table and identify each part
4. Watch one YouTube video of someone assembling an S500 — just to visualize it

---

### PHASE 2 — Build the Drone (No Electronics Yet)
**⏱ Time: 1 afternoon**

1. Assemble the S500 frame — screw the arms onto the center plate
2. Mount the 4 motors onto the arm ends — each motor has 4 screws
3. Put a drop of Loctite on each screw so they don't vibrate loose mid-flight
4. Mount the landing gear legs at the bottom
5. **Do NOT connect any wires yet** — just make sure the frame feels solid, nothing wobbles

---

### PHASE 3 — Solder & Wire Power
**⏱ Time: 2-3 hours**

This is the only hard part. Go slow.

1. Solder the 4 ESCs to the power distribution board — red to +, black to –
2. Solder the XT60 battery connector to the power distribution board
3. Plug each motor's 3 wires into its ESC — order doesn't matter yet, fix spin direction later in software
4. Plug the power module between the battery and the frame
5. **Test:** plug in battery, all 4 ESCs should beep once = power flowing correctly. Unplug immediately.

---

### PHASE 4 — Mount the Pixhawk
**⏱ Time: 30 minutes**

1. Stick vibration dampening foam pad in the CENTER of the frame — critical, vibrations kill sensor readings
2. Mount Pixhawk on top of that foam, arrow pointing FORWARD
3. Connect ESC signal wires to Pixhawk outputs:
   - Motor 1 → front-right
   - Motor 2 → rear-left
   - Motor 3 → front-left
   - Motor 4 → rear-right
4. Mount the GPS mast on the back arm, plug GPS into Pixhawk GPS port
5. Plug in the buzzer and safety switch — required to arm

---

### PHASE 5 — First Pixhawk Setup on Your Laptop
**⏱ Time: 1-2 hours**

1. Download **Mission Planner** (free at ardupilot.org)
2. Plug Pixhawk into laptop via USB
3. Click Connect in the top right
4. Go to **Setup → Install Firmware** → pick ArduCopter for Quadcopter → flash
5. Tilt the drone — the horizon on screen moves. **This confirms the Pixhawk is alive.**
6. Run **Accelerometer Calibration** — place drone flat, then on each side
7. Run **Compass Calibration** — spin the drone in circles as shown
8. Set **Frame Type** to X (quad)
9. **Motor Test** — spin each motor at 5% throttle with NO PROPS to confirm direction

---

### PHASE 6 — Set Up the Raspberry Pi
**⏱ Time: 2-3 hours**

1. Download **Raspberry Pi Imager** on your laptop
2. Flash **Raspberry Pi OS Lite** onto MicroSD card
3. Enable SSH and set WiFi password in the imager settings before ejecting
4. Put SD card in Pi, power it on
5. Connect via SSH from your laptop:
```bash
ssh pi@raspberrypi.local
```
6. Run these commands:
```bash
sudo apt update && sudo apt upgrade -y
pip install pymavlink dronekit flask flask-socketio
```
7. Wire the Pi to the Pixhawk (3 wires as described above)
8. In Mission Planner set `SERIAL2_PROTOCOL = 2` and `SERIAL2_BAUD = 921`

---

### PHASE 7 — Test the Software Connection (NO PROPS, INDOORS)
**⏱ Time: 1 hour**

1. Get the Python bridge file (one script, ~100 lines)
2. Put it on the Pi and run it
3. Open the HTML cockpit on your laptop browser
4. **You should see:** battery voltage, GPS satellites, attitude moving when you tilt the drone
5. Click ARM in the cockpit — Pixhawk buzzer beeps and safety LED changes
6. **This is the moment the HTML file and the drone are officially synced** ✓

---

### PHASE 8 — First Outdoor Test (PROPS ON, LOW HOVER)
**⏱ Time: 1 afternoon, open field**

1. Put props on — double check CW props on CW motors, CCW on CCW
2. Go to an open field, no people within 30 meters
3. Arm with your RC transmitter first — NOT the cockpit yet
4. Slowly raise throttle to hover at 1 meter
5. Land immediately — just checking it doesn't flip or vibrate badly
6. If it flips → one motor spinning wrong direction, fix in Mission Planner
7. If it shakes badly → check prop balance or foam mounting
8. Repeat until it hovers clean and stable

---

### PHASE 9 — First Cockpit-Controlled Flight
**⏱ Time: 1 hour outdoors**

1. Pi powered and connected to Pixhawk, hotspot on
2. Laptop connected to that WiFi
3. Open cockpit in Chrome
4. Confirm live telemetry is showing
5. Set mode to **LOITER** (GPS hold) — drone stays in one spot automatically
6. Arm via RC transmitter, take off manually, get to 3 meters
7. Watch the cockpit — altitude, speed, heading all live
8. Land, disarm
9. **You now have a live-synced cockpit with a real drone** ✓

---

### PHASE 10 — First Autonomous Waypoint Mission
**⏱ Time: 1 hour outdoors**

1. Open cockpit, click the map, drop 3 waypoints in a triangle
2. Set altitude 10 meters, speed 3 m/s (conservative for first time)
3. Arm, take off to 5 meters manually
4. Switch to AUTO mode in the cockpit
5. **Watch the drone fly your planned route by itself**
6. It will complete the route and land automatically
7. 🎉 **You now have a fully working autonomous drone with browser cockpit**

---

## Honest Timeline

| Phase | Time Needed |
|---|---|
| Buy hardware | 1-2 weeks |
| Build & wire drone | 1 weekend |
| Pixhawk + Pi setup | 1 evening |
| Indoor software sync test | 1 evening |
| First hover test | 1 afternoon |
| Full cockpit autonomous flight | 1 afternoon |
| **Total from zero to flying** | **~3-4 weeks** |

---

## ⚠️ 3 Rules To Not Crash It

1. **Always test indoors with NO PROPS first** — software bugs won't destroy hardware
2. **Never arm in AUTO mode** — always take off manually, then switch to auto
3. **Always have RC transmitter in hand** as override — cockpit is the brain, RC is the emergency brake

---

## Next Steps When Ready

| What you need | Ask for it |
|---|---|
| Python bridge file (Pi ↔ Pixhawk ↔ Browser) | "Write me the bridge script" |
| Rebuild cockpit for delivery dispatch | "Build the delivery version" |
| Geofence setup for CVS stores | "Add geofencing to the cockpit" |
| Chain of custody / drop confirmation | "Add delivery confirmation system" |
| 4G long-range setup | "How do I set up 4G telemetry" |

---

*APEX GCS — Built for CVS Drone Delivery POC*
*Stack: ArduPilot + MAVLink + Python + WebSocket + Browser*
*Hardware: Holybro S500 + Pixhawk 6C + Raspberry Pi 4*
