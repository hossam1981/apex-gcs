#!/bin/bash
# ============================================================
#  APEX GCS — Gazebo 3D Simulator Setup (Mac)
#  Run once: ./setup_gazebo.sh
# ============================================================
set -e

echo "============================================================"
echo "  APEX GCS — Gazebo + ArduPilot SITL Setup"
echo "============================================================"

# ── 1. Homebrew ───────────────────────────────────────────────
if ! command -v brew &>/dev/null; then
  echo "[1/6] Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
  echo "[1/6] Homebrew already installed ✓"
fi

# ── 2. Gazebo Harmonic ────────────────────────────────────────
if ! command -v gz &>/dev/null; then
  echo "[2/6] Installing Gazebo Harmonic (this takes ~5 min)..."
  brew tap osrf/simulation
  brew install gz-harmonic
else
  echo "[2/6] Gazebo already installed ✓ ($(gz --version 2>/dev/null | head -1))"
fi

# ── 3. ArduPilot source ───────────────────────────────────────
if [ ! -d "$HOME/ardupilot" ]; then
  echo "[3/6] Cloning ArduPilot (~500 MB, takes a few min)..."
  git clone --recurse-submodules https://github.com/ArduPilot/ardupilot.git "$HOME/ardupilot"
else
  echo "[3/6] ArduPilot source already at ~/ardupilot ✓"
fi

# ── 4. ArduPilot Mac dependencies ────────────────────────────
echo "[4/6] Installing ArduPilot build dependencies..."
cd "$HOME/ardupilot"
# Install required packages via brew
brew install python3 gcc cmake pkg-config genromfs || true
pip3 install empy==3.3.4 pexpect future --quiet || true

# ── 5. ardupilot_gazebo plugin ───────────────────────────────
if [ ! -d "$HOME/ardupilot_gazebo" ]; then
  echo "[5/6] Cloning ardupilot_gazebo plugin..."
  git clone https://github.com/ArduPilot/ardupilot_gazebo.git "$HOME/ardupilot_gazebo"
else
  echo "[5/6] ardupilot_gazebo plugin already at ~/ardupilot_gazebo ✓"
fi

echo "[5/6] Building ardupilot_gazebo plugin..."
cd "$HOME/ardupilot_gazebo"
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo 2>&1 | tail -5
make -j$(sysctl -n hw.ncpu) 2>&1 | tail -10
echo "      Plugin built ✓"

# ── 6. Build ArduCopter SITL ─────────────────────────────────
echo "[6/6] Configuring ArduCopter SITL build (first time is slow ~10 min)..."
cd "$HOME/ardupilot"
./waf configure --board sitl 2>&1 | tail -5
./waf copter 2>&1 | tail -10
echo "      ArduCopter SITL built ✓"

# ── Done ──────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  ✅  Setup complete!"
echo "============================================================"
echo ""
echo "  Next step — run the simulator:"
echo "    cd /Users/hossamelnaggar/Downloads/drone/bridge"
echo "    ./start_gazebo.sh"
echo ""
echo "  Then open the cockpit:"
echo "    http://localhost:5500/drone-cockpit.html"
echo "    WebSocket URL: ws://localhost:5000"
echo ""
