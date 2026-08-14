#!/usr/bin/env bash
# Developer Present Agent - first-time setup (macOS / Linux)
set -u
cd "$(dirname "$0")"

echo "== Developer Present Agent - first-time setup =="
echo

command -v python3 >/dev/null 2>&1 || { echo "[ERROR] Python 3.10+ is required."; exit 1; }
command -v ffmpeg  >/dev/null 2>&1 || echo "[WARN] ffmpeg not found - frame extraction will not work."
command -v gh      >/dev/null 2>&1 || echo "[WARN] gh CLI not found - repo collection will not work."

echo "[1/4] console env (.venv-app)"
[ -x ".venv-app/bin/python" ] || python3 -m venv .venv-app || { echo "[ERROR] venv creation failed."; exit 1; }
.venv-app/bin/python -m pip install --quiet --upgrade pip
.venv-app/bin/python -m pip install --quiet -e . || { echo "[ERROR] dependency install failed."; exit 1; }

echo "[2/4] fonts"
.venv-app/bin/python tools/get_fonts.py || echo "[WARN] font download failed - the page will fall back to a system font."

echo "[3/4] TTS engine (voicewright / Supertonic-3)"
echo "       voicewright's installer is Windows-only today (install.bat)."
echo "       Skipping on this OS - deck/subtitles still work, narration audio will not."
.venv-app/bin/python tools/wire_tts.py

echo "[4/4] connection check"
if ! .venv-app/bin/python scripts/smoke_claude.py --only text; then
  echo
  echo "[WARN] Claude Code login needed. Run \"claude\" once in a terminal, then retry."
fi

echo
echo "Done. Start with:  ./run.sh"
