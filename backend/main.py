"""Servidor local: http://127.0.0.1:8000"""
import asyncio
import itertools
import queue
import threading
import time
import webbrowser

import uvicorn
from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

import config
import simulacro
from claude_session import ClaudeSession
from prompt import build_system_prompt

app = FastAPI()
clients: set[WebSocket] = set()
loop: asyncio.AbstractEventLoop | None = None

state = {
    "listening": False,
    "auto": config.AUTO_RESPONDER,
    "whisper_ready": False,
    "claude_ready": False,
    "device": "",
}
transcripts: list[dict] = []
_tid = itertools.count(1)

transcriber = None
listener = None
claude: ClaudeSession | None = None
audio_q: queue.Queue = queue.Queue()


# ---------------- difusión a la página ----------------
async def _broadcast(msg: dict):
    dead = []
    for ws in list(clients):
        try:
            await ws.send_json(msg)
        except Exception:  # noqa: BLE001
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


def push(msg: dict):
    """Seguro de llamar desde cualquier hilo."""
    if loop:
        asyncio.run_coroutine_threadsafe(_broadcast(msg), loop)


def push_state():
    push({"type": "state", **state})


def on_claude_event(ev: dict):
    if ev["type"] == "claude_status":
        state["claude_ready"] = ev["ready"]
        push_state()
    else:
        push(ev)


# ---------------- hilos de trabajo ----------------
def load_whisper():
    global transcriber
    push({"type": "info", "message": f"Cargando Whisper '{config.WHISPER_MODEL}' (la 1ª vez se descarga ~500 MB)..."})
    from transcriber import Transcriber
    transcriber = Transcriber()
    state["whisper_ready"] = True
    push_state()
    push({"type": "info", "message": "Whisper listo."})


def transcribe_worker():
    while True:
        audio = audio_q.get()
        while transcriber is None:
            time.sleep(0.2)
        t0 = time.time()
        text = transcriber.transcribe(audio)
        if not text:
            continue
        item = {"id": next(_tid), "text": text, "secs": round(time.time() - t0, 1)}
        transcripts.append(item)
        push({"type": "transcript", **item})
        if state["auto"] and claude:
            claude.ask(text)


def start_listening():
    global listener
    from audio import LoopbackListener
    listener = LoopbackListener(on_segment=audio_q.put)
    listener.start()
    state["listening"] = True
    state["device"] = listener.device_name
    push_state()


def stop_listening():
    global listener
    if listener:
        listener.stop()
        listener = None
    state["listening"] = False
    push_state()


# ---------------- rutas ----------------
@app.on_event("startup")
async def startup():
    global loop, claude
    loop = asyncio.get_running_loop()
    threading.Thread(target=load_whisper, daemon=True).start()
    threading.Thread(target=transcribe_worker, daemon=True).start()
    claude = ClaudeSession(build_system_prompt(), on_claude_event)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    await ws.send_json({"type": "state", **state})
    await ws.send_json({"type": "history", "transcripts": transcripts[-50:]})
    try:
        while True:
            msg = await ws.receive_json()
            t = msg.get("type")
            try:
                if t == "start" and not state["listening"]:
                    await asyncio.to_thread(start_listening)
                elif t == "stop":
                    await asyncio.to_thread(stop_listening)
                elif t == "set_auto":
                    state["auto"] = bool(msg.get("value"))
                    push_state()
                elif t == "ask" and msg.get("text", "").strip():
                    claude.ask(msg["text"].strip(), force=True)
                elif t == "reload_profile":
                    claude.system_prompt = build_system_prompt()
                    claude.restart()
                    push({"type": "info", "message": "Perfil recargado y Claude reiniciado."})
            except Exception as e:  # noqa: BLE001
                await ws.send_json({"type": "error", "message": str(e)})
    except WebSocketDisconnect:
        clients.discard(ws)


# ---------------- simulacros ----------------
@app.get("/api/simulacros")
def listar_simulacros():
    return simulacro.listar()


@app.get("/api/simulacros/{sid}")
def obtener_simulacro(sid: str):
    try:
        return simulacro.obtener(sid)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/api/simulacros")
async def crear_simulacro(datos: dict = Body(...)):
    """Guarda las preguntas en simulacro/preguntas_<nombre>.txt y genera el audio .wav."""
    try:
        return await asyncio.to_thread(
            simulacro.guardar_y_generar, str(datos.get("nombre", "")), str(datos.get("texto", "")),
            int(datos.get("pausa") or 18), bool(datos.get("saludo", True)))
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e)) from e


@app.delete("/api/simulacros/{sid}")
def borrar_simulacro(sid: str):
    simulacro.eliminar(sid)
    return {"ok": True}


config.SIMULACRO_DIR.mkdir(exist_ok=True)
app.mount("/simulacro", StaticFiles(directory=config.SIMULACRO_DIR), name="simulacro")
app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    url = f"http://{config.HOST}:{config.PORT}"
    print(f"\n  Interview Copilot en {url}\n")
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="warning")
