# -*- coding: utf-8 -*-
"""유튜브 썸네일 지시문 — **스튜디오가 바로 먹는 꼴로 두 벌.**

예전에는 원고 한 장(`유튜브썸네일-원고.txt`)을 내고, 사람이 그것을 스튜디오의
「프롬프트 생성기」에 넣어 프롬프트를 **다시 짓게** 했다. 한 다리를 더 건너는
만큼 결이 그때그때 달라졌다 — 어떤 판은 차콜 글자, 어떤 판은 남색 글자가 됐다.

★ **두 벌을 낸다.** 사람이 둘을 뽑아 보고 고른다(2026-08-17: "후킹형인가
  감성형인가 이렇게 2개를 제가 손수 굽습니다"). 어느 쪽이 나을지는 장마다
  달라서 기계가 고를 일이 아니다.

    후킹형   "무엇을 재는 숫자일까" 하는 궁금증을 준다. 강조색을 조금 더 쓴다
    차분형   신뢰감·전문성. 절제된 색, 정돈된 학습용 비주얼

★ 슬라이드 그림과 **다른 규격**이다. 그림은 3:2(1536×1024)에 플랫 벡터인데,
  썸네일은 16:9 에 클레이메이션이다. 그래서 봉투를 따로 낸다 — 한 봉투에 섞으면
  `style_hint` 가 전 장에 덧붙어 슬라이드 그림까지 점토로 나온다.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from render.youtube import _headline

# 썸네일은 클레이메이션이다 — 슬라이드 그림(플랫 벡터)과 결을 일부러 가른다.
# 목록에서 눈에 걸려야 하고, 그 안은 차분해야 한다.
STYLE = ("스톱모션 퍼핏 / 클레이메이션 — 점토·펠트 질감의 미니어처 세트, "
         "손으로 빚은 듯한 형태, 실사 조명, 부드러운 그림자, 얕은 심도")

# ★ 두 벌의 차이는 **무드 한 줄**뿐이다. 장면·색·글자 규칙은 같아야 한다 —
#   둘이 통째로 다르면 고르는 것이 아니라 딴 그림 둘이 된다.
MOODS = [
    ("후킹형", "「무엇을 재는 숫자일까」 하는 궁금증을 주는 무드. 다만 과장된 "
               "광고 느낌은 피하고, 장면 자체가 질문을 던지게 한다"),
    ("차분형", "신뢰감 있고 전문적인 무드. 과한 장식이나 캐릭터성을 피하고 "
               "정돈된 학습용 비주얼을 유지한다"),
]


def _subjects(deck: Dict[str, Any], led: Dict[str, Any], n: int = 8) -> List[str]:
    """그 영상이 다루는 것 — 라벨 헤드라인에서 뽑는다. 장면 재료가 된다."""
    out: List[str] = []
    for s in (deck.get("slides") or []):
        if s.get("drop"):
            continue
        h = _headline(s, led)
        if h and h not in out:
            out.append(h)
    return out[:n]


def _line(t: Any, n: int) -> str:
    return re.sub(r"\s+", " ", str(t or "")).strip()[:n]


def prompts(deck: Dict[str, Any], *, title: str, cfg: Dict[str, Any],
            led: Optional[Dict] = None, book: str = "") -> List[Dict[str, Any]]:
    """썸네일 지시문 두 벌. 슬라이드 지시문과 같은 행 모양으로 낸다."""
    led = led or {}
    img = cfg["image"]
    bg = img.get("bg", "#F6F1E8")
    subs = _subjects(deck, led)
    # ★ 썸네일에 박히는 글자는 **한 줄**이다. 장 제목보다 그 장의 첫 헤드라인이
    #   짧고 세다 — 목록에서 읽히는 것은 그쪽이다.
    word = subs[0] if subs else (title or "")
    scene = " · ".join(subs[:5]) or title

    rows: List[Dict[str, Any]] = []
    for i, (kind, mood) in enumerate(MOODS, 1):
        lines = [
            # 바탕을 맨 앞에 — 슬라이드 지시문과 같은 이유다(s3a_imgprompt 주석)
            f"바탕: 화면 전체를 밝은 아이보리({bg})로 고르게 칠한다. "
            "어두운 배경·검정 판·야간 장면·비네팅·발광 금지",
            f"장면: {STYLE}. 사물 배치만으로 뜻을 전한다 — "
            f"이 영상이 다루는 것은 {_line(scene, 180)}",
            "구도: 가로 16:9. 장면이 주인공이고 글자는 얹는 것이다. "
            "미니어처 오브젝트를 가운데와 아래에 풍성하게 두고, "
            "약간 위에서 내려다보는 3/4 각도. 글자가 앉을 위쪽 한쪽 구석을 비운다",
            f"색: 진한 파랑({img['accent_a']})과 밝은 파랑({img['accent_b']})을 "
            "사물에, 글자는 차콜(#2B2B2B). 바탕은 위에 적은 아이보리",
            f"무드: {mood}",
            f'글자(한 줄만, 굵은 산세리프, 크지 않게, 위쪽 한쪽 구석): "{_line(word, 24)}"',
            "넣지 마라: 보조문구·말풍선·숫자 설명·로고·실존 인물·사람 얼굴. "
            "글자가 화면을 지배하거나 한가운데를 가리면 안 된다",
        ]
        rows.append({
            "n": i,
            "title": f"{kind} — {_line(word, 24)}",
            "type": "photo",
            "level": "이해",
            "prompt": "\n".join(lines),
            "negative": img.get("negative", ""),
            "keywords": [kind],
            "place": True,
            "file": f"썸네일-{kind}.png",
            "data_id": f"thumb-{kind}",
        })
    return rows


def bundle(deck: Dict[str, Any], *, title: str, cfg: Dict[str, Any],
           led: Optional[Dict] = None, book: str = "") -> Dict[str, Any]:
    """스튜디오가 먹는 봉투. 슬라이드 쪽과 **같은 아홉 칸**이되 규격이 다르다."""
    rows = prompts(deck, title=title, cfg=cfg, led=led, book=book)
    return {
        "deck": f"{book} {title}".strip() + " (썸네일)",
        # ★ 여기에는 **문체만.** 장마다 다른 글을 넣으면 스튜디오가 전 항목에
        #   덧붙인다(슬라이드 쪽에서 27장이 같은 헤드라인을 이고 나온 적이 있다).
        "style_hint": STYLE,
        "aspect": "landscape",
        "target_box": "16:9 (1536×864) youtube thumbnail",
        "count": len(rows),
        "deck_slides": len([s for s in (deck.get("slides") or []) if not s.get("drop")]),
        "photos_found": 0,
        "file_naming": ("썸네일-후킹형.png · 썸네일-차분형.png 로 저장하세요. "
                        "둘을 견줘 보고 하나를 고릅니다."),
        "prompts": rows,
    }
