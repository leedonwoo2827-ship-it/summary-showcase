# -*- coding: utf-8 -*-
"""S3a 그림 지시문 — **원장에 없는 장만 만든다.**

이 단계의 핵심은 **안 부르는 것**이다. 세 겹으로 안 부른다.

    1. 원고가 `data-img` 를 들고 왔으면      → 그것을 쓴다. Claude 를 안 부른다
    2. 원장에 있고 몸통 해시가 같으면        → 옛 프롬프트를 쓴다. 안 부른다
    3. 그 밖에만                              → Claude 에게 쓰게 한다

값을 아끼려는 게 아니다. **같은 장의 프롬프트가 이유 없이 바뀌면 이미 그려 둔
그림과 어긋난다.** 원고를 고쳐 번호가 밀렸을 뿐인 장까지 다시 그리게 되면, 장
하나 끼워 넣은 값이 스물네 장을 다시 그리는 값이 된다.

★ ①이 가장 중요하다. 작가 에이전트가 원고를 쓰면서 **같은 몸통을 보고** 그림
  지시문을 같이 썼다. 여기서 제목·본문을 다시 읽어 조립하면 화면 문구와 그림이
  따로 논다 — 같은 단계에서 같은 몸통을 본 쪽이 늘 더 맞다.

★ 문체(`style_hint`)와 「글자 없음」 꼬리는 **코드가 붙인다.** 모델이 매번 다시
  쓰게 두면 장마다 조금씩 달라져서 한 덱 안에서 그림 결이 갈린다.

원장은 `09_이미지/원장.json` 이고 키는 **이름표**다(`core/ledger.py`). 번호는
내보낼 때(S3b) 처음 매긴다.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from core import config, ledger as lg, workspace as ws
from llm.claude_provider import ClaudeProvider
from pipeline.registry import STAGES, cached_data, write_cache

BATCH = 10
LEVELS = ("기억", "이해", "적용", "분석", "평가", "창조")

# ★ 프롬프트 **모양**의 판번호. 원장은 「몸통이 안 바뀌면 다시 안 만든다」로 도는데,
#   프롬프트 꼴 자체가 바뀌면 몸통은 그대로여도 옛 프롬프트를 쓰면 안 된다.
#   판번호가 다른 칸은 다시 만든다.
#     1  영어 · 「글자 없음」 삽화 (2026-08-14 오전)
#     2  한국어 다섯 칸 · 헤드라인/서브카피가 그림에 박힘 (2026-08-14 저녁)
#     3  + 글자 크기 못박기(헤드라인 8~10%) · 「안 잘린다, 네 귀퉁이까지 채워라」
#     4  + 「원고 제목을 헤드라인에 다시 쓰지 마라」 · 헤드라인 더 작게(6~8%)
#     5  + 라벨 2~4개를 사물 둘레에 · 배치 여섯 갈래 · 글자 세 단 크기
#     6  + 라벨마다 **몇 번째 문장에서 말하는지**(`say_i`) · 말하는 차례로 적기
#        ★ 19장에서 겪은 것 때문이다. 그림이 한 판으로 오면 「어디에 무슨 글자가
#          있는지」가 사라져서, 뒤에서 상자를 오려 읽어 되찾아야 했다. 31장 중
#          25장이 라벨을 좌우로 두어 위→아래 정렬로는 차례가 안 정해졌고,
#          2.4 장은 제일 먼저 말하는 「목표」가 화면 맨 아래라 마지막에 떴다.
#          만들 때 적어 두면 되찾을 일이 없다(2026-08-17 지시: "20장 할 때
#          깔끔하게 나오게 수정을 해둬").
PROMPT_FMT = 6

# 그림이 들어갈 수 있는 레인.
#   html        원고 장 — 몸통을 그림 한 판으로 갈아끼운다
#   text_image  예전 캡처 레인 — 글 옆에 그림이 붙는다
WANT_MEDIA = ("html", "text_image", "thumb")

# ★ 라벨을 벌려 놓는 여섯 갈래. 본보기(NotebookLM 슬라이드 20쪽)를 재어 보니
#   이 여섯이 되풀이된다. 「알아서 배치하라」고 두면 죄다 상단에 몰아 놓는다.
#   값은 곧 프롬프트에 적히는 자리 지시다(아래 `_PLACE`).
ARRANGE = ("좌우", "세로삼단", "아래삼등분", "사방", "가로흐름", "가운데위")

# 갈래마다 라벨이 앉는 자리. 라벨 수가 모자라면 앞에서부터 쓴다.
# ★ 갈래마다 **다섯~여섯 자리**를 둔다. 긴 장은 라벨이 더 필요한데(아래 `want_n`)
#   자리가 셋뿐이면 넷째부터 갈 데가 없다.
_PLACE: Dict[str, List[str]] = {
    # ★ 좌우는 **번갈아** 앉힌다. 왼쪽 셋을 먼저 채우면 「좌우로 나눈다」가 깨진다
    "좌우":       ["왼쪽 가운데", "오른쪽 위", "오른쪽 아래",
                   "왼쪽 위", "왼쪽 아래", "오른쪽 가운데"],
    "세로삼단":   ["오른쪽 위", "오른쪽 가운데", "오른쪽 아래",
                   "왼쪽 위", "왼쪽 아래"],
    "아래삼등분": ["아래 왼쪽", "아래 가운데", "아래 오른쪽",
                   "위 왼쪽", "위 오른쪽"],
    "사방":       ["왼쪽 위", "오른쪽 위", "왼쪽 아래", "오른쪽 아래",
                   "가운데 위", "가운데 아래"],
    "가로흐름":   ["아래 왼쪽", "아래 가운데 왼쪽", "아래 가운데 오른쪽",
                   "아래 오른쪽", "위 왼쪽", "위 오른쪽"],
    "가운데위":   ["가운데 위", "왼쪽 아래", "오른쪽 아래",
                   "왼쪽 가운데", "오른쪽 가운데"],
}

# 라벨 수 — 그 장이 **몇 초짜리냐**에 맞춘다. 사람이 라벨을 하나씩 밝히며
# 이야기를 끄는데, 45초 장에 셋뿐이면 한 라벨이 십오 초씩 버텨야 한다.
# 대략 **열 초에 하나**로 잡고 셋~여섯 사이로 묶는다.
LABEL_MIN, LABEL_MAX = 3, 6
SEC_PER_LABEL = 10.0


def say_sentences(say: str) -> List[str]:
    """대본을 문장으로 쪼갠다. **번호가 곧 말하는 차례다.**

    ★ 나중에 음성이 나오면 자막(`08_자막/NNN.srt`)이 거의 이 단위로 끊긴다.
      그래서 여기서 매긴 번호가 그대로 「몇 초에 뜨는가」로 이어진다.
    """
    t = re.sub(r"\s+", " ", str(say or "")).strip()
    if not t:
        return []
    return [x.strip() for x in re.split(r"(?<=[.!?。])\s+", t) if x.strip()]


def _say_lines(say: str) -> str:
    ss = say_sentences(say)
    if not ss:
        return "  (없음)"
    return "\n".join(f"  {i}. {x}" for i, x in enumerate(ss, 1))


def want_n(say: str, cps: float = 5.7) -> int:
    """이 장에 라벨을 몇 개 쓸까. 대본 길이로 어림한다."""
    n = len(re.sub(r"\s", "", str(say or "")))
    sec = n / max(cps, 0.1)
    return max(LABEL_MIN, min(LABEL_MAX, round(sec / SEC_PER_LABEL)))
# 순서가 있는 갈래 — 라벨 사이에 화살표를 넣게 한다
_FLOW = ("가로흐름",)

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "prompts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "data_id": {"type": "string"},
                    "level": {"type": "string", "enum": list(LEVELS)},
                    "background": {"type": "string"},
                    "layout": {"type": "string"},
                    "tone": {"type": "string"},
                    # 그림 안에 인쇄될 글자. **이것도 쓴다** — 원고 문장을 그대로
                    # 옮기면 길고 딱딱해서 카드가 안 된다(원고는 읽는 글, 이건 보는 글).
                    "title": {"type": "string"},
                    # ★ **라벨을 여러 개 받는다.** 제목 한 줄만 박힌 그림은 45초
                    #   동안 화면에 볼 것이 없다 — 마스킹으로 하나씩 밝힐 덩어리가
                    #   없어서다(2026-08-16 요청). 사물 둘레에 흩어 놓는다.
                    "labels": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "head": {"type": "string"},   # 굵은 소제목 6~12자
                                "body": {"type": "string"},   # 설명 2~3줄
                                # ★ **몇 번째 문장에서 말하는가**(1부터). 0=못 정함.
                                #   이것이 나중에 「글자가 언제 떠야 하나」가 된다.
                                "say_i": {"type": "integer"},
                            },
                            "required": ["head", "body", "say_i"],
                            "additionalProperties": False,
                        },
                    },
                    # 라벨을 어떻게 벌려 놓을까 — 그 장이 말하는 꼴에 맞춰 고른다
                    "arrange": {"type": "string", "enum": list(ARRANGE)},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["data_id", "level", "background", "layout", "tone",
                             "title", "labels", "arrange", "keywords"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["prompts"],
    "additionalProperties": False,
}


def _one(t: Any, n: int) -> str:
    """한 줄로 눌러 담는다. 프롬프트는 칸마다 한 줄이라 줄바꿈이 들어가면 칸이 깨진다."""
    return re.sub(r"\s+", " ", str(t or "")).strip()[:n]


def compose(*, background: str, layout: str, tone: str, title: str,
            labels: List[Dict[str, Any]], arrange: str,
            cfg: Dict[str, Any]) -> str:
    """이미지 스튜디오가 그대로 먹는 **한국어 프롬프트.**

    ★ 이 그림은 **글자를 넣는 그림**이다. 예전엔 정반대였다 — 영어로 「no text」를
      세 겹으로 걸었다. 그림이 몸통을 대신하는데 글자가 없으면 그 장이 말하려던
      것이 통째로 사라진다(2026-08-14 실측: 제목 한 줄만 남고 문단·불릿·타임라인이
      전부 없어졌다).

    ★ **제목 한 줄로는 모자란다.** 한 장이 45초씩 가는데 화면에 읽을 것이 그것뿐이면
      말만 길고 볼 것이 없다. 사람이 그 구간에 마스킹 효과를 거는데, 걸 덩어리가
      없어서 장당 세 개(대부분 제목)밖에 안 잡혔다(2026-08-16 요청).
      그래서 **사물 둘레에 라벨을 흩어 놓는다** — 굵은 소제목 + 설명 두세 줄.

    ★ 자리를 **갈래로 못박는다.** 「알아서 배치하라」고 두면 죄다 상단에 몰아 놓는다.
      본보기(NotebookLM 슬라이드)를 재어 보니 여섯 갈래가 되풀이됐다(`ARRANGE`).
    """
    img = cfg["image"]
    # ★ **「중심」이라고 쓰지 않는다.** 그 낱말은 "이 색으로 화면을 채우라" 로
    #   읽힌다. 실제로 원하는 것은 *글자와 강조에* 그 파랑을 쓰라는 것이다.
    tone = _one(tone, 220) or (
        f"글자와 강조에 진한 파랑({img['accent_a']})과 밝은 파랑({img['accent_b']}), "
        "본문 글자는 슬레이트(#334155), 플랫 벡터에 은은한 입체감")
    arrange = arrange if arrange in ARRANGE else "좌우"
    spots = _PLACE[arrange]

    lines = [
        # ★ **바탕을 맨 앞 독립된 줄로.** 예전에는 색/톤 줄 **끝에** 붙였는데,
        #   모델은 그 줄을 앞에서부터 읽어 "진한 파랑" 을 먼저 만나면 그것을
        #   화면의 지배색 = 배경으로 잡아 버린다. 뒤에 오는 "바탕은 아이보리" 는
        #   이미 정해진 배경을 못 뒤집는다. 그래서 **대부분 맞다가 간혹 뒤집히는**
        #   산발적 실패가 났다(2026-08-16 003 · 2026-08-17 20장의 006·010).
        # ★ 검정만 막으면 **비네팅·어두운 그라데이션·발광**으로 빠져나간다.
        #   결과는 똑같이 글자가 묻힌다 — 006 이 그 경우였다. 같이 막는다.
        f"바탕: 화면 전체를 밝은 아이보리({img.get('bg', '#F6F1E8')}) 단색으로 고르게 "
        "칠한다 — 네 귀퉁이와 가장자리까지 같은 밝기다. 어두운 배경·검정 판·"
        "야간 장면·비네팅(가장자리 어둡게)·어두운 그라데이션·발광(글로우) 금지 "
        "— 글자가 묻힌다. 진한 파랑은 글자와 강조에만 쓰고 배경에는 쓰지 않는다",
        f"배경: {_one(background, 220)}",
        f"구도: {_one(layout, 260)}",
        f"색/톤: {tone}",
        f'제목(한글, 굵게, 화면 맨 위 가운데): "{_one(title, 40)}"',
    ]
    for i, lb in enumerate(labels[:len(spots)]):
        head = _one((lb or {}).get("head"), 20)
        body = _one((lb or {}).get("body"), 80)
        if not head:
            continue
        lines.append(f'라벨 {i + 1} ({spots[i]}): 굵게 "{head}" / 그 아래 작게 "{body}"')
    if arrange in _FLOW and len(labels) > 1:
        lines.append("라벨 사이에 진행 방향을 가리키는 화살표를 하나씩 넣어라 "
                     "— 왼쪽에서 오른쪽으로 이어지는 순서다")
    # ★ **잇는 선을 넣지 않는다**(2026-08-16 지시). 라벨과 그림을 가는 선으로
    #   이으면 화면이 지저분해지고, 마스크로 라벨을 하나씩 밝힐 때 선만 먼저
    #   떠 있어 다음에 무엇이 나올지 미리 보인다. 라벨은 **가까이 놓아** 무엇을
    #   가리키는지 알게 한다.
    lines.append("라벨은 **글자만** 놓아라 — 라벨과 그림을 잇는 선이나 점을 그리지 "
                 "말고, 라벨을 상자·카드·둥근 판·테두리에 담지도 마라. 바탕 위에 "
                 "글자만 얹고, 가리키는 부분 **가까이에** 놓아 저절로 이어져 보이게 한다")

    # ★ **글자 크기를 세 단으로 못박는다.** 안 적으면 모델이 라벨을 제목만큼 키워
    #   화면이 글자로 덮인다. 본보기의 제목:소제목:설명이 대략 1 : 0.6 : 0.4 였다.
    lines.append("글자 크기: 제목은 그림 높이의 7% 안팎, 라벨 소제목은 제목의 60%, "
                 "라벨 설명은 소제목의 65%. 세 단이 눈에 띄게 달라야 한다. "
                 "글자가 화면을 덮으면 안 된다 — 그림이 주인공이고 라벨은 그 둘레에 "
                 "얹힌다. 포스터 제목처럼 키우지 마라")
    # ★ **액자 안이 곧 그림 전부다.** 화면에서 이 그림은 3:2 액자에 통째로 앉고
    #   한 픽셀도 안 잘린다(`render/slides.py` 의 `.s-swap` — 자르지 않으려고
    #   남는 자리를 바탕으로 처리했다). 그런데 「16:9 로 잘릴 수 있다」고 적어
    #   두면 모델이 가장자리를 비워 두려고 주제를 한가운데로 몰아 화면이 헐거워진다.
    #   이제는 반대로 **가장자리까지 다 쓰라고** 말해 준다.
    lines.append("산출물 규격: 3:2 가로(1536×1024). 화면의 액자 안에 통째로 들어가며 "
                 "잘리는 부분이 없다 — 가장자리까지 다 쓰고, 안전 여백을 위해 "
                 "주제를 한가운데로 몰지 마라. 실존 로고·서비스 화면·실존 인물 금지")
    return "\n".join(lines)


def plain_title(s: Dict[str, Any]) -> str:
    """제목에서 앞 순번(`3 `)을 뗀 것. 헤드라인을 못 받았을 때 이걸 쓴다."""
    return re.sub(r"^\s*\d+[.\s]\s*", "", str(s.get("title") or "")).strip()


def first_line(s: Dict[str, Any]) -> str:
    """원고의 첫 글줄. 서브카피를 못 받았을 때 쓰고, 브리프에도 재료로 넣는다."""
    for b in (s.get("blocks") or []):
        t = _one(b.get("html"), 80)
        if t and not t.startswith("[그림]"):
            return t
    return _one(s.get("say"), 80)


def slide_id(slug: str, s: Dict[str, Any]) -> str:
    """이 장의 이름표. 원고가 안 줬으면 만들어 준다.

    원장은 이름표가 있어야 도는데, 문제집 원고(`1과목2.html` 계열)에는 `data-id`
    가 없다. 그럴 때는 번호로 만든다 — 이름표만큼 튼튼하지는 않지만(장이 끼어들면
    같이 밀린다), 없는 것보다는 낫고 그 갈래는 원고가 잘 안 바뀐다.
    """
    return str(s.get("data_id") or "").strip() or f"{slug}-{int(s['no']):03d}"


def body_of(s: Dict[str, Any]) -> List[Dict[str, Any]]:
    """몸통 해시를 낼 때 쓰는 줄 목록. `ledger.body_hash()` 가 먹는 모양으로."""
    texts = s.get("html_text") or []
    if texts:
        return [{"kind": "line", "html": str(t)} for t in texts]
    # 원고 장이 아니면(text_image 레인) 본문 한 덩어리가 전부다
    return [{"kind": "note", "html": str(s.get("note") or "")}]


def build_brief(project: Dict[str, Any], batch: List[Dict[str, Any]]) -> str:
    lines = ["# 발표", project.get("title") or "", "", "# 그림을 그릴 장"]
    for s in batch:
        rows = "\n".join(f"  - {b['html']}" for b in s["blocks"] if b.get("html"))
        lines += [
            # ★ 제목은 **화면 위에 이미 뜬다.** 그걸 안 알려 주면 모델이 제목을
            #   그대로 헤드라인에 옮겨서 한 화면에 같은 말이 두 번 뜬다
            #   (2026-08-15 실측: "1.2. 짧은 물결과 긴 흐름" 위에 "짧은 물결과 긴 흐름").
            f"\n## {s['data_id']}",
            f"- 화면 위에 이미 떠 있는 제목(**그림 제목에 다시 쓰지 마라**): "
            f"{plain_title(s)}",
            # ★ 장마다 **몇 개를 쓸지 숫자로 준다.** 사람이 말하는 차례대로 라벨을
            #   하나씩 밝히며 이야기를 끄는데, 45초 장에 셋뿐이면 한 라벨이
            #   십오 초씩 버텨야 한다(2026-08-16: "그 말을 할 때 나타나서 말하는
            #   동안 계속 빛을 비춘다"). 열 초에 하나꼴로 잡아 준다.
            f"- **이 장은 라벨 {want_n(s.get('say'))}개를 써라.**",
            # ★ 대본을 **문장마다 번호를 붙여** 준다. 라벨이 그 번호를 가리키게
            #   하려는 것이다(`say_i`). 한 덩이로 주면 「몇 번째 말에 이 라벨이
            #   뜨는가」를 가리킬 방법이 없다.
            "- 말할 것(문장 번호가 곧 말하는 차례다):",
            _say_lines(s.get("say")),
            "- 그 장의 화면 문구(라벨은 여기서 뽑아 쓴다):",
            rows or "  (없음)",
        ]
    lines.append("\n주어진 data_id 만 채워라. 장마다 적힌 라벨 개수를 지켜라. "
                 "JSON 만 출력.")
    return "\n".join(lines)


def run(job, pid: int, slug: str, project: Dict[str, Any], *, force: bool = False):
    stage = STAGES["s3a-imgprompt"]
    cfg = config.load()

    outline = cached_data(pid, slug, "s2b-outline") or {}
    slides = outline.get("slides") or []
    if not slides:
        raise RuntimeError("구조 설계(s2b-outline)를 먼저 돌리세요")

    targets = [s for s in slides if s.get("media_kind") in WANT_MEDIA]
    if not targets:
        raise RuntimeError("그림이 들어갈 장이 없습니다 (html · text_image 레인이 없음)")

    rows: List[Dict[str, Any]] = []
    for s in targets:
        blocks = body_of(s)
        rows.append({
            "data_id": slide_id(slug, s),
            "no": s["no"],
            "title": s.get("title") or "",
            "say": s.get("say") or "",
            "img": re.sub(r"\s+", " ", str(s.get("img") or "")).strip(),
            "blocks": blocks,
            "body_hash": lg.body_hash(blocks, s.get("title") or ""),
        })

    book = ws.load_ledger(pid, slug)
    make_ids, keep_ids = lg.plan(book, rows)
    # ★ 프롬프트 꼴이 바뀌었으면 몸통이 그대로여도 다시 만든다. 안 그러면 원장이
    #   「바뀐 것 없음」 이라 말하고 옛 꼴 프롬프트가 그대로 나간다.
    old_fmt = [d for d in keep_ids
               if int(((book.get("by_id") or {}).get(d) or {}).get("fmt") or 1) != PROMPT_FMT]
    if old_fmt:
        keep_ids = [d for d in keep_ids if d not in set(old_fmt)]
        make_ids = make_ids + old_fmt
        job.add_log(f"프롬프트 꼴이 바뀌어 다시 씁니다 — {len(old_fmt)}장 "
                    "(옛 꼴: 영어·글자 없는 삽화)")
    if force:
        make_ids, keep_ids = [r["data_id"] for r in rows], []

    # ★ 원고의 `data-img` 는 **이 모드에 못 쓴다.** 그것은 「글자 없는 삽화를
    #   글 뒤에 깐다」는 전제로 영어로 쓰인 것이라(끝에 no text 가 세 겹) 지금
    #   필요한 「글이 박힌 한 판」과 정반대다. 그래서 여기서는 늘 새로 쓴다.
    #   원장은 그대로 작동한다 — 몸통이 안 바뀐 장은 다시 안 부른다.
    made: Dict[str, Dict[str, Any]] = {}
    by_id = {r["data_id"]: r for r in rows}
    ask_ids = list(make_ids)

    job.add_log(f"그림이 필요한 장 {len(rows)}개 — 원장에서 그대로 {len(keep_ids)}개 · "
                f"새로 쓸 것 {len(ask_ids)}개")

    # ── ③ 남은 것만 Claude 에게 ──────────────────────────────────────────────
    warn: List[str] = []
    cost = 0.0
    if ask_ids:
        want = [by_id[d] for d in ask_ids]
        system = (Path(__file__).resolve().parent.parent
                  / "llm" / "prompts" / "imgprompt.md").read_text(encoding="utf-8")
        batches = [want[i:i + BATCH] for i in range(0, len(want), BATCH)]
        p = ClaudeProvider(
            model=(project.get("models") or {}).get("imgprompt") or cfg["models"]["imgprompt"],
            effort=cfg["effort"]["imgprompt"],
            budget_usd=cfg["budget_usd"]["per_stage"],
            on_activity=job.add_log,
        )
        for i, batch in enumerate(batches):
            job.progress(i, len(batches), f"{batch[0]['data_id']} … {batch[-1]['data_id']}")
            try:
                raw = p.structured(system,
                                   [{"role": "user",
                                     "content": build_brief(project, batch)}],
                                   schema=SCHEMA)
            except Exception as e:                    # noqa: BLE001
                warn.append(f"{batch[0]['data_id']} 묶음 실패: {type(e).__name__}: {e}")
                continue
            cost += p.last_cost_usd
            for r in raw.get("prompts") or []:
                did = (r.get("data_id") or "").strip()
                if did not in by_id:
                    warn.append(f"모르는 이름표라 버렸습니다: {did}")
                    continue
                src = by_id[did]
                if len(_one(r.get("layout"), 999)) < 20:
                    warn.append(f"{did}: 구도가 너무 짧습니다")
                    continue
                labels = [x for x in (r.get("labels") or [])
                          if _one((x or {}).get("head"), 20)]
                if len(labels) < 2:
                    # 라벨이 하나뿐이면 마스킹으로 밝힐 덩어리가 안 생긴다 —
                    # 그림을 뽑기 전에 걸러야 스물아홉 장을 또 버리지 않는다.
                    warn.append(f"{did}: 라벨이 {len(labels)}개뿐입니다")
                made[did] = {
                    "title": src["title"],
                    "level": r.get("level") if r.get("level") in LEVELS else "이해",
                    # ★ 표본 JSON 은 전부 `photo` 다. 갈릴 축이 없어 고정한다 —
                    #   스튜디오도 이 칸을 안 읽는다.
                    "type": "photo",
                    "fmt": PROMPT_FMT,
                    # 유튜브 챕터·썸네일이 이 값을 읽는다(render/youtube.py)
                    "label_heads": [_one(x["head"], 20) for x in labels],
                    # ★ 라벨마다 **몇 번째 문장에서 말하는가**. 모션이 이걸 읽어
                    #   상자 차례를 정한다 — 그림이 오고 나서 되찾을 필요가 없다.
                    "label_says": [max(0, int(x.get("say_i") or 0)) for x in labels],
                    # 제목을 못 받으면 원고 제목으로 받쳐 준다 — 글자 없는 카드가
                    # 나가는 것보다 원고 제목이라도 박히는 편이 낫다.
                    "prompt": compose(background=r.get("background"),
                                      layout=r.get("layout"), tone=r.get("tone"),
                                      title=_one(r.get("title"), 40) or plain_title(src),
                                      labels=labels, arrange=r.get("arrange") or "",
                                      cfg=cfg),
                    "keywords": [str(k) for k in (r.get("keywords") or [])][:1],
                }
        job.progress(len(batches), len(batches), "정리")

    book = lg.apply(book, made, rows)
    ws.save_ledger(pid, slug, book)

    miss = [r["data_id"] for r in rows
            if not ((book["by_id"].get(r["data_id"]) or {}).get("prompt") or "").strip()]
    job.add_log(f"원장 {len(book['by_id'])}칸 · 지시문 있는 장 "
                f"{len(rows) - len(miss)}/{len(rows)}개 · ${cost:.3f}")
    if miss:
        job.add_log(f"지시문이 없는 장 {len(miss)}개: {', '.join(miss[:10])}")
    for w in warn[:10]:
        job.add_log(w)

    return write_cache(pid, slug, "s3a-imgprompt",
                       input_hash=stage.input_hash(pid, slug, project),
                       data={"made": len(made), "kept": len(keep_ids),
                             "fmt": PROMPT_FMT,
                             "asked": len(ask_ids), "missing": miss,
                             "ledger": len(book["by_id"])},
                       code_version=stage.code_version, cost_usd=cost,
                       status="degraded" if miss or warn else "ok",
                       warnings=warn + ([f"지시문이 없는 장 {len(miss)}개"] if miss else []))


STAGES["s3a-imgprompt"].run = run
