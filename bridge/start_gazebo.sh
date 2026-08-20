#!/bin/bash
# ============================================================
#  APEX GCS — Start Gazebo 3D Sim + ArduPilot SITL + Bridge
#  Run every time:  ./start_gazebo.sh
# ============================================================

BRIDGE_DIR="$(cd "$(dirname "$0")" && pwd)"
ARDUPILOT_DIR="$HOME/ardupilot"
GAZEBO_PLUGIN_DIR="$HOME/ardupilot_gazebo"
WORLD_FILE="$BRIDGE_DIR/worlds/cvs_delivery.sdf"

echo "============================================================"
echo "  APEX GCS — Gazebo 3D Flight Simulator"
echo "============================================================"

# ── Check prerequisites ───────────────────────────────────────
if ! command -v gz &>/dev/null; then
  echo "❌ Gazebo not found. Run ./setup_gazebo.sh first."
  exit 1
fi
if [ ! -f "$ARDUPILOT_DIR/build/sitl/bin/arducopter" ]; then
  echo "❌ ArduCopter SITL binary not found. Run ./setup_gazebo.sh first."
  exit 1
fi
if [ ! -f "$GAZEBO_PLUGIN_DIR/build/libArduPilotPlugin.so" ] && \
   [ ! -f "$GAZEBO_PLUGIN_DIR/build/libArduPilotPlugin.dylib" ]; then
  echo "❌ Gazebo plugin not built. Run ./setup_gazebo.sh first."
  exit 1
fi

# ── Set Gazebo environment paths ──────────────────────────────
export GZ_SIM_SYSTEM_PLUGIN_PATH="$GAZEBO_PLUGIN_DIR/build:$GZ_SIM_SYSTEM_PLUGIN_PATH"
export GZ_SIM_RESOURCE_PATH="$GAZEBO_PLUGIN_DIR/models:$GAZEBO_PLUGIN_DIR/worlds:$BRIDGE_DIR/worlds:$GZ_SIM_RESOURCE_PATH"

echo ""
echo "[1/3] Starting Gazebo 3D world..."
echo "      World: $WORLD_FILE"
gz sim -v3 -r "$WORLD_FILE" &
GAZEBO_PID=$!
echo "      Gazebo PID: $GAZEBO_PID"

echo ""
echo "[2/3] Waiting 5s for Gazebo to initialize..."
sleep 5

echo ""
echo "[3a/3] Starting ArduCopter SITL (connected to Gazebo)..."
cd "$ARDUPILOT_DIR"
build/sitl/bin/arducopter \
  --model JSON \
  --home 40.7128,-74.0060,0,0 \
  --defaults "$GAZEBO_PLUGIN_DIR/config/gazebo-iris.parm" \
  -I0 &
SITL_PID=$!
echo "      ArduCopter SITL PID: $SITL_PID"

echo ""
echo "[3b/3] Waiting 3s for SITL to start..."
sleep 3

echo ""
echo "[3c/3] Starting MAVLink WebSocket bridge..."
python3 "$BRIDGE_DIR/bridge.py" --sitl tcp:127.0.0.1:5760 &
BRIDGE_PID=$!
echo "       Bridge PID: $BRIDGE_PID"

echo ""
echo "============================================================"
echo "  ✅  Everything running!"
echo "============================================================"
echo ""
echo "  🎮 Gazebo 3D window — fly your drone visually"
echo "  🌐 Cockpit: http://localhost:5500/drone-cockpit.html"
echo "  🔌 WebSocket: ws://localhost:5000"
echo ""
echo "  Controls in cockpit → joystick / keyboard arrows"
echo "  Gazebo shows 3D view simultaneously"
echo ""
echo "  Press Ctrl+C to stop everything."
echo ""

# ── Cleanup on exit ───────────────────────────────────────────
cleanup() {
  echo ""
  echo "[STOP] Shutting down..."
  kill $BRIDGE_PID $SITL_PID $GAZEBO_PID 2>/dev/null
  echo "[STOP] Done."
}
trap cleanup INT TERM

wait $BRIDGE_PID
