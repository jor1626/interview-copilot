"""Transcripción local con faster-whisper en CPU."""
import os
import re

import numpy as np
from faster_whisper import WhisperModel

import config

# Frases que Whisper "alucina" sobre silencio o música.
ALUCINACIONES = {
    "gracias.", "gracias", "¡gracias!", "gracias por ver el video.", "gracias por ver.",
    "subtítulos realizados por la comunidad de amara.org",
    "subtítulos por la comunidad de amara.org", "...", "¿", "mmm.",
}


class Transcriber:
    def __init__(self):
        threads = max(2, (os.cpu_count() or 4) - 4)
        self.model = WhisperModel(
            config.WHISPER_MODEL, device="cpu", compute_type="int8", cpu_threads=threads
        )

    def transcribe(self, audio: np.ndarray) -> str:
        segments, _ = self.model.transcribe(
            audio,
            language=config.LANGUAGE,
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
            initial_prompt="Entrevista de trabajo.",
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        # Quita repeticiones alucinadas tipo "y y y y y".
        text = re.sub(r"(?:\b(\w{1,4})\b[ ,.]*)(?:\1\b[ ,.]*){3,}", "", text, flags=re.I).strip()
        if text.lower() in ALUCINACIONES or "amara.org" in text.lower():
            return ""
        return text
