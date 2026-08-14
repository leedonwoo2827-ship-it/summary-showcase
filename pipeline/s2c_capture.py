# -*- coding: utf-8 -*-
"""S2c 구조 설계 — HTML 참고자료를 **그대로** 슬라이드 구조로.

참고자료가 이미 장별로 정리된 HTML(이론 요약 같은 것)이면, "몇 장으로 나눌까"
를 AI 가 판단할 필요가 없다 — 제목 경계가 이미 그 판단이다. 그래서 HTML 참고
자료가 있으면 이 문으로 들어와 S0a(설문)·S0(기획서)·S2b(AI 구조설계)를 전부
건너뛰고 **바로 목차가 확정된 상태**로 간다.

    참고자료의 HTML 문서 하나당: 표지 1장 + 항목마다 1장 + 마무리 1장
    문서가 여럿이면 순서대로 이어 붙인다.

── 두 가지 방식 ────────────────────────────────────────────────────────
`html`(기본) — `tools/split_sections.mjs` 가 그 구간의 **HTML 을 오려 온다.**
    납작한 그림이 아니라 살아 있는 글이라, 줄 하나씩 시간에 맞춰 나타나게 할 수
    있고 나중에 그 줄을 영상으로 갈아끼울 수도 있다. 글자도 원래 해상도로 다시
    그려져 더 선명하다.
`image` — `tools/capture_sections.mjs` 가 **화면을 찍어 PNG** 로 만든다. 2026-08-14
    까지 쓰던 방식. 원고가 오려 내기 어려운 꼴이면(본문이 제목보다 깊이 들어가
    있다든지) 이쪽으로 되돌릴 수 있게 남겨 둔다. `showcase.config.json` 의
    `capture.mode` 또는 프로젝트의 `capture_mode` 로 고른다.

결과는 s2b-outline 캐시를 **직접 쓴다**(오버라이드가 아니다) — 뒤 단계
(문구·대본)가 그 캐시를 읽으므로, 여기서 확정해야 곧바로 이어진다.
"""
from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from core import config, htmldoc, workspace as ws
from pipeline.registry import STAGES, write_cache

APP = Path(__file__).resolve().parent.parent
CAPTURE_SCRIPT = APP / "tools" / "capture_sections.mjs"
SPLIT_SCRIPT = APP / "tools" / "split_sections.mjs"


def _mode(project: Dict[str, Any]) -> str:
    """`html`(기본) 또는 `image`. 프로젝트가 설정보다 세다."""
    cfg = (config.load().get("capture") or {}).get("mode")
    m = str(project.get("capture_mode") or cfg or "html").lower()
    return m if m in ("html", "image") else "html"


def _node(job, cmd: List[str], what: str, *, timeout: int = 180) -> None:
    proc = subprocess.run(cmd, cwd=str(APP), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    for line in (proc.stdout or "").splitlines():
        if line.strip():
            job.add_log("  " + line[:160])
    if proc.returncode != 0:
        for line in (proc.stderr or "").splitlines()[-6:]:
            if line.strip():
                job.add_log("  " + line[:200])
        raise RuntimeError(f"{what} 실패")


def _split(job, node: str, pid: int, slug: str, root: Path, i: int,
           src: Path, item: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """원고를 항목별로 나눈 HTML 한 장을 만들고, 그 파일의 프로젝트 상대 경로를 준다.

    ★ **이미 나뉜 원고는 다시 나누지 않는다.** 사람이 `_new-context/1과목2.html`
      처럼 이미 나눠 둔 것을 그대로 넣는 흐름이 있다(그 파일은 브라우저로 열어
      눈으로 확인한 바로 그 파일이다). 다시 나누면 그 파일의 `<section>` 들이
      본문으로 오인돼 빈 장이 잔뜩 생긴다. 안에 `#manifest` 가 있으면 나뉜
      원고라는 뜻이므로 손대지 않고 그대로 쓴다.
    """
    label = item.get("label") or src.stem
    man = htmldoc.manifest(src)
    if man:
        job.add_log(f"  {label} — 이미 나뉜 원고({len(man.get('slides') or [])}장), 그대로 씁니다")
        return man, item["file"]

    out_dir = ws.cache_dir(pid, slug) / "_split" / str(i)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{src.stem}2.html"
    _node(job, [node, str(SPLIT_SCRIPT), str(src), "--out", str(out)],
          f"{label} 나누기")
    man = htmldoc.manifest(out)
    if not man:
        raise RuntimeError(f"{label} — 나눈 결과에서 장 목록을 못 읽었습니다")

    # 참고자료 자리에 앉힌다 — 렌더러가 여기서 조각을 오려 온다
    d = ws.sub_dir(pid, slug, "prd", "참고")
    name = f"{ws.nfc(src.stem)}2.html"
    (d / name).write_bytes(out.read_bytes())
    return man, f"{ws.STEPS['prd'][0]}/참고/{name}"


def _capture(job, node: str, pid: int, slug: str, i: int, src: Path,
             label: str) -> Tuple[Dict[str, Any], Path]:
    """예전 방식 — 화면을 찍어 PNG 로. `capture.mode: "image"` 일 때만 온다."""
    out_dir = ws.cache_dir(pid, slug) / "_capture" / str(i)
    _node(job, [node, str(CAPTURE_SCRIPT), str(src), "--out", str(out_dir)],
          f"{label} 캡처", timeout=120)
    man = ws.read_json(out_dir / "manifest.json", None)
    if not man:
        raise RuntimeError(f"{label} manifest 를 못 읽었습니다")
    return man, out_dir


def run(job, pid: int, slug: str, project: Dict[str, Any], *, force: bool = False):
    stage = STAGES["s2c-capture"]
    root = ws.project_dir(pid, slug)
    refs = (project.get("refs") or {}).get("items") or []
    html_items = [r for r in refs if r.get("kind") == "html"]
    if not html_items:
        raise RuntimeError("HTML 참고자료가 없습니다")

    node = shutil.which("node")
    if not node:
        raise RuntimeError("node 를 찾지 못했습니다 — Node.js 설치를 확인하세요")

    mode = _mode(project)
    job.add_log(f"방식: {'HTML 그대로 오려 오기' if mode == 'html' else '화면 캡처(PNG)'}")

    slides: List[Dict[str, Any]] = []
    images: List[Tuple[int, Path]] = []
    no = 1
    job.progress(0, len(html_items), "구조 읽기")
    for i, item in enumerate(html_items, 1):
        src = root / item["file"]
        if not src.is_file():
            job.add_log(f"  건너뜀 — 파일 없음: {src}")
            continue
        label = item.get("label") or src.stem

        if mode == "html":
            manifest, doc_rel = _split(job, node, pid, slug, root, i, src, item)
        else:
            manifest, out_dir = _capture(job, node, pid, slug, i, src, label)
            doc_rel = None

        for s in manifest["slides"]:
            # manifest 의 `section` 은 항목 갈래일 뿐 — 덱의 장 종류(SLIDE_KINDS)에는
            # 없는 이름이다. 표지·마무리만 그대로 두고 나머지는 `note` 로 앉힌다.
            k = s.get("kind") or "note"
            slide: Dict[str, Any] = {
                "no": no, "section": label,
                "kind": k if k in ("cover", "closing") else "note",
                "title": s["title"], "note": "",
                "media_kind": s.get("media_kind", "text"), "video_id": None,
                "evidence_hint": "", "body": "", "narration": {},
            }
            if slide["media_kind"] == "html" and doc_rel:
                blocks = s.get("blocks") or []
                # ★ 조각 HTML 자체는 여기 담지 않는다. 원고 파일이 원본이고 슬라이드는
                #   거기를 가리킬 뿐이다 — 조각을 목차 캐시에 복사해 넣으면 원고를
                #   고쳤을 때 두 벌이 어긋난다. 조각은 조립(s8)이 그때 읽어 온다.
                slide["html_file"] = doc_rel
                slide["html_sec"] = s.get("sec")
                slide["html_blocks"] = len(blocks)
                # 수정 화면이 줄마다 보여 줄 미리보기 — HTML 을 파싱하지 않게 미리 뽑아 둔다
                slide["html_text"] = [b.get("text") or "" for b in blocks]
                # 줄 길이 — 조립(s8)이 음성 길이를 알게 된 뒤 시각을 다시 나눌 때 쓴다.
                # `html_text` 는 80자에서 잘린 미리보기라 길이를 재는 데 못 쓴다.
                slide["html_chars"] = [int(b.get("chars") or 0) for b in blocks]
                # 자동 배분값. 사람이 고친 값(overrides.html_at)이 이것을 이긴다.
                slide["html_at_default"] = [float(b.get("at") or 0) for b in blocks]
                if s.get("q"):
                    slide["evidence_hint"] = f"문항 {s['q']}회"
            if s.get("image"):
                images.append((no, out_dir / s["image"]))
            slides.append(slide)
            no += 1
        job.progress(i, len(html_items), f"{label} 완료")

    if not slides:
        raise RuntimeError("씬을 하나도 못 만들었습니다")

    # ── 목차(s2b-outline 캐시)를 직접 확정한다 ──────────────────────────────
    secs_by_id: Dict[str, Dict[str, Any]] = {}
    for s in slides:
        lb = s["section"]
        if lb and lb not in secs_by_id:
            secs_by_id[lb] = {"id": lb, "title": lb, "kind": "text", "summary": ""}
    for sec in secs_by_id.values():
        sec["slide_nos"] = [s["no"] for s in slides if s["section"] == sec["id"]]

    outline_data = {
        "deck_title": project.get("title") or slug, "deck_subtitle": "",
        "sections": list(secs_by_id.values()), "slides": slides,
        "budget": len(slides), "dropped": [],
    }
    write_cache(pid, slug, "s2b-outline",
               input_hash="capture:" + stage.input_hash(pid, slug, project),
               data=outline_data, code_version=STAGES["s2b-outline"].code_version,
               model=f"({'원고' if mode == 'html' else '캡처'})",
               cost_usd=0.0, status="ok", warnings=[])

    # ── 캡처 이미지를 그 장의 참고자료 자리에 앉힌다 (image 방식일 때만) ────
    if images:
        d = ws.sub_dir(pid, slug, "prd", "참고")
        ov = ws.load_overrides(pid, slug)
        for no_, img_path in images:
            raw = img_path.read_bytes()
            name = f"{no_:03d}.png"
            (d / name).write_bytes(raw)
            rel = f"{ws.STEPS['prd'][0]}/참고/{name}"
            cur = ov.setdefault("slides", {}).setdefault(str(no_), {})
            cur["images"] = [rel]
            cur["image"] = rel
        ws.save_overrides(pid, slug, ov)

    # ── 목차 확정 표시 — 화면이 "설문/기획서"가 아니라 "목차 확정됨"으로 본다
    doc = ws.load_project(pid, slug)
    doc["outline_confirmed_at"] = datetime.now().isoformat(timespec="seconds")
    doc["slide_budget"] = len(slides)
    doc["overrides_rev"] = int(doc.get("overrides_rev") or 0) + 1
    ws.save_project(pid, slug, doc)

    n_html = sum(1 for s in slides if s["media_kind"] == "html")
    n_line = sum(int(s.get("html_blocks") or 0) for s in slides)
    extra = f" · 원고 장 {n_html}개(줄 {n_line}개)" if n_html else ""
    job.add_log(f"씬 확정 — {len(slides)}장 (문서 {len(html_items)}개){extra}"
                " · 문구·대본을 채우면 됩니다")

    return write_cache(pid, slug, "s2c-capture",
                       input_hash=stage.input_hash(pid, slug, project),
                       data={"slides": len(slides), "docs": len(html_items),
                             "mode": mode, "html_slides": n_html, "lines": n_line},
                       code_version=stage.code_version, status="ok", warnings=[])


STAGES["s2c-capture"].run = run
