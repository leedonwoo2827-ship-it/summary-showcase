/* 화면 캡처 — 사이트를 **라우트 목록대로** 돌며 스크린샷을 뜬다.
 *
 * 발표를 만들 때 화면 40장을 손으로 뜨는 일이 매번 반복된다. 문제는 장수가
 * 아니라 **순서와 이름**이다. 손으로 뜨면 파일명이 제각각이라 나중에 어느 장이
 * 어느 메뉴였는지 다시 열어 봐야 하고, 화면을 고치면 처음부터 다시 뜬다.
 *
 * 여기서는 목록이 JSON 에 있고 파일명이 `역할-번호-슬러그.png` 로 나온다.
 * **파일명 = 사이드바 순서 = 발표 설명 순서.** 사이트를 고쳐도 같은 이름으로
 * 덮어써지므로 덱을 다시 만들 필요가 없다.
 *
 *     node tools/shots.mjs tools/shots.<사이트>.json
 *     node tools/shots.mjs <config> --role personal        한 역할만
 *     node tools/shots.mjs <config> --only profile,career  슬러그 몇 개만
 *     node tools/shots.mjs <config> --force                이미 있어도 다시
 *     node tools/shots.mjs <config> --headed               창을 띄워 눈으로 확인
 *
 * ★ 공통 화면은 한 번만 찍는다. `common` 에 적힌 라우트는 처음 만난 역할에서
 *   `공통/` 으로 떨어지고, 나머지 역할은 건너뛴다. 매니페스트에 `roles` 로
 *   "누구 메뉴에 걸려 있었는지" 를 남기므로, 발표에서 공통 섹션으로 모을 때
 *   판단이 아니라 사실로 쓸 수 있다.
 *
 * ★ 비밀번호는 이 파일에도 config 에도 없다. `<config>` 옆의 `<config>.local.json`
 *   에서 읽는다(gitignore 대상). 없으면 SHOTS_PW_<ROLE> 환경변수를 본다.
 */
import { chromium } from "playwright";
import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync, rmSync } from "node:fs";
import { dirname, join, resolve, sep } from "node:path";

// ── 인자 ───────────────────────────────────────────────────────────────────
const argv = process.argv.slice(2);
const flag = (n) => argv.includes(n);
const opt = (n) => { const i = argv.indexOf(n); return i >= 0 ? argv[i + 1] : null; };

const cfgPath = argv.find((a) => !a.startsWith("--") && a.endsWith(".json"));
if (!cfgPath) {
  console.error("사용법: node tools/shots.mjs <config.json> [--role x] [--only a,b] [--force] [--headed]");
  process.exit(2);
}
const FORCE = flag("--force");
const HEADED = flag("--headed");
const ONLY_ROLE = opt("--role");
const ONLY_SLUGS = (opt("--only") || "").split(",").map((s) => s.trim()).filter(Boolean);

// ── 설정 ───────────────────────────────────────────────────────────────────
const cfg = JSON.parse(readFileSync(cfgPath, "utf-8"));
const localPath = cfgPath.replace(/\.json$/, ".local.json");
const local = existsSync(localPath) ? JSON.parse(readFileSync(localPath, "utf-8")) : {};

const BASE = cfg.base.replace(/\/$/, "");
const OUT = resolve(cfg.out);
const VP = { width: 1440, height: 900, scale: 2, ...(cfg.viewport || {}) };
const SETTLE = cfg.settle_ms ?? 1200;
const TIMEOUT = cfg.timeout_ms ?? 30000;
const FULL = cfg.full_page !== false;
const HIDE = cfg.hide || [];
const COMMON = new Set(cfg.common || []);

const passOf = (role) =>
  (local.pass || {})[role.id] ?? role.pass ?? process.env[`SHOTS_PW_${role.id.toUpperCase()}`] ?? null;

// ── 유틸 ───────────────────────────────────────────────────────────────────
const pad2 = (n) => String(n).padStart(2, "0");
const ensure = (d) => { mkdirSync(d, { recursive: true }); return d; };
const log = (...a) => console.log(...a);

/** 캡처 직전 화면을 조용하게 만든다 — 애니메이션·플로팅 버튼·토스트는 장마다
 *  다르게 찍혀서 같은 화면을 두 번 찍은 것처럼 안 보이게 만든다. */
async function quiet(page) {
  await page.addStyleTag({
    content: `*,*::before,*::after{animation:none!important;transition:none!important;
      caret-color:transparent!important}
      html{scroll-behavior:auto!important}`,
  }).catch(() => {});
  // ★ hide 는 CSS 가 아니라 **Playwright 셀렉터**로 받는다. `:has-text()` 같은 게
  //   쓸 수 있어야 하는데(플로팅 "오류 신고" 버튼이 그렇다) CSS 로는 못 고른다.
  for (const sel of HIDE) {
    const n = await page.locator(sel).count().catch(() => 0);
    for (let i = 0; i < n; i++) {
      await page.locator(sel).nth(i)
        .evaluate((el) => { el.style.setProperty("visibility", "hidden", "important"); })
        .catch(() => {});
    }
  }
  // 지연 로딩(이미지·차트)이 뷰포트 밖에서 안 뜨는 것을 막는다
  await page.evaluate(async () => {
    await new Promise((r) => {
      let y = 0;
      const step = () => {
        window.scrollTo(0, y);
        y += window.innerHeight;
        if (y < document.body.scrollHeight) setTimeout(step, 60);
        else { window.scrollTo(0, 0); setTimeout(r, 120); }
      };
      step();
    });
  }).catch(() => {});
}

async function login(ctx, role) {
  const pw = passOf(role);
  if (!pw) throw new Error(`비밀번호 없음: ${localPath} 의 pass.${role.id}`);
  const page = await ctx.newPage();
  const L = cfg.login;
  await page.goto(BASE + (L.path || "/login"), { waitUntil: "networkidle", timeout: TIMEOUT });
  // ★ 하이드레이션을 기다린다. domcontentloaded 직후에 채우고 누르면 React 가
  //   아직 핸들러를 안 붙였을 때가 있고, 그러면 아무 일도 안 일어난 채 로그인
  //   화면에 그대로 남는다 — "비밀번호가 틀렸다" 로 오해하기 딱 좋은 증상이다.
  await page.waitForTimeout(1500);
  await page.fill(L.email, role.user);
  await page.fill(L.password, pw);
  await Promise.all([
    page.waitForURL(role.login_done || L.done || "**/*", { timeout: TIMEOUT }).catch(() => {}),
    page.click(L.submit),
  ]);
  await page.waitForLoadState("networkidle", { timeout: TIMEOUT }).catch(() => {});
  const landed = page.url();
  await page.close();
  if (/\/login/.test(landed)) throw new Error(`로그인 실패 — ${landed} 에 머물렀습니다`);
  return landed;
}

// ── 본체 ───────────────────────────────────────────────────────────────────
const browser = await chromium.launch({ headless: !HEADED });
const manifest = [];
const seenCommon = new Map();   // path → 매니페스트 항목(두 번째 역할부터는 roles 만 덧붙임)
let ok = 0, skipped = 0, failed = 0;

for (const role of cfg.roles) {
  if (ONLY_ROLE && role.id !== ONLY_ROLE) continue;

  const ctx = await browser.newContext({
    viewport: { width: VP.width, height: VP.height },
    deviceScaleFactor: VP.scale,
    locale: "ko-KR",
    timezoneId: "Asia/Seoul",
    reducedMotion: "reduce",
  });

  if (role.user) {
    try {
      const landed = await login(ctx, role);
      log(`\n■ ${role.label} 로그인 → ${landed}`);
    } catch (e) {
      log(`\n■ ${role.label} — ${e.message}`);
      failed += role.shots.length;
      await ctx.close();
      continue;
    }
  } else {
    log(`\n■ ${role.label} (로그인 없음)`);
  }

  const page = await ctx.newPage();
  page.setDefaultTimeout(TIMEOUT);
  let no = 0;

  for (const shot of role.shots) {
    no += 1;
    if (ONLY_SLUGS.length && !ONLY_SLUGS.includes(shot.slug)) continue;

    const isCommon = COMMON.has(shot.path);
    if (isCommon && seenCommon.has(shot.path)) {
      const prev = seenCommon.get(shot.path);
      prev.roles.push(role.id);
      prev.menu_no[role.id] = no;
      log(`  · ${pad2(no)} ${shot.label} — 공통, ${prev.file} 재사용`);
      continue;
    }

    const dir = isCommon ? ensure(join(OUT, "공통")) : ensure(join(OUT, role.id));
    const name = isCommon ? `공통-${shot.slug}.png` : `${role.id}-${pad2(no)}-${shot.slug}.png`;
    const file = join(dir, name);
    const fullDir = ensure(join(dir, "전체"));
    const fullFile = join(fullDir, name);

    const entry = {
      role: role.id, role_label: role.label, no, slug: shot.slug, label: shot.label,
      group: shot.group || "", path: shot.path, url: BASE + shot.path,
      file: (isCommon ? "공통/" : role.id + "/") + name,
      common: isCommon, roles: [role.id], menu_no: { [role.id]: no }, status: "ok",
    };

    if (!FORCE && existsSync(file)) {
      log(`  · ${pad2(no)} ${shot.label} — 있음, 건너뜀`);
      manifest.push(entry); if (isCommon) seenCommon.set(shot.path, entry);
      skipped += 1; continue;
    }

    try {
      const res = await page.goto(BASE + shot.path, { waitUntil: "domcontentloaded", timeout: TIMEOUT });
      await page.waitForLoadState("networkidle", { timeout: TIMEOUT }).catch(() => {});
      const status = res ? res.status() : 0;
      const landed = page.url();

      if (status >= 400) throw new Error(`HTTP ${status}`);
      if (/\/login/.test(landed) && !/\/login/.test(shot.path))
        throw new Error(`로그인으로 튕김 (권한 없음?)`);

      await page.waitForTimeout(SETTLE);
      await quiet(page);

      // 슬라이드에 바로 얹을 1440×900, 그리고 스크롤 전체 — 두 벌.
      await page.screenshot({ path: file, fullPage: false });
      if (FULL) await page.screenshot({ path: fullFile, fullPage: true });

      entry.title = await page.title().catch(() => "");
      manifest.push(entry);
      if (isCommon) seenCommon.set(shot.path, entry);
      ok += 1;
      log(`  ✓ ${pad2(no)} ${shot.label}${isCommon ? " (공통)" : ""}  →  ${entry.file}`);
    } catch (e) {
      entry.status = "fail"; entry.error = String(e.message || e);
      manifest.push(entry);
      failed += 1;
      log(`  ✗ ${pad2(no)} ${shot.label}  —  ${entry.error}`);
    }
  }

  await ctx.close();
}

await browser.close();

// ── 매니페스트 ─────────────────────────────────────────────────────────────
// 발표 목차가 읽을 목록. 캡처 단위(라우트)와 슬라이드 단위는 다르므로,
// 여기서는 **전부** 남기고 고르는 일은 목차 화면이 한다.
ensure(OUT);
writeFileSync(
  join(OUT, "shots.json"),
  JSON.stringify({ base: BASE, viewport: VP, captured_from: cfgPath, shots: manifest }, null, 2),
  "utf-8"
);

// ★ 목록에서 뺀 화면의 옛 파일은 남는다 — 번호가 밀리면 같은 화면이 두 이름으로
//   앉아 있게 되고, 나중에 폴더만 보고는 어느 쪽이 최신인지 알 수 없다.
//   지우는 건 눈으로 보고 하도록 --prune 을 눌러야 한다.
if (!ONLY_ROLE && !ONLY_SLUGS.length) {
  const keep = new Set(manifest.map((m) => m.file.replace(/\//g, sep)));
  const orphans = [];
  for (const d of readdirSync(OUT, { withFileTypes: true }).filter((e) => e.isDirectory())) {
    for (const f of readdirSync(join(OUT, d.name)).filter((f) => f.endsWith(".png"))) {
      if (!keep.has(join(d.name, f))) orphans.push(join(d.name, f));
    }
  }
  if (orphans.length) {
    log(`\n목록에 없는 옛 파일 ${orphans.length}개:`);
    for (const o of orphans) log(`  ? ${o}`);
    if (flag("--prune")) {
      for (const o of orphans) {
        rmSync(join(OUT, o), { force: true });
        rmSync(join(OUT, dirname(o), "전체", o.split(sep).pop()), { force: true });
      }
      log(`  → 지웠습니다(--prune).`);
    } else {
      log(`  → 지우려면 --prune 을 붙여 다시 실행하세요.`);
    }
  }
}

log(`\n─────────────────────────────────────────`);
log(`성공 ${ok} · 건너뜀 ${skipped} · 실패 ${failed}`);
log(`${join(OUT, "shots.json")}`);
if (failed) log(`\n실패한 것만 다시: node ${cfgPath} --only <슬러그,슬러그> --force`);
