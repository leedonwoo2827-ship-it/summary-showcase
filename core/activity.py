# -*- coding: utf-8 -*-
"""최근 한 일 — **무엇을 이미 했고, 무엇을 다시 해야 하는가.**

이 툴에서 가장 자주 잃는 감각이 이것이다(2026-08-14 지적):

    "하다 보면 영상을 렌더링한 건지 그 앞선 슬라이드를 렌더링한 건지,
     뭘 다시 해야 하는지 잘 모르겠더라고요."

단계가 열여섯 개인데 각 단계는 자기 상태만 알고, 산출물은 폴더 깊이 흩어져 있다.
현황판(`/board`)은 **지금 상태**를 보여 주지만 **시간 순서**를 안 보여 준다 —
"방금 무엇을 눌렀나" 는 거기서 안 읽힌다.

여기서는 시간 순서로 한 줄씩 모은다. 근거는 두 갈래다.

    한 일   `_cache/{단계}.json` 의 `at`(없으면 파일 시각) + 산출물 파일 시각
    할 일   지금 낡은(stale) · 아직 안 돈(missing) 단계

★ **새로 기록하지 않는다.** 별도 이력 파일을 두면 그것이 진실과 어긋나는 순간이
  온다(사람이 폴더를 지우거나 캐시만 되돌리는 일이 실제로 있다). 이미 디스크에
  있는 것만 읽어서 만든다 — 그러면 목록이 항상 실제와 같다.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import workspace as ws
from pipeline.registry import ORDER, STAGES, read_cache, stage_states

# 산출물 — 무엇을 만든 것인지 사람 말로. 이게 "영상인지 슬라이드인지" 를 가른다.
DIST = [
    (".html", "슬라이드 한 장 파일", "메일·USB 로 보내면 그대로 열립니다"),
    (".mp4", "영상", "슬라이드와 내레이션을 이어 붙인 mp4"),
]


def _when(p: Path) -> Optional[str]:
    try:
        return datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        return None


def _mb(p: Path) -> float:
    try:
        return round(p.stat().st_size / 1048576, 1)
    except OSError:
        return 0.0


def build(pid: int, slug: str, project: Dict[str, Any], *,
          limit: int = 40) -> Dict[str, Any]:
    root = ws.project_dir(pid, slug)
    done: List[Dict[str, Any]] = []

    # ── 돌린 단계 ──────────────────────────────────────────────────────────
    cdir = ws.cache_dir(pid, slug, create=False)
    for key in ORDER:
        env = read_cache(pid, slug, key)
        if not env:
            continue
        at = env.get("at") or _when(cdir / f"{key}.json")
        if not at:
            continue
        st = STAGES[key]
        done.append({
            "at": at, "kind": "stage", "key": key, "label": st.label,
            "status": env.get("status") or "ok",
            "cost_usd": env.get("cost_usd") or 0.0,
            "model": env.get("model") or "",
            "note": _stage_note(key, env.get("data")),
            "warn": len(env.get("warnings") or []),
        })

    # ── 만든 것 ────────────────────────────────────────────────────────────
    # ★ 여기가 핵심이다. "영상을 냈나 슬라이드를 냈나" 는 단계 목록이 아니라
    #   **파일이 언제 생겼나**로만 확실히 알 수 있다. 단계는 성공했는데 파일이
    #   안 나온 경우도 있어서(중간에 껐다든지), 파일 쪽을 따로 본다.
    dist = root / ws.STEPS["dist"][0]
    if dist.is_dir():
        for f in sorted(dist.iterdir()):
            if not f.is_file():
                continue
            hit = next((d for d in DIST if f.name.lower().endswith(d[0])), None)
            if not hit:
                continue
            at = _when(f)
            if at:
                done.append({"at": at, "kind": "dist", "key": f.name,
                             "label": hit[1], "note": hit[2],
                             "mb": _mb(f), "status": "ok"})

    # 손편집 — 눌러서 돌린 게 아니라 사람이 고친 것. 이것도 "한 일" 이다.
    ovp = ws.overrides_path(pid, slug, create=False)
    at = _when(ovp)
    if at:
        ov = ws.read_json(ovp, {}) or {}
        n = len(ov.get("slides") or {})
        done.append({"at": at, "kind": "hand", "key": "overrides",
                     "label": "손으로 고침", "status": "ok",
                     "note": f"{n}장" if n else "설정"})

    done.sort(key=lambda r: r["at"], reverse=True)

    # ── 다시 해야 할 것 ────────────────────────────────────────────────────
    # ★ **낡은 것만** 올린다. "아직 안 돈 단계" 는 여기 섞지 않는다 — 발표 하나에
    #   열여섯 단계가 다 필요한 경우는 거의 없고(영상이 없으면 프레임 추출은
    #   영영 안 돈다), 그것들이 늘 목록에 앉아 있으면 목록 자체를 안 보게 된다.
    #   여기서 답할 질문은 "무엇을 **다시** 해야 하나" 이고, 그 답은 낡은 것뿐이다.
    #   아직 안 한 것은 숫자만 세어 현황판으로 보낸다.
    todo: List[Dict[str, Any]] = []
    pending = 0
    for st in stage_states(pid, slug, project):
        if not st["implemented"] or st["blocked"]:
            continue
        if st["state"] == "stale":
            todo.append({"key": st["key"], "label": st["label"],
                         "state": "stale", "kind": st["kind"]})
        elif st["state"] == "missing":
            pending += 1

    return {"done": done[:limit], "todo": todo, "pending": pending,
            "spent_usd": round(sum(r.get("cost_usd") or 0 for r in done), 4)}


def _stage_note(key: str, data: Any) -> str:
    """그 단계가 **무엇을 냈는지** 한 줄로. 숫자가 없으면 빈 문자열 — 억지로 쓰지
    않는다(할 말 없는 줄이 목록의 절반이면 목록을 안 읽게 된다)."""
    if not isinstance(data, dict):
        return ""
    if key == "s2c-capture":
        n, m = data.get("slides"), data.get("mode")
        way = {"html": "원고 그대로", "image": "화면 캡처"}.get(m, "")
        line = f"{n}장" if n else ""
        if data.get("html_slides"):
            line += f" · 원고 {data['html_slides']}장(줄 {data.get('lines') or 0})"
        return (line + (f" · {way}" if way else "")).strip(" ·")
    if key == "s2b-outline":
        n = len(data.get("slides") or [])
        return f"{n}장" if n else ""
    if key == "s10-tts":
        n = len(data.get("slides") or {})
        t = data.get("total_sec")
        return f"{n}장" + (f" · {int(t // 60)}분 {int(t % 60)}초" if t else "")
    if key == "s11-audio":
        n = len(data.get("slides") or {})
        return f"{n}장 큐시트" if n else ""
    if key in ("s1-frames", "s3-caption"):
        n = len(data.get("items") or {})
        return f"영상 {n}개" if n else ""
    for k in ("slides", "images"):
        v = data.get(k)
        if isinstance(v, dict) and v:
            return f"{len(v)}장"
        if isinstance(v, int) and v:
            return f"{v}장"
    return ""
