#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON="${PYTHON:-.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="python3"
fi

if ! "$PYTHON" -m PyInstaller --version >/dev/null 2>&1; then
  echo "[ERROR] PyInstaller is not installed."
  echo "[INFO] Run: $PYTHON -m pip install -r requirements-dev.txt"
  exit 1
fi

if [[ -z "${PTU_MAC_FFMPEG_DIR:-}" ]]; then
  FFMPEG_PATH="$(command -v ffmpeg || true)"
  FFPROBE_PATH="$(command -v ffprobe || true)"
  if [[ -n "$FFMPEG_PATH" && -n "$FFPROBE_PATH" ]]; then
    FFMPEG_DIR="$(dirname "$FFMPEG_PATH")"
    if [[ "$FFMPEG_DIR" == "$(dirname "$FFPROBE_PATH")" ]]; then
      export PTU_MAC_FFMPEG_DIR="$FFMPEG_DIR"
    fi
  fi
fi

if [[ -z "${PTU_MAC_FFMPEG_DIR:-}" ]]; then
  echo "[ERROR] Missing macOS FFmpeg/FFprobe directory."
  echo "[INFO] Put ffmpeg and ffprobe on PATH, or set PTU_MAC_FFMPEG_DIR=/path/to/bin"
  exit 1
fi

if [[ ! -x "$PTU_MAC_FFMPEG_DIR/ffmpeg" || ! -x "$PTU_MAC_FFMPEG_DIR/ffprobe" ]]; then
  echo "[ERROR] PTU_MAC_FFMPEG_DIR must contain executable ffmpeg and ffprobe."
  echo "[INFO] Current: $PTU_MAC_FFMPEG_DIR"
  exit 1
fi

rm -rf build/Ptu-macos dist/Ptu.app
"$PYTHON" -m PyInstaller --clean --noconfirm build_macos.spec

echo "[OK] Mac app output: dist/Ptu.app"
