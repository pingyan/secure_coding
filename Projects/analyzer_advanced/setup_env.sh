#!/usr/bin/env bash
set -euo pipefail

echo "==> Creating virtual environment..."
python3 -m venv .venv

echo "==> Upgrading pip..."
.venv/bin/pip install --upgrade pip

echo "==> Installing PyTorch (CPU wheel — MPS auto-detected at runtime)..."
.venv/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

echo "==> Installing project dependencies..."
.venv/bin/pip install -r requirements.txt

echo ""
echo "==> Verifying imports..."
.venv/bin/python -c "import librosa, ultralytics, easyocr, cv2; print('All imports OK')"

echo ""
echo "Setup complete. Activate with: source .venv/bin/activate"
