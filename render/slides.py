# -*- coding: utf-8 -*-
"""덱 → 슬라이드 HTML. **이 앱의 유일한 HTML 생성기.**

미리보기와 최종 산출물이 같은 함수를 쓴다. 편집 화면에서 iframe 으로 보는 것도
이것이고, `dist/` 로 굽는 것도 이것이다 — 셋이 갈라지면 "OK 한 면" 과 "나가는 면"
이 달라진다.

**미완성 상태에서도 렌더된다.** 음성·자막·그림이 아직 없어도 제목과 본문만으로
면이 나와야 한다. 텍스트 연계가 어울리는지는 실제 면을 봐야 판단된다.

★ PPT 교안처럼 만들지 않는다. 불릿 나열 대신 **한 장에 하나**를 말하고,
  근거(파일 경로 · 커밋 · 수치)가 주인공 자리에 온다.

★ 브라우저 자동재생 정책: 소리 있는 오디오는 사용자 제스처 전에 재생되지 않는다.
  슬라이드를 넘기는 행위가 제스처라 2번째 장부터는 문제없지만 **첫 장은
  `▶ 시작` 이 필요하다.** 그 버튼이 첫 제스처가 되고 이후는 자동으로 흐른다.
"""
from __future__ import annotations

import html
import json
from typing import Any, Dict, List

# 레인 색 — 브랜드 하나에서 파생한 계조. 범주형 색을 섞지 않는다.
LANE_COLORS = ["#9a4d33", "#c0714f", "#7d6a55", "#5c6b62", "#8a7f9a", "#a8894f"]

KIND_LABEL = {
    "cover": "", "context": "배경", "feature": "기능", "architecture": "구조",
    "decision": "판단", "metric": "수치", "ops": "운영", "note": "", "closing": "",
}


def esc(s: Any) -> str:
    return html.escape(str(s or ""), quote=True)


def _paras(text: str) -> str:
    """Claude 가 쓴 것은 **평문**이다. 전부 escape 하고 빈 줄만 문단으로 바꾼다."""
    parts = [p.strip() for p in str(text or "").split("\n\n") if p.strip()]
    return "".join(f"<p>{esc(p)}</p>" for p in parts)


def _evidence(s: Dict[str, Any]) -> str:
    ev = s.get("evidence") or []
    if not ev:
        return ""
    lis = "".join(f"<li>{esc(e)}</li>" for e in ev[:6])
    return f'<ul class="ev">{lis}</ul>'


def _media(s: Dict[str, Any], res) -> str:
    kind = s.get("media_kind")
    no = s.get("no")
    frames = [f for f in (s.get("frames") or []) if f.get("file")]

    if kind == "video" and s.get("video_id"):
        src = res.video(s)
        poster = res.asset(frames[0]["file"]) if frames else ""
        if src:
            p = f' poster="{esc(poster)}"' if poster else ""
            cap = (f'<figcaption>{esc(frames[0]["caption"])}</figcaption>'
                   if frames and frames[0].get("caption") else "")
            c = s.get("clip") or {}
            dur = float(s.get("video_duration") or 0)
            # ★ 편집 정보를 **항상** 내보낸다. 예전엔 사람이 자른 장에만 붙였는데,
            #   그러면 안 자른 장은 재생기가 "영상이 없는 장" 으로 보고 음성만
            #   기다렸다 — 영상이 도는 중에 다음 장으로 넘어가던 원인이다.
            #   안 자른 장은 0 ~ 원본 길이가 곧 구간이다.
            attr = (f' data-start="{float(c.get("start") or 0):.2f}"'
                    f' data-end="{float(c.get("end") or dur):.2f}"'
                    f' data-speed="{float(c.get("speed") or 1):.2f}"'
                    f' data-cuts="{esc(json.dumps(c.get("cuts") or []))}"')
            return (f'<figure class="m"><video playsinline preload="metadata" muted'
                    f'{p}{attr} src="{esc(src)}"></video>{cap}</figure>')
        if frames:
            f = frames[0]
            cap = f'<figcaption>{esc(f["caption"])}</figcaption>' if f.get("caption") else ""
            return (f'<figure class="m"><img loading="lazy" src="{esc(res.asset(f["file"]))}"'
                    f' alt=""/>{cap}</figure>')
        return '<div class="m m-todo">영상 대기</div>'

    if kind == "html":
        # ★ 조각은 이미 조립(s8)이 읽어 넣어 두었다 — 여기서 파일을 열지 않는다.
        #   렌더러는 `res` 가 주는 URL 밖에 못 보고, `dist/` 는 파일 한 장으로
        #   나가야 해서 나중에 불러올 수도 없다.
        frag = (s.get("html") or "").strip()
        if not frag:
            return f'<div class="m m-todo">원고 대기 — {int(no):03d}</div>'
        # 줄이 몇 초에 뜨는가. 조각 안 글자를 다시 쓰지 않고 **한 뭉치**로 넘긴다 —
        # 줄마다 심으려면 파이썬이 HTML 을 파싱해야 하는데, 그 순간 이 파일이
        # 렌더러가 아니라 파서가 된다. 순서(배열 자리)가 곧 줄 번호다.
        ats = [float(x) for x in (s.get("html_times") or [])]
        return (f'<figure class="m m-shots m-html" data-n="{len(ats)}"'
                f' data-at="{esc(json.dumps(ats))}">'
                f'<div class="doc">{frag}</div></figure>')

    if kind == "text_image":
        shots = [x for x in (s.get("images") or ([s["image"]] if s.get("image") else [])) if x]
        if shots:
            # ★ 여러 장이면 대본 시간을 나눠 차례로 넘어간다 —
            #   멘토링처럼 신청 화면과 수락 화면이 따로 있는 메뉴가 있다.
            imgs = "".join(
                f'<img loading="lazy" src="{esc(res.asset(x))}" alt=""'
                f'{" class=on" if i == 0 else ""}/>' for i, x in enumerate(shots))
            dots = ("".join("<i></i>" for _ in shots)) if len(shots) > 1 else ""
            return (f'<figure class="m m-shots" data-n="{len(shots)}">{imgs}'
                    f'{f"<span class=sdots>{dots}</span>" if dots else ""}</figure>')
        return f'<div class="m m-todo">그림 대기 — {int(no):03d}.png</div>'

    if frames:
        f = frames[0]
        cap = f'<figcaption>{esc(f["caption"])}</figcaption>' if f.get("caption") else ""
        return (f'<figure class="m"><img loading="lazy" src="{esc(res.asset(f["file"]))}"'
                f' alt=""/>{cap}</figure>')
    return ""      # code 장은 근거 목록이 코드 자리를 대신한다


def _audio(s: Dict[str, Any], res) -> str:
    """장별 내레이션. `data-no` 로 JS 가 찾아 재생한다."""
    f = (s.get("audio") or {}).get("file")
    if not f:
        return ""
    return (f'<audio class="na" preload="none" data-no="{s.get("no")}"'
            f' src="{esc(res.asset(f))}"></audio>')


def _slide(s: Dict[str, Any], lane_i: int, total: int, res) -> str:
    no = s.get("no")
    kind = s.get("kind") or "note"
    color = LANE_COLORS[lane_i % len(LANE_COLORS)]
    label = KIND_LABEL.get(kind, "")
    au = _audio(s, res)

    if kind == "cover":
        p = s.get("_project") or {}
        meta = " · ".join(x for x in [p.get("repo", {}).get("name_with_owner"),
                                      " / ".join((p.get("stack") or [])[:3])] if x)
        return (
            f'<section class="s s-cover" data-no="{no}" data-src="{s.get("src_no") or no}"'
            f' style="--lane:{color}">'
            f'<div class="wrap">'
            f'<h1>{esc(s.get("title"))}</h1>'
            f'{_paras(s.get("body"))}'
            f'{f"<p class=meta>{esc(meta)}</p>" if meta else ""}'
            f'</div>{au}</section>'
        )

    tag = f'<span class="tag">{esc(label)}</span>' if label else ""
    media = _media(s, res)
    # ★ 캡처 이미지 장(text_image)은 본문이 늘 비어 있다(S2c 캡처가 채우지
    #   않는다) — 그런데도 2단 그리드(텍스트 칸 + 이미지 칸)를 쓰면 빈 텍스트
    #   칸만큼 이미지가 절반 폭으로 쪼그라든다. "화면을 이미지가 다 덮어야
    #   한다"(2026-08-13 지시)는 요구와 맞지 않아 이 종류만 통짜 폭으로 뺀다.
    # ★ 원고 장(html)도 `s-shots` 를 그대로 쓴다. 흰 배경 · 번호 감추기 · 좁은 제목
    #   여백 · 통짜 폭 · 재생 중 제목이 흔들리지 않게 하는 예외까지 전부 이미 여기
    #   붙어 있다. 새 클래스를 만들면 그 규칙들을 하나씩 다시 벌어야 한다.
    cls = "s" + (" s-media" if media else "") + (
        " s-shots" if s.get("media_kind") in ("text_image", "html") else "")

    return (
        f'<section class="{cls}" data-no="{no}" data-src="{s.get("src_no") or no}"'
        f' style="--lane:{color}">'
        f'<div class="wrap">'
        f'<header><span class="no">{no}<span class="of">/{total}</span></span>{tag}</header>'
        f'<h2>{esc(s.get("title"))}</h2>'
        f'<div class="cols">'
        f'<div class="txt">{_paras(s.get("body"))}{_evidence(s)}</div>'
        f'{media}'
        f'</div></div>{_cc_static(s)}{au}</section>'
    )


def _cc_static(s: Dict[str, Any]) -> str:
    """편집 화면에서만 보이는 자막 — **고친 것이 보여야 고칠 수 있다.**

    발표에서는 자막이 재생 중에 시간에 맞춰 뜨는데, 편집 화면의 iframe 은 소리를
    내지 않으므로 자막층이 꺼져 있다. 그러면 자막을 고쳐도 화면이 그대로라
    "저장이 안 되나" 로 읽힌다. 여기서는 시간과 무관하게 통째로 깔아 둔다.
    """
    t = ((s.get("narration") or {}).get("srt_text") or "").strip()
    return f'<div class="cc-st">{esc(t)}</div>' if t else ""


CSS = """
*,*::before,*::after{box-sizing:border-box}
html,body{margin:0;height:100%}
body{
  background:#f7f5f1;color:#2e2b27;
  font-family:"Pretendard",-apple-system,BlinkMacSystemFont,"Segoe UI","Malgun Gothic",system-ui,sans-serif;
  line-height:1.62;-webkit-font-smoothing:antialiased;
  word-break:keep-all;overflow:hidden;
}
#deck{height:100vh;overflow:hidden;position:relative}
.s{
  position:absolute;inset:0;display:grid;place-items:center;
  padding:6vh 7vw 9vh;opacity:0;pointer-events:none;transition:opacity .18s;
}
.s.on{opacity:1;pointer-events:auto}
/* ★ 이미지가 있는 장은 세로 중앙 정렬(place-items:center)을 쓰지 않는다.
   제목 줄 수가 장마다 달라 .wrap 높이가 조금씩 바뀌는데, 중앙 정렬이면 그때마다
   .wrap 전체가 위아래로 살짝 흔들린다 — 장을 넘길 때마다 그림이 미세하게
   움직이는 것처럼 보인다(2026-08-13 지적: "노란면이 움직이면 안 된다").
   위쪽 정렬로 고정하면 상단 padding 만큼에서 항상 시작해 흔들리지 않는다. */
.s-media{align-items:start}
.wrap{width:min(1180px,100%)}
header{display:flex;align-items:center;gap:10px;margin-bottom:14px}
.no{font-variant-numeric:tabular-nums;font-weight:800;font-size:15px;color:var(--lane)}
.of{color:#948e86;font-weight:600}
.tag{padding:2px 9px;border-radius:99px;background:#efebe4;color:#6b6660;
  font-size:11px;font-weight:700}
h1{margin:0 0 20px;font-size:clamp(28px,4.4vw,54px);font-weight:700;
   letter-spacing:-.03em;line-height:1.18;color:#1f1d1a}
h2{margin:0 0 22px;font-size:clamp(21px,2.7vw,34px);font-weight:700;
   letter-spacing:-.025em;line-height:1.28;color:#1f1d1a}
h2::after{content:"";display:block;width:52px;height:3px;margin-top:14px;background:var(--lane)}
p{margin:0 0 11px;font-size:clamp(14px,1.15vw,17px);color:#4a453f;max-width:62ch}
.s-cover p{font-size:clamp(15px,1.3vw,19px);color:#6b6660}
.s-cover .meta{margin-top:22px;font-size:12.5px;color:#948e86;
  font-family:ui-monospace,SFMono-Regular,Consolas,monospace}

.cols{display:grid;gap:34px;grid-template-columns:1fr}
.s-media .cols{grid-template-columns:minmax(0,1fr) minmax(0,1.05fr);align-items:start}
/* ★ 분기를 640 까지 낮춘다. 편집 화면의 iframe 은 700~900px 이라 900 으로 두면
   거기서만 세로로 쌓여서, 실제 발표 화면과 다른 배치를 보고 판단하게 된다. */
@media (max-width:640px){.s-media .cols{grid-template-columns:1fr}}
/* 좁은 폭에서는 간격과 글자를 줄여 두 칸이 그대로 유지되게 */
@media (max-width:900px){.cols{gap:20px}.s{padding:5vh 5vw 7vh}}

/* 근거 — 이게 주인공이다. 불릿 나열이 아니라 출처 목록. */
.ev{margin:18px 0 0;padding:0;list-style:none;
    border-top:1px solid rgb(40 34 28/.10);padding-top:12px}
.ev li{font-family:ui-monospace,SFMono-Regular,"Cascadia Mono",Consolas,monospace;
  font-size:11.5px;color:#7d756b;padding:2px 0;word-break:break-all}
.ev li::before{content:"";display:inline-block;width:5px;height:5px;
  margin-right:8px;vertical-align:middle;background:var(--lane);border-radius:1px}

.m{margin:0;min-width:0}
.m video,.m img{width:100%;display:block;border-radius:10px;background:#efebe4;
  box-shadow:0 1px 0 rgb(40 34 28/.10)}
.m figcaption{margin-top:8px;font-size:12px;color:#7d756b}

/* ★ 영상은 **재생 중에만 커진다.**
   장이 뜰 때는 제목·본문과 나란히 작게 있다가, 재생이 시작되면 화면을 차지하고,
   끝나면 다시 제자리로 돌아온다. 발표에서 눈이 갈 곳이 매 순간 하나여야 한다.
   레이아웃을 갈아치우지 않고 grid-template-columns 와 opacity 만 바꾼다 —
   video 요소가 DOM 에서 안 움직이므로 재생이 끊기지 않는다. */
.s-media .cols{transition:grid-template-columns .55s cubic-bezier(.22,.68,.2,1)}
.s-media .txt{transition:opacity .34s,transform .55s cubic-bezier(.22,.68,.2,1)}
/* ★ "재생 중 커지기" 효과는 작은 썸네일이 화면을 차지하러 커지는 연출이다 —
   .s-shots 는 처음부터 폭 전체를 쓰므로 커질 자리가 없다. 그런데도 JS 는
   모든 그림 장에 .vplay 를 그대로 걸어서(render/slides.py JS, armShots),
   이 규칙이 .s-shots 에도 그대로 먹으면 커지는 건 안 보이고 **제목만 진하게
   가라앉았다 돌아오는 깜빡임**만 남는다(2026-08-13 지적: "흔들려 보인다").
   .s-shots 는 이 대상에서 뺀다 — 제목이 재생 내내 그대로다. */
.s-media.vplay:not(.s-shots) .cols{grid-template-columns:0fr minmax(0,1fr);gap:0}
.s-media.vplay:not(.s-shots) .txt{opacity:0;transform:translateX(-14px);pointer-events:none;overflow:hidden}
.s-media.vplay:not(.s-shots) h2,.s-media.vplay:not(.s-shots) header{opacity:.34;transition:opacity .3s}
.s-media.vplay .m video{border-radius:12px;box-shadow:0 10px 40px rgb(40 34 28/.18)}
.s-media.vplay .m figcaption{opacity:0}
.m-shots{position:relative}
/* ★ 캡처 높이를 이 박스 비율(padding-top:62.5%)에 맞춰 뽑으므로 보통은 여백이
   안 남는다 — 그래도 마지막 항목처럼 내용이 짧아 남는 경우, 배경(#efebe4,
   누런빛)이 비쳐 보이던 것을 없애고(투명 → 페이지 배경과 같아짐) 위쪽에
   붙인다(2026-08-13: 덱 레이아웃은 그대로 두고 이미지만 위로). */
.m-shots img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;
  object-position:top;background:transparent;
  opacity:0;transition:opacity .35s}
.m-shots img.on{opacity:1}
.m-shots::before{content:"";display:block;padding-top:62.5%}

/* ★ 캡처(text_image) 장 전용 — 텍스트 칸이 늘 비어 있으니 통짜 폭으로 쓰고,
   고정 비율 박스 없이 캡처 원래 크기 그대로 얹는다. 장마다 이미지 실제
   높이만큼만 차지하고 화면 맨 위(제목 바로 아래)에서 시작하며, 남는 아래
   쪽은 그냥 페이지 배경이다 — 억지로 박스를 채우려 자르거나 늘이지 않는다
   (2026-08-13 지시: "화면 최상단에 이미지가 실제 크기로 뜨면 된다").
   장 번호 표시(header)는 그 공간을 아끼려 이 종류에서는 숨긴다(가려도
   된다고 확인받음).
   ★ `.wrap`은 원래 `.s{place-items:center}`를 물려받아 **가로로 가운데
   정렬**된다 — 폭이 min(1180px,100%)로 고정돼 있으니, 영상은 항상
   1920px 로 찍혀서(render_frames.mjs) 좌우로 남는 폭이 커 왼쪽 패딩을
   아무리 줄여도 정작 왼쪽 정렬 효과가 약했다(2026-08-14: "좌측은 최대로
   붙여야"). justify-items 를 start 로 바꿔 이 장 종류만 왼쪽 끝(패딩
   위치)에 붙인다. */
/* ★ 이 장 종류만 배경을 흰색으로 바꾼다(2026-08-14: "배경을 하얀색으로") —
   카드(.m-shots)는 이미 흰색인데 그 둘레(제목 위·오른쪽 여백)만 크림색
   (#f7f5f1, body 배경)이라 화면 전체가 하나로 안 보였다. 전체 앱의
   body 배경은 그대로 둔다 — 다른 장 종류(표지·판단 등)는 크림 바탕을
   기준으로 태그·색이 설계돼 있어서 거긴 안 건드린다. */
.s-shots{padding:2vh 7vw 2vh 0.5vw;justify-items:start;background:#fff}
.s-shots header{display:none}
.s-shots h2{margin-bottom:6px}
.s-shots h2::after{margin-top:6px}
.s-shots .cols{grid-template-columns:1fr;gap:0}
.s-shots .m-shots::before{content:none}
/* ★ 폭을 100%로 꽉 채우지 않는다(2026-08-14 지시) — 캡처 원본이 옆으로
   넓게 늘어나 보이던 것을, 왼쪽 정렬 + 폭 제한으로 오른쪽에 배경이 남게
   바꾼다. 세로(fitShot, 위 JS)는 그대로 — 높이가 길면 그쪽만 줄어든다.
   기본 block 요소라 margin 없이 두면 저절로 왼쪽 붙는다.
   ★ 카드(.m-shots)에 흰 배경만 준다(늘리지는 않는다 — 위 fitShot 참고) —
   이미지 자체와 카드 경계 사이에 이질감이 없게, 테두리 그림자도 뺐다. */
/* ★ .wrap 자체는 그대로 둔다(2026-08-14: "슬라이드 판은 그냥 두고 이미지만
   늘려달라") — 제목·레이아웃 자리는 안 건드린다. 대신 박스 폭을 %(=wrap
   기준, 1180px 에서 막힘) 가 아니라 **vw(=화면 기준)** 로 준다 — 그러면
   wrap 폭과 무관하게 박스가 그 오른쪽 경계를 넘어 실제로 더 커진다. wrap
   을 벗어나도 막는 것(overflow:hidden)이 없어서 그대로 커져 보인다.
   61vw ≈ 화면 전체 기준 오른쪽 여백이 1/3 정도 되도록 실측한 값. */
/* ★ max-width 로는 안 됐다 — 그리드 칸(.cols)이 기본으로 wrap 폭(1180px)
   까지 아이템을 늘리는데(stretch), max-width 값이 그보다 크면(예: 66vw=
   1267px > 1180px) 상한이 실제 계산값보다 커서 아무 효과가 없다(실측:
   66vw 줘도 그대로 1180px 로 나옴). width 를 직접 줘야 그 스트레치를
   덮어쓰고 지정한 크기 그대로(넘치면 넘치는 대로) 나간다. */
/* ★ vw(화면 폭 비례)에서 고정 px로 바꾼다(2026-08-14 지시: "너비를
   강제할 수 없나요") — vw 는 미리보기 창 크기에 따라 실제 픽셀이 계속
   달라져서 볼 때마다 다르게 보였다. 영상은 항상 1920px 로 찍히니
   (render_frames.mjs), 그 기준 66%인 1267px 로 못박는다 — 미리보기
   창 크기와 무관하게 항상 이 값이다. */
.s-shots .m-shots{background:#fff;width:1536px;max-width:none}
/* ★ `:first-child` 도 붙여 아래 `.m-shots img:first-child{position:absolute}`
   (여러 장 캡션 전환용 — 이 종류엔 항상 이미지가 한 장뿐이라 그게 곧
   first-child 다)와 명시성을 맞춘다. 같은 명시성이면 소스 순서상 저 규칙이
   나중이라 이겨서 `position:static` 이 씹혔다 — 그러면 이미지가 레이아웃
   흐름을 안 채워 카드(.m-shots) 높이가 0으로 무너진다(2026-08-14 실측:
   화면엔 잘 보이는데 좌표를 재면 height:0). */
.s-shots .m-shots img:first-child{position:static;width:auto;max-width:100%;
  height:auto;object-fit:unset;object-position:unset;opacity:1;box-shadow:none}
.m-shots img:first-child{position:absolute}

/* ── 원고 장(html) — 그림이 아니라 **글 그대로** ────────────────────────
   ★ 캡처와 **픽셀이 겹치도록** 만든 값이다. 실측 근거:
       원본 문서는 960px 뷰포트에서 배치되고, body 테두리 상자는 944px 이다
       (UA 기본값 `body{margin:8px}` 이 좌우로 8px 씩 먹는다).
       그것을 2배로 찍어 1888px PNG 가 되고, 위 `.m-shots{width:1536px}` 상자에
       들어가 축소된다 → 실효 배율 1536 / 944 = 1.62712.
   그래서 살아 있는 글도 **944px 폭에서 배치한 뒤 1.62712 배로 확대**한다.
   줄바꿈 위치도 표 칸 너비도 캡처와 같다 — 배치가 같은 폭에서 일어나기 때문이다.
   `zoom` 이나 글자 크기 키우기로는 안 된다. `zoom` 은 1536px 에서 배치를 다시 해
   줄바꿈이 달라지고, 글자 크기는 원본이 섞어 쓰는 rem(문서 기준)과 em(부모 기준)이
   서로 다른 비율로 자라 비례가 깨진다. */
.m-html{position:relative;margin:0;background:#fff;overflow:hidden}
.m-html>.doc{width:944px;transform-origin:top left;box-sizing:border-box}
/* 조각 안은 원본 문서의 상자 계산을 그대로 둔다 — 위 전역 border-box 가 표 칸
   여백까지 바꿔 버리면 캡처와 어긋난다. */
.m-html>.doc *{box-sizing:content-box}
/* 원본 `body` 의 좌우 여백(4px)은 남기고 위아래는 뺀다 — 그 여백은 문서의 처음과
   끝에 두라고 준 것인데 조각은 문서 중간이다. 좌우를 빼면 본문 폭이 936→944 로
   벌어져 줄바꿈이 달라지므로 **좌우는 꼭 남긴다.** */
.m-html>.doc{padding-top:5px;padding-bottom:0}
.m-html>.doc>*:first-child{margin-top:0}
.m-html>.doc>*:last-child{margin-bottom:0}

/* 줄 등장 — `display` 가 아니라 `opacity` 다. display 로 감추면 줄이 뜰 때마다
   아래 내용이 밀려 글이 통째로 튄다. 자리는 처음부터 잡아 두고 보이기만 바꾼다.
   ★ `<tr>` 에는 transform 이 안 먹는다(표 행은 이동 대상이 아니다) — 그래서
     올라오는 움직임 없이 opacity 만 쓴다. 종류마다 다르게 하면 표와 불릿이
     서로 다른 리듬으로 떠서 산만하다. */
.m-html .hb{opacity:0;transition:opacity .34s}
.m-html .hb.on{opacity:1}
/* 인쇄·PDF 에는 시간이 없다 — 다 보여야 한다. 안 그러면 안 뜬 줄이 통째로 빈다. */
@media print{.m-html .hb{opacity:1}}
.sdots{position:absolute;left:50%;bottom:-16px;transform:translateX(-50%);
  display:flex;gap:5px}
.sdots i{width:5px;height:5px;border-radius:50%;background:#d6cfc4;transition:background .2s}
.sdots i.on{background:#9a4d33}
.m-todo{display:grid;place-items:center;aspect-ratio:16/9;border-radius:10px;
  background:#efebe4;color:#948e86;font-size:12px;
  box-shadow:inset 0 0 0 1px rgb(40 34 28/.08)}

/* 자막 — 발표 중에는 켜 두고, 녹화할 때는 C 로 끈다 */
#cc{position:fixed;left:50%;bottom:52px;transform:translateX(-50%);
  max-width:min(900px,86vw);padding:9px 18px;border-radius:8px;
  background:rgb(31 29 26/.86);color:#fff;font-size:clamp(14px,1.5vw,19px);
  line-height:1.5;text-align:center;text-wrap:balance;
  opacity:0;transition:opacity .12s;pointer-events:none}
#cc.on{opacity:1}

/* 시작 — 첫 제스처. 이게 없으면 1장 음성이 브라우저에 막힌다. */
#gate{position:fixed;inset:0;display:grid;place-items:center;z-index:9;
  background:rgb(247 245 241/.94);backdrop-filter:blur(3px)}
#gate.off{display:none}
.gate-in{display:grid;justify-items:center;gap:10px}
.gate-in>button{margin:0}
#gate button.alt{background:#efebe4;color:#6b6660;box-shadow:none}
#gate button.alt:hover{background:#e6e0d7}
#gate button{display:inline-flex;align-items:center;gap:10px;
  padding:14px 28px;border:0;border-radius:99px;background:#9a4d33;color:#fff;
  font-family:inherit;font-size:16px;font-weight:700;cursor:pointer;
  box-shadow:0 6px 24px rgb(154 77 51/.28)}
#gate p{margin-top:16px;color:#948e86;font-size:12.5px;text-align:center}

/* 진행 — 레인이 번호에 섞여 있으므로 색 눈금이 갈래를 보여 준다 */
#bar{position:fixed;left:0;right:0;bottom:0;height:3px;display:flex;gap:1px;background:#efebe4;z-index:8}
#bar i{flex:1;background:#e0dad1;transition:background .15s;cursor:pointer}
#bar i.done{background:var(--c)}
/* ★ 오른쪽 **위**다(2026-08-14 지시: "우하단에 있는 것을 우상단으로").
   먼저 왼쪽에서 오른쪽으로 옮겼던 이유는 그대로 살아 있다 — .s-shots 장은 흰
   카드를 왼쪽에 붙이므로 왼쪽 아래에 두면 카드 위에 겹쳐 표를 가린다. 이번에는
   거기서 한 번 더 위로 올린다: **우하단이 아바타(말하는 사람) 자리**가 되기
   때문이다(#av). 그 자리에 버튼이 있으면 나중에 아바타가 버튼을 깔고 앉는다.
   진행바(#bar)는 화면 아래 가로 전체를 3px 로 지나갈 뿐이라 그대로 둔다. */
#pz{position:fixed;right:18px;top:18px;z-index:8;
  padding:6px 14px;border:0;border-radius:99px;
  background:rgb(31 29 26/.62);color:#fff;backdrop-filter:blur(6px);
  font-family:inherit;font-size:12px;font-weight:700;cursor:pointer}
#pz:hover{background:rgb(31 29 26/.86)}
#pz.on{background:#9a4d33}
body.one #pz{display:none}
/* 배경음악 토글 — 재생 버튼 바로 아래. 발표 중에 손이 닿아야 한다.
   ★ button 이라 클릭 네비게이션에서 이미 제외된다(아래 click 핸들러의 closest). */
#bgmb{position:fixed;right:18px;top:56px;z-index:8;width:30px;height:30px;
  padding:0;border:0;border-radius:99px;background:rgb(31 29 26/.5);color:#fff;
  backdrop-filter:blur(6px);font-size:13px;line-height:1;cursor:pointer;opacity:.55}
#bgmb:hover{opacity:1}
#bgmb.on{background:#9a4d33;opacity:1}
body.one #bgmb{display:none}
#hud{position:fixed;right:18px;top:96px;font-size:11px;color:#948e86;
     font-variant-numeric:tabular-nums;z-index:8;text-align:right}
/* 아바타 자리 — **비워만 둔다.** 나중에 말하는 사람이 여기 들어온다.
   본문은 1920 중 왼쪽 1536px 을 쓰므로 오른쪽이 이미 비어 있고, 그 아래쪽이다.
   ★ 고정 px 이 아니라 %/비율로 잡는다 — 영상은 1920×1080 으로 찍히는데 편집
     화면 iframe 은 더 좁은 폭으로 그린 뒤 줄여 보여 준다. px 로 두면 두 자리가
     어긋나 미리보기에서 본 위치와 영상 위치가 달라진다.
   ★ pointer-events:none — 아직 아무것도 없으니 클릭을 먹지 않아야 한다. */
#av{position:fixed;right:0;bottom:0;width:20%;aspect-ratio:3/4;z-index:7;
    pointer-events:none}
body.one #av{display:none}
#hud b{color:#6b6660}
#hud kbd{font:inherit;color:#b3aca3}
#hud em{font-style:normal;font-weight:800;color:#9a4d33}
#hud em.p{color:#b01f41}
/* 한 장만 보는 자리 — 진행바·HUD·자막층은 군더더기다 */
body.one #bar,body.one #hud,body.one #cc{display:none}
body.one .s{padding:5vh 5vw}
/* …대신 자막을 통째로 깔아 둔다. 발표본에서는 안 나온다(재생 중에 #cc 가 맡는다) */
.cc-st{display:none}
body.one .cc-st{display:block;position:absolute;left:5vw;right:5vw;bottom:2.2vh;
  font-size:15px;line-height:1.6;color:#6f675e;text-align:center;
  border-top:1px solid rgba(0,0,0,.07);padding-top:10px}
@media print{
  body{overflow:visible}
  #deck{height:auto}
  .s{position:static;opacity:1;pointer-events:auto;page-break-after:always;
     min-height:100vh;padding:8vh 8vw}
  #bar,#hud,#cc,#gate{display:none}
}
"""

JS = r"""
const D=window.__DECK__||{cues:{}};
const slides=[...document.querySelectorAll('.s')];
const bar=document.getElementById('bar'),hud=document.getElementById('hud'),
      cc=document.getElementById('cc'),gate=document.getElementById('gate'),
      pz=document.getElementById('pz');
slides.forEach(s=>{const b=document.createElement('i');
  b.style.setProperty('--c',getComputedStyle(s).getPropertyValue('--lane'));bar.appendChild(b);});
const ticks=[...bar.children];
ticks.forEach((t,k)=>t.onclick=()=>go(k));
/* ★ 시작 장은 **쿼리 먼저, 해시 나중.**
   해시만 다른 URL(`#2` → `#5`)은 브라우저가 문서를 다시 읽지 않아서, 편집 화면의
   iframe 이 앞 장을 그대로 보여 준다(머리글은 2인데 안은 5인 상태가 실제로 났다).
   쿼리는 URL 자체가 달라지므로 항상 새로 읽힌다. */
const _p=new URLSearchParams(location.search);
const _q=_p.get('n');
/* ★ 편집 화면의 iframe(=한 장만 보는 자리)에서는 시작 문을 띄우지 않는다.
   거기서는 소리를 낼 일이 없고, 문이 면을 가려서 정작 볼 것을 못 본다.
   `?n=` 이 붙어 있다는 것 자체가 "한 장만 본다" 는 뜻이다. */
const _one=_q!=null;
/* ★ `?at=` — **그 시각의 화면을 정지 상태로** 그린다. 영상 프레임을 찍을 때
   (tools/render_frames.mjs) 와 수정 화면에서 "9초에 어떻게 보이나" 를 확인할 때
   쓴다. 애니메이션이 아니라 결과 상태라서, 찍는 쪽이 몇 초를 기다릴 필요가 없다. */
const _atQ=_p.has('at')?parseFloat(_p.get('at')):null;
// 한 장만 보는 자리 — 진행바·HUD·자막층은 군더더기다
if(_one){document.body.classList.add('one');}
/* ★ `?n=` 은 **원래 번호**(src_no)다 — 순번이 아니다. 뺀 장이 있으면 조립이
   1부터 다시 번호를 매기므로(s8_assemble), 순번으로 읽으면 뺀 장 뒤부터 편집
   화면과 미리보기가 한 장씩 어긋난다. 먼저 src 로 찾고, 없으면 순번으로 본다
   (뺀 장이 없던 시절에 만든 링크·북마크가 그대로 돌아야 한다). */
const _want=parseInt(_q||location.hash.slice(1))||1;
const _bySrc=slides.findIndex((s)=>parseInt(s.dataset.src)===_want);
let i=_bySrc>=0?_bySrc:Math.max(0,Math.min(slides.length-1,_want-1));
// ★ 기본값을 꺼짐으로 바꿨다(2026-08-14 지시) — 자막을 몰라서 못 끄는
//   사람(동료 데모, SME)에게는 그냥 안 뜨는 게 낫다. 궁금하면 C로 켠다
//   (안내는 화면 우하단 "C 자막"에 이미 있다). 지운 게 아니라 기본값만
//   뒤집은 거라 기능은 그대로 산다.
let started=false, subs=false, timer=null, lead$=null;

/* ★ 자동 넘김 — **내레이션이 끝나면 다음 장으로.**
   발표 영상이 필요하면 이걸 켜고 화면녹화만 하면 된다. 통합 mp4 를 만들지 않는
   대신 이 방법을 쓴다 — 지루한 구간은 편집에서 배속·삭제하면 되고, 중간에
   ←/→ 로 끼어들 수도 있다(수동 조작이 들어오면 자동은 그 장에서 멈추지 않는다).

   음성이 없는 장은 자막 글자수로 시간을 잡는다. 영상만 있는 장은 영상 길이. */
let auto=new URLSearchParams(location.search).get('auto')==='1';
let hold=null, holdH=null, paused=false;
const DEFAULT_HOLD=4200, PER_CHAR=170, TAIL=600;
/* 원고 장에서 **마지막 줄이 뜬 뒤** 더 머무는 시간. 마지막 줄이 흔히 그림이나
   결론이라, 뜨자마자 넘기면 그걸 보라고 순서를 정한 의미가 없어진다
   (2026-08-14 실측: TAIL 만 두니 1.1초 뒤에 넘어갔다). */
const LAST_HOLD=1600;

/* ── 배경음악 ──────────────────────────────────────────────────────────
   ★ **자동 재생으로 시작했을 때만** 저절로 튼다. 손으로 넘기며 설명하는
     자리에서는 음악이 말을 방해하기만 한다. ♪ 버튼과 M 키로 언제든 켤 수 있다.
   ★ 내레이션이 나올 동안은 볼륨을 낮춘다(덕킹). 이게 없으면 말이 안 들린다.
     볼륨을 뚝 끊으면 그것대로 거슬려서 짧게 램프를 준다.
   ★ `onended=` 대입은 쓰지 않는다 — armAuto 가 이미 그 자리를 쓰고 있어서
     서로 덮어쓴다. addEventListener 로만 붙인다. */
const bgmEl=document.getElementById('bgm'),
      bgmBtn=document.getElementById('bgmb');
const BG=(D.bgm||{on:false,vol:.2,duck:.06});
let bgmWant=false, ducked=false, fade$=null, duckT=null;

function bgmFade(to,ms){
  if(!bgmEl)return;
  clearInterval(fade$);
  const from=bgmEl.volume, steps=Math.max(1,Math.round(ms/25));
  let k=0;
  fade$=setInterval(()=>{
    k++;
    bgmEl.volume=Math.min(1,Math.max(0,from+(to-from)*k/steps));
    if(k>=steps)clearInterval(fade$);
  },25);
}
function applyDuck(on){
  if(!bgmEl||ducked===on)return;
  /* ★ 음악이 꺼져 있어도 **상태는 따라간다.** 안 그러면 말이 나오는 도중에 M 으로
     켰을 때 원래 볼륨으로 튀어나와 그 장의 내레이션을 덮는다. */
  ducked=on;
  if(bgmWant)bgmFade(on?BG.duck:BG.vol,on?220:700);
}
function bgmDuck(on){
  /* ★ 올리는 것만 **늦춘다.** 자동 재생에서는 한 장이 끝나고 다음 장이 곧바로
     말을 시작하는데, 끝나자마자 음악을 올리면 장마다 부풀었다 꺼졌다 해서
     내레이션보다 그 출렁임이 더 귀에 걸린다. 잠깐 기다렸다가, 그 사이에 다음
     말이 시작되면 올리지 않는다. */
  clearTimeout(duckT);
  if(on){ applyDuck(true); return; }
  duckT=setTimeout(()=>applyDuck(false),900);
}
function bgmSet(on){
  if(!bgmEl)return;
  bgmWant=on;
  if(bgmBtn)bgmBtn.classList.toggle('on',on);
  if(on){
    bgmEl.volume=0;
    bgmEl.play().catch(()=>{});
    bgmFade(ducked?BG.duck:BG.vol,600);
  }else{
    clearInterval(fade$);
    bgmEl.pause();
  }
}
if(bgmBtn)bgmBtn.onclick=()=>bgmSet(!bgmWant);

function holdMs(sec){
  const no=sec.dataset.no, cues=D.cues[no]||[];
  /* ★ 원고 장은 **마지막 줄이 뜬 뒤까지** 머문다. 안 그러면 28초에 뜨기로 한
     줄이 나오기도 전에 다음 장으로 넘어가서, 사람이 시각을 정해 둔 의미가 없다.
     자막이 있으면 둘 중 늦은 쪽을 기다린다. */
  const last=htmlLastMs(sec);
  if(cues.length) return Math.max(cues[cues.length-1][1]*1000, last)+TAIL;
  if(last) return last+TAIL+LAST_HOLD;
  /* 대본이 없는 장 — 글자 수로 어림한다. ★ `.txt` 만 본다. 예전엔 없으면 장
     전체(`sec`)를 봤는데, 원고 장은 본문 글자가 통째로 거기 들어 있어서 어림값이
     늘 20초 상한에 붙어 버린다(원고 장은 위에서 이미 돌아 나간다 — 여기 오는
     것은 줄이 하나도 없는 장뿐이다). */
  const t=(sec.querySelector('.txt')||{}).textContent||'';
  return Math.max(DEFAULT_HOLD, Math.min(20000, t.replace(/\s/g,'').length*PER_CHAR));
}
function armAuto(sec){
  clearTimeout(hold); clearTimeout(holdH);
  if(!auto||paused||i>=slides.length-1) return;
  const m=media(sec);

  /* ★ **영상과 음성 중 긴 쪽을 기다린다.**
     음성이 끝났다고 넘기면 영상이 돌던 중에 잘린다. 반대로 영상만 보면 영상이
     짧은 장에서 말이 잘린다. 둘 다 끝나야 다음 장이다.
     한쪽만 있는 장은 그 하나만 기다린다. */
  /* ★ 원고 장의 **마지막 줄**도 기다린다. 사람이 손으로 "이 줄은 40초에" 라고
     정해 뒀는데 음성이 30초에 끝나면, 그 줄은 뜨지도 못하고 다음 장으로 넘어간다.
     시각을 정할 수 있게 만들어 놓고 그 시각을 안 지키면 만든 의미가 없다. */
  const lastH=htmlLastMs(sec);
  const needA=!!m.a, needV=!!(m.v&&m.v.dataset.end), needH=lastH>0;
  let doneA=!needA, doneV=!needV, doneH=!needH;
  const tick=()=>{ if(auto&&!paused&&doneA&&doneV&&doneH) setTimeout(()=>{
    if(auto&&!paused) go(i+1); },450); };

  if(needA){ m.a.onended=()=>{ doneA=true; tick(); }; }
  // 마지막 줄이 뜨자마자 넘기지 않는다 — 뜬 것을 읽을 시간이 필요하다(실측:
  // TAIL 만으로는 1.1초 뒤에 넘어가서 마지막 그림을 못 봤다). holdMs 와 같은 값.
  if(needH){ holdH=setTimeout(()=>{ doneH=true; tick(); }, lastH+TAIL+LAST_HOLD); }

  if(needV){
    const st=parseFloat(m.v.dataset.start||0), en=parseFloat(m.v.dataset.end||0),
          sp=parseFloat(m.v.dataset.speed||1);
    const cues=D.cues[sec.dataset.no]||[];
    const lead=cues.length>1?Math.min(cues[0][1]*1000,6000):600;   // 소개 문장만큼 늦게 뜬다
    hold=setTimeout(()=>{ doneV=true; tick(); },
                    Math.max(1200,(en-st)/sp*1000+lead+TAIL));
  }

  /* 텍스트만 있는 장 — 자막 길이로 잡는다.
     ★ `needH` 를 빼야 한다. 줄 등장이 있는 장은 위 holdH 가 이미 넘김을 맡는데,
       여기서 또 타이머를 걸면 **둘 다 넘겨서 한 장을 건너뛴다**(holdH 가 넘긴
       뒤 900ms 후에 이 타이머가 한 번 더 go(i+1) 를 부른다). */
  if(!needA&&!needV&&!needH){
    hold=setTimeout(()=>{ if(auto&&!paused) go(i+1); }, holdMs(sec));
  }
}

function media(s){return {a:s.querySelector('audio.na'),v:s.querySelector('video')};}

/* ★ 캡처 이미지가 화면보다 길면(표가 긴 장 등) 원래 크기 그대로 얹다가
   화면 밑으로 잘려 나갔다 — 배경이 한 톨도 안 보이니 "잘렸다"와 "다 안
   보여준다"를 구분할 수 없다(2026-08-13 지적). 그래서 이미지가 시작하는
   지점부터 화면 끝까지 남는 높이를 재서, 그보다 크면 **비율 그대로 축소**
   한다(자르지 않는다) — 그러면 밑에 배경이 최소 BOTTOM_GAP 만큼은 항상
   보이고, 화면에 맞는 장은 원래 크기(100%) 그대로다. */
const SHOT_BOTTOM_GAP=18;
function fitShot(sec){
  if(!sec||!sec.classList.contains('s-shots'))return;
  const img=sec.querySelector('.m-shots img');
  const fig=sec.querySelector('.m-shots');
  if(!img||!fig)return;
  const top=img.getBoundingClientRect().top;
  const avail=Math.round(innerHeight-top-SHOT_BOTTOM_GAP);
  img.style.maxHeight=Math.max(40,avail)+'px';
  // ★ 카드를 남는 높이까지 강제로 늘리는 건 되돌린다(2026-08-14 재지적:
  //   "최대로 긴 게 가득 차면 딱인데" — 내용이 짧은 장까지 억지로 늘리면
  //   빈 흰 종이만 커 보인다). 원래 그대로 — 카드는 이미지 자기 키만큼만.
  //   내용이 화면 높이에 가까운 장은 원래도 거의 꽉 찬다. 이음매(그림자)만
  //   없앤 상태로 둔다(아래 .s-shots .m-shots img 의 box-shadow:none).
}
/* ── 원고 장(html) — 크기 맞추기 · 줄 등장 ─────────────────────────────
   비율은 CSS 주석(.m-html)에 적어 둔 그 값이다: 944px 폭에서 배치하고 1.62712 배.
   여기서는 **화면 폭에서 직접 잰다** — 미리보기 창이 1920 이 아닐 수도 있어서,
   상수를 박아 두면 그때 캡처와 어긋난다. 상자 폭 ÷ 944 가 곧 배율이다. */
const HTML_SRC_W=944;
function fitHtml(sec){
  if(!sec)return;
  const box=sec.querySelector('.m-html'); if(!box)return;
  const doc=box.firstElementChild; if(!doc)return;
  doc.style.transform='none';            // 재려면 먼저 풀어야 한다
  box.style.height='auto';
  const nat=doc.scrollHeight;            // 944px 폭에서의 실제 높이
  let k=box.clientWidth/HTML_SRC_W;
  const avail=Math.round(innerHeight-box.getBoundingClientRect().top-SHOT_BOTTOM_GAP);
  // 한 화면을 넘칠 때만 줄인다 — 자르지 않는다(fitShot 과 같은 원칙).
  if(nat*k>avail) k=avail/Math.max(nat,1);
  doc.style.transform='scale('+k+')';
  /* ★ transform 은 배치 높이에 기여하지 않는다 — 상자 높이를 직접 넣어야 한다.
     안 넣으면 화면엔 멀쩡히 보이는데 좌표를 재면 height:0 이다. `.m-shots` 에서
     똑같은 사고가 있었다(2026-08-14 실측). */
  box.style.height=Math.ceil(nat*k)+'px';
}

let htmlT=[], htmlT0=0, htmlAcc=0;
function htmlAts(box){
  try{return JSON.parse(box.dataset.at||'[]');}catch(e){return [];}
}
/* 줄을 시각에 맞춰 띄운다.
   음성이 있으면 아래 go() 의 100ms 시계(showCue 와 같은 타이머)가 맡는다 —
   `audio.currentTime` 이 유일하게 멈춤·되감기를 따라오는 시계다. 음성이 없는
   장만 여기서 타이머로 돈다(armShots 가 쓰는 방식 그대로).
   ★ 그 장에서 **흐른 시간을 따로 센다**(htmlAcc). 멈췄다 이어서 할 때 이걸 안
     세면 처음부터 다시 시작해서, 이미 떠 있던 줄이 도로 사라졌다 다시 뜬다. */
function armHtml(sec,resume){
  htmlT.forEach(clearTimeout); htmlT=[];
  if(!sec)return;
  fitHtml(sec);
  const box=sec.querySelector('.m-html'); if(!box)return;
  const bs=[...box.querySelectorAll('.hb')], ats=htmlAts(box);
  /* 한 장만 보는 자리(편집 화면 iframe)와 시작 전에는 **다 보여 준다.**
     거기서는 시간이 흐르지 않아서 안 뜬 줄이 영원히 안 뜬다 — 고친 줄이 화면에
     없으면 고쳤는지 알 수가 없다. `?at=` 이 있으면 그 시각 상태로 굳힌다
     (영상 프레임 촬영이 이걸 쓴다). */
  if(_atQ!=null){bs.forEach((b,k)=>b.classList.toggle('on',(ats[k]||0)<=_atQ));return;}
  if(_one||!started){bs.forEach(b=>b.classList.add('on'));return;}
  if(!resume)htmlAcc=0;
  htmlT0=Date.now();
  if(media(sec).a) return;               // 음성이 있으면 시계가 맡는다
  const el=htmlAcc;
  bs.forEach((b,k)=>{
    const at=(ats[k]||0)*1000;
    if(at<=el)b.classList.add('on');
    else htmlT.push(setTimeout(()=>b.classList.add('on'),at-el));
  });
}
function pauseHtml(){
  if(htmlT0)htmlAcc+=Date.now()-htmlT0;
  htmlT0=0;
  htmlT.forEach(clearTimeout); htmlT=[];
}
function showReveal(sec,t){
  const box=sec&&sec.querySelector('.m-html'); if(!box)return;
  const ats=htmlAts(box);
  box.querySelectorAll('.hb').forEach((b,k)=>{
    b.classList.toggle('on',(ats[k]||0)<=t);
  });
}
/* 그 장의 마지막 줄이 뜨는 시각(ms) — 자동 넘김이 이보다 일찍 넘어가면 안 된다. */
function htmlLastMs(sec){
  const box=sec&&sec.querySelector('.m-html'); if(!box)return 0;
  const ats=htmlAts(box);
  return ats.length?ats[ats.length-1]*1000:0;
}
addEventListener('resize',()=>{fitShot(slides[i]);fitHtml(slides[i]);});

/* ★ 그림만 있는 장도 **한 번 커졌다 내려온다.**
   영상과 같은 리듬이다 — 소개 문장 동안은 글과 나란히 작게, 그다음 커져서 보여
   주고, 말이 끝나갈 때 다시 내려와 마무리를 듣게 한다.
   그림이 여러 장이면 커져 있는 동안 **대본 시간을 나눠 차례로 넘어간다.** */
let shotT=[];
function armShots(sec){
  fitShot(sec);
  shotT.forEach(clearTimeout); shotT=[];
  const fig=sec.querySelector('.m-shots'); if(!fig)return;
  const imgs=[...fig.querySelectorAll('img')];
  imgs.forEach((im,k)=>im.classList.toggle('on',k===0));
  const dots=[...fig.querySelectorAll('.sdots i')];
  dots.forEach((d,k)=>d.classList.toggle('on',k===0));
  if(!started)return;

  const cues=D.cues[sec.dataset.no]||[];
  const total=(cues.length?cues[cues.length-1][1]:holdMs(sec)/1000)*1000;
  const lead=cues.length>1?Math.min(cues[0][1]*1000,5000):900;   // 소개 문장
  const tail=Math.min(2600,total*0.22);                          // 마무리
  const big=Math.max(1200,total-lead-tail);

  shotT.push(setTimeout(()=>sec.classList.add('vplay'),lead));
  shotT.push(setTimeout(()=>sec.classList.remove('vplay'),lead+big));
  if(imgs.length>1){
    const step=big/imgs.length;
    imgs.forEach((_,k)=>{
      if(!k)return;
      shotT.push(setTimeout(()=>{
        imgs.forEach((im,j)=>im.classList.toggle('on',j===k));
        dots.forEach((d,j)=>d.classList.toggle('on',j===k));
      },lead+step*k));
    });
  }
}

/* 무음 영상 편집을 재생기가 따른다 — 구간 · 배속 · 들어내기.
   파일을 다시 굽지 않으므로 편집 화면에서 본 것과 여기가 정확히 같다. */
slides.forEach(sec=>{
  const v=sec.querySelector('video[data-end]'); if(!v)return;
  const st=parseFloat(v.dataset.start||0), en=parseFloat(v.dataset.end||0),
        sp=parseFloat(v.dataset.speed||1);
  let cuts=[]; try{cuts=JSON.parse(v.dataset.cuts||'[]');}catch(e){}
  v.addEventListener('loadedmetadata',()=>{v.playbackRate=sp;v.currentTime=st;});
  v.addEventListener('timeupdate',()=>{
    if(v.currentTime<st-0.05)v.currentTime=st;
    /* ★ 끝나면 **마지막 프레임에서 멈춘다.** 되감지 않는다 —
       영상이 음성보다 짧으면 남은 말이 끝날 때까지 그 화면이 서 있어야 한다.
       되감아 다시 돌면 같은 장면이 두 번 나가고 발표가 어수선해진다. */
    if(en&&v.currentTime>=en){v.pause();v.currentTime=Math.max(st,en-0.05);return;}
    for(const c of cuts){if(v.currentTime>=c[0]&&v.currentTime<c[1]){v.currentTime=c[1];break;}}
  });
  v.addEventListener('ended',()=>{v.currentTime=Math.max(st,(en||v.duration)-0.05);});
});

function showCue(no,t){
  if(!subs){cc.className='';return;}
  const list=D.cues[no]||[];
  const c=list.find(x=>t>=x[0]&&t<x[1]);
  cc.textContent=c?c[2]:'';
  cc.className=c?'on':'';
}

// 영상은 재생 중에만 커진다 — 시작하면 펼치고 끝나면 접는다
slides.forEach(s=>{
  const v=s.querySelector('video');
  if(!v)return;
  v.addEventListener('play',()=>s.classList.add('vplay'));
  ['ended','pause'].forEach(e=>v.addEventListener(e,()=>s.classList.remove('vplay')));
});

/* 내레이션이 끝나면 음악을 원래대로. **한 번만** 걸어 둔다 — go() 안에서 걸면
   장을 오갈 때마다 같은 핸들러가 쌓인다. */
document.querySelectorAll('audio.na').forEach(a=>{
  a.addEventListener('ended',()=>bgmDuck(false));
});

function go(n){
  const prev=slides[i];
  if(prev){const m=media(prev);if(m.a)m.a.pause();if(m.v)m.v.pause();
           prev.classList.remove('vplay');}
  clearInterval(timer); clearTimeout(lead$); shotT.forEach(clearTimeout); shotT=[];
  htmlT.forEach(clearTimeout); htmlT=[];
  // 떠난 장의 줄은 도로 걷는다 — 되돌아왔을 때 처음부터 다시 떠야 한다.
  if(prev)prev.querySelectorAll('.m-html .hb').forEach(b=>b.classList.remove('on'));
  i=Math.max(0,Math.min(slides.length-1,n));
  slides.forEach((s,k)=>s.classList.toggle('on',k===i));
  ticks.forEach((t,k)=>t.classList.toggle('done',k<=i));
  const no=slides[i].dataset.no;
  paint();
  history.replaceState(null,'','#'+(i+1));
  cc.className='';cc.textContent='';
  const m=media(slides[i]);
  // 말이 나오는 장에서만 음악을 낮춘다. 말 없는 장에서는 원래 볼륨으로 돌린다.
  bgmDuck(!!m.a && started);
  if(started){
    // 영상은 항상 무음이다 — 소리는 내레이션 트랙이 낸다
    if(m.a){m.a.currentTime=0;m.a.play().catch(()=>{});}
    /* ★ 영상은 **작게 시작한다.** 장이 뜨는 순간 화면을 덮으면 소개할 틈이 없다.
       "여섯 기능 중 첫 번째는 이것입니다" 를 말하는 동안은 제목·본문과 나란히
       작게 있다가, 그 문장이 끝나면 그때 커지면서 재생된다.
       기준은 **첫 자막 큐가 끝나는 시각** — 소개 문장 하나가 딱 그것이다. */
    if(m.v){
      m.v.muted=true; m.v.pause();
      m.v.currentTime=parseFloat(m.v.dataset.start||0);
      const cues=D.cues[no]||[];
      const lead=cues.length>1?cues[0][1]*1000:(m.a?1800:600);
      const mine=slides[i];
      lead$=setTimeout(()=>{
        if(slides[i]!==mine) return;        // 그새 넘어갔으면 재생하지 않는다
        m.v.play().catch(()=>{});           // play 이벤트가 .vplay 를 켠다
      }, Math.min(lead, 6000));
    }
  }
  armShots(slides[i]);
  armHtml(slides[i]);
  armAuto(slides[i]);
  if(m.a){
    /* ★ 시계는 **하나뿐이다.** 자막과 줄 등장이 같은 100ms 틱을 나눠 쓴다.
       타이머를 따로 두면 둘이 조금씩 어긋나서, 자막은 넘어갔는데 줄은 아직
       안 뜬 상태가 생긴다. 그리고 `audio.currentTime` 이 유일하게 멈춤·되감기를
       따라오는 시계다 — setTimeout 은 멈추면 그대로 흘러가 버린다. */
    timer=setInterval(()=>{
      showCue(no,m.a.currentTime);
      showReveal(slides[i],m.a.currentTime);
    },100);
  }else if(D.cues[no]&&D.cues[no].length){
    // 음성이 아직 없는 장 — 자막을 첫 줄만 띄워 둔다
    cc.textContent=D.cues[no][0][2];cc.className=subs?'on':'';
  }
}
addEventListener('keydown',e=>{
  if(e.key===' '){
    e.preventDefault();
    /* 자동일 때 Space 는 **멈춤/재개**다. 발표 중 질문을 받으면 세워야 한다.
       자동이 아닐 때는 예전처럼 다음 장으로 넘긴다. */
    if(auto) setPaused(!paused); else go(i+1);
    return;
  }
  if(e.key==='ArrowRight'||e.key==='PageDown'){e.preventDefault();go(i+1);}
  if(e.key==='ArrowLeft'||e.key==='PageUp'){e.preventDefault();go(i-1);}
  if(e.key==='Home')go(0); if(e.key==='End')go(slides.length-1);
  if(e.key==='c'||e.key==='C'){subs=!subs;if(!subs)cc.className='';}
  if(e.key==='a'||e.key==='A'){setAuto(!auto);}
  if(e.key==='m'||e.key==='M'){bgmSet(!bgmWant);}
});

function setPaused(on){
  paused=on;
  const m=media(slides[i]);
  // 멈추면 음악도 같이 선다 — 질문을 받는 동안 혼자 흐르면 이상하다
  if(bgmEl&&bgmWant){ on?bgmEl.pause():bgmEl.play().catch(()=>{}); }
  // 멈추면 아직 안 뜬 줄도 그 자리에 선다 — 타이머만 걷으면 된다(음성 있는 장은
  // 시계가 멈춘 오디오를 읽으므로 저절로 선다).
  if(on){ clearTimeout(hold); pauseHtml();
          if(m.a)m.a.pause(); if(m.v)m.v.pause(); }
  else  { if(m.a)m.a.play().catch(()=>{}); if(m.v&&slides[i].classList.contains('vplay'))
            m.v.play().catch(()=>{});
          armShots(slides[i]);
          armHtml(slides[i],true);        // 이어서 — 흐른 시간을 이어 센다
  armAuto(slides[i]); }
  paint();
}

function paint(){
  /* ★ 이 단추는 **항상 보인다.** 예전엔 자동일 때만 나타났는데, 자동을 켜는
   * 길이 A 키뿐이라 키를 모르면 영영 못 켰다. 그래서 편집 화면에 "전체 자동
   * 재생" 버튼을 따로 뒀고, 그게 "슬라이드 보기" 와 같은 것으로 보였다.
   * 여기서 켤 수 있으면 버튼은 하나면 된다. */
  if(pz){
    pz.hidden=false;
    pz.textContent=!auto?'▶ 자동 재생':(paused?'▶ 이어서':'❚❚ 멈춤');
    pz.className=(auto&&!paused)?'on':'';
    pz.title=!auto?'내레이션이 끝나면 다음 장으로 — 녹화용 (A)':'멈춤 (Space)';
  }
  hud.innerHTML='<b>'+(i+1)+'</b> / '+slides.length
    +(auto?(paused?' &nbsp;<em class="p">멈춤</em>':' &nbsp;<em>자동</em>'):'')
    +' &nbsp;<kbd>Space 멈춤 · ← → · A 자동 · C 자막</kbd>';
}

function setAuto(on){
  auto=on;
  paused=false;
  clearTimeout(hold);
  const u=new URL(location); on?u.searchParams.set('auto','1'):u.searchParams.delete('auto');
  history.replaceState(null,'',u);
  // ★ 음악은 **자동 재생일 때만** 저절로 튼다. 손으로 넘기며 설명하는 자리에서는
  //   음악이 말을 방해하기만 한다. 필요하면 ♪ 나 M 으로 켠다.
  if(BG.on) bgmSet(on);
  if(on){ if(!started){started=true;if(gate)gate.className='off';} go(i); }
  else { clearTimeout(hold); paint(); }
}
if(pz)pz.onclick=()=>{ if(!auto){setAuto(true);setPaused(false);} else setPaused(!paused); };
addEventListener('click',e=>{if(e.target.closest('video,audio,a,button,#bar'))return;
  go(e.clientX<innerWidth*0.28?i-1:i+1);});
let x0=null;
addEventListener('touchstart',e=>x0=e.touches[0].clientX,{passive:true});
addEventListener('touchend',e=>{if(x0==null)return;
  const dx=e.changedTouches[0].clientX-x0;if(Math.abs(dx)>50)go(i+(dx<0?1:-1));x0=null;},{passive:true});

/* 한 장만 보는 자리에서는 서버가 문을 아예 안 그린다. 여기서는 있으면 잇는다. */
if(gate){
  gate.querySelector('[data-go="manual"]').onclick=()=>{started=true;gate.className='off';go(i);};
  gate.querySelector('[data-go="auto"]').onclick=()=>{started=true;gate.className='off';setAuto(true);};
}
/* 자동재생 정책 때문에 첫 제스처가 필요하다. 다만 —
   · 한 장만 보는 자리(`?n=`)  문을 아예 없앤다. 소리도 내지 않는다
   · 음성이 하나도 없는 덱      낼 소리가 없으니 문이 필요 없다
   ★ 배경음악이 있으면 **낼 소리가 있다.** 내레이션이 없다고 문을 닫아 버리면
     첫 제스처가 사라져서 음악이 정책에 막힌다. */
if(!gate){started=false;}
else if(!document.querySelector('audio.na')&&!BG.on){started=true;gate.className='off';}
go(i);
"""


class PreviewResolver:
    """미리보기 — 서버 API 로 미디어를 가리킨다(파일 복사 없음)."""

    def __init__(self, pid: int) -> None:
        self.pid = pid

    def asset(self, rel: str) -> str:
        from urllib.parse import quote
        return f"/api/projects/{self.pid}/file/{quote(rel)}" if rel else ""

    def video(self, s: Dict[str, Any]) -> str:
        v = s.get("video_id")
        return f"/api/projects/{self.pid}/video/{v}" if v else ""


def cue_map(deck: Dict[str, Any]) -> Dict[str, List[Any]]:
    """장별 자막 큐 `[[start, end, text], …]`. SRT 파일을 다시 읽지 않고
    같은 분할 규칙을 여기서 한 번 더 돌린다 — 산출물이 자기완결이어야 한다."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from vendor.vw_srt import auto_time_cues, split_into_cues

    out: Dict[str, List[Any]] = {}
    for s in deck.get("slides") or []:
        txt = (s.get("narration") or {}).get("srt_text") or ""
        if not txt:
            continue
        dur = float((s.get("audio") or {}).get("sec")
                    or (s.get("narration") or {}).get("est_sec") or 0)
        if dur <= 0:
            continue
        cues = auto_time_cues(split_into_cues(txt), dur)
        out[str(s.get("no"))] = [[round(c.start, 2), round(c.end, 2), c.text] for c in cues]
    return out


def render_deck(deck: Dict[str, Any], res, *, title: str = "",
                one: bool = False, bgm: str = "", bgm_vol: float = 0.15,
                bgm_duck: float = 0.04) -> str:
    sections = deck.get("sections") or []
    lane_i = {s["id"]: i for i, s in enumerate(sections)}
    slides = deck.get("slides") or []
    total = len(slides)
    proj = deck.get("project") or {}

    for s in slides:
        s["_project"] = proj
    body = "".join(_slide(s, lane_i.get(s.get("section"), 0), total, res) for s in slides)
    for s in slides:
        s.pop("_project", None)

    t = esc(title or proj.get("title") or "덱")
    # ★ 한 장만 보는 자리(편집 화면 iframe)에는 배경음악을 넣지 않는다. 거기서
    #   소리가 나면 스무 장을 훑는 동안 스무 번 음악이 새로 시작한다.
    bg = "" if one else (bgm or "")
    data = json.dumps({"cues": cue_map(deck),
                       "bgm": {"on": bool(bg), "vol": bgm_vol, "duck": bgm_duck}},
                      ensure_ascii=False)

    return (
        "<!DOCTYPE html><html lang=\"ko\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{t}</title>"
        "<meta name=\"color-scheme\" content=\"light\">"
        f"<style>{CSS}</style>"
        # 참고 원고의 원래 스타일 — **문서당 한 벌, 페이지에 한 번.** 장마다 넣으면
        # 4KB 짜리가 장 수만큼 복사돼 `dist/` 한 장 파일이 수백 KB 씩 불어난다.
        # 셀렉터는 이미 `.doc` 밑으로 가둬져 있다(tools/split_sections.mjs) —
        # 안 가두면 원고의 `body{}` · `*{max-width:100%}` 가 덱 CSS 를 무너뜨린다.
        + (f"<style>{deck.get('html_style')}</style>" if deck.get("html_style") else "")
        + "</head><body>"
        f"<main id=\"deck\">{body}</main>"
        "<div id=\"cc\"></div>"
        + ("" if one else
           "<div id=\"gate\"><div class=\"gate-in\">"
           "<button type=\"button\" data-go=\"manual\">&#9654; 시작</button>"
           "<button type=\"button\" data-go=\"auto\" class=\"alt\">&#9654;&#9654; 자동 재생</button>"
           "<p>자동 재생은 내레이션이 끝나면 다음 장으로 넘어갑니다 — 이대로 화면녹화하면 발표 영상이 됩니다.<br>"
           "언제든 ←/→ 로 끼어들 수 있고, A 로 자동을 껐다 켤 수 있습니다.</p></div></div>")
        + (f"<audio id=\"bgm\" loop preload=\"auto\" src=\"{bg}\"></audio>"
           "<button id=\"bgmb\" type=\"button\" title=\"배경음악 켜기/끄기 (M)\">"
           "&#9834;</button>" if bg else "")
        + "<button id=\"pz\" type=\"button\" hidden></button>"
        # 아바타(말하는 사람) 자리 — 지금은 **비어 있다.** 자리만 잡아 두면 나중에
        # 채울 때 이 한 줄에 내용만 넣으면 되고, 그 전까지 다른 것이 그 자리를
        # 차지하지 않는다(그래서 재생 단추들을 우상단으로 올렸다).
        "<div id=\"av\"></div>"
        "<div id=\"bar\"></div><div id=\"hud\"></div>"
        f"<script>window.__DECK__={data};</script>"
        f"<script>{JS}</script></body></html>"
    )
