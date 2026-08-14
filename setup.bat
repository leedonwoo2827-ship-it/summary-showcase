@echo off
setlocal
cd /d "%~dp0"

echo == Developer Showcase Agent - first-time setup ==
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python 3.10+ is required and was not found on PATH.
  goto :fail
)

where ffmpeg >nul 2>&1
if errorlevel 1 echo [WARN] ffmpeg not on PATH - frame extraction will not work.
where gh >nul 2>&1
if errorlevel 1 echo [WARN] gh CLI not on PATH - repo collection will not work.

echo [1/3] console env (.venv-app)
if not exist ".venv-app\Scripts\python.exe" python -m venv .venv-app
if errorlevel 1 (echo [ERROR] venv creation failed. & goto :fail)
".venv-app\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv-app\Scripts\python.exe" -m pip install --quiet -e .
if errorlevel 1 (echo [ERROR] dependency install failed. & goto :fail)

echo [2/3] TTS engine (voicewright / Supertonic-3)
if not exist "voicewright\install.bat" (
  where git >nul 2>&1
  if errorlevel 1 (
    echo        [WARN] git not on PATH - skipping voicewright. Narration audio will be unavailable.
    goto :tts_wire
  )
  echo        cloning voicewright into .\voicewright ...
  git clone --quiet https://github.com/leedonwoo2827-ship-it/voicewright.git voicewright
  if errorlevel 1 echo        [WARN] clone failed - continuing without TTS.
)
if exist "voicewright\.venv\Scripts\python.exe" if exist "voicewright\assets\onnx\vocoder.onnx" (
  echo        voicewright already installed.
) else if exist "voicewright\install.bat" (
  echo        voicewright is cloned but not installed yet.
  echo        Run voicewright\install.bat once ^(needs git-lfs, downloads ~250MB, 5-10 min^),
  echo        then re-run this setup.bat to finish wiring it in.
)
:tts_wire
".venv-app\Scripts\python.exe" tools\wire_tts.py

echo [3/3] connection check
".venv-app\Scripts\python.exe" scripts\smoke_claude.py --only text
if errorlevel 1 (
  echo.
  echo [WARN] Claude Code login needed. Run "claude" once in a terminal, then retry.
)

echo.
echo Setup complete. Start with run.bat
echo.
pause
exit /b 0

:fail
echo.
echo Setup did not finish. The message above says why.
pause
exit /b 1
