// M.A.R.I.A. Micro-Engine — web sprite-shell.
// Talks to the same-origin OpenAI-compatible API and reads the
// `x_micro_engine` extension to visualize relationship state.

const els = {
  log: document.getElementById("log"),
  form: document.getElementById("composer"),
  input: document.getElementById("input"),
  send: document.getElementById("send"),
  model: document.getElementById("model"),
  reset: document.getElementById("reset"),
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
  messages: [], // OpenAI-style history for the active character
  sessionId: loadSessionId(),
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

// Neutral little faces driven by the affection fraction; a stranger is blank,
// a close companion beams. Packs with real sprites can replace this later.
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
    const value = axes[key] || 0;
    const pct = Math.max(0, Math.min(100, (value / state.axisMax) * 100));
    els.bars[key].style.width = pct + "%";
  }
  const affFrac = (axes.affection || 0) / state.axisMax;
  els.face.textContent = faceFor(affFrac);

  els.stage.textContent = ext.stage ? ext.stage.replace(/_/g, " ") : "—";
  if (ext.stage_changed) {
    els.stage.classList.remove("changed");
    void els.stage.offsetWidth; // restart the animation
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

async function loadModels() {
  const res = await fetch("/v1/models");
  const data = await res.json();
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
    els.name.textContent = els.model.value;
  }
}

function startConversation() {
  state.messages = [];
  els.log.innerHTML = "";
  resetHud();
  if (els.model.value) {
    els.name.textContent = els.model.value;
    addBubble("system", `Now chatting with ${els.model.value}.`);
  }
}

async function send(text) {
  if (state.busy || !els.model.value) return;
  state.busy = true;
  els.send.disabled = true;

  state.messages.push({ role: "user", content: text });
  addBubble("user", text);
  const pending = addBubble("system", "…");

  try {
    const res = await fetch("/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: els.model.value,
        user: state.sessionId,
        messages: state.messages,
      }),
    });
    const data = await res.json();
    pending.remove();

    if (!res.ok) {
      const msg = (data.error && data.error.message) || `Error ${res.status}`;
      addBubble("error", msg);
      state.messages.pop(); // drop the turn that failed
      return;
    }

    const reply = data.choices[0].message.content;
    state.messages.push({ role: "assistant", content: reply });
    addBubble("assistant", reply);
    updateHud(data.x_micro_engine);
  } catch (err) {
    pending.remove();
    addBubble("error", "Could not reach the server.");
    state.messages.pop();
  } finally {
    state.busy = false;
    els.send.disabled = false;
    els.input.focus();
  }
}

els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = els.input.value.trim();
  if (!text) return;
  els.input.value = "";
  send(text);
});

els.model.addEventListener("change", startConversation);
els.reset.addEventListener("click", startConversation);

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
