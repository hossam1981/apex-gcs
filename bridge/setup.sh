#!/bin/bash
# APEX GCS — One-time Mac setup for ArduPilot SITL + Python bridge
# Run once: chmod +x setup.sh && ./setup.sh

set -e

echo "========================================"
echo "  APEX GCS — SITL Bridge Setup (Mac)"
echo "========================================"

# 1. Homebrew check
if ! command -v brew &>/dev/null; then
  echo "[1/5] Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
  echo "[1/5] Homebrew already installed ✓"
fi

# 2. Python 3 check
if ! command -v python3 &>/dev/null; then
  echo "[2/5] Installing Python 3..."
  brew install python
else
  echo "[2/5] Python 3 already installed: $(python3 --version) ✓"
fi

# 3. pip packages
echo "[3/5] Installing Python packages..."
pip3 install --upgrade pip
pip3 install pymavlink==2.4.41 websockets==12.0 dronekit-sitl==3.3.0

# 4. ArduPilot SITL binary via dronekit-sitl
echo "[4/5] Downloading ArduPilot SITL copter binary..."
python3 -c "
import dronekit_sitl
sitl = dronekit_sitl.start_default(lat=40.7128, lon=-74.0060)
print('  SITL binary ready at:', sitl.path)
sitl.stop()
"

echo "[5/5] All done!"
echo ""
echo "========================================"
echo "  To start the bridge + SITL, run:"
echo "  python3 start_sitl.py"
echo ""
echo "  Then open in Chrome:"
echo "  http://localhost:5500/drone-cockpit.html"
echo "  (make sure the HTTP server is running)"
echo "========================================"
