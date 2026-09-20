/* VinUni Compass client.
   Talks to /api/chat (SSE) and /api/evaluation. Conversations live in this
   browser only — nothing is uploaded and nothing is shared between viewers. */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const icon = (name, cls = "ic") =>
  `<svg class="${cls}" viewBox="0 0 24 24"><use href="#i-${name}"/></svg>`;

const STATUS = {
  supported:        { label: "Supported by sources", icon: "check",    cls: "ok" },
  partial_evidence: { label: "Partial evidence",     icon: "alert",    cls: "warn" },
  not_found:        { label: "Not found in sources", icon: "notfound", cls: "none" },
};

const SAFE_FAILURE =
  "I could not reach the retrieval service just now, so I will not guess. " +
  "Please try again in a moment, or check the official VinUni pages directly.";

const MODES = {
  auto: "Automatic",
  admissions: "Admissions Mode",
  student_life: "Student Life Mode",
};

// ---------------------------------------------------------------- state
const store = {
  load(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; }
    catch { return fallback; }
  },
  save(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode */ }
  },
};

const prefs = Object.assign(
  { mode: "auto", topK: 5, debug: false, demo: false, theme: null },
  store.load("compass.prefs", {})
);
let chats = store.load("compass.chats", []);
let currentId = null;
let streaming = false;

const savePrefs = () => store.save("compass.prefs", prefs);
const saveChats = () => store.save("compass.chats", chats);
const current = () => chats.find((c) => c.id === currentId) || null;

// ---------------------------------------------------------------- theme
function applyTheme() {
  if (prefs.theme) document.documentElement.dataset.theme = prefs.theme;
  else document.documentElement.removeAttribute("data-theme");
}
function resolvedTheme() {
  return prefs.theme ??
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}
applyTheme();
$("#theme-btn").addEventListener("click", () => {
  prefs.theme = resolvedTheme() === "dark" ? "light" : "dark";
  applyTheme(); savePrefs();
  if ($("#view-explore").classList.contains("is-active")) renderEval();
});

// ---------------------------------------------------------------- views
function show(view) {
  $$(".view").forEach((v) => v.classList.toggle("is-active", v.id === `view-${view}`));
  $$(".nav-item").forEach((b) => b.classList.toggle("is-active", b.dataset.view === view));
  closeSidebar();
  if (view === "explore") renderEval();
  if (view === "history") renderHistory();
}
$$(".nav-item").forEach((b) => b.addEventListener("click", () => show(b.dataset.view)));

const openSidebar  = () => { $("#sidebar").classList.add("open"); $("#scrim").hidden = false; };
const closeSidebar = () => { $("#sidebar").classList.remove("open"); $("#scrim").hidden = true; };
$("#menu-btn").addEventListener("click", openSidebar);
$("#scrim").addEventListener("click", closeSidebar);

// ---------------------------------------------------------------- mode menu
const modeBtn = $("#mode-btn"), modeMenu = $("#mode-menu");
function setMode(mode) {
  prefs.mode = mode; savePrefs();
  $("#mode-label").textContent = MODES[mode];
  $$("[data-mode]", modeMenu).forEach((b) =>
    b.setAttribute("aria-selected", String(b.dataset.mode === mode)));
}
modeBtn.addEventListener("click", () => {
  const open = modeMenu.hidden;
  modeMenu.hidden = !open;
  modeBtn.setAttribute("aria-expanded", String(open));
});
$$("[data-mode]", modeMenu).forEach((b) => b.addEventListener("click", () => {
  setMode(b.dataset.mode);
  modeMenu.hidden = true; modeBtn.setAttribute("aria-expanded", "false");
}));
document.addEventListener("click", (e) => {
  if (!modeMenu.hidden && !e.target.closest(".mode-wrap")) {
    modeMenu.hidden = true; modeBtn.setAttribute("aria-expanded", "false");
  }
});
setMode(prefs.mode);

// ---------------------------------------------------------------- chips
function syncChips() {
  $("#topk").textContent = prefs.topK;
  $("#chip-debug").setAttribute("aria-pressed", String(prefs.debug));
  $("#chip-demo").setAttribute("aria-pressed", String(prefs.demo));
}
$$(".chip .step").forEach((b) => b.addEventListener("click", () => {
  prefs.topK = Math.max(3, Math.min(10, prefs.topK + Number(b.dataset.step)));
  savePrefs(); syncChips();
}));
$("#chip-debug").addEventListener("click", () => {
  prefs.debug = !prefs.debug; savePrefs(); syncChips(); renderThread();
});
$("#chip-demo").addEventListener("click", () => {
  prefs.demo = !prefs.demo; savePrefs(); syncChips();
});
syncChips();

// ---------------------------------------------------------------- greeting
{
  const h = new Date().getHours();
  $("#greeting").textContent =
    h < 12 ? "Good morning," : h < 18 ? "Good afternoon," : "Good evening,";
}

// ---------------------------------------------------------------- rendering
/** Render markdown, then turn `[n]` markers into chips that jump to a card.
    A marker with no matching source stays plain text — the UI never invents a
    link to evidence that was not returned. */
function renderAnswer(text, msgKey, sourceCount) {
  const clean = String(text ?? "").replace(/\n+(?:Nguồn tham khảo|Sources):[\s\S]*$/i, "").trim();
  let html = "";
  if (typeof window !== "undefined" && window.marked?.parse) {
    const safe = clean.replace(/</g, "&lt;");
    html = window.marked.parse(safe, { breaks: true, gfm: true });
  } else {
    html = esc(clean)
      .split(/\n{2,}/)
      .map((para) => `<p>${para.replace(/\n/g, "<br/>")}</p>`)
      .join("");
  }
  return html.replace(/\[(\d{1,2})\]/g, (m, n) => {
    const i = Number(n);
    return i >= 1 && i <= sourceCount
      ? `<a class="cite" href="#src-${msgKey}-${i}" title="Source ${i}">${i}</a>`
      : m;
  });
}

const META_FIELDS = [
  ["policy_version", "Policy Version"],
  ["effective_date", "Effective"],
  ["snapshot_id", "Data Snapshot"],
  ["data_snapshot", "Data Snapshot"],
  ["mode", "Mode"],
];

function renderSources(sources, msgKey) {
  if (!sources?.length) return "";
  const cards = sources.map((s, i) => {
    const m = s.metadata || {};
    const title = m.title || s.id || "Untitled source";
    let quote = String(s.content || "").replace(/\s+/g, " ").trim();
    if (quote.length > 320) quote = quote.slice(0, 320).replace(/\s\S*$/, "") + "…";

    const chips = [`Retrieval: ${s.retrieval_method || "unknown"}`];
    const seen = new Set();
    for (const [key, label] of META_FIELDS) {
      if (m[key] && !seen.has(label)) { seen.add(label); chips.push(`${label}: ${m[key]}`); }
    }
    const link = m.url
      ? `<a class="card-link" href="${esc(m.url)}" target="_blank" rel="noopener noreferrer">
           ${icon("link")}Open the official page</a>`
      : "";
    return `<div class="card" id="src-${msgKey}-${i + 1}">
      <div class="card-head"><span class="card-n">${i + 1}</span>
        <span class="card-title">${esc(title)}</span></div>
      <div class="quote">${esc(quote) || "No excerpt available."}</div>
      <div class="meta">${chips.map((c) => `<span>${esc(c)}</span>`).join("")}</div>
      ${link}</div>`;
  }).join("");

  // Raw scores are diagnostics, not part of the answer — they stay folded away.
  const debug = prefs.debug
    ? `<details class="debug" open><summary>Retrieval details</summary>
        <div class="tbl-wrap" style="margin-top:8px"><table>
          <thead><tr><th class="num">#</th><th>Chunk ID</th><th class="num">Score</th>
            <th>Method</th><th>Source file</th></tr></thead>
          <tbody>${sources.map((s, i) => `<tr>
            <td class="num">${i + 1}</td><td>${esc(s.id)}</td>
            <td class="num">${Number(s.score ?? 0).toFixed(4)}</td>
            <td>${esc(s.retrieval_method)}</td>
            <td>${esc((s.metadata || {}).source || "—")}</td></tr>`).join("")}
          </tbody></table></div></details>`
    : "";

  return `<div class="srcs-head">${icon("doc")}Public Sources</div>${cards}${debug}`;
}

function messageHTML(msg, key) {
  if (msg.role === "user") {
    return `<div class="msg">
      <div class="msg-head"><span class="avatar user">You</span><span class="who">You</span></div>
      <div class="bubble">${esc(msg.content).replace(/\n/g, "<br/>")}</div></div>`;
  }
  const st = STATUS[msg.status] || STATUS.not_found;
  const n = msg.sources?.length || 0;
  return `<div class="msg">
    <div class="msg-head">
      <span class="avatar bot">${icon("compass")}</span><span class="who">Compass</span>
    </div>
    <div class="status ${st.cls}">${icon(st.icon)}${esc(st.label)}</div>
    <div class="answer ${st.cls}">${renderAnswer(msg.content, key, n)}</div>
    ${renderSources(msg.sources, key)}</div>`;
}

function renderThread() {
  const chat = current();
  const msgs = chat?.messages || [];
  $("#hero").style.display = msgs.length ? "none" : "";
  $("#thread").innerHTML = msgs.map((m, i) => messageHTML(m, `${chat.id}-${i}`)).join("");
}

function groupLabel(ts) {
  const day = 86400000, now = new Date().setHours(0, 0, 0, 0);
  if (ts >= now) return "Today";
  if (ts >= now - day) return "Yesterday";
  if (ts >= now - 7 * day) return "Previous 7 days";
  return "Earlier";
}

function renderSidebar() {
  const groups = new Map();
  for (const c of [...chats].sort((a, b) => b.updated - a.updated)) {
    const g = groupLabel(c.updated);
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g).push(c);
  }
  $("#threads").innerHTML = groups.size
    ? [...groups].map(([label, list]) => `<h4>${label}</h4>` + list.map((c) =>
        `<button class="thread-link ${c.id === currentId ? "is-active" : ""}"
                 data-chat="${c.id}" type="button" title="${esc(c.title)}">${esc(c.title)}</button>`
      ).join("")).join("")
    : `<p class="muted" style="padding:10px 11px;font-size:12.5px">No conversations yet.</p>`;

  $$("[data-chat]", $("#threads")).forEach((b) => b.addEventListener("click", () => {
    currentId = b.dataset.chat; show("chat"); renderThread(); renderSidebar();
  }));
}

function renderHistory() {
  const body = $("#history-body");
  if (!chats.length) { body.innerHTML = `<p class="empty">No conversations yet.</p>`; return; }
  body.innerHTML = `<div class="tbl-wrap"><table>
    <thead><tr><th>Conversation</th><th class="num">Messages</th><th>Mode</th><th>Updated</th><th></th></tr></thead>
    <tbody>${[...chats].sort((a, b) => b.updated - a.updated).map((c) => `<tr>
      <td class="q"><button class="thread-link" data-open="${c.id}" style="padding:0">${esc(c.title)}</button></td>
      <td class="num">${c.messages.length}</td>
      <td>${esc(MODES[c.mode] || c.mode)}</td>
      <td>${new Date(c.updated).toLocaleString()}</td>
      <td><button class="btn-ghost" data-del="${c.id}">${icon("trash")}Delete</button></td>
    </tr>`).join("")}</tbody></table></div>`;

  $$("[data-open]", body).forEach((b) => b.addEventListener("click", () => {
    currentId = b.dataset.open; show("chat"); renderThread(); renderSidebar();
  }));
  $$("[data-del]", body).forEach((b) => b.addEventListener("click", () => {
    chats = chats.filter((c) => c.id !== b.dataset.del);
    if (currentId === b.dataset.del) currentId = null;
    saveChats(); renderHistory(); renderSidebar(); renderThread();
  }));
}

$("#clear-all").addEventListener("click", () => {
  if (!chats.length || !confirm("Delete every conversation stored in this browser?")) return;
  chats = []; currentId = null; saveChats(); renderHistory(); renderSidebar(); renderThread();
});

// ---------------------------------------------------------------- composer
const input = $("#input"), sendBtn = $("#send");
const autosize = () => { input.style.height = "auto"; input.style.height = input.scrollHeight + "px"; };
input.addEventListener("input", autosize);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#composer").requestSubmit(); }
});
$$("#starters button").forEach((b) => b.addEventListener("click", () => {
  input.value = b.textContent.trim(); autosize(); $("#composer").requestSubmit();
}));
$("#new-chat").addEventListener("click", () => {
  currentId = null; renderThread(); renderSidebar(); show("chat"); input.focus();
});
$("#search-btn").addEventListener("click", () => { show("history"); });
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement !== input && !e.metaKey && !e.ctrlKey) {
    e.preventDefault(); show("chat"); input.focus();
  }
});

$("#composer").addEventListener("submit", (e) => { e.preventDefault(); send(); });

async function send() {
  const query = input.value.trim();
  if (!query || streaming) return;

  if (!current()) {
    currentId = String(Date.now());
    chats.push({
      id: currentId, title: query.slice(0, 60), mode: prefs.mode,
      updated: Date.now(), messages: [],
    });
  }
  const chat = current();
  chat.messages.push({ role: "user", content: query });
  chat.updated = Date.now();
  chat.mode = prefs.mode;
  input.value = ""; autosize();
  saveChats(); renderThread(); renderSidebar();

  streaming = true; sendBtn.disabled = true;
  const scroll = $("#chat-scroll");
  const live = document.createElement("div");
  live.className = "msg";
  live.innerHTML = `<div class="msg-head">
      <span class="avatar bot">${icon("compass")}</span><span class="who">Compass</span></div>
    <div class="typing"><i></i><i></i><i></i></div>`;
  $("#thread").append(live);
  scroll.scrollTop = scroll.scrollHeight;

  let text = "", sources = [], status = null, failed = false;
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query, mode: prefs.mode, top_k: prefs.topK, demo: prefs.demo,
        history: chat.messages.slice(0, -1).map((m) => ({ role: m.role, content: m.content })),
      }),
    });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop();                       // keep the partial frame
      for (const frame of frames) {
        const line = frame.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        const ev = JSON.parse(line.slice(6));
        if (ev.type === "warning") banner(ev.data);
        else if (ev.type === "metadata") status = ev.metadata?.evidence_status || status;
        else if (ev.type === "delta") {
          text += ev.data;
          live.innerHTML = `<div class="msg-head">
              <span class="avatar bot">${icon("compass")}</span><span class="who">Compass</span></div>
            <div class="answer ${(STATUS[status] || STATUS.supported).cls}">
              ${renderAnswer(text, "live", sources.length)}</div>`;
          scroll.scrollTop = scroll.scrollHeight;
        } else if (ev.type === "sources") {
          sources = ev.metadata?.sources || [];
          status = ev.metadata?.evidence_status || status;
        } else if (ev.type === "error") { failed = true; text = ev.data || SAFE_FAILURE; }
        else if (ev.type === "done") status = ev.metadata?.evidence_status || status;
      }
    }
  } catch {
    failed = true;
  }

  // A provider or transport failure degrades to a safe message; the thread and
  // every earlier answer stay exactly where they were.
  if (failed || !text.trim()) { text = SAFE_FAILURE; sources = []; status = "not_found"; }

  live.remove();
  chat.messages.push({ role: "assistant", content: text, sources, status: status || "supported" });
  chat.updated = Date.now();
  saveChats(); renderThread(); renderSidebar();
  streaming = false; sendBtn.disabled = false;
  scroll.scrollTop = scroll.scrollHeight;
  input.focus();
}

let bannerTimer;
function banner(message) {
  $("#banner-text").textContent = message;
  $("#banner").hidden = false;
  clearTimeout(bannerTimer);
  bannerTimer = setTimeout(() => { $("#banner").hidden = true; }, 9000);
}

// ---------------------------------------------------------------- Explore
const METRICS = [
  ["faithfulness", "Faithfulness"],
  ["answer_relevance", "Answer relevance"],
  ["context_recall", "Context recall"],
  ["context_precision", "Context precision"],
  ["recall_at_5", "Recall@5"],
  ["citation_correctness", "Citation correctness"],
  ["refusal_accuracy", "Refusal accuracy"],
];

let evalData = null;

async function renderEval() {
  const body = $("#eval-body");
  if (!evalData) {
    try {
      const res = await fetch("/api/evaluation");
      evalData = await res.json();
    } catch {
      body.innerHTML = `<p class="empty">Could not load evaluation results.</p>`;
      return;
    }
  }
  const { run = {}, configs = [], sample } = evalData;
  $("#eval-tag").textContent = sample ? "Sample data" : "Offline report";

  if (!configs.length) { body.innerHTML = `<p class="empty">This run has no configurations.</p>`; return; }

  const sampleNote = sample
    ? `<div class="banner" style="margin:0 0 18px">${icon("alert")}
        <span><strong>Sample data.</strong> Placeholder numbers for reviewing the layout.
        Run the evaluation harness to write a real result file into
        <code>group_project/evaluation/results/</code>.</span></div>`
    : "";

  const shortGen = String(run.generator || "—").split(" ")[0];
  const shortEval = String(run.evaluator || "—").split(" ")[0];
  const shortSnap = String(run.data_snapshot || "—").split(" ")[0];

  const kpis = `<div class="kpis">
    <div class="stat"><div class="k">Golden cases</div><div class="v">${esc(run.dataset_size ?? "—")}</div></div>
    <div class="stat"><div class="k">top_k</div><div class="v">${esc(run.top_k ?? "—")}</div></div>
    <div class="stat" title="${esc(run.generator ?? '')}"><div class="k">Generator</div><div class="v sm">${esc(shortGen)}</div></div>
    <div class="stat" title="${esc(run.evaluator ?? '')}"><div class="k">Evaluator</div><div class="v sm">${esc(shortEval)}</div></div>
    <div class="stat" title="${esc(run.data_snapshot ?? '')}"><div class="k">Data Snapshot</div><div class="v sm">${esc(shortSnap)}</div></div>
  </div>`;

  body.innerHTML = sampleNote + kpis +
    `<div class="section">
       <h3>Quality metrics by configuration</h3>
       <p class="sub">All metrics share a 0–1 scale. Hover or focus a bar for its value;
          every value is also in the table below.</p>
       <div class="chart-card">
         <div class="legend">${configs.map((c, i) =>
           `<span><i style="background:var(--s${i + 1})"></i>${esc(c.label || c.name)}</span>`).join("")}</div>
         <div class="chart" id="chart"></div>
       </div>
       <details class="debug" style="margin-top:10px">
         <summary>Scores as a table</summary>${aggregateTable(configs)}</details>
     </div>
     <div class="section"><h3>Latency</h3>
       <p class="sub">Measured on the same cases and generator.</p>${latencyTable(configs)}</div>
     <div class="section"><h3>Per-case results</h3>
       <div class="filters" id="filters"></div><div id="cases"></div></div>
     <div class="section"><h3>Worst performers</h3>
       <p class="sub">Lowest mean quality score. These rows drive the failure analysis in RESULT.md.</p>
       <div id="worst"></div></div>
     <div class="section"><h3>Refusal behaviour</h3><div id="refusal"></div></div>`;

  drawChart(configs);
  buildFilters(configs);
  renderRefusal(configs);
}

function aggregateTable(configs) {
  const rows = METRICS.filter(([k]) => configs.some((c) => c.aggregate?.[k] != null));
  const delta = configs.length === 2;
  return `<div class="tbl-wrap" style="margin-top:8px"><table>
    <thead><tr><th>Metric</th>${configs.map((c) =>
      `<th class="num">${esc(c.label || c.name)}</th>`).join("")}
      ${delta ? `<th class="num">Δ (B−A)</th>` : ""}</tr></thead>
    <tbody>${rows.map(([key, label]) => {
      const vals = configs.map((c) => c.aggregate?.[key]);
      const d = delta && vals[0] != null && vals[1] != null ? (vals[1] - vals[0]).toFixed(3) : "";
      return `<tr><td>${label}</td>${vals.map((v) =>
        `<td class="num">${v == null ? "—" : v.toFixed(3)}</td>`).join("")}
        ${delta ? `<td class="num">${d > 0 ? "+" : ""}${d}</td>` : ""}</tr>`;
    }).join("")}</tbody></table></div>`;
}

function latencyTable(configs) {
  return `<div class="tbl-wrap"><table>
    <thead><tr><th>Configuration</th><th class="num">p50 (ms)</th><th class="num">p95 (ms)</th></tr></thead>
    <tbody>${configs.map((c) => `<tr><td>${esc(c.label || c.name)}</td>
      <td class="num">${esc(c.aggregate?.latency_p50_ms ?? "—")}</td>
      <td class="num">${esc(c.aggregate?.latency_p95_ms ?? "—")}</td></tr>`).join("")}
    </tbody></table></div>`;
}

/* Grouped bars: magnitude across a fixed set of metrics, identity by series.
   Marks stay thin (≤24px), the two bars in a band are separated by a 2px
   surface gap rather than a stroke, gridlines are solid hairlines, and no
   value is printed on the marks — the axis, tooltip and table carry them. */
function drawChart(configs) {
  const rows = METRICS.filter(([k]) => configs.some((c) => c.aggregate?.[k] != null));
  const W = 920, H = 340, padL = 34, padR = 10, padT = 10, padB = 74;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const y = (v) => padT + plotH * (1 - v);
  const band = plotW / rows.length;
  const GAP = 2;
  const barW = Math.min(24, (band * 0.62 - GAP * (configs.length - 1)) / configs.length);
  const groupW = barW * configs.length + GAP * (configs.length - 1);

  const bar = (x, v) => {
    const h = Math.max(1, plotH * v), top = y(v), r = Math.min(4, h, barW / 2);
    return `M${x} ${top + h}V${top + r}a${r} ${r} 0 0 1 ${r} ${-r}h${barW - 2 * r}` +
           `a${r} ${r} 0 0 1 ${r} ${r}V${top + h}Z`;
  };

  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const grid = ticks.map((t) =>
    `<line class="${t === 0 ? "base" : "gl"}" x1="${padL}" x2="${W - padR}" y1="${y(t)}" y2="${y(t)}"/>
     <text class="tick" x="${padL - 8}" y="${y(t) + 4}" text-anchor="end">${t.toFixed(2)}</text>`).join("");

  const groups = rows.map(([key, label], gi) => {
    const cx = padL + band * gi + band / 2;
    const x0 = cx - groupW / 2;
    const bars = configs.map((c, ci) => {
      const v = c.aggregate?.[key];
      if (v == null) return "";
      const x = x0 + ci * (barW + GAP);
      return `<path class="bar" d="${bar(x, v)}" fill="var(--s${ci + 1})"/>
        <rect class="hit" tabindex="0" role="img" x="${x - 2}" y="${padT}"
              width="${barW + 4}" height="${plotH}"
              data-tip="${esc(c.label || c.name)} · ${esc(label)}: ${v.toFixed(3)}"
              aria-label="${esc(c.label || c.name)}, ${esc(label)}, ${v.toFixed(3)}"/>`;
    }).join("");
    return `<g class="grp">${bars}
      <text x="${cx}" y="${padT + plotH + 18}" text-anchor="end"
            transform="rotate(-28 ${cx} ${padT + plotH + 18})">${esc(label)}</text></g>`;
  }).join("");

  $("#chart").innerHTML =
    `<svg viewBox="0 0 ${W} ${H}" role="group" aria-label="Quality metrics by configuration">
       ${grid}${groups}</svg>`;

  // Tooltips enhance; they never gate a value — the table view has them all.
  let tip = $(".tip");
  if (!tip) { tip = document.createElement("div"); tip.className = "tip"; document.body.append(tip); }
  const showTip = (e) => {
    const t = e.target.dataset?.tip;
    if (!t) return;
    const [who, val] = t.split(": ");
    tip.innerHTML = `${esc(who)}: <b>${esc(val)}</b>`;
    const r = e.target.getBoundingClientRect();
    tip.style.left = `${Math.min(r.left, innerWidth - 240)}px`;
    tip.style.top = `${Math.max(8, r.top - 38)}px`;
    tip.classList.add("on");
  };
  const hideTip = () => tip.classList.remove("on");
  $$("#chart .hit").forEach((h) => {
    h.addEventListener("mouseenter", showTip);
    h.addEventListener("focus", showTip);
    h.addEventListener("mouseleave", hideTip);
    h.addEventListener("blur", hideTip);
  });
}

function allCases(configs) {
  return configs.flatMap((c) =>
    (c.cases || []).map((x) => ({ ...x, config: c.label || c.name })));
}

function buildFilters(configs) {
  const rows = allCases(configs);
  const uniq = (key) => [...new Set(rows.map((r) => r[key]).filter(Boolean))].sort();
  const select = (id, label, values) =>
    `<select id="${id}" aria-label="${label}"><option value="">${label}: all</option>
      ${values.map((v) => `<option>${esc(v)}</option>`).join("")}</select>`;

  $("#filters").innerHTML =
    select("f-cat", "Category", uniq("category")) +
    select("f-lang", "Language", uniq("language")) +
    select("f-cfg", "Configuration", uniq("config"));

  const apply = () => {
    const cat = $("#f-cat").value, lang = $("#f-lang").value, cfg = $("#f-cfg").value;
    const filtered = rows.filter((r) =>
      (!cat || r.category === cat) && (!lang || r.language === lang) && (!cfg || r.config === cfg));
    renderCases(filtered);
    renderWorst(filtered);
  };
  $$("#filters select").forEach((s) => s.addEventListener("change", apply));
  apply();
}

const meanScore = (r) => {
  const vals = METRICS.map(([k]) => r[k]).filter((v) => typeof v === "number");
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
};

function renderCases(rows) {
  if (!rows.length) { $("#cases").innerHTML = `<p class="empty">No cases match these filters.</p>`; return; }
  const cols = [
    ["id", "ID"], ["question", "Question"], ["config", "Configuration"],
    ["category", "Category"], ["language", "Lang"], ["mode", "Mode"],
    ["faithfulness", "Faith."], ["answer_relevance", "Relev."],
    ["context_recall", "Recall"], ["context_precision", "Prec."],
    ["recall_at_5", "R@5"], ["citation_correctness", "Cite"], ["latency_ms", "ms"],
  ];
  $("#cases").innerHTML = `<div class="tbl-wrap"><table>
    <thead><tr>${cols.map(([k, l]) =>
      `<th class="${typeof rows[0][k] === "number" ? "num" : ""}">${l}</th>`).join("")}
      <th>Refusal</th></tr></thead>
    <tbody>${rows.map((r) => `<tr>${cols.map(([k]) => {
      const v = r[k];
      const num = typeof v === "number";
      return `<td class="${num ? "num" : k === "question" ? "q" : ""}">${
        v == null ? "—" : num && k !== "latency_ms" ? v.toFixed(3) : esc(v)}</td>`;
    }).join("")}<td>${refusalOutcome(r)}</td></tr>`).join("")}</tbody></table></div>`;
}

function renderWorst(rows) {
  const scored = rows.map((r) => ({ ...r, mean: meanScore(r) }))
    .filter((r) => r.mean != null)
    .sort((a, b) => a.mean - b.mean).slice(0, 10);
  if (!scored.length) { $("#worst").innerHTML = `<p class="empty">Nothing to rank yet.</p>`; return; }
  $("#worst").innerHTML = `<div class="tbl-wrap"><table>
    <thead><tr><th>ID</th><th>Question</th><th>Configuration</th><th class="num">Mean</th>
      <th>Failure stage</th><th>Root cause</th></tr></thead>
    <tbody>${scored.map((r) => `<tr><td>${esc(r.id)}</td><td class="q">${esc(r.question)}</td>
      <td>${esc(r.config)}</td><td class="num">${r.mean.toFixed(3)}</td>
      <td>${esc(r.failure_stage || "—")}</td><td class="q">${esc(r.root_cause || "—")}</td>
    </tr>`).join("")}</tbody></table></div>`;
}

function refusalOutcome(r) {
  if (r.expected_refusal == null || r.refused == null) return "—";
  if (r.expected_refusal && r.refused) return "Correct refusal";
  if (r.expected_refusal && !r.refused) return "Missed refusal";
  if (!r.expected_refusal && r.refused) return "Over-refusal";
  return "Correct answer";
}

function renderRefusal(configs) {
  const rows = allCases(configs).filter((r) => r.expected_refusal != null && r.refused != null);
  if (!rows.length) { $("#refusal").innerHTML = `<p class="empty">No refusal data in this run.</p>`; return; }
  const counts = new Map();
  for (const r of rows) {
    const key = `${r.config}|${refusalOutcome(r)}`;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  $("#refusal").innerHTML = `<div class="tbl-wrap"><table>
    <thead><tr><th>Configuration</th><th>Outcome</th><th class="num">Cases</th></tr></thead>
    <tbody>${[...counts].sort().map(([key, n]) => {
      const [cfg, outcome] = key.split("|");
      return `<tr><td>${esc(cfg)}</td><td>${esc(outcome)}</td><td class="num">${n}</td></tr>`;
    }).join("")}</tbody></table></div>`;
}

// ---------------------------------------------------------------- boot
renderSidebar();
renderThread();
