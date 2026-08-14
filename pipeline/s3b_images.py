# -*- coding: utf-8 -*-
"""S3b 슬라이드 이미지 — **파일로만 주고받는다.**

`text_image` 레인 장에는 그림이 들어간다. 그 그림은 이 앱이 만들지 않는다.
이미지 에이전트(`260628-로컬이미지_앞에프롬프트필더`)가 ChatGPT OAuth 로 만들고,
여기는 **Claude 구독 OAuth** 를 쓴다. 둘을 코드로 잇지 않는다.

    이 앱  →  09_이미지/slides.json   (프롬프트 목록)
              ↓  사람이 이미지 앱에 넣고 돌린다
    이 앱  ←  09_이미지/005.png       (번호가 곧 슬라이드 번호)

★ 브릿지를 만들지 않는 이유는 취향이 아니라 사고 예방이다. 두 앱은 인증 주체가
  다르고, 프로세스를 이어 붙이면 한쪽 세션이 다른 쪽 계정으로 도는 사고가 난다.
  **접점은 폴더 하나**고, 그 폴더는 사람이 눈으로 볼 수 있다.

파일명 규약은 `260804-ppt2eduvideo` 의 것을 그대로 쓴다 — `{"prompts":[{"n":5,
"prompt":"…"}]}` 를 내보내고 `005.png` 로 받는다. 그쪽 앱이 이미 이 모양을 안다.

이 스테이지는 **결정론**이다. Claude 를 부르지 않는다 — 프롬프트는 S2b 가 이미 쓴
제목·본문에서 조립한다. 그림 지시를 또 생성하면 화면 문구와 그림이 따로 논다.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from core import workspace as ws
from pipeline.registry import STAGES, cached_data, write_cache

# 이미지가 필요한 레인
WANT_MEDIA = {"text_image"}
STYLE = ("평평한 벡터 일러스트, 굵은 윤곽선 없음, 배경 아이보리 #f7f5f1, "
         "강조색 테라코타 #9a4d33 계열 한 가지만, 글자 없음, 사람 얼굴 없음, "
         "16:9 가로")


def build_prompt(s: Dict[str, Any], dec: Dict[str, Any]) -> str:
    """슬라이드가 말하는 것을 **한 장면**으로 압축한다.

    화면 문구를 그대로 그림으로 옮기지 않는다 — 글자를 그리게 하면 반드시 깨진다.
    개념을 도형·배치로 옮기고, 글자는 렌더러가 HTML 로 얹는다.
    """
    bits: List[str] = [s.get("title") or ""]
    if s.get("note"):
        bits.append(re.sub(r"\s+", " ", s["note"])[:220])
    d = dec.get(str(s["no"]))
    if d:
        if d.get("problem"):
            bits.append("문제: " + re.sub(r"\s+", " ", d["problem"])[:120])
        if d.get("choice"):
            bits.append("선택: " + re.sub(r"\s+", " ", d["choice"])[:120])
    body = " / ".join(b for b in bits if b)
    return (f"{body}\n\n이 내용을 설명하는 개념도 한 장. **그림 안에 글자를 넣지 마라** "
            f"— 텍스트는 나중에 따로 얹는다. {STYLE}")


def run(job, pid: int, slug: str, project: Dict[str, Any], *, force: bool = False):
    stage = STAGES["s3b-images"]

    outline = cached_data(pid, slug, "s2b-outline") or {}
    slides = outline.get("slides") or []
    if not slides:
        raise RuntimeError("구조 설계(s2b-outline)를 먼저 돌리세요")
    dec = (cached_data(pid, slug, "s5-decisions") or {}).get("slides", {})

    targets = [s for s in slides if s.get("media_kind") in WANT_MEDIA]
    d = ws.step_dir(pid, slug, "images")

    prompts = [{"n": s["no"], "prompt": build_prompt(s, dec),
                "title": s.get("title") or ""} for s in targets]
    ws.write_json(d / "slides.json", {
        "schema": "codex-studio-slides@1",
        "project": project.get("title") or slug,
        "count": len(prompts),
        "prompts": prompts,
    })

    # ★ 그림은 **두 곳**에서 온다. 규칙은 하나 — 파일명이 번호로 시작하면 그 장이다.
    #     09_이미지/       이미지 에이전트가 낸 것
    #     00_기획/참고/    기획서가 "이 캡처가 필요합니다" 해서 사람이 찍어 넣은 것
    #   요청(기획서)과 납품(참고 폴더)이 한 자리에 있어야 잊히지 않는다.
    ref_dir = ws.sub_dir(pid, slug, "prd", "참고", create=False)
    ref_by_no: Dict[int, Path] = {}
    if ref_dir.is_dir():
        from core.refs import IMG_EXT, slide_no
        for f in sorted(ref_dir.iterdir()):
            if not (f.is_file() and f.suffix.lower() in IMG_EXT):
                continue
            # 복사할 때 `01-` 접두가 붙으므로 원래 이름 뒤쪽에서도 번호를 찾는다
            n = slide_no(f.name) or slide_no(re.sub(r"^\d{2}-", "", f.name))
            if n and n not in ref_by_no:
                ref_by_no[n] = f

    # ★ 한 장에 **여러 그림**을 넣을 수 있다. 멘토링처럼 신청 화면과 수락 화면이
    #   따로 있는 메뉴는 한 컷으로 안 된다. 규칙은 번호 뒤에 `-2`, `-3`:
    #       005.png · 005-2.png · 005-3.png
    #   순서는 파일명 순이고, 발표에서 대본 시간을 나눠 차례로 넘어간다.
    found: Dict[str, Any] = {}
    missing: List[int] = []
    EXT = (".png", ".webp", ".jpg", ".jpeg")
    for s in targets:
        no = s["no"]
        shots: List[Dict[str, Any]] = []

        def add(f: Path, step: str) -> None:
            shots.append({"file": f"{step}/{f.name}", "name": f.name,
                          "bytes": f.stat().st_size,
                          "from": "참고" if step.endswith("참고") else "이미지"})

        for base, step in ((d, ws.STEPS["images"][0]),
                           (ref_dir, f"{ws.STEPS['prd'][0]}/참고")):
            if not base.is_dir():
                continue
            for f in sorted(base.iterdir()):
                if not (f.is_file() and f.suffix.lower() in EXT):
                    continue
                stem = re.sub(r"^\d{2}-", "", f.stem)       # 참고 폴더의 복사 접두 제거
                m = re.match(r"^0*(\d{1,3})(?:-(\d+))?$", stem)
                if m and int(m.group(1)) == no:
                    add(f, step)
        if shots:
            found[str(no)] = {**shots[0], "shots": shots, "count": len(shots)}
        else:
            missing.append(no)

    multi = [k for k, v in found.items() if v.get("count", 1) > 1]
    if multi:
        job.add_log(f"그림 여러 장인 슬라이드: "
                    + ", ".join(f"{k}({found[k]['count']}장)" for k in sorted(multi, key=int)))
    n_ref = sum(1 for v in found.values() if v.get("from") == "참고")
    job.add_log(f"이미지가 필요한 장 {len(targets)}개 → 도착 {len(found)}개"
                + (f" (참고 폴더에서 {n_ref}개)" if n_ref else ""))
    job.add_log(f"프롬프트: {d / 'slides.json'}")
    if missing:
        job.add_log(f"아직 없는 그림: {missing}")
        job.add_log(f"번호로 넣으면 붙습니다 — {d}")
        job.add_log(f"  또는 직접 찍은 캡처를 {ref_dir} 에 005.png 처럼")

    warn = [f"그림이 없는 장 {len(missing)}개: {missing}"] if missing else []
    return write_cache(pid, slug, "s3b-images",
                       input_hash=stage.input_hash(pid, slug, project),
                       data={"dir": str(d), "targets": [s["no"] for s in targets],
                             "images": found, "missing": missing},
                       code_version=stage.code_version,
                       status="degraded" if missing else "ok", warnings=warn)


STAGES["s3b-images"].run = run
