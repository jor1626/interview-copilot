"""Mantiene UN proceso de Claude Code vivo (modo headless, stream-json) que usa tu sesión
de claude.ai. Le envía cada pregunta y devuelve la respuesta token a token."""
import itertools
import json
import queue
import shutil
import subprocess
import threading

import config

SKIP = "[SKIP]"


class ClaudeSession:
    def __init__(self, system_prompt: str, on_event):
        self.system_prompt = system_prompt
        self.on_event = on_event  # callback(dict), se llama desde un hilo
        self.q: queue.Queue = queue.Queue()
        self.proc: subprocess.Popen | None = None
        self.ready = False
        self._ids = itertools.count(1)
        threading.Thread(target=self._worker, daemon=True).start()

    # ---------- API pública ----------
    def ask(self, text: str, force: bool = False) -> int:
        """Encola un texto. Si force=False, Claude puede decidir que no es una pregunta."""
        qid = next(self._ids)
        self.q.put((qid, text, force))
        return qid

    def restart(self):
        self._kill()
        self.q.put(("restart", None, None))

    # ---------- proceso ----------
    def _spawn(self):
        exe = shutil.which("claude")
        if not exe:
            raise RuntimeError("No encuentro el comando 'claude'. Instálalo con: npm install -g @anthropic-ai/claude-code")
        config.CLAUDE_WORKDIR.mkdir(exist_ok=True)
        config.LOG_DIR.mkdir(exist_ok=True)
        prompt_file = config.CLAUDE_WORKDIR / "system_prompt.md"
        prompt_file.write_text(self.system_prompt, encoding="utf-8")
        cmd = [
            exe, "-p",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--include-partial-messages",
            "--verbose",
            "--model", config.CLAUDE_MODEL,
            "--effort", "low",
            "--tools", "",
            "--system-prompt-file", str(prompt_file),
        ]
        self.proc = subprocess.Popen(
            cmd,
            cwd=config.CLAUDE_WORKDIR,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=open(config.LOG_DIR / "claude_stderr.log", "a", encoding="utf-8"),
            text=True,
            encoding="utf-8",
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.ready = True
        self.on_event({"type": "claude_status", "ready": True})

    def _kill(self):
        self.ready = False
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None

    def _ensure(self):
        if not self.proc or self.proc.poll() is not None:
            self._spawn()

    # ---------- bucle principal ----------
    def _worker(self):
        try:
            self._ensure()
        except Exception as e:  # noqa: BLE001
            self.on_event({"type": "error", "message": str(e)})
        while True:
            qid, text, force = self.q.get()
            if qid == "restart":
                try:
                    self._ensure()
                except Exception as e:  # noqa: BLE001
                    self.on_event({"type": "error", "message": str(e)})
                continue
            try:
                self._ensure()
                self._run_turn(qid, text, force)
            except Exception as e:  # noqa: BLE001
                self._kill()
                self.on_event({"type": "answer_end", "id": qid, "skipped": True})
                self.on_event({"type": "error", "message": f"Claude falló: {e}"})

    def _run_turn(self, qid: int, text: str, force: bool):
        prefix = "PREGUNTA (respóndela sí o sí)" if force else "ENTREVISTADOR"
        msg = {"type": "user", "message": {"role": "user", "content": f"{prefix}: {text}"}}
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

        pending = ""        # retenemos el inicio hasta saber si es [SKIP]
        decided = False
        skipped = False
        got_partials = False

        def emit(chunk: str):
            nonlocal pending, decided, skipped
            if decided:
                if not skipped:
                    self.on_event({"type": "answer_delta", "id": qid, "text": chunk})
                return
            pending += chunk
            stripped = pending.lstrip()
            if len(stripped) < len(SKIP) and SKIP.startswith(stripped):
                return  # todavía no sabemos
            decided = True
            skipped = stripped.startswith(SKIP)
            if not skipped:
                self.on_event({"type": "answer_start", "id": qid, "question": text})
                self.on_event({"type": "answer_delta", "id": qid, "text": stripped})

        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("el proceso de Claude se cerró (revisa logs/claude_stderr.log; "
                                   "¿iniciaste sesión con 'claude' en una terminal?)")
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = ev.get("type")
            if t == "stream_event":
                e = ev.get("event", {})
                if e.get("type") == "content_block_delta" and e.get("delta", {}).get("type") == "text_delta":
                    got_partials = True
                    emit(e["delta"]["text"])
            elif t == "assistant" and not got_partials:
                for block in ev.get("message", {}).get("content", []):
                    if block.get("type") == "text":
                        emit(block["text"])
            elif t == "result":
                if ev.get("is_error"):
                    raise RuntimeError(str(ev.get("result") or ev.get("subtype")))
                if not decided:  # respuesta muy corta
                    skipped = pending.strip().startswith(SKIP) or not pending.strip()
                    if not skipped:
                        self.on_event({"type": "answer_start", "id": qid, "question": text})
                        self.on_event({"type": "answer_delta", "id": qid, "text": pending})
                self.on_event({"type": "answer_end", "id": qid, "skipped": skipped})
                return
