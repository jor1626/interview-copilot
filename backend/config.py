"""Configuración general. Edita estos valores si necesitas ajustar algo."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PERFIL_DIR = ROOT / "perfil"          # tu CV, la oferta y notas (.md, .txt o .pdf)
STATIC_DIR = ROOT / "frontend"
CLAUDE_WORKDIR = ROOT / ".claude_workdir"  # carpeta vacía para que Claude no lea otros proyectos
LOG_DIR = ROOT / "logs"

HOST = "127.0.0.1"
PORT = 8000

# --- Transcripción (faster-whisper en CPU) ---
WHISPER_MODEL = "small"     # "base" = más rápido / menos preciso, "medium" = más lento / más preciso
LANGUAGE = "es"

# --- Detección de voz ---
VAD_AGGRESSIVENESS = 2      # 0-3: más alto = filtra más ruido
SILENCE_MS = 900            # silencio que marca el fin de una frase del entrevistador
MIN_SPEECH_MS = 700         # ignora ruidos más cortos que esto
MAX_SEGMENT_S = 25          # corta frases muy largas

# --- Claude Code (usa tu sesión de claude.ai) ---
CLAUDE_MODEL = "sonnet"     # "sonnet" = rápido y gasta menos cupo; "opus" = más calidad, más lento
AUTO_RESPONDER = True       # si es False, solo respondes al hacer clic en una frase
