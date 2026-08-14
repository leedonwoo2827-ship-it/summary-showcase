# -*- coding: utf-8 -*-
"""S6 내레이션 대본 — 37장 전체의 **자막**과 **발음**.

세 텍스트가 서로 다르다. 이걸 섞으면 발표가 교안 낭독이 된다:

    슬라이드 문구   화면에 박혀 있는 글      (S2b·S5 가 이미 만든 것)
    자막 srt_text   입으로 말하는 것의 원문   ← 여기서 만든다
    발음 narration  TTS 가 소리 내는 표기     ← 여기서 만든다

`srt_text` 와 `narration_text` 는 **같은 문장의 두 표기**다. "2vCPU" 를 자막엔
그대로 두고 발음만 "투 브이씨피유" 로 바꾼다. voicewright 가 이미 쓰는 규약이라
TTS 가 공짜로 붙는다.

★ **영상 장은 길이가 제약이다.** 대본이 클립보다 길면 영상이 끝나고 말이 남는다.
  한 영상을 여러 장이 나눠 쓰면 길이도 나눠 갖는다. 초과분은 경고로 남기고
  편집표에서 눈에 띄게 한다 — 줄이든 마지막 프레임을 홀드하든 사람이 정한다.

S5 와 같은 이유로 **묶음으로 쪼갠다.** 한 콜에 37장을 넣으면 예산에서 끊기고
그때까지 쓴 것이 통째로 날아간다(실제로 겪었다).
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Dict, List

from core import config, workspace as ws
from llm.claude_provider import ClaudeProvider
from pipeline.registry import STAGES, cached_data, write_cache

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "no": {"type": "integer"},
                    "srt_text": {"type": "string"},
                    "narration_text": {"type": "string"},
                },
                "required": ["no", "srt_text", "narration_text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["slides"],
    "additionalProperties": False,
}

# 장 종류별 기본 길이(초). 영상 장은 클립 길이가 이긴다.
BASE_SEC = {
    "cover": 8, "context": 14, "feature": 16, "architecture": 18,
    "decision": 20, "metric": 14, "ops": 14, "note": 12, "closing": 10,
}
MD = re.compile(r"[*_`#>\[\]]|^\s*[-•]\s+", re.M)


def est_sec(text: str, cps: float) -> float:
    """scriptforge 규칙 — 공백 뺀 글자수 / 초당 글자수."""
    n = len(re.sub(r"\s", "", text or ""))
    return round(math.ceil(n / max(cps, 0.1) * 10) / 10, 1)


def budgets(slides: List[Dict[str, Any]], frames: Dict[str, Any],
            clips: Dict[str, Any] | None = None,
            target_sec: float = 0.0) -> Dict[int, float]:
    """장마다 몇 초를 줄지. **영상 장은 클립 길이를 n등분한다.**

    한 영상을 3장이 나눠 쓰면 각 장은 그 영상의 1/3 안에서 말해야 한다.
    그래야 슬라이드를 넘길 때 영상도 같이 흘러간다.
    """
    clips = clips or {}
    share: Dict[str, int] = {}
    for s in slides:
        if s.get("video_id"):
            share[s["video_id"]] = share.get(s["video_id"], 0) + 1

    out: Dict[int, float] = {}
    for s in slides:
        vid = s.get("video_id")
        if vid:
            # ★ **자른 길이를 따른다.** 사람이 구간을 줄였으면 그만큼만 말하면 된다.
            #   원본 길이로 잡으면 잘라 놓고도 대본이 그대로라 발표가 안 줄어든다.
            c = (clips.get(str(s["no"])) or {}).get("clip") or {}
            cut = sum(max(0.0, float(b) - float(a)) for a, b in (c.get("cuts") or []))
            if c.get("end"):
                dur = max(1.0, (float(c["end"]) - float(c.get("start") or 0) - cut)
                          / float(c.get("speed") or 1))
                out[s["no"]] = max(6.0, round(dur, 1))
                continue
            dur = (frames.get(vid) or {}).get("duration_sec")
            if dur:
                # ★ 영상 시간을 **채우는 것**이 목표다. 예전엔 0.5초를 빼서 "이 안에
                #   들어가라" 로 줬는데, 그러니 짧게 쓰고 영상만 도는 시간이 생겼다
                #   (실제로 181초). 이제는 규칙이 다르다 — 둘 중 긴 쪽을 기다리고
                #   영상이 짧으면 마지막 프레임에서 선다. 그러니 채우는 게 맞다.
                out[s["no"]] = max(6.0, round(dur / share[vid], 1))
                continue
        out[s["no"]] = float(BASE_SEC.get(s.get("kind"), 12))

    # ★ 목표 길이가 정해져 있으면 **텍스트 장을 거기에 맞춘다.**
    #   영상 장은 이미 클립 길이로 고정이라 건드리지 않는다. 남는 시간을
    #   텍스트 장에 나눠 준다 — 종류별 비중(표지는 짧고 판단은 길게)은 지킨다.
    if target_sec:
        vid_no = {s["no"] for s in slides if s.get("video_id")}
        txt = [s["no"] for s in slides if s["no"] not in vid_no]
        used = sum(out[n] for n in vid_no)
        left = max(0.0, target_sec - used)
        base = sum(out[n] for n in txt) or 1.0
        if txt and left > 0:
            k = left / base
            for n in txt:
                out[n] = max(5.0, round(out[n] * k, 1))
    return out


def build_brief(chunk: List[Dict[str, Any]], deck: Dict[str, Any],
                dec: Dict[str, Any], budget: Dict[int, float],
                prev_tail: str) -> str:
    lines: List[str] = []
    lines.append(f"# 발표\n{deck.get('deck_title') or ''}")
    if deck.get("deck_subtitle"):
        lines.append(deck["deck_subtitle"])
    lines.append(f"총 {len(deck.get('slides') or [])}장 중 아래 {len(chunk)}장을 쓴다.")
    if prev_tail:
        lines.append(f"\n# 바로 앞 장의 마지막 말\n{prev_tail}\n여기서 이어라.")

    lines.append("\n# 쓸 장")
    for s in chunk:
        no = s["no"]
        lines.append(f"\n## {no} · {s.get('title') or ''}   (목표 {budget[no]:.0f}초)")
        lines.append(f"종류: {s.get('kind')}")
        if s.get("note"):
            lines.append(f"화면 문구: {s['note']}")
        if s.get("video_id"):
            sec = budget[no]
            lines.append(f"영상: {s['video_id']} — 이 장에서 화면 녹화가 {sec:.0f}초 동안 "
                         f"돈다. **그 시간을 채워라.** 화면에서 벌어지는 일을 순서대로 "
                         f"짚으면 그만큼 나온다 (공백 뺀 글자 약 {int(sec * 5.7)}자).")
        if s.get("evidence_hint"):
            lines.append(f"근거: {s['evidence_hint']}")
        d = dec.get(str(no))
        if d:
            lines.append("판단(이 장의 재료 — 화면에 이미 적힌 것은 다시 읽지 마라):")
            for k, label in (("problem", "증상"), ("choice", "고른 것"),
                             ("rationale", "이유"), ("tradeoff", "포기한 것")):
                if d.get(k):
                    lines.append(f"  {label}: {d[k]}")
            for e in (d.get("evidence") or [])[:3]:
                lines.append(f"  근거: {e.get('ref')}")

    lines.append("\n주어진 no 만 채워라. JSON 만 출력.")
    return "\n".join(lines)


def clean(t: str) -> str:
    """평문만 남긴다 — 렌더러도 자막도 마크다운을 모른다."""
    return MD.sub("", str(t or "")).strip()


def run(job, pid: int, slug: str, project: Dict[str, Any], *, force: bool = False):
    cfg = config.load()
    stage = STAGES["s6-script"]

    deck = cached_data(pid, slug, "s2b-outline") or {}
    slides = deck.get("slides") or []
    if not slides:
        raise RuntimeError("구조 설계(s2b-outline)를 먼저 돌리세요")
    dec = (cached_data(pid, slug, "s5-decisions") or {}).get("slides", {})
    frames = (cached_data(pid, slug, "s1-frames") or {}).get("items", {})

    cps = float((project.get("narration") or cfg["narration"]).get("chars_per_sec", 5.7))
    ovr = ws.load_overrides(pid, slug)
    target_sec = float(ovr.get("target_min") or 0) * 60
    budget = budgets(slides, frames, ovr.get("slides", {}), target_sec)
    if target_sec:
        job.add_log(f"목표 {target_sec / 60:.0f}분 — 예산 합계 "
                    f"{sum(budget.values()) / 60:.1f}분")

    system = (Path(__file__).resolve().parent.parent
              / "llm" / "prompts" / "script.md").read_text(encoding="utf-8")

    # ★ 이미 나온 장은 다시 사지 않는다.
    #   묶음 하나가 실패해도 나머지는 살아남게 해 뒀는데, 재시도할 때 전부 다시
    #   부르면 실패 하나가 매번 전체 값을 물린다. 실패한 묶음만 채운다.
    prior = (cached_data(pid, slug, "s6-script") or {}).get("slides", {}) if not force else {}
    todo = [s for s in slides if str(s["no"]) not in prior]
    if prior:
        job.add_log(f"이미 나온 {len(prior)}장 재사용 · 남은 {len(todo)}장")

    CHUNK = int(cfg.get("script_chunk", 6))
    chunks = [todo[i:i + CHUNK] for i in range(0, len(todo), CHUNK)]
    job.add_log(f"{len(slides)}장 → {len(chunks)}묶음 (묶음당 {CHUNK}장)")
    job.progress(0, len(chunks), "대본")

    out: Dict[str, Any] = dict(prior)
    warn: List[str] = []
    total_cost = 0.0
    model_used = ""
    prev_tail = ""

    for ci, chunk in enumerate(chunks, 1):
        if job.canceled:
            warn.append(f"{ci}묶음에서 취소됨")
            break
        p = ClaudeProvider(
            model=(project.get("models") or cfg["models"]).get("script")
                  or cfg["models"]["script"],
            effort=cfg["effort"].get("script", "high"),
            allowed_tools=[],          # 레포를 다시 읽지 않는다 — 재료는 이미 왔다
            max_turns=1,
            budget_usd=cfg["budget_usd"]["per_stage"],
            # 2~3분씩 간다. 무엇을 읽고 있는지 보여야 멈춘 걸로 안 본다.
            on_activity=lambda s: job.progress(0, 1, s),
        )
        model_used = p.model
        nos = [s["no"] for s in chunk]
        try:
            raw = p.structured(
                system,
                [{"role": "user",
                  "content": build_brief(chunk, deck, dec, budget, prev_tail)}],
                schema=SCHEMA)
        except Exception as e:  # noqa: BLE001
            # 한 묶음이 실패해도 나머지는 계속한다
            warn.append(f"{ci}묶음({nos}) 실패: {type(e).__name__}: {str(e)[:120]}")
            job.add_log(f"  {ci}/{len(chunks)} 실패 — 계속")
            total_cost += p.last_cost_usd
            continue

        total_cost += p.last_cost_usd
        want = set(nos)
        got = 0
        for r in raw.get("slides") or []:
            no = int(r.get("no") or 0)
            if no not in want:
                warn.append(f"요청하지 않은 슬라이드 {no} → 버림")
                continue
            srt = clean(r.get("srt_text"))
            nar = clean(r.get("narration_text")) or srt
            if not srt:
                warn.append(f"{no}: 자막이 비어 있다")
                continue
            sec = est_sec(nar, cps)
            rec = {"srt_text": srt, "narration_text": nar,
                   "narration_seconds": sec, "budget_sec": budget[no]}
            # ★ 초과 판정은 **영상 장에만** 건다.
            #   텍스트 장의 목표 초는 길이를 잡아 주는 기준값일 뿐 제약이 아니다 —
            #   화면이 멈춰 있어도 되므로 대본이 길어도 아무것도 깨지지 않는다.
            #   영상은 다르다. 클립이 끝나고 말이 남으면 화면이 정지한 채 들린다.
            # ★ 이제 초과는 문제가 아니다. 재생기가 **둘 중 긴 쪽을 기다리고**
            #   영상이 짧으면 마지막 프레임에서 선다. 문제는 반대 — 영상은 도는데
            #   말이 모자란 경우다. 그걸 잡는다.
            is_video = any(s["no"] == no and s.get("video_id") for s in chunk)
            short = round(budget[no] - sec, 1)
            if is_video and short > 3.0:
                rec["short_sec"] = short
                warn.append(f"{no}: 영상이 {short:.0f}초 더 도는데 말이 없다")
            out[str(no)] = rec
            got += 1

        tail = None
        for s in reversed(chunk):
            if str(s["no"]) in out:
                tail = out[str(s["no"])]["srt_text"]
                break
        if tail:
            prev_tail = tail[-160:]

        job.progress(ci, len(chunks), f"{ci}/{len(chunks)}묶음 · ${total_cost:.2f}")
        job.add_log(f"  {ci}/{len(chunks)} {nos} → {got}장 · ${p.last_cost_usd:.3f}")

    missing = [s["no"] for s in slides if str(s["no"]) not in out]
    if missing:
        warn.append(f"대본이 없는 장: {missing}")

    total_sec = round(sum(v["narration_seconds"] for v in out.values()), 1)
    over = [n for n, v in out.items() if v.get("over_sec")]
    job.add_log(f"{len(out)}장 · 합계 {total_sec:.0f}초 "
                f"({total_sec / 60:.1f}분) · 길이 초과 {len(over)}장 · ${total_cost:.3f}")

    return write_cache(pid, slug, "s6-script",
                       input_hash=stage.input_hash(pid, slug, project),
                       data={"slides": out, "total_sec": total_sec,
                             "chars_per_sec": cps},
                       code_version=stage.code_version,
                       model=model_used, cost_usd=total_cost,
                       status="degraded" if (missing or over) else "ok",
                       warnings=warn)


STAGES["s6-script"].run = run
