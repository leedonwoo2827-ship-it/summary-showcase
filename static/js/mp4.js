/* 영상 렌더링 — 장마다 화면을 찍어 두고 **계산으로** mp4 한 편을 만든다(S12).
 *
 * ★ 예전에는 여기서 슬라이드를 통째로 재생하며 크롬이 그 탭을 스스로 받아 적게
 *   했다. 그 길은 버렸다(2026-08-14). 지지직 소리가 섞이고, 크롬이 mp4 안에
 *   opus 를 넣어 줘서 폰 갤러리·KMPlayer 가 검은 화면만 띄우고, 무엇보다
 *   **18분짜리를 얻으려면 18분을 실제로 재생해야 했다** — 그 사이 창을 한 번
 *   건드리면 그 회차가 통째로 날아간다.
 *
 * ★ 지금은 실시간이 아니라 계산이다. 장마다 줄이 뜨는 순간을 한 컷씩 찍어 두고,
 *   컷마다 다음 컷 시각까지 머무는 조각을 만들어 번호 순서로 잇는다. 조각 길이가
 *   곧 내레이션 길이라 **화면과 소리가 어긋날 자리가 없고**, 몇 번을 돌려도 같은
 *   파일이 나온다. 줄이 하나씩 뜨는 것도 그대로 담긴다(실측 4-2: 137장 → 571컷).
 *
 * ★ 이 화면이 하는 일은 두 가지뿐이다 — **미리 보고**, **굽는다.** 미리보기를
 *   1920 폭으로 그리는 것은 덱의 설계 해상도가 1920×1080 이기 때문이다. 더 좁게
 *   그리면 원고 상자의 줄바꿈이 달라져 여기서 본 것과 구운 것이 달라진다.
 */
"use strict";

import { el, api, icon, toast, fitFrame } from "./util.js";
import { state } from "./store.js";
import { navigate } from "./shell.js";
import { runSteps } from "./runner.js";
import { stepBadge, DECK } from "./steps.js";

export const meta = {
  title: "영상 렌더링",
  subtitle: "장마다 화면을 찍어 내레이션 길이만큼 이어 붙여 mp4 한 편을 만듭니다",
};

const clock = (s) => {
  const v = Math.max(0, Math.round(s));
  const m = Math.floor(v / 60);
  return `${m}:${String(v % 60).padStart(2, "0")}`;
};

export async function mount(root, ctx) {
  const page = el("div", "page vpage");
  root.appendChild(page);

  if (!state.projectId) {
    page.appendChild(el("div", "empty", "먼저 프로젝트를 고르세요."));
    return;
  }

  let deck;
  try {
    deck = await api(`/api/projects/${state.projectId}/deck`);
  } catch (e) {
    page.appendChild(el("div", "empty", "읽지 못했습니다: " + e.message));
    return;
  }
  const slides = ((deck.ready && deck.slides) || []).filter((s) => !s.drop);
  if (!slides.length) {
    const box = el("div", "empty");
    box.appendChild(el("p", null, "아직 장이 없습니다."));
    const b = el("button", "btn primary");
    b.type = "button";
    b.append(icon("layers", 14), el("span", null, "현황판 열기"));
    b.onclick = () => navigate("/board");
    box.appendChild(b);
    page.appendChild(box);
    return;
  }

  // 나올 영상의 길이는 **이미 정해져 있다** — 내레이션 길이의 합이 그대로 영상 길이다
  const totalSec = slides.reduce((a, s) =>
    a + ((s.audio && s.audio.sec) || (s.narration && s.narration.est_sec) || 0), 0);
  const nAudio = slides.filter((s) => s.audio && s.audio.file).length;

  const hd = el("div", "deck-head");
  const sum = el("p", "deck-sub");
  sum.textContent = `${slides.length}장 · 영상 ${clock(totalSec)}`
    + (nAudio === slides.length ? " · 음성 전부 있음"
       : ` · 음성 ${nAudio}/${slides.length}장 (없는 장은 무음으로 지나갑니다)`);
  hd.appendChild(sum);
  page.appendChild(hd);

  // ── 미리보기 ──────────────────────────────────────────────────────────
  const stage = el("div", "rec-stage");
  const fr = el("iframe", "focus-frame");
  fr.title = "슬라이드 전체 재생";
  fr.allow = "autoplay; fullscreen";
  stage.appendChild(fr);
  page.appendChild(stage);
  fitFrame(stage, fr, 1920);

  const src = () => `/preview/${state.projectId}?auto=1&bare=1&t=${Date.now()}#1`;
  fr.src = src();

  // ── 조작 ──────────────────────────────────────────────────────────────
  const bar = el("div", "rec-bar");
  page.appendChild(bar);

  const btn = el("button", "btn primary lg");
  btn.type = "button";
  const bLab = el("span", null, "(전체) 영상 렌더");
  btn.append(stepBadge(DECK.video, "영상 렌더링"), icon("film", 15), bLab);
  bar.appendChild(btn);

  const again = el("button", "btn");
  again.type = "button";
  again.append(icon("refresh", 14), el("span", null, "미리보기 처음부터"));
  again.onclick = () => { fr.src = src(); };
  bar.appendChild(again);

  const note = el("span", "rec-note", "");
  bar.appendChild(note);

  const out = el("div", "rec-out");
  out.hidden = true;
  page.appendChild(out);

  // ── 안내 ──────────────────────────────────────────────────────────────
  const help = el("div", "rec-help");
  help.appendChild(el("b", null, "누르고 자리를 뜨셔도 됩니다"));
  const ul = el("ul");
  for (const [t1, t2] of [
    ["재생하지 않습니다 — 계산해서 만듭니다",
     "장마다 화면을 사진으로 찍고, 이미 만들어 둔 내레이션 길이만큼 그 사진을 "
     + "보여 주는 조각을 만들어 번호 순서로 잇습니다. 재생 시간보다 빨리 끝납니다"],
    ["줄이 하나씩 뜨는 것도 담깁니다",
     "한 장을 줄이 뜨는 순간마다 여러 컷으로 나눠 찍습니다 — 내레이션이 그 줄을 "
     + "읽는 순간에 그 줄이 뜹니다"],
    ["화면과 소리가 어긋나지 않습니다",
     "조각 길이를 재생 타이밍이 아니라 내레이션 길이라는 숫자로 정하기 때문입니다. "
     + "몇 번을 돌려도 같은 파일이 나옵니다"],
    ["폰에서도 그냥 열립니다",
     "h264 / aac 로 굽고 색인을 파일 맨 앞에 둡니다 — 옮겨서 바로 재생됩니다"],
  ]) {
    const li = el("li");
    li.append(el("b", null, t1), el("span", null, t2));
    ul.appendChild(li);
  }
  help.appendChild(ul);
  page.appendChild(help);

  // ── 굽기 ──────────────────────────────────────────────────────────────
  /* 끝나면 **파일이 어디 있는지**와 **폴더 열기** 하나만 남긴다. 다음에 할 일이
     그것뿐이기 때문이다(내려받기는 두지 않는다 — 브라우저 기본 폴더에 떨어뜨리면
     나중에 "그 영상 어디 갔지" 가 되고, 이 앱은 산출물을 한 자리에 모아 왔다). */
  btn.onclick = async () => {
    again.disabled = true;
    out.hidden = true;
    out.textContent = "";
    note.textContent = "";
    note.className = "rec-note";

    /* 결과는 **스테이지가 이미 남기는 로그**에서 줍는다(`영상 완료 …` / `파일: …`).
       `/stages` 는 상태만 싣고 값을 안 실어 주므로, 값을 보자고 서버에 창구를 하나
       더 뚫는 것보다 이쪽이 낫다 — 로그는 어차피 사람이 보라고 찍고 있는 것이다. */
    const logs = [];
    const ok = await runSteps(["s12-video"], {
      btn, label: bLab, names: {"s12-video": "영상 렌더"},
      // ★ 한 줄이 아니라 **새로 늘어난 줄들**이 온다(runner.js) — 풀어서 담는다
      onLog: (lines) => {
        for (const l of lines) logs.push(String(l));
        note.textContent = (logs[logs.length - 1] || "").slice(0, 90);
      },
    });
    again.disabled = false;
    toast(ok ? "영상이 나왔습니다" : "영상 렌더를 끝내지 못했습니다", ok ? "ok" : "err");
    if (!ok) return;

    note.textContent = "";
    // 로그는 앞에 시각이 붙어 온다(`14:01:12  영상 완료 …`) — 떼고 본다
    const bare = logs.map((l) => l.replace(/^\d{2}:\d{2}:\d{2}\s+/, ""));
    const done = bare.filter((l) => l.startsWith("영상 완료")).pop() || "영상이 나왔습니다";
    const file = bare.filter((l) => l.startsWith("파일:")).pop() || "";

    out.hidden = false;
    out.appendChild(el("div", "fm-lb", done));
    if (file) out.appendChild(el("div", "imgdrop-path", file.replace(/^파일:\s*/, "")));

    const row = el("div", "imgdrop-bar");
    const open = el("button", "btn primary");
    open.type = "button";
    open.append(icon("folder", 14), el("span", null, "폴더 열기"));
    open.onclick = () =>
      api(`/api/projects/${state.projectId}/reveal`, {method: "POST"})
        .catch((e) => toast("폴더를 열지 못했습니다: " + e.message, "err"));
    row.appendChild(open);
    out.appendChild(row);
  };
}
