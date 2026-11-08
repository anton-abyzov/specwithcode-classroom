const state = {
  mode: "finish",
  history: [],
  exhausted: new Set(JSON.parse(localStorage.getItem("swc.exhausted") || "[]")),
  switches: Number(localStorage.getItem("swc.switches") || 0),
  providers: [],
};

const $ = (s) => document.querySelector(s);
const feed = $("#feed");
const KIND = { grant: "Credits", "free-tier": "Free tier", subscription: "Subscription", machine: "Machine" };

function saveLocal() {
  localStorage.setItem("swc.exhausted", JSON.stringify([...state.exhausted]));
  localStorage.setItem("swc.switches", String(state.switches));
}

function renderRing(activeId) {
  const list = $("#providers");
  list.innerHTML = "";
  let total = 0;
  for (const p of state.providers) {
    total += p.used;
    const node = $("#tpl-provider").content.firstElementChild.cloneNode(true);
    node.classList.add(p.status);
    if (p.id === activeId) node.classList.add("active");
    node.querySelector(".p-label").textContent = p.label;
    node.querySelector(".p-meta").textContent = `${KIND[p.kind]} · ${p.model}`;
    const pct = p.status === "exhausted" ? 100 : Math.min(100, (p.used / p.budget) * 100);
    node.querySelector(".bar i").style.width = `${Math.max(pct, 2)}%`;
    const left = p.status === "offline" ? "not connected" : p.status === "exhausted" ? "out of tokens today" : `${(p.budget - p.used).toLocaleString()} tokens left`;
    node.querySelector(".p-note").textContent = `${p.note} · ${left}`;
    const t = node.querySelector(".toggle");
    if (p.status === "offline") t.remove();
    else {
      t.textContent = state.exhausted.has(p.id) ? "Refill" : "Run out";
      t.onclick = () => {
        state.exhausted.has(p.id) ? state.exhausted.delete(p.id) : state.exhausted.add(p.id);
        saveLocal();
        loadRing();
      };
    }
    list.appendChild(node);
  }
  $("#totalTokens").textContent = total.toLocaleString();
  $("#totalSwitches").textContent = state.switches;
}

async function loadRing(activeId) {
  const r = await fetch(`/api/ring?exhausted=${[...state.exhausted].join(",")}`);
  state.providers = (await r.json()).providers;
  renderRing(activeId);
}

function renderMarkdown(el, text) {
  el.innerHTML = marked.parse(text);
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

function routeChips(route) {
  const wrap = document.createElement("div");
  wrap.className = "route";
  const label = Object.fromEntries(state.providers.map((p) => [p.id, p.label.replace(" free tier", "")]));
  const hops = [];
  for (const e of route) {
    const last = hops[hops.length - 1];
    if (last && last.outcome === "served" && e.outcome === "served" && last.provider === e.provider) {
      last.ms += e.ms; last.tokens += e.tokens; last.calls += 1;
    } else hops.push({ ...e, calls: 1 });
  }
  for (const e of hops) {
    const hop = document.createElement("span");
    hop.className = `hop ${e.outcome}`;
    hop.title = e.detail;
    hop.textContent = e.outcome === "served"
      ? `${label[e.provider] || e.provider} ✓ ${e.calls} calls · ${(e.ms / 1000).toFixed(1)}s · ${e.tokens.toLocaleString()} tok`
      : `${label[e.provider] || e.provider} · ${e.detail.split(":")[0]}`;
    wrap.appendChild(hop);
  }
  return wrap;
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
  box.innerHTML = `<div class="artifact-bar"><strong></strong><span class="agent-tag">spec.md</span></div>
    <div class="spec-body"><p class="goal"></p><h5>Acceptance criteria</h5><ul class="ac"></ul><h5>Tasks</h5><ol class="tasks"></ol></div>`;
  box.querySelector("strong").textContent = a.title;
  box.querySelector(".goal").textContent = a.goal;
  a.acceptance_criteria.forEach((t, i) => {
    const li = document.createElement("li");
    li.textContent = `AC-${String(i + 1).padStart(2, "0")}  ${t}`;
    box.querySelector(".ac").appendChild(li);
  });
  a.tasks.forEach((t) => {
    const li = document.createElement("li");
    li.textContent = t;
    box.querySelector(".tasks").appendChild(li);
  });
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
  addUser(text);
  $(".welcome")?.remove();
  const bot = document.createElement("div");
  bot.className = "msg bot";
  bot.innerHTML = '<div class="thinking">Coach is picking a subscription with tokens left</div>';
  feed.appendChild(bot);
  feed.scrollTop = feed.scrollHeight;
  $("#send").disabled = true;
  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history: state.history, mode: state.mode, exhausted: [...state.exhausted] }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || r.statusText);
    state.switches += data.route.filter((e) => e.outcome === "switched").length;
    saveLocal();
    bot.innerHTML = "";
    const head = document.createElement("div");
    head.className = "who-said";
    head.innerHTML = '<span class="agent-tag"></span>';
    head.querySelector(".agent-tag").textContent = data.agent;
    head.appendChild(routeChips(data.route));
    bot.appendChild(head);
    const body = document.createElement("div");
    renderMarkdown(body, data.reply);
    bot.appendChild(body);
    for (const a of data.artifacts) bot.appendChild(a.type === "slides" ? slidesArtifact(a) : a.type === "spec" ? specArtifact(a) : appArtifact(a));
    state.history.push({ role: "user", content: text }, { role: "assistant", content: data.reply });
    state.providers = data.providers;
    const served = [...data.route].reverse().find((e) => e.outcome === "served");
    renderRing(served?.provider);
  } catch (err) {
    bot.innerHTML = `<p class="error"></p>`;
    bot.querySelector(".error").textContent = `Couldn't finish: ${err.message}`;
  } finally {
    $("#send").disabled = false;
    feed.scrollTop = feed.scrollHeight;
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
document.querySelectorAll(".chips button").forEach((b) => (b.onclick = () => send(b.dataset.prompt)));
document.querySelectorAll(".mode button").forEach((b) => (b.onclick = () => {
  state.mode = b.dataset.mode;
  document.querySelectorAll(".mode button").forEach((x) => x.classList.toggle("on", x === b));
}));
$("#resetRing").onclick = async () => {
  state.exhausted.clear();
  state.switches = 0;
  saveLocal();
  const r = await fetch("/api/ring/reset", { method: "POST" });
  state.providers = (await r.json()).providers;
  renderRing();
};

loadRing();
