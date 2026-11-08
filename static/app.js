import { animate, stagger } from "https://cdn.jsdelivr.net/npm/motion@12.43.0/+esm";

const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
const move = (el, kf, opts = {}) => animate(el, kf, calm ? { duration: 0 } : opts);
const spring = { type: "spring", stiffness: 260, damping: 24 };

const state = {
  mode: "learn",
  ledger: JSON.parse(localStorage.getItem("swc.ledger") || "[]"),
  history: [],
  exhausted: new Set(JSON.parse(localStorage.getItem("swc.exhausted") || "[]")),
  providers: [],
};

const $ = (s) => document.querySelector(s);
const feed = $("#feed");
const KIND = { grant: "Credits", "free-tier": "Free tier", subscription: "Subscription", machine: "Machine" };

function saveLocal() {
  localStorage.setItem("swc.exhausted", JSON.stringify([...state.exhausted]));
  localStorage.setItem("swc.ledger", JSON.stringify(state.ledger.slice(-500)));
}

const meterWas = new Map();
let shownTokens = 0;
let batonAt = null;

function countTo(el, from, to) {
  if (calm || from === to) { el.textContent = to.toLocaleString(); return; }
  animate(from, to, { duration: 0.8, ease: "easeOut", onUpdate: (v) => (el.textContent = Math.round(v).toLocaleString()) });
}

const today = () => new Date().toDateString();
function todaysLedger() {
  return state.ledger.filter((e) => new Date(e.at).toDateString() === today());
}

function renderRing(activeId) {
  const list = $("#providers");
  list.innerHTML = "";
  const rows = todaysLedger();
  const usedBy = {};
  for (const e of rows) usedBy[e.provider] = (usedBy[e.provider] || 0) + e.tokens;
  const total = rows.reduce((n, e) => n + e.tokens, 0);
  for (const p of state.providers) {
    p.used = usedBy[p.id] || 0;
    const node = $("#tpl-provider").content.firstElementChild.cloneNode(true);
    node.dataset.id = p.id;
    node.classList.add(p.status);
    if (p.id === activeId) node.classList.add("active");
    node.querySelector(".node-name").textContent = p.label;
    node.querySelector(".node-model").textContent = `${KIND[p.kind]}, ${p.model}`;
    const left = p.status === "offline" ? "Not connected yet" : p.status === "exhausted" ? "Out of tokens today" : `${(p.budget - p.used).toLocaleString()} tokens left`;
    node.querySelector(".node-left").textContent = left;
    const share = p.status === "exhausted" ? 1 : p.status === "offline" ? 0 : Math.max(0.02, 1 - p.used / p.budget);
    const bar = node.querySelector(".meter i");
    const before = meterWas.has(p.id) ? meterWas.get(p.id) : share;
    bar.style.transform = `scaleX(${before})`;
    move(bar, { transform: `scaleX(${share})` }, { duration: 0.7, ease: "easeOut" });
    meterWas.set(p.id, share);
    const btn = node.querySelector(".node-btn");
    if (p.status === "offline") {
      btn.disabled = true;
      btn.title = "Add a school computer with SWC_MACHINES";
    } else {
      btn.title = state.exhausted.has(p.id) ? "Tap to refill" : "Tap to make it run out";
      btn.setAttribute("aria-pressed", String(state.exhausted.has(p.id)));
      btn.onclick = async () => {
        const out = !state.exhausted.has(p.id);
        out ? state.exhausted.add(p.id) : state.exhausted.delete(p.id);
        saveLocal();
        if (out) await move(btn, { x: [0, -7, 7, -4, 4, 0] }, { duration: 0.4 });
        loadRing(activeId);
      };
    }
    list.appendChild(node);
  }
  countTo($("#totalTokens"), shownTokens, total);
  shownTokens = total;
  $("#totalSwitches").textContent = rows.filter((e) => e.outcome === "switched").length;
  $("#totalCalls").textContent = rows.filter((e) => e.outcome === "served").length;
  requestAnimationFrame(layoutWire);
}

function nodeEl(id) {
  return document.querySelector(`.node[data-id="${id}"]`);
}

function anchor(id) {
  const n = nodeEl(id);
  if (!n) return null;
  const t = $("#track").getBoundingClientRect();
  const r = n.getBoundingClientRect();
  return { x: r.left - t.left + r.width / 2 - 9, y: r.top - t.top - 9 };
}

function layoutWire() {
  const nodes = document.querySelectorAll(".node");
  if (!nodes.length) return;
  const a = anchor(nodes[0].dataset.id), b = anchor(nodes[nodes.length - 1].dataset.id);
  const line = $("#wireLine");
  line.setAttribute("x1", a.x + 9); line.setAttribute("x2", b.x + 9);
  line.setAttribute("y1", a.y + 9); line.setAttribute("y2", a.y + 9);
  if (batonAt) {
    const p = anchor(batonAt);
    if (p) Object.assign($("#baton").style, { transform: `translate(${p.x}px, ${p.y - 3}px)` });
  }
}

async function batonTo(id, opts = {}) {
  const p = anchor(id);
  if (!p) return;
  const baton = $("#baton");
  if (batonAt === null) {
    baton.style.transform = `translate(${p.x}px, ${p.y - 3}px)`;
    await move(baton, { opacity: [0, 1], scale: [0.2, 1] }, { duration: 0.3 });
  } else {
    await move(baton, { transform: `translate(${p.x}px, ${p.y - 3}px)`, opacity: 1 }, { ...spring, ...opts });
  }
  batonAt = id;
}

async function bounceOff(id) {
  await batonTo(id, { stiffness: 380 });
  const btn = nodeEl(id)?.querySelector(".node-btn");
  if (btn) move(btn, { x: [0, -6, 6, -3, 0] }, { duration: 0.35 });
  await move($("#baton"), { scale: [1, 0.6, 1] }, { duration: 0.25 });
}

let pulse = null;
function startPulse() {
  if (calm) return;
  pulse = animate($("#baton"), { scale: [1, 1.45, 1] }, { duration: 1.1, repeat: Infinity, ease: "easeInOut" });
}
function stopPulse() {
  pulse?.stop();
  pulse = null;
}

async function relayWhileWaiting(say = () => {}) {
  for (const p of state.providers) {
    if (p.status === "offline") continue;
    if (state.exhausted.has(p.id) || p.status === "exhausted") {
      say(`${p.label} is out of tokens today, trying the next one`, "skip");
      await bounceOff(p.id);
      continue;
    }
    say(`Working on it with ${p.label} (${p.model})`, "live");
    await batonTo(p.id);
    nodeEl(p.id)?.classList.add("active");
    startPulse();
    return;
  }
}

async function landOn(route) {
  stopPulse();
  for (const e of route) {
    if (e.outcome === "switched" && !state.exhausted.has(e.provider)) await bounceOff(e.provider);
  }
  const served = [...route].reverse().find((e) => e.outcome === "served");
  if (served) {
    await batonTo(served.provider);
    move($("#baton"), { scale: [1, 1.8, 1] }, { duration: 0.45 });
  }
  return served?.provider;
}

async function loadRing(activeId) {
  const r = await fetch(`/api/ring?exhausted=${[...state.exhausted].join(",")}`);
  state.providers = (await r.json()).providers;
  renderRing(activeId);
}

function renderMarkdown(el, text) {
  // Shield LaTeX from the markdown parser, which would eat its backslashes and underscores.
  const math = [];
  const shielded = text.replace(/\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$[^$\n]+?\$/g, (m) => {
    math.push(m);
    return `@@MATH${math.length - 1}@@`;
  });
  const esc = (m) => m.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  el.innerHTML = marked.parse(shielded).replace(/@@MATH(\d+)@@/g, (_, i) => esc(math[Number(i)]));
  renderMathInElement(el, {
    delimiters: [
      { left: "$$", right: "$$", display: true },
      { left: "\\[", right: "\\]", display: true },
      { left: "$", right: "$", display: false },
      { left: "\\(", right: "\\)", display: false },
    ],
    throwOnError: false,
  });
}

function addUser(text) {
  const el = document.createElement("div");
  el.className = "msg user";
  el.textContent = text;
  feed.appendChild(el);
}

function routeStory(route) {
  const name = (id) => state.providers.find((p) => p.id === id)?.label || id;
  const model = (id) => state.providers.find((p) => p.id === id)?.model || "";
  const served = route.filter((e) => e.outcome === "served");
  const skipped = [...new Set(route.filter((e) => e.outcome === "switched").map((e) => name(e.provider)))];
  const order = [...new Set(served.map((e) => e.provider))];
  const tokens = served.reduce((n, e) => n + e.tokens, 0);
  const secs = served.reduce((n, e) => n + e.ms, 0) / 1000;
  const list = (xs) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs.at(-1)}`);
  let text = order.length > 1
    ? `Started on ${name(order[0])} and finished on ${name(order.at(-1))} after it ran out.`
    : `Answered by ${name(order[0])} (${model(order[0])}).`;
  if (skipped.length) text += ` ${list(skipped)} ${skipped.length > 1 ? "were" : "was"} out of tokens, so it moved on by itself.`;
  text += ` ${served.length} model calls, ${tokens.toLocaleString()} tokens, ${secs.toFixed(0)} s. Cost to Maya: $0.`;
  return text;
}

function slidesArtifact(deck) {
  const box = document.createElement("div");
  box.className = "artifact";
  const pages = [{ cover: true }, ...deck.slides];
  box.innerHTML = `
    <div class="artifact-bar"><strong></strong>
      <div class="actions"><div class="nav"><button data-d="-1">‹</button><span class="pos"></span><button data-d="1">›</button></div>
      <button class="btn dl">Download .pptx</button></div></div>
    <div class="stage"></div><div class="notes"></div>`;
  box.querySelector("strong").textContent = deck.title;
  const stage = box.querySelector(".stage");
  pages.forEach((s, i) => {
    const el = document.createElement("div");
    el.className = "slide" + (s.cover ? " cover" : "");
    if (s.cover) {
      el.innerHTML = "<h3></h3><p></p>";
      el.querySelector("h3").textContent = deck.title;
      el.querySelector("p").textContent = deck.subtitle;
    } else {
      el.innerHTML = `<span class="num">${String(i).padStart(2, "0")}</span><h4></h4><ul></ul>`;
      el.querySelector("h4").textContent = s.heading;
      for (const b of s.bullets) {
        const li = document.createElement("li");
        li.textContent = b;
        el.querySelector("ul").appendChild(li);
      }
    }
    stage.appendChild(el);
  });
  let at = 0;
  const show = () => {
    stage.querySelectorAll(".slide").forEach((el, i) => el.classList.toggle("on", i === at));
    move(stage.querySelector(".slide.on"), { opacity: [0, 1], x: [18, 0] }, { duration: 0.3, ease: "easeOut" });
    box.querySelector(".pos").textContent = `${at + 1}/${pages.length}`;
    box.querySelector(".notes").textContent = pages[at].cover ? "Speaker notes appear here." : `🎤 ${pages[at].speaker_notes}`;
  };
  box.querySelectorAll(".nav button").forEach((b) => (b.onclick = () => { at = (at + Number(b.dataset.d) + pages.length) % pages.length; show(); }));
  box.querySelector(".dl").onclick = async () => {
    const r = await fetch("/api/pptx", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(deck) });
    const url = URL.createObjectURL(await r.blob());
    Object.assign(document.createElement("a"), { href: url, download: `${deck.title}.pptx` }).click();
  };
  show();
  return box;
}

function specArtifact(a) {
  const box = document.createElement("div");
  box.className = "artifact spec";
  box.innerHTML = `<div class="artifact-bar"><strong></strong><span class="check-count"></span></div>
    <div class="spec-body"><p class="goal"></p><h5>Done when (you check these)</h5><ul class="ac"></ul><h5>Plan</h5><ol class="tasks"></ol></div>`;
  box.querySelector("strong").textContent = `Spec: ${a.title}`;
  box.querySelector(".goal").textContent = a.goal;
  const count = box.querySelector(".check-count");
  const update = () => {
    const boxes = [...box.querySelectorAll(".ac input")];
    const n = boxes.filter((b) => b.checked).length;
    count.textContent = n === boxes.length ? `All ${n} checked by Maya` : `Maya checked ${n} of ${boxes.length}`;
    count.classList.toggle("done", n === boxes.length);
  };
  a.acceptance_criteria.forEach((t) => {
    const li = document.createElement("li");
    li.innerHTML = `<label><input type="checkbox"><span></span></label>`;
    li.querySelector("span").textContent = t;
    li.querySelector("input").onchange = (e) => {
      update();
      if (e.target.checked) move(e.target, { scale: [0.6, 1.15, 1] }, { duration: 0.3 });
    };
    box.querySelector(".ac").appendChild(li);
  });
  a.tasks.forEach((t) => {
    const li = document.createElement("li");
    li.textContent = t;
    box.querySelector(".tasks").appendChild(li);
  });
  update();
  return box;
}

function appArtifact(a) {
  const box = document.createElement("div");
  box.className = "artifact";
  box.innerHTML = `
    <div class="artifact-bar"><strong></strong>
      <div class="actions"><button class="btn alt open">Open full screen</button><button class="btn dl">Download .html</button></div></div>
    <div class="phone-wrap"><div class="phone"><iframe sandbox="allow-scripts allow-forms allow-modals" title="Student app preview"></iframe></div></div>`;
  box.querySelector("strong").textContent = a.name;
  box.querySelector("iframe").srcdoc = a.html;
  const blobUrl = () => URL.createObjectURL(new Blob([a.html], { type: "text/html" }));
  box.querySelector(".open").onclick = () => window.open(blobUrl(), "_blank");
  box.querySelector(".dl").onclick = () => Object.assign(document.createElement("a"), { href: blobUrl(), download: `${a.name}.html` }).click();
  return box;
}

async function send(text) {
  const welcome = $(".welcome");
  if (welcome) {
    await move(welcome, { opacity: 0, y: -10 }, { duration: 0.2 });
    welcome.remove();
  }
  addUser(text);
  const bot = document.createElement("div");
  bot.className = "msg bot";
  bot.innerHTML = '<ol class="progress"></ol><p class="elapsed"></p>';
  feed.appendChild(bot);
  move(bot, { opacity: [0, 1], y: [12, 0] }, { duration: 0.3 });
  bot.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "end" });
  $("#send").disabled = true;
  const say = (msg, kind) => {
    const li = Object.assign(document.createElement("li"), { className: kind, textContent: msg });
    bot.querySelector(".progress")?.appendChild(li);
    move(li, { opacity: [0, 1], x: [-8, 0] }, { duration: 0.25 });
  };
  say("Finding a subscription that still has tokens", "done");
  const started = Date.now();
  const tick = setInterval(() => {
    const el = bot.querySelector(".elapsed");
    if (el) el.textContent = `${Math.round((Date.now() - started) / 1000)} s. Writing the spec first, then the work.`;
  }, 1000);
  relayWhileWaiting(say);
  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history: state.history, mode: state.mode, exhausted: [...state.exhausted] }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || r.statusText);
    const at = new Date().toISOString();
    for (const e of data.route) {
      state.ledger.push({ at, request: text.slice(0, 80), agent: data.agent, trace_id: data.trace_id, ...e });
    }
    saveLocal();
    clearInterval(tick);
    bot.innerHTML = "";
    const head = document.createElement("div");
    head.className = "who-said";
    head.innerHTML = '<span class="agent-tag"></span><p class="story"></p>';
    head.querySelector(".agent-tag").textContent = data.agent;
    head.querySelector(".story").append(routeStory(data.route));
    const receipts = Object.assign(document.createElement("button"), { type: "button", className: "linkish", textContent: "See the receipts" });
    receipts.onclick = () => $("#openLog").click();
    head.querySelector(".story").append(" ", receipts);
    bot.appendChild(head);
    for (const a of data.artifacts) bot.appendChild(a.type === "slides" ? slidesArtifact(a) : a.type === "spec" ? specArtifact(a) : appArtifact(a));
    const body = document.createElement("div");
    body.className = "reply";
    renderMarkdown(body, data.reply);
    bot.appendChild(body);
    state.history.push({ role: "user", content: text }, { role: "assistant", content: data.reply });
    move(bot.children, { opacity: [0, 1], y: [10, 0] }, { delay: stagger(0.08), duration: 0.35 });
    bot.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "start" });
    const servedBy = await landOn(data.route);
    state.providers = data.providers;
    renderRing(servedBy);
  } catch (err) {
    clearInterval(tick);
    stopPulse();
    bot.innerHTML = `<p class="error"></p>`;
    bot.querySelector(".error").textContent = `This request didn't finish: ${err.message}. Try again, or refill a subscription above.`;
  } finally {
    $("#send").disabled = false;
  }
}

$("#composer").onsubmit = (e) => {
  e.preventDefault();
  const text = $("#input").value.trim();
  if (!text) return;
  $("#input").value = "";
  send(text);
};
$("#input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#composer").requestSubmit(); }
});
document.querySelectorAll(".starters button").forEach((b) => (b.onclick = () => send(b.dataset.prompt)));
document.querySelectorAll(".mode button").forEach((b) => (b.onclick = () => {
  state.mode = b.dataset.mode;
  document.querySelectorAll(".mode button").forEach((x) => {
    x.classList.toggle("on", x === b);
    x.setAttribute("aria-checked", String(x === b));
  });
}));
$("#openHow").onclick = () => {
  const d = $("#how");
  d.showModal();
  move(d, { opacity: [0, 1], scale: [0.96, 1] }, { duration: 0.25 });
};
addEventListener("resize", layoutWire);

const labelOf = (id) => state.providers.find((p) => p.id === id)?.label || id;
const isOpenAI = (id) => id.startsWith("openai");

function renderLog() {
  const rows = [...state.ledger].reverse();
  const body = $("#logRows");
  body.innerHTML = "";
  const served = state.ledger.filter((e) => e.outcome === "served");
  const sum = (f) => served.reduce((n, e) => n + (e[f] || 0), 0);
  const byProvider = {};
  for (const e of served) byProvider[e.provider] = (byProvider[e.provider] || 0) + e.tokens;
  $("#logSum").innerHTML = "";
  const chips = [
    `${served.length} model calls`,
    `${sum("input_tokens").toLocaleString()} tokens in`,
    `${sum("output_tokens").toLocaleString()} tokens out`,
    ...Object.entries(byProvider).map(([id, n]) => `${labelOf(id)}: ${n.toLocaleString()}`),
  ];
  for (const c of chips) $("#logSum").appendChild(Object.assign(document.createElement("span"), { textContent: c }));
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="6" class="log-empty">No calls yet. Ask for something and every model call will show up here.</td></tr>';
    return;
  }
  for (const e of rows) {
    const tr = document.createElement("tr");
    tr.className = e.outcome;
    const cells = [
      new Date(e.at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" }),
      `${e.agent}: ${e.request}`,
      `${labelOf(e.provider)}${e.outcome === "served" ? `, ${e.detail}` : `, skipped (${e.detail})`}`,
      e.outcome === "served" ? `${(e.input_tokens || 0).toLocaleString()} / ${(e.output_tokens || 0).toLocaleString()}` : "",
      e.outcome === "served" ? `${(e.ms / 1000).toFixed(1)} s` : "",
    ];
    for (const c of cells) tr.appendChild(Object.assign(document.createElement("td"), { textContent: c }));
    const td = document.createElement("td");
    if (e.outcome === "served") {
      const id = e.response_id || e.request_id;
      td.appendChild(Object.assign(document.createElement("code"), { className: "receipt", textContent: id || "no id returned" }));
      const actions = document.createElement("div");
      actions.className = "receipt-actions";
      if (e.response_id && isOpenAI(e.provider)) {
        const b = Object.assign(document.createElement("button"), { className: "mini", type: "button", textContent: "Check with OpenAI" });
        b.onclick = async () => {
          b.textContent = "Checking…";
          const r = await fetch(`/api/verify/${e.provider}/${e.response_id}`);
          const v = await r.json();
          if (r.ok) {
            b.className = "mini ok";
            b.textContent = `Confirmed: ${v.model}, ${v.input_tokens} in / ${v.output_tokens} out`;
          } else {
            b.className = "mini bad";
            b.textContent = v.detail || "Not found";
          }
        };
        actions.appendChild(b);
      }
      if (e.trace_id) {
        actions.appendChild(Object.assign(document.createElement("a"), {
          className: "mini", textContent: "Trace", target: "_blank", rel: "noopener",
          href: `https://platform.openai.com/traces/trace?trace_id=${e.trace_id}`,
        }));
      }
      td.appendChild(actions);
    }
    tr.appendChild(td);
    body.appendChild(tr);
  }
}

$("#openLog").onclick = () => {
  renderLog();
  const d = $("#log");
  d.showModal();
  move(d, { opacity: [0, 1], scale: [0.97, 1] }, { duration: 0.25 });
};
$("#clearLog").onclick = () => {
  if (!confirm("Clear the usage log in this browser?")) return;
  state.ledger = [];
  saveLocal();
  renderLog();
  renderRing();
};
$("#exportLog").onclick = () => {
  const cols = ["at", "agent", "request", "provider", "detail", "outcome", "input_tokens", "output_tokens", "tokens", "ms", "response_id", "request_id", "trace_id"];
  const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const csv = [cols.join(","), ...state.ledger.map((e) => cols.map((c) => q(e[c])).join(","))].join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  Object.assign(document.createElement("a"), { href: url, download: "specwithcode-classroom-usage.csv" }).click();
};
$("#resetRing").onclick = async () => {
  state.exhausted.clear();
  saveLocal();
  await loadRing();
  await move($("#baton"), { opacity: 0 }, { duration: 0.2 });
  batonAt = null;
};

// One orchestrated entrance: the relay lights up left to right, then the desk arrives.
await loadRing();
move(".node", { opacity: [0, 1], y: [14, 0] }, { delay: stagger(0.08), duration: 0.45, ease: "easeOut" });
move("#wireLine", { strokeDashoffset: [120, 0] }, { duration: 1.2, ease: "easeOut" });
move(".welcome > *", { opacity: [0, 1], y: [16, 0] }, { delay: stagger(0.08, { startDelay: 0.3 }), duration: 0.5, ease: "easeOut" });
