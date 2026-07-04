// M.A.R.I.A. Micro-Engine — web sprite-shell.
// Talks to the same-origin OpenAI-compatible API and reads the
// `x_micro_engine` extension to visualize relationship state. Also browses and
// clears per-character conversation history via the /sessions endpoints.

const els = {
  log: document.getElementById("log"),
  form: document.getElementById("composer"),
  input: document.getElementById("input"),
  send: document.getElementById("send"),
  model: document.getElementById("model"),
  reset: document.getElementById("reset"),
  history: document.getElementById("history"),
  clearDay: document.getElementById("clear-day"),
  clearAll: document.getElementById("clear-all"),
  resetRel: document.getElementById("reset-rel"),
  name: document.getElementById("name"),
  stage: document.getElementById("stage"),
  face: document.getElementById("face"),
  avatar: document.getElementById("avatar"),
  meta: document.getElementById("meta"),
  bars: {
    affection: document.getElementById("bar-affection"),
    trust: document.getElementById("bar-trust"),
    bond: document.getElementById("bar-bond"),
  },
};

const state = {
  axisMax: 100,
  messages: [], // live OpenAI-style history for the active character
  sessionId: loadSessionId(),
  viewing: null, // null = live chat; otherwise a "YYYY-MM-DD" being reviewed
  busy: false,
};

function loadSessionId() {
  let id = localStorage.getItem("micro_engine_session");
  if (!id) {
    id = "web-" + Math.random().toString(36).slice(2);
    localStorage.setItem("micro_engine_session", id);
  }
  return id;
}

function model() {
  return els.model.value;
}

function faceFor(fraction) {
  if (fraction >= 0.75) return "^_^";
  if (fraction >= 0.5) return "•‿•";
  if (fraction >= 0.25) return "·‿·";
  return "·_·";
}

function addBubble(role, text) {
  const div = document.createElement("div");
  div.className = "bubble " + role;
  div.textContent = text;
  els.log.appendChild(div);
  els.log.scrollTop = els.log.scrollHeight;
  return div;
}

function updateHud(ext) {
  if (!ext) return;
  const axes = ext.axes || {};
  for (const key of ["affection", "trust", "bond"]) {
    const pct = Math.max(0, Math.min(100, ((axes[key] || 0) / state.axisMax) * 100));
    els.bars[key].style.width = pct + "%";
  }
  els.face.textContent = faceFor((axes.affection || 0) / state.axisMax);
  els.stage.textContent = ext.stage ? ext.stage.replace(/_/g, " ") : "—";
  if (ext.stage_changed) {
    els.stage.classList.remove("changed");
    void els.stage.offsetWidth;
    els.stage.classList.add("changed");
    els.avatar.classList.add("pulse");
    setTimeout(() => els.avatar.classList.remove("pulse"), 400);
  }
}

function resetHud() {
  for (const key of ["affection", "trust", "bond"]) els.bars[key].style.width = "0";
  els.stage.textContent = "—";
  els.face.textContent = "·_·";
}

function setComposerEnabled(enabled) {
  els.input.disabled = !enabled;
  els.send.disabled = !enabled;
  els.input.placeholder = enabled ? "Say something…" : "Viewing history — switch to Live chat to talk";
}

// ---------------------------------------------------------------- API

async function loadModels() {
  const data = await fetch("/v1/models").then((r) => r.json());
  els.model.innerHTML = "";
  for (const card of data.data) {
    const opt = document.createElement("option");
    opt.value = card.id;
    opt.textContent = card.id;
    els.model.appendChild(opt);
  }
  if (!data.data.length) {
    els.meta.textContent = "No characters loaded. Add a pack under characters/.";
    els.send.disabled = true;
  } else {
    els.name.textContent = model();
  }
}

async function refreshDays() {
  if (!model()) return;
  const params = new URLSearchParams({ user: state.sessionId });
  let days = [];
  try {
    days = (await fetch(`/sessions/${model()}/days?${params}`).then((r) => r.json())).days || [];
  } catch {
    days = [];
  }
  const previous = els.history.value;
  els.history.innerHTML = '<option value="">Live chat</option>';
  for (const day of days.slice().reverse()) {
    const opt = document.createElement("option");
    opt.value = day;
    opt.textContent = day;
    els.history.appendChild(opt);
  }
  els.history.value = days.includes(previous) ? previous : "";
}

async function viewDay(day) {
  const params = new URLSearchParams({ user: state.sessionId, day });
  const turns = (await fetch(`/sessions/${model()}/transcript?${params}`).then((r) => r.json())).turns || [];
  state.viewing = day;
  els.log.innerHTML = "";
  const banner = document.createElement("div");
  banner.className = "viewing-banner";
  banner.textContent = `Viewing ${day} — read only`;
  els.log.appendChild(banner);
  let last = null;
  for (const turn of turns) {
    addBubble("user", turn.user);
    addBubble("assistant", turn.reply);
    last = turn;
  }
  if (last) updateHud({ axes: last.axes, stage: last.stage });
  setComposerEnabled(false);
}

// ---------------------------------------------------------------- views

function renderLive() {
  els.log.innerHTML = "";
  if (model()) addBubble("system", `Now chatting with ${model()}.`);
  for (const m of state.messages) addBubble(m.role, m.content);
}

function goLive() {
  state.viewing = null;
  els.history.value = "";
  setComposerEnabled(true);
  renderLive();
}

function startConversation() {
  state.messages = [];
  resetHud();
  goLive();
  refreshDays();
}

// ---------------------------------------------------------------- chat

async function send(text) {
  if (state.busy || !model() || state.viewing !== null) return;
  state.busy = true;
  els.send.disabled = true;

  state.messages.push({ role: "user", content: text });
  addBubble("user", text);
  const pending = addBubble("system", "…");

  try {
    const res = await fetch("/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: model(), user: state.sessionId, messages: state.messages }),
    });
    const data = await res.json();
    pending.remove();
    if (!res.ok) {
      addBubble("error", (data.error && data.error.message) || `Error ${res.status}`);
      state.messages.pop();
      return;
    }
    const reply = data.choices[0].message.content;
    state.messages.push({ role: "assistant", content: reply });
    addBubble("assistant", reply);
    updateHud(data.x_micro_engine);
    refreshDays();
  } catch {
    pending.remove();
    addBubble("error", "Could not reach the server.");
    state.messages.pop();
  } finally {
    state.busy = false;
    els.send.disabled = state.viewing !== null;
    els.input.focus();
  }
}

// ---------------------------------------------------------------- history controls

async function clearSelectedDay() {
  if (!state.viewing) return;
  const params = new URLSearchParams({ user: state.sessionId, day: state.viewing });
  await fetch(`/sessions/${model()}/transcript?${params}`, { method: "DELETE" });
  await refreshDays();
  goLive();
}

async function clearAllHistory() {
  if (!confirm(`Delete the entire saved conversation with ${model()}?`)) return;
  const params = new URLSearchParams({ user: state.sessionId });
  await fetch(`/sessions/${model()}/transcript?${params}`, { method: "DELETE" });
  state.messages = [];
  await refreshDays();
  goLive();
}

async function resetRelationship() {
  if (!confirm(`Reset your relationship with ${model()} back to the start?`)) return;
  const params = new URLSearchParams({ user: state.sessionId });
  await fetch(`/sessions/${model()}/reset?${params}`, { method: "POST" });
  state.messages = [];
  resetHud();
  goLive();
}

// ---------------------------------------------------------------- wiring

els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = els.input.value.trim();
  if (!text) return;
  els.input.value = "";
  send(text);
});

els.model.addEventListener("change", () => {
  els.name.textContent = model();
  startConversation();
});
els.reset.addEventListener("click", startConversation);
els.history.addEventListener("change", () => {
  const day = els.history.value;
  if (day) viewDay(day);
  else goLive();
});
els.clearDay.addEventListener("click", clearSelectedDay);
els.clearAll.addEventListener("click", clearAllHistory);
els.resetRel.addEventListener("click", resetRelationship);

(async function init() {
  try {
    const health = await fetch("/healthz").then((r) => r.json());
    if (health.axis_max) state.axisMax = health.axis_max;
    els.meta.textContent = `Micro-Engine v${health.version}`;
  } catch {
    els.meta.textContent = "Server unreachable.";
  }
  await loadModels();
  startConversation();
})();
