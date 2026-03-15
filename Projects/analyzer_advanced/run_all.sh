#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

source .venv/bin/activate

echo "=============================="
echo " Project Sentinel — Super People Behavioral Miner"
echo "=============================="
echo ""

echo "[1/3] Calibrating thresholds and HUD regions..."
python calibrate.py
echo ""

echo "[2/3] Running closed-loop behavioral analysis..."
python analyzer.py
echo ""

echo "[3/3] Generating final report..."
python report.py
echo ""

echo "=============================="
echo " Done."
echo " Outputs: behavior_timeline.json, final_report.json, highlights.txt"
echo "=============================="
