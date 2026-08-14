# -*- coding: utf-8 -*-
"""showcase.config.json 로더.

**환경변수 → 파일 → 기본값** 순으로 덮는다. 파일에 없는 키가 있어도 기본값으로
메워지므로, 설정 파일을 갱신하지 않은 동료의 PC 에서도 그냥 돈다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("SHOWCASE_CONFIG") or (APP_DIR / "showcase.config.json"))

# ★ 내 PC 전용 값은 여기로 뺀다 — **배포본에 개인 절대경로가 나가면 안 된다.**
#   TTS 엔진 위치, 실측 보정값처럼 사람마다 다른 것이 여기 산다. gitignore 대상이고,
#   없으면 그냥 없는 대로 돈다(TTS 는 건너뛰고 덱·자막은 전부 나온다).
LOCAL_PATH = APP_DIR / "showcase.config.local.json"

DEFAULTS: Dict[str, Any] = {
    "port": 5178,
    "auth": "claude-code",
    "vision_mode": "inline",
    "models": {
        "caption": "claude-sonnet-5",
        "link": "claude-sonnet-5",
        "decisions": "claude-opus-5",
        "script": "claude-opus-5",
        "theme": "claude-opus-5",
    },
    "effort": {
        "caption": "medium", "link": "medium",
        "decisions": "high", "script": "high", "theme": "medium",
    },
    "budget_usd": {"per_stage": 1.5, "warn_total": 5.0},
    "frames": {
        "scene_threshold": 0.35, "anchor_interval": 8.0, "min_gap_sec": 1.5,
        "max_frames": 12, "display_width": 1600, "vision_width": 1024,
    },
    "narration": {"chars_per_sec": 3.0, "voice": "F2", "speed": 1.0, "total_step": 8},
    "tts": {"engine": "none", "python": None, "voicewright_dir": None,
            "assets_dir": None, "timeout_ms": 300000},
    "render": {"seed_hex": "#7a5cc0", "max_single_file_mb": 10,
               "single_file_audio": "opus32"},
}


def _deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


_cache: Dict[str, Any] | None = None


def load(force: bool = False) -> Dict[str, Any]:
    global _cache
    if _cache is not None and not force:
        return _cache
    file_cfg: Dict[str, Any] = {}
    if CONFIG_PATH.is_file():
        try:
            # ★ utf-8-sig — BOM 을 허용한다. 메모장이나 PowerShell 의
            #   Set-Content -Encoding UTF8 은 BOM 을 붙이는데, 순수 utf-8 로 읽으면
            #   "Unexpected UTF-8 BOM" 으로 통째로 터진다(실제로 겪음).
            file_cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"{CONFIG_PATH.name} 를 읽지 못했습니다: {e}") from e
    # 내 PC 전용 덮어쓰기 — 있으면 마지막에 이긴다
    local_cfg: Dict[str, Any] = {}
    if LOCAL_PATH.is_file():
        try:
            local_cfg = json.loads(LOCAL_PATH.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"{LOCAL_PATH.name} 를 읽지 못했습니다: {e}") from e

    cfg = _deep_merge(_deep_merge(DEFAULTS, file_cfg), local_cfg)
    if p := os.environ.get("PORT") or os.environ.get("SHOWCASE_PORT"):
        try:
            cfg["port"] = int(p)
        except ValueError:
            pass
    _cache = cfg
    return cfg


# 이 키들은 **사람마다 다른 값**이라 배포본이 아니라 local 파일로 간다
LOCAL_KEYS = {"tts"}


def save(patch: Dict[str, Any]) -> Dict[str, Any]:
    """설정 화면에서 바꾼 값만 덮어쓴다. 파일에 없던 키는 그대로 둔다.

    ★ `tts` 처럼 절대경로가 들어가는 키는 `showcase.config.local.json` 으로 보낸다.
      배포본 설정 파일에 내 PC 경로가 섞이면 동료가 받았을 때 엉뚱한 곳을 가리킨다.
    """
    local_patch = {k: v for k, v in (patch or {}).items() if k in LOCAL_KEYS}
    patch = {k: v for k, v in (patch or {}).items() if k not in LOCAL_KEYS}
    if local_patch:
        cur_local: Dict[str, Any] = {}
        if LOCAL_PATH.is_file():
            try:
                cur_local = json.loads(LOCAL_PATH.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError:
                cur_local = {}
        LOCAL_PATH.write_text(
            json.dumps(_deep_merge(cur_local, local_patch), ensure_ascii=False, indent=2),
            encoding="utf-8")

    cur: Dict[str, Any] = {}
    if CONFIG_PATH.is_file():
        try:
            cur = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            cur = {}
    merged = _deep_merge(cur, patch or {})
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_PATH)
    return load(force=True)
