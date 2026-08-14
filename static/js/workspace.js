/* 워크스페이스 — 패널. 산출물 폴더 · 연결 상태 · 모델 설정. */
"use strict";

import { el, api, icon, toast } from "./util.js";
import { getSettings, saveSettings, getProjects, invalidate, state } from "./store.js";
import { closePanel } from "./panel.js";

export const meta = { title: "워크스페이스", subtitle: "산출물 폴더 · 연결 · 모델" };

function row(k, v) {
  const r = el("div", "kv");
  r.append(el("span", "kv-k", k), el("span", "kv-v", v));
  return r;
}

export async function mount(root) {
  const h = await api("/api/health").catch(() => null);
  const cfg = await getSettings(true).catch(() => null);

  root.appendChild(el("h2", "sec-title", "산출물 폴더"));
  const wsCard = el("div", "card");
  if (h) {
    wsCard.appendChild(row("앱", h.app_dir));
    wsCard.appendChild(row("산출물", h.workspace.root));
    wsCard.appendChild(row("지정 방식",
      h.workspace.from_env ? "SHOWCASE_WORKSPACE 환경변수" : "앱 폴더의 형제 (기본값)"));
    wsCard.appendChild(row("프로젝트", `${h.workspace.projects}개`));
    wsCard.appendChild(el("div", "card-note",
      "산출물을 앱 밖에 두면 git clean 이나 레포 재클론이 만들어 둔 쇼케이스를 지울 수 없습니다."));
  }
  root.appendChild(wsCard);

  root.appendChild(el("h2", "sec-title", "연결"));
  const cCard = el("div", "card");
  if (h) {
    cCard.appendChild(el("span", "badge " + (h.claude_cli ? "ok" : "err"),
      h.claude_cli ? "Claude Code 로그인됨" : "로그인 필요"));
    cCard.appendChild(row("CLI", h.claude_cli || "찾지 못함"));
    cCard.appendChild(row("비전 모드", h.vision_mode));
    cCard.appendChild(el("div", "card-note",
      "API 키를 쓰지 않습니다. 이 PC 의 구독 로그인으로 나갑니다."));
  }
  root.appendChild(cCard);

  await projectSection(root);

  if (cfg) {
    root.appendChild(el("h2", "sec-title", "모델"));
    const mCard = el("div", "card");
    for (const [k, v] of Object.entries(cfg.models || {})) mCard.appendChild(row(k, v));
    mCard.appendChild(row("스테이지당 예산", `$${cfg.budget_usd.per_stage}`));
    mCard.appendChild(el("div", "card-note",
      "호출당 최소 비용이 약 $0.24 입니다. 프레임은 항목당 한 번에 묶어 보냅니다."));
    root.appendChild(mCard);
  }
}


/* ── 프로젝트 정리 ──────────────────────────────────────────────────────────
 *
 * ★ **앱은 지우지 않는다.** 감추기만 하고, 지울 폴더 경로를 정확히 알려 준다.
 *
 * 산출물 폴더에는 몇 시간짜리 Claude 호출 결과와 손으로 고친 대본이 들어 있다.
 * 그것을 버튼 하나로 없애는 코드는 두지 않는다 — 잘못 눌렀을 때 되돌릴 방법이
 * 없기 때문이다. 브라우저 확인창(prompt)도 쓰지 않는다: 새 창이 튀어나오면
 * 사람은 내용을 안 읽고 확인을 누른다. 대신 **경로를 화면에 띄워 놓고** 두 번
 * 누르게 한다.
 */
async function projectSection(root) {
  let list = [];
  try { list = await getProjects(true); } catch { return; }

  root.appendChild(el("h2", "sec-title", "프로젝트"));
  const card = el("div", "card");
  const focus = state.focusProject;
  state.focusProject = null;          // 한 번만 쓴다

  for (const p of list) {
    const r = el("div", "prow" + (p.id === focus ? " focus" : ""));
    /* ★ 줄을 누르면 그 프로젝트로 옮겨 간다. 목록을 보러 왔다가 "이걸로 가자"
     * 가 되는 자리라, 여기서 못 옮기면 패널을 닫고 레일로 다시 가야 한다. */
    const here = p.id === state.projectId;
    const L = el("div", "prow-l");
    L.append(el("div", "prow-name", p.title || p.slug),
             el("div", "prow-dir", p.dir || ""));

    /* ★ 이동은 **보이는 버튼**이어야 한다. 줄 전체를 누르게 해 뒀더니
     * "이동 버튼이 없다" 는 말을 들었다 — 눌러도 되는지 모르면 안 누른다. */
    const go = el("button", "btn sm primary");
    go.type = "button";
    go.textContent = here ? "지금 이것" : "이 프로젝트로 이동";
    go.disabled = here;
    go.onclick = () => { state.projectId = p.id; closePanel(); };
    const btn = el("button", "btn sm");
    btn.type = "button";
    btn.textContent = "목록에서 감추기";

    let armed = false;
    btn.onclick = async () => {
      if (!armed) {                       // 한 번 더 눌러야 실행된다
        armed = true;
        btn.classList.add("danger");
        btn.textContent = "한 번 더 누르면 감춥니다";
        setTimeout(() => {
          if (!armed) return;
          armed = false;
          btn.classList.remove("danger");
          btn.textContent = "목록에서 감추기";
        }, 5000);
        return;
      }
      btn.disabled = true;
      try {
        const res = await api(`/api/projects/${p.id}`, {method: "DELETE"});
        invalidate();
        if (state.projectId === p.id) {
          const rest = (await getProjects(true)).filter((x) => x.id !== p.id);
          state.projectId = rest.length ? rest[0].id : null;
        }
        r.replaceWith(doneRow(p, res.dir));
      } catch (e) {
        toast("감추지 못했습니다: " + e.message, "err");
        btn.disabled = false;
      }
    };
    r.append(L, go, btn);
    card.appendChild(r);
  }
  if (!list.length) card.appendChild(el("div", "empty", "프로젝트가 없습니다."));
  if (focus) {
    // 패널이 열린 뒤에 스크롤해야 위치가 잡힌다
    setTimeout(() => card.querySelector(".prow.focus")
      ?.scrollIntoView({block: "center", behavior: "smooth"}), 60);
  }
  card.appendChild(el("div", "card-note",
    "감추기는 목록에서만 치웁니다 — 폴더와 파일은 그대로 남습니다. "
    + "폴더 안의 _감춤 파일을 지우면 목록에 다시 나옵니다."));
  root.appendChild(card);
}

/* 감춘 뒤 — **지울 폴더를 여기 띄워 둔다.** 사람이 탐색기에서 직접 지운다. */
function doneRow(p, dir) {
  const box = el("div", "pdone");
  box.appendChild(el("div", "pdone-hd", `${p.title || p.slug} — 목록에서 감췄습니다`));
  box.appendChild(el("div", "pdone-say", "완전히 없애려면 이 폴더를 탐색기에서 직접 지우세요:"));

  const line = el("div", "pdone-path");
  line.appendChild(el("code", null, dir));
  const cp = el("button", "btn sm");
  cp.type = "button";
  cp.textContent = "경로 복사";
  cp.onclick = async () => {
    try {
      await navigator.clipboard.writeText(dir);
      cp.textContent = "복사됨";
      setTimeout(() => { cp.textContent = "경로 복사"; }, 1500);
    } catch { toast("복사하지 못했습니다 — 경로를 직접 끌어 쓰세요", "err"); }
  };
  line.appendChild(cp);
  box.appendChild(line);
  box.appendChild(el("div", "pdone-note",
    "앱은 폴더를 지우지 않습니다. 몇 시간짜리 결과가 들어 있어 되돌릴 수 없기 때문입니다."));
  return box;
}
