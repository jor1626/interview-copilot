const $ = (id) => document.getElementById(id);
let ws;
let state = {};
const answers = {}; // id -> {question, text}
let currentId = null;

function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = (e) => handle(JSON.parse(e.data));
  ws.onclose = () => { log("Conexión perdida, reintentando…", true); setTimeout(connect, 1500); };
}
const send = (msg) => ws && ws.readyState === 1 && ws.send(JSON.stringify(msg));

function handle(m) {
  switch (m.type) {
    case "state": state = m; renderState(); break;
    case "history": m.transcripts.forEach(addTranscript); break;
    case "transcript": addTranscript(m); break;
    case "answer_start": startAnswer(m.id, m.question); break;
    case "answer_delta": if (answers[m.id]) { answers[m.id].text += m.text; if (m.id === currentId) renderCurrent(); } break;
    case "answer_end": endAnswer(m.id, m.skipped); break;
    case "info": log(m.message); break;
    case "error": log(m.message, true); break;
  }
}

function renderState() {
  setPill("st-whisper", state.whisper_ready ? "Whisper listo" : "Cargando Whisper…", state.whisper_ready && "ok");
  setPill("st-claude", state.claude_ready ? "Claude listo" : "Claude…", state.claude_ready && "ok");
  setPill("st-mic", state.listening ? "● Escuchando" : "Detenido", state.listening && "live");
  $("st-mic").title = state.device || "";
  $("auto").checked = !!state.auto;
  const b = $("btn-listen");
  b.textContent = state.listening ? "■ Detener" : "▶ Escuchar";
  b.className = state.listening ? "stop" : "primary";
}
function setPill(id, text, cls) { const el = $(id); el.textContent = text; el.className = "pill " + (cls || ""); }

function addTranscript(t) {
  const el = document.createElement("div");
  el.className = "tr";
  el.innerHTML = `<span></span><small>${t.secs ?? ""}s de transcripción · clic para responder</small>`;
  el.firstChild.textContent = t.text;
  el.onclick = () => send({ type: "ask", text: t.text });
  const box = $("transcripts");
  box.appendChild(el);
  box.scrollTop = box.scrollHeight;
}

// Divide el texto que llega en "PUNTOS:" y "GUION:"
function parse(text) {
  const [a, b = ""] = text.split(/GUI[OÓ]N:/i);
  const points = a.replace(/PUNTOS:/i, "").split("\n")
    .map((l) => l.replace(/^\s*[-•*]\s*/, "").trim()).filter(Boolean);
  return { points, script: b.trim() };
}

function startAnswer(id, question) {
  if (currentId && answers[currentId]?.done) archive(currentId);
  answers[id] = { question, text: "", done: false };
  currentId = id;
  $("current").className = "card current streaming";
  renderCurrent();
}

function renderCurrent() {
  const a = answers[currentId];
  const { points, script } = parse(a.text);
  $("cur-q").textContent = a.question;
  $("cur-points").innerHTML = "";
  points.forEach((p) => { const li = document.createElement("li"); li.textContent = p; $("cur-points").appendChild(li); });
  $("cur-script").textContent = script;
}

function endAnswer(id, skipped) {
  if (skipped || !answers[id]) return;
  answers[id].done = true;
  if (id === currentId) $("current").className = "card current";
}

function archive(id) {
  const a = answers[id];
  const { points, script } = parse(a.text);
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `<div class="q"></div><ul></ul><details><summary>Guion</summary><p></p></details>`;
  card.querySelector(".q").textContent = a.question;
  points.forEach((p) => { const li = document.createElement("li"); li.textContent = p; card.querySelector("ul").appendChild(li); });
  card.querySelector("p").textContent = script;
  $("history").prepend(card);
}

function log(msg, isErr) {
  const el = document.createElement("div");
  el.textContent = `${new Date().toLocaleTimeString()} · ${msg}`;
  if (isErr) el.className = "err";
  $("log").prepend(el);
}

$("btn-listen").onclick = () => send({ type: state.listening ? "stop" : "start" });
$("auto").onchange = (e) => send({ type: "set_auto", value: e.target.checked });
$("btn-reload").onclick = () => send({ type: "reload_profile" });
$("manual").onsubmit = (e) => {
  e.preventDefault();
  const v = $("manual-input").value.trim();
  if (v) { send({ type: "ask", text: v }); $("manual-input").value = ""; }
};

// ---------------- Simulacro ----------------
let simActual = null; // {id, audio, ...}

async function api(url, opts) {
  const r = await fetch(url, opts);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail || `Error ${r.status}`);
  return d;
}
function simEstado(html, err) {
  $("sim-estado").innerHTML = html;
  $("sim-estado").className = err ? "err" : "muted";
}
const escHtml = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function simSeleccionar(item) {
  simActual = item;
  $("sim-practicar").disabled = !item?.audio;
}

function simMostrar(d) {
  $("sim-nombre").value = d.id;
  $("sim-texto").value = d.texto;
  $("sim-saludo").checked = false; // el texto cargado ya trae sus frases de saludo
  simSeleccionar(d);
}

async function simCargarLista() {
  const items = await api("/api/simulacros");
  const box = $("sim-lista");
  if (!items.length) { box.textContent = "Aún no hay simulacros."; return; }
  box.innerHTML = "";
  items.forEach((i) => {
    const row = document.createElement("div");
    row.className = "sim-item" + (simActual?.id === i.id ? " on" : "");
    row.innerHTML = `<button class="sim-abrir"><b></b><small></small></button><button class="sim-borrar" title="Eliminar">🗑</button>`;
    row.querySelector("b").textContent = i.id;
    row.querySelector("small").textContent = `${i.preguntas} preguntas · ${i.audio ? "con audio" : "sin audio"}`;
    row.querySelector(".sim-abrir").onclick = async () => {
      try {
        const d = await api(`/api/simulacros/${encodeURIComponent(i.id)}`);
        simMostrar(d);
        simEstado(`Cargado <code>${escHtml(d.txt)}</code>.`);
        simCargarLista();
      } catch (e) { simEstado(escHtml(e.message), true); }
    };
    row.querySelector(".sim-borrar").onclick = async () => {
      if (!confirm(`¿Eliminar el simulacro "${i.id}" (preguntas y audio)?`)) return;
      await api(`/api/simulacros/${encodeURIComponent(i.id)}`, { method: "DELETE" });
      if (simActual?.id === i.id) simSeleccionar(null);
      simCargarLista();
    };
    box.appendChild(row);
  });
}

$("btn-sim").onclick = () => {
  $("sim-dialog").showModal();
  simCargarLista().catch((e) => simEstado(escHtml(e.message), true));
};

$("sim-generar").onclick = async () => {
  const b = $("sim-generar");
  b.disabled = true;
  const t0 = Date.now();
  const timer = setInterval(() => simEstado(`Generando audio con la voz de Windows… ${Math.round((Date.now() - t0) / 1000)}s`), 500);
  try {
    const d = await api("/api/simulacros", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nombre: $("sim-nombre").value, texto: $("sim-texto").value,
        pausa: +$("sim-pausa").value || 18, saludo: $("sim-saludo").checked }),
    });
    clearInterval(timer);
    simMostrar(d);
    simEstado(`✅ ${d.preguntas} preguntas guardadas en <code>simulacro/${escHtml(d.txt)}</code> con su audio. Pulsa <b>▶ Practicar</b>.`);
    simCargarLista();
  } catch (e) {
    clearInterval(timer);
    simEstado(escHtml(e.message), true);
  } finally {
    b.disabled = false;
  }
};

$("sim-practicar").onclick = () => {
  if (!simActual?.audio) return;
  if (!state.listening) send({ type: "start" });
  $("sim-bar-nombre").textContent = simActual.id;
  $("sim-audio").src = simActual.audio;
  $("sim-bar").hidden = false;
  $("sim-dialog").close();
  // Un segundo para que arranque la captura de audio antes de la primera frase.
  setTimeout(() => $("sim-audio").play().catch(() => log("Pulsa ▶ en el reproductor para empezar el simulacro.")), 1000);
};

$("sim-bar-cerrar").onclick = () => {
  $("sim-audio").pause();
  $("sim-audio").removeAttribute("src");
  $("sim-bar").hidden = true;
};

connect();
