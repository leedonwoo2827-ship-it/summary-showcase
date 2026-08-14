/* 영상 렌더링 — 슬라이드를 **통째로 재생하면서 그 화면을 녹화한다.**
 *
 * ★ 왜 녹화인가. 이 덱은 시간이 흐르는 화면이다 — 줄이 하나씩 뜨고, 그림이
 *   커졌다 내려오고, 음성이 그 위를 지나간다. 장마다 정지 화면 한 장을 찍어
 *   이어 붙이는 방식(S12)으로는 **그 순서가 담기지 않는다.** 실제로 도는 화면을
 *   그대로 받아 적는 것이 지금으로선 가장 정확하다(2026-08-14: "이걸 실제
 *   실행한 걸 녹화하면 되지 않을까?").
 *
 * ★ 우상단 단추는 감추고 재생한다(`?bare=1`). 안 감추면 재생 단추·안내 글자가
 *   본문 오른쪽 끝과 겹쳐 영상에 같이 찍힌다.
 *
 * ★ 소리는 **탭 오디오**로 받는다. 공유 창에서 「탭」을 고르고 «탭 오디오도
 *   공유» 를 켜야 내레이션이 들어간다 — 그 안내가 이 화면의 절반이다. 놓치면
 *   18분짜리 무음 영상이 나오고, 그건 다 끝나고서야 알게 된다.
 */
"use strict";

import { el, api, icon, toast, fitFrame } from "./util.js";
import { state } from "./store.js";
import { navigate } from "./shell.js";
import { runSteps } from "./runner.js";
import { stepBadge, DECK } from "./steps.js";

export const meta = {
  title: "영상 렌더링",
  subtitle: "슬라이드를 통째로 재생하면서 그 화면을 녹화합니다",
};

/* 브라우저마다 받아 적을 수 있는 그릇이 다르다. mp4 로 바로 받을 수 있으면 그게
   제일 좋고(어디서나 열린다), 안 되면 webm 이다 — 요즘 편집기는 다 읽는다. */
const CANDIDATES = [
  ["video/mp4;codecs=h264,aac", "mp4"],
  ["video/mp4", "mp4"],
  ["video/webm;codecs=vp9,opus", "webm"],
  ["video/webm;codecs=vp8,opus", "webm"],
  ["video/webm", "webm"],
];
function pickType() {
  for (const [mime, ext] of CANDIDATES) {
    if (window.MediaRecorder && MediaRecorder.isTypeSupported(mime)) return {mime, ext};
  }
  return {mime: "", ext: "webm"};
}

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

  // 예상 길이 — 녹화가 언제 끝나는지 알아야 자리를 뜰 수 있다
  const totalSec = slides.reduce((a, s) =>
    a + ((s.audio && s.audio.sec) || (s.narration && s.narration.est_sec) || 0), 0);
  const nAudio = slides.filter((s) => s.audio && s.audio.file).length;

  const hd = el("div", "deck-head");
  const sum = el("p", "deck-sub");
  sum.textContent = `${slides.length}장 · 예상 ${clock(totalSec)}`
    + (nAudio === slides.length ? " · 음성 전부 있음"
       : ` · 음성 ${nAudio}/${slides.length}장 (없는 장은 무음으로 지나갑니다)`);
  hd.appendChild(sum);
  page.appendChild(hd);

  // ── 화면 ──────────────────────────────────────────────────────────────
  const stage = el("div", "rec-stage");
  const fr = el("iframe", "focus-frame");
  fr.title = "슬라이드 전체 재생";
  fr.allow = "autoplay; fullscreen";
  stage.appendChild(fr);
  page.appendChild(stage);
  /* 1920 폭으로 그리고 창에 맞춰 줄인다 — 덱은 설계 해상도가 1920×1080 이고
     원고 상자 폭이 그 기준으로 잡혀 있다. 더 좁게 그리면 여기서 본 것과
     녹화된 것이 달라진다. */
  fitFrame(stage, fr, 1920);

  const src = (extra = "") =>
    `/preview/${state.projectId}?auto=1&bare=1${extra}&t=${Date.now()}#1`;
  fr.src = src();

  // ── 조작 ──────────────────────────────────────────────────────────────
  const bar = el("div", "rec-bar");
  page.appendChild(bar);

  const btn = el("button", "btn primary lg");
  btn.type = "button";
  btn.append(stepBadge(DECK.record, "영상 렌더링"), icon("film", 15),
             el("span", null, "녹화 시작"));
  bar.appendChild(btn);

  const again = el("button", "btn");
  again.type = "button";
  again.append(icon("refresh", 14), el("span", null, "처음부터"));
  again.onclick = () => { fr.src = src(); };
  bar.appendChild(again);

  const t = el("span", "rec-t", "0:00");
  bar.appendChild(t);
  const note = el("span", "rec-note", "");
  bar.appendChild(note);

  const out = el("div", "rec-out");
  out.hidden = true;
  page.appendChild(out);

  // ── 안내 ──────────────────────────────────────────────────────────────
  const help = el("div", "rec-help");
  help.appendChild(el("b", null, "녹화 시작을 누르면 공유 창이 뜹니다"));
  const ul = el("ul");
  for (const [t1, t2] of [
    ["「이 탭」 을 고르세요", "창이나 전체 화면을 고르면 브라우저 테두리까지 같이 찍힙니다"],
    ["«탭 오디오도 공유» 를 켜세요", "★ 이걸 놓치면 무음 영상이 나옵니다 — 다 끝나고서야 알게 됩니다"],
    ["공유를 누르면 슬라이드가 1장부터 자동 재생됩니다", "화면은 전체 화면으로 커집니다"],
    ["끝나면 «멈춤» 을 누르세요", "곧바로 완성본 폴더에 저장하거나 내려받을 수 있습니다"],
  ]) {
    const li = el("li");
    li.append(el("b", null, t1), el("span", null, t2));
    ul.appendChild(li);
  }
  help.appendChild(ul);
  page.appendChild(help);

  // ── 다른 길 — 결정론적 mp4(S12) ───────────────────────────────────────
  const alt = el("div", "rec-alt");
  alt.appendChild(el("div", "fm-lb", "다른 길 — 장마다 정지 화면으로 이어 붙이기"));
  alt.appendChild(el("p", null,
    "장마다 화면을 한 장씩 찍고 내레이션 길이만큼 보여 주는 mp4 를 만듭니다. "
    + "빠르고 화면·소리가 어긋나지 않지만, 정지 화면이라 "
    + "**줄이 차례로 뜨는 것은 담기지 않습니다** — 다 뜬 상태로 나옵니다."));
  const vBtn = el("button", "btn");
  vBtn.type = "button";
  vBtn.append(icon("wand", 14), el("span", null, "(전체) 영상 렌더"));
  const vLog = el("span", "rec-note", "");
  vBtn.onclick = async () => {
    const ok = await runSteps(["s12-video"], {
      btn: vBtn, label: vBtn.querySelector("span"), names: {"s12-video": "영상 렌더"},
      onLog: (l) => { vLog.textContent = String(l).slice(0, 90); },
    });
    toast(ok ? "영상이 나왔습니다" : "영상 렌더를 끝내지 못했습니다", ok ? "ok" : "err");
  };
  const abar = el("div", "imgdrop-bar");
  abar.append(vBtn, vLog);
  alt.appendChild(abar);
  page.appendChild(alt);

  // ── 녹화 ──────────────────────────────────────────────────────────────
  let rec = null, stream = null, chunks = [], t0 = 0, tick = null, ext = "webm";

  function setRunning(on) {
    btn.classList.toggle("rec-on", on);
    btn.lastChild.textContent = on ? "멈춤" : "녹화 시작";
    again.disabled = on;
    vBtn.disabled = on;
  }

  function stopAll() {
    clearInterval(tick);
    if (stream) stream.getTracks().forEach((k) => k.stop());
    stream = null;
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    setRunning(false);
  }

  async function start() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
      toast("이 브라우저는 화면 녹화를 지원하지 않습니다 — Chrome 또는 Edge 를 쓰세요", "err");
      return;
    }
    try {
      stream = await navigator.mediaDevices.getDisplayMedia({
        video: {frameRate: 30},
        audio: {echoCancellation: false, noiseSuppression: false, autoGainControl: false},
        // Chrome 전용 — 공유 창에서 이 탭이 먼저 골라져 있게 한다
        preferCurrentTab: true,
      });
    } catch (e) {
      // 사용자가 취소한 것은 오류가 아니다
      if (e && e.name !== "NotAllowedError") toast("화면을 받지 못했습니다: " + e.message, "err");
      return;
    }

    if (!stream.getAudioTracks().length) {
      note.textContent = "소리 없이 녹화 중 — 다음엔 «탭 오디오도 공유» 를 켜세요";
      note.className = "rec-note warn";
    } else {
      note.textContent = "";
      note.className = "rec-note";
    }

    const {mime, ext: e2} = pickType();
    ext = e2;
    chunks = [];
    try {
      rec = new MediaRecorder(stream, mime ? {mimeType: mime, videoBitsPerSecond: 8e6} : undefined);
    } catch (err) {
      toast("녹화를 시작하지 못했습니다: " + err.message, "err");
      stopAll();
      return;
    }
    rec.ondataavailable = (ev) => { if (ev.data && ev.data.size) chunks.push(ev.data); };
    rec.onstop = () => finish(mime);
    // 사용자가 공유 창의 «공유 중지» 를 눌러도 끝나야 한다
    stream.getVideoTracks()[0].onended = () => { if (rec && rec.state !== "inactive") rec.stop(); };

    out.hidden = true;
    out.textContent = "";
    setRunning(true);
    rec.start(1000);
    t0 = Date.now();
    t.textContent = "0:00";
    tick = setInterval(() => { t.textContent = clock((Date.now() - t0) / 1000); }, 500);

    // 화면을 크게 — 녹화가 이 탭을 받으므로 전체 화면이면 슬라이드만 남는다
    try { await stage.requestFullscreen(); } catch { /* 막혀 있어도 녹화는 된다 */ }

    /* 1장부터 새로 시작하고 자동 재생 문을 연다.
       ★ 같은 서버라(same-origin) iframe 안을 만질 수 있다. 브라우저 자동재생
         정책 때문에 첫 소리에는 사람의 동작이 필요한데, 방금 «녹화 시작» 을
         누른 것이 그 동작이라 이어진다. 그래도 막히면 문이 그대로 보이므로
         사람이 직접 누르면 된다 — 그래서 문을 없애지 않는다. */
    fr.src = src();
    fr.onload = () => {
      try {
        const d = fr.contentDocument;
        d.querySelector('#gate [data-go="auto"]')?.click();
      } catch { /* 못 누르면 사람이 누른다 */ }
    };
  }

  function finish(mime) {
    clearInterval(tick);
    const sec = (Date.now() - t0) / 1000;
    const blob = new Blob(chunks, {type: mime || "video/webm"});
    chunks = [];
    stopAll();
    if (!blob.size) { toast("받아 적힌 것이 없습니다", "err"); return; }

    out.hidden = false;
    out.textContent = "";
    out.appendChild(el("div", "fm-lb",
      `녹화 ${clock(sec)} · ${(blob.size / 1e6).toFixed(1)}MB · ${ext}`));

    const row = el("div", "imgdrop-bar");
    const save = el("button", "btn primary");
    save.type = "button";
    save.append(icon("download", 14), el("span", null, "완성본 폴더에 저장"));
    save.onclick = async () => {
      save.disabled = true;
      save.lastChild.textContent = "저장 중…";
      try {
        const r = await fetch(
          `/api/projects/${state.projectId}/recording?ext=${ext}`,
          {method: "POST", headers: {"Content-Type": "application/octet-stream"}, body: blob});
        if (!r.ok) throw new Error(await r.text());
        const j = await r.json();
        toast(`${j.name} 저장했습니다`);
        out.appendChild(el("div", "imgdrop-path", j.path));
      } catch (e) {
        toast("저장하지 못했습니다: " + e.message, "err");
      } finally {
        save.disabled = false;
        save.lastChild.textContent = "완성본 폴더에 저장";
      }
    };
    row.appendChild(save);

    // 브라우저로 내려받기 — 폴더에 저장이 막히는 상황(권한 등)의 뒷문
    const dl = el("a", "btn");
    dl.href = URL.createObjectURL(blob);
    dl.download = `${deck.deck_title || "발표"}.${ext}`;
    dl.append(icon("download", 14), el("span", null, "내려받기"));
    row.appendChild(dl);

    const play = el("video", "rec-play");
    play.controls = true;
    play.src = dl.href;
    out.append(row, play);
  }

  btn.onclick = () => {
    if (rec && rec.state !== "inactive") rec.stop();
    else start();
  };

  // 화면을 떠나면 반드시 끈다 — 안 끄면 탭 공유가 계속 살아 있다
  page.addEventListener("x-unmount", () => {
    if (rec && rec.state !== "inactive") { try { rec.stop(); } catch { /* 이미 끝남 */ } }
    stopAll();
  });
}
