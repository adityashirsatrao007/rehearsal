/* Rehearsal — vanilla JS front end. No build step, no framework, no CDN. */

const $ = (sel) => document.querySelector(sel);

const state = {
  sessionId: null,
  scenario: null,
  model: null,
  busy: false,
  scenarios: [],
  status: null,
};

const views = { pick: $("#viewPick"), session: $("#viewSession"), history: $("#viewHistory") };

/* ── boot ─────────────────────────────────────────────────────────── */

init();

async function init() {
  await Promise.all([loadStatus(), loadScenarios()]);
  loadStats();
}

async function loadStatus() {
  try {
    const res = await fetch("/api/status");
    state.status = await res.json();
  } catch {
    state.status = { ready: false, models: [], detail: "Could not reach the Rehearsal server." };
  }

  const select = $("#modelSelect");
  const models = state.status.models || [];
  select.innerHTML = "";

  if (models.length) {
    for (const name of models) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      select.appendChild(opt);
    }
    const preferred = models.includes(state.status.model)
      ? state.status.model
      : models.find((m) => m.startsWith("gemma")) || models[0];
    select.value = preferred;
    state.model = preferred;
  } else {
    const opt = document.createElement("option");
    opt.textContent = "no model installed";
    select.appendChild(opt);
    select.disabled = true;
  }

  const banner = $("#offlineBanner");
  if (!state.status.ready) {
    banner.hidden = false;
    banner.innerHTML =
      `${state.status.detail} Install it with <code>ollama pull gemma2:2b</code>, ` +
      `then reload this page.`;
  } else if (state.status.warming) {
    banner.hidden = false;
    banner.textContent = state.status.detail;
    // Poll until the model is resident so the banner clears itself.
    setTimeout(loadStatus, 3000);
  } else {
    banner.hidden = true;
  }
}

$("#modelSelect").addEventListener("change", (e) => {
  state.model = e.target.value;
  toast(`Switched to ${state.model}`);
});

async function loadScenarios() {
  try {
    const res = await fetch("/api/scenarios");
    state.scenarios = await res.json();
  } catch {
    state.scenarios = [];
  }

  const grid = $("#scenarioGrid");
  grid.innerHTML = "";
  for (const s of state.scenarios) {
    const btn = document.createElement("button");
    btn.className = "scenario";
    btn.type = "button";
    btn.innerHTML = `
      <span class="scenario-glyph">${s.emoji}</span>
      <span class="scenario-title">${escapeHtml(s.title)}</span>
      <span class="scenario-blurb">${escapeHtml(s.blurb)}</span>`;
    btn.addEventListener("click", () => startSession(s));
    grid.appendChild(btn);
  }
}

/* ── views ────────────────────────────────────────────────────────── */

function show(view) {
  for (const [name, el] of Object.entries(views)) el.hidden = name !== view;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

$("#historyBtn").addEventListener("click", loadHistory);
$("#backBtn").addEventListener("click", () => show("pick"));
$("#newBtn").addEventListener("click", () => {
  state.sessionId = null;
  show("pick");
});

/* ── session ──────────────────────────────────────────────────────── */

async function startSession(scenario) {
  const res = await fetch("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario: scenario.id }),
  });
  if (!res.ok) return toast("Could not start a session.");

  const session = await res.json();
  state.sessionId = session.id;
  state.scenario = scenario;

  $("#sessionTitle").textContent = scenario.title;
  $("#sessionScenario").textContent = scenario.emoji + "  " + scenario.blurb;
  $("#messages").innerHTML = "";
  $("#corrections").innerHTML = `<p class="empty">Write something and your feedback lands here.</p>`;
  $("#scorePanel").hidden = true;

  if (scenario.opening) addMessage("partner", scenario.opening);
  show("session");
  $("#input").focus();
  loadStats();
}

$("#composer").addEventListener("submit", (e) => {
  e.preventDefault();
  send();
});

$("#input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});

$("#input").addEventListener("input", (e) => {
  const el = e.target;
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 160) + "px";
});

async function send() {
  const input = $("#input");
  const text = input.value.trim();
  if (!text || state.busy || !state.sessionId) return;

  state.busy = true;
  $("#sendBtn").disabled = true;
  input.value = "";
  input.style.height = "auto";
  state.pendingLearner = text;

  addMessage("learner", text);
  const typing = addMessage("partner", "…", { typing: true });

  try {
    const res = await fetch(`/api/sessions/${state.sessionId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text, model: state.model }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Request failed (${res.status})`);
    }

    await readStream(res, (event) => handleEvent(event, typing));
  } catch (err) {
    typing.remove();
    toast(err.message);
  } finally {
    state.busy = false;
    $("#sendBtn").disabled = false;
    $("#input").focus();
  }
}

async function readStream(res, onEvent) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const chunk = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 2);
      if (!chunk.startsWith("data:")) continue;
      try {
        onEvent(JSON.parse(chunk.slice(5)));
      } catch {
        /* ignore malformed frames */
      }
    }
  }
}

function handleEvent(event, typingEl) {
  switch (event.type) {
    case "reply": {
      const target = typingEl.isConnected ? typingEl : null;
      if (!target) return;
      target.classList.remove("msg-typing");
      const body = target.querySelector(".msg-body");
      if (body.textContent === "…") body.textContent = "";
      body.textContent += event.delta;
      scrollMessages();
      break;
    }
    case "reply_done": {
      if (typingEl.isConnected) {
        const body = typingEl.querySelector(".msg-body");
        if (!body.textContent.trim()) body.textContent = "(no reply)";
        typingEl.classList.remove("msg-typing");
      }
      break;
    }
    case "correction":
      renderCorrection(event, state.pendingLearner);
      break;
    case "error":
      if (typingEl.isConnected) typingEl.remove();
      toast(`${event.stage}: ${event.detail}`);
      break;
    case "done":
      scrollMessages();
      break;
  }
}

/* ── rendering ────────────────────────────────────────────────────── */

function addMessage(role, text, opts = {}) {
  const wrap = document.createElement("div");
  wrap.className = `msg msg-${role}` + (opts.typing ? " msg-typing" : "");
  wrap.innerHTML = `
    <span class="msg-who">${role === "learner" ? "You" : "Them"}</span>
    <div class="msg-body"></div>`;
  wrap.querySelector(".msg-body").textContent = text;
  $("#messages").appendChild(wrap);
  scrollMessages();
  return wrap;
}

function renderCorrection(c, originalText) {
  const box = $("#corrections");
  const empty = box.querySelector(".empty");
  if (empty) empty.remove();

  const card = document.createElement("div");
  card.className = "card";

  if (!c.parsed || (!c.corrected && !c.why && !c.better)) {
    card.innerHTML = `<div class="card-raw"></div>`;
    card.querySelector(".card-raw").textContent = c.raw || "No feedback returned.";
  } else {
    const parts = [];
    const original = (originalText || "").trim();
    const isVerbatim = original && c.corrected.toLowerCase() === original.toLowerCase();

    if (original && !isVerbatim) {
      parts.push(`<div class="card-original">${escapeHtml(original)}</div>`);
    }
    if (c.corrected) parts.push(`<div class="card-corrected">${escapeHtml(c.corrected)}</div>`);
    if (c.why && c.why !== "Clear and natural.") parts.push(`<div class="card-why">${escapeHtml(c.why)}</div>`);
    if (c.better) parts.push(`<div class="card-better"><strong>Say it like this</strong>${escapeHtml(c.better)}</div>`);
    if (!parts.length) parts.push(`<div class="card-corrected">${escapeHtml(c.why || "Clear and natural.")}</div>`);
    card.innerHTML = parts.join("");
  }

  box.appendChild(card);
  card.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function scrollMessages() {
  const el = $("#messages");
  el.scrollTop = el.scrollHeight;
}

/* ── scorecard ────────────────────────────────────────────────────── */

$("#endBtn").addEventListener("click", async () => {
  if (!state.sessionId || state.busy) return;
  $("#endBtn").disabled = true;
  try {
    const res = await fetch(`/api/sessions/${state.sessionId}/summary`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not score this session.");

    const rows = [
      ["Fluency", data.fluency],
      ["Accuracy", data.accuracy],
      ["Vocabulary", data.vocabulary],
    ]
      .map(
        ([label, val]) => `
        <div class="score-row">
          <span class="score-label">${label}</span>
          <span class="score-track"><span class="score-fill" style="width:${val * 10}%"></span></span>
          <span class="score-num">${val}</span>
        </div>`
      )
      .join("");

    $("#scoreBody").innerHTML = `
      ${rows}
      <p class="score-note">${escapeHtml(data.summary)}<br />
      <strong>Next:</strong> ${escapeHtml(data.next_step)}</p>`;

    $("#scorePanel").hidden = false;
    $("#scorePanel").scrollIntoView({ block: "nearest", behavior: "smooth" });
    loadStats();
    toast("Session scored.");
  } catch (err) {
    toast(err.message);
  } finally {
    $("#endBtn").disabled = false;
  }
});

async function loadStats() {
  try {
    const res = await fetch("/api/progress");
    const s = await res.json();
    $("#statsBody").innerHTML = [
      [s.sessions_completed, "Sessions"],
      [s.learner_messages, "Messages"],
      [s.corrections, "Corrections"],
      [s.avg_accuracy || "–", "Avg accuracy"],
    ]
      .map(([n, cap]) => `<div><div class="stat-num">${n}</div><div class="stat-cap">${cap}</div></div>`)
      .join("");
  } catch {
    /* non-fatal */
  }
}

/* ── history ──────────────────────────────────────────────────────── */

async function loadHistory() {
  const [sessionsRes, scenariosRes] = await Promise.all([
    fetch("/api/sessions"),
    fetch("/api/scenarios"),
  ]);
  const sessions = await sessionsRes.json();
  const scenarios = await scenariosRes.json();
  show("history");

  const list = $("#historyList");
  if (!sessions.length) {
    list.innerHTML = `<p class="empty">No sessions yet.</p>`;
    return;
  }

  list.innerHTML = "";
  for (const s of sessions) {
    const scenario = scenarios.find((x) => x.id === s.scenario);
    const scored =
      s.ended_at != null
        ? `Scored ${s.score_fluency}/${s.score_accuracy}/${s.score_vocabulary}`
        : "In progress";
    const row = document.createElement("div");
    row.className = "history-row";
    row.innerHTML = `
      <div class="history-main">
        <div class="history-title">${s.emoji || (scenario ? scenario.emoji : "💬")} ${escapeHtml(s.scenario_title)}</div>
        <div class="history-meta">${scored} · ${new Date(s.created_at).toLocaleString()} · ${escapeHtml(s.model)}</div>
      </div>
      <div class="history-actions"></div>`;

    const actions = row.querySelector(".history-actions");

    const resume = document.createElement("button");
    resume.className = "btn btn-outline";
    resume.textContent = "Open";
    resume.addEventListener("click", () => resumeSession(s, scenario));
    actions.appendChild(resume);

    const del = document.createElement("button");
    del.className = "btn btn-ghost";
    del.textContent = "Delete";
    del.addEventListener("click", async () => {
      await fetch(`/api/sessions/${s.id}`, { method: "DELETE" });
      loadHistory();
    });
    actions.appendChild(del);

    list.appendChild(row);
  }
}

async function resumeSession(summary, scenario) {
  const res = await fetch(`/api/sessions/${summary.id}`);
  const data = await res.json();

  state.sessionId = summary.id;
  state.scenario = scenario || { id: summary.scenario, title: summary.scenario_title, opening: "" };

  $("#sessionTitle").textContent = summary.scenario_title;
  $("#sessionScenario").textContent = scenario ? scenario.blurb : summary.scenario;
  $("#messages").innerHTML = "";
  $("#corrections").innerHTML = `<p class="empty">Write something and your feedback lands here.</p>`;
  $("#scorePanel").hidden = true;

  // The scripted opening is not persisted; restore it so the thread reads naturally.
  if (!data.messages.some((m) => m.role === "partner") && scenario?.opening) {
    addMessage("partner", scenario.opening);
  }

  const learnerById = new Map(
    data.messages.filter((m) => m.role === "learner").map((m) => [m.id, m.content])
  );
  for (const m of data.messages) addMessage(m.role === "learner" ? "learner" : "partner", m.content);

  show("session");
  if (data.corrections.length) {
    $("#corrections").innerHTML = "";
    for (const c of data.corrections) {
      renderCorrection({ ...c, parsed: true, raw: c.better }, learnerById.get(c.message_id));
    }
  }
}

/* ── utils ────────────────────────────────────────────────────────── */

let toastTimer;
function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), 4200);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
