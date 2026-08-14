/* 덱의 각 장을 정지 화면으로 캡처한다 — 영상 렌더(S12)의 재료.
 *
 * `/preview/{pid}?n={no}` 는 그 장 하나만 시작 문 없이 그려 준다(server.py 의
 * `/preview` 참고) — 편집 화면의 iframe 이 이미 이 자리를 쓰고 있다. 영상은
 * 소리가 따로(오디오 파일을 안다) 필요 없으니 스크린샷만 뜨면 된다.
 *
 *     node tools/render_frames.mjs --pid 1 --out <폴더> [--base http://127.0.0.1:5178]
 *
 * 결과: <out>/001.png … (뺀 장은 건너뛴다)
 */
import { chromium } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const argv = process.argv.slice(2);
const opt = (n, d) => { const i = argv.indexOf(n); return i >= 0 ? argv[i + 1] : d; };

const PID = opt("--pid");
const OUT = opt("--out");
const BASE = (opt("--base", "http://127.0.0.1:5178")).replace(/\/$/, "");
const WIDTH = parseInt(opt("--width", "1920"), 10);
const HEIGHT = parseInt(opt("--height", "1080"), 10);

if (!PID || !OUT) {
  console.error("사용법: node tools/render_frames.mjs --pid <id> --out <폴더> [--base url]");
  process.exit(2);
}

mkdirSync(OUT, { recursive: true });

const deckRes = await fetch(`${BASE}/api/projects/${PID}/deck`);
if (!deckRes.ok) {
  console.error(`덱을 못 읽었습니다: ${deckRes.status} ${await deckRes.text()}`);
  process.exit(1);
}
const deck = await deckRes.json();
const slides = (deck.slides || []).filter((s) => !s.drop);
if (!slides.length) {
  console.error("장이 없습니다 — 목차부터 확정하세요");
  process.exit(1);
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: WIDTH, height: HEIGHT } });

const manifest = [];
for (const s of slides) {
  const url = `${BASE}/preview/${PID}?n=${s.no}&t=${Date.now()}`;
  await page.goto(url, { waitUntil: "load" });
  // 폰트·미디어가 자리 잡을 시간 — 짧게 고정. 페이지 자체가 의존성 0(외부 요청 없음)이라
  // networkidle 을 기다릴 필요가 없다.
  await page.waitForTimeout(400);
  // ★ 한 장만 보는 자리(`?n=`)는 시작 문(#gate)이 없다(render/slides.py 참고) —
  //   그래서 `started` 플래그가 영영 true 가 안 되고, 이미지 확대(.vplay)를
  //   스케줄하는 armShots() 안의 `if(!started)return` 에 걸려 확대가 아예 안
  //   돈다. 재생 상태를 진짜로 흉내 낼 필요는 없으니, 확대 클래스만 직접 얹는다.
  await page.evaluate(() => {
    document.querySelector("section.on")?.classList.add("vplay");
    // ★ `?n=` 화면은 오디오가 없으니 재생 중이 아닌데도 그 장 첫 자막 줄을
    //   미리 띄워 둔다(render/slides.py `go()` — 정지 화면에서 훑어볼 때
    //   쓰라고 넣은 것이다). 그런데 이 스크린샷이 영상(S12)의 프레임 그대로
    //   쓰이니, 그 자막 말풍선이 장 전체 길이만큼 **영상에 구워져 버린다**
    //   (2026-08-13 지적: "번인" — Windows 실시간 캡션이 아니라 이거였다).
    //   실제 재생 중 자막은 덱 화면(오디오 재생 중)에서만 뜨면 되므로, 영상
    //   재료로 찍을 때는 지운다.
    const cc = document.getElementById("cc");
    if (cc) cc.style.display = "none";
    // ★ 이게 진짜 범인이었다(2026-08-14 재확인 — 렌더된 mp4에서 여전히
    //   보임). `#cc`와는 별개로 `.cc-st`(_cc_static, render/slides.py)가
    //   있다 — `body.one`(=`?n=` 모드) 에서는 `subs` 값과 무관하게 **항상**
    //   자막 원문을 화면 하단에 깔아 둔다. "편집 화면 iframe에서 자막을
    //   고쳤는데 화면이 그대로면 저장이 안 된 줄 안다"는 별개 문제를 풀려고
    //   넣은 장치인데, 영상 프레임 캡처도 같은 `?n=` 모드를 타는 바람에 이
    //   장치가 그대로 영상에 구워졌다. `#cc`만 지운 지난 수정으로는 이걸
    //   못 잡았다 — 화면에 없던 게 아니라 이쪽이 진짜 소스였다.
    //   ★ 장마다 하나씩(총 슬라이드 수만큼) DOM에 이미 다 들어 있다 —
    //   `.querySelector`(첫 번째 하나만)로는 지금 보이는 장 것을 못 잡을
    //   때가 많다(엉뚱하게 1번 장 것만 지워짐). 전부 지운다.
    document.querySelectorAll(".cc-st").forEach((el) => { el.style.display = "none"; });
    /* ★ 원고 장(html)의 줄은 **전부 뜬 상태로** 찍는다.
       정지 화면 한 장에는 "차례로 나타나는 것" 을 담을 수 없다. 담으려면 한 장을
       등장 단계 수만큼 여러 컷으로 쪼개고 음성도 그 오프셋으로 나눠야 하는데,
       프레임 수가 장당 3~6배로 늘어 렌더 시간이 그만큼 든다. 그건 뒤로 미루고
       지금은 **다 뜬 마지막 상태**를 찍는다 — 빠뜨리는 내용은 없고, 영상에서만
       등장 순서가 안 보인다(발표 화면에서는 그대로 산다).
       `?n=` 모드가 이미 다 띄우지만(render/slides.py `armHtml` 의 `_one` 갈래),
       그쪽이 바뀌어도 영상이 조용히 반쯤 빈 화면을 굽지 않도록 여기서도 못박는다.
       ★ 나중에 단계별로 찍으려면 `?n={no}&at={초}` 를 쓰면 된다 — 그 시각의
         화면을 정지 상태로 그려 주는 길이 이미 열려 있다. */
    document.querySelectorAll(".m-html .hb").forEach((el) => { el.classList.add("on"); });
  });
  // grid-template-columns 전환에 .55s 걸린다 — 최종 배치가 자리 잡을 시간을 준다.
  await page.waitForTimeout(700);
  const name = `${String(s.no).padStart(3, "0")}.png`;
  await page.screenshot({ path: join(OUT, name), type: "png" });
  manifest.push({ no: s.no, title: s.title, image: name,
                  audio: (s.audio || {}).file || null, sec: (s.audio || {}).sec || 0 });
  console.log(`[${s.no}] ${s.title || ""}`);
}
await browser.close();

writeFileSync(join(OUT, "frames.json"), JSON.stringify(manifest, null, 2), "utf-8");
console.log(`\n완료 — ${manifest.length}장 → ${OUT}`);
