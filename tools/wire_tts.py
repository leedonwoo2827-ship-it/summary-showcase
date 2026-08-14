# -*- coding: utf-8 -*-
"""voicewright 설치 여부를 보고 showcase.config.local.json 의 tts 를 채운다.

이 프로젝트 자신의 `voicewright/` 서브폴더만 본다 — 다른 프로젝트의 절대경로를
쓰지 않는다(다른 PC에 새로 셋업해도 항상 이 폴더 기준으로 다시 잡힌다). 설치가
안 됐으면 tts.engine 을 "none" 으로 둔다 — 파이프라인은 음성 없이도 덱·자막·
큐시트가 전부 나온다.
"""
from __future__ import annotations

from pathlib import Path

from core import config

APP = Path(__file__).resolve().parent.parent
VW_DIR = APP / "voicewright"
PY = VW_DIR / ".venv" / "Scripts" / "python.exe"
ASSETS = VW_DIR / "assets"
VOCODER = ASSETS / "onnx" / "vocoder.onnx"


def main() -> None:
    if PY.is_file() and VOCODER.is_file():
        config.save({"tts": {
            "engine": "voicewright",
            "python": str(PY),
            "voicewright_dir": str(APP),
            "assets_dir": str(ASSETS),
            "timeout_ms": 300000,
        }})
        print(f"[tts] voicewright wired: {PY}")
    else:
        config.save({"tts": {"engine": "none", "python": None,
                              "voicewright_dir": None, "assets_dir": None}})
        if VW_DIR.is_dir():
            print("[tts] voicewright is cloned but not installed yet — "
                  "run voicewright\\install.bat once, then re-run setup.bat")
        else:
            print("[tts] voicewright not found — narration audio will be skipped "
                  "(deck/subtitles still work)")


if __name__ == "__main__":
    main()
