"""Captura el audio del sistema (lo que suena por tus parlantes/audífonos = el entrevistador)
con WASAPI loopback y lo corta en frases usando detección de voz."""
import collections
import queue
import threading

import numpy as np
import pyaudiowpatch as pyaudio
import webrtcvad

import config

TARGET_SR = 16000
FRAME_MS = 30
FRAME_SAMPLES = TARGET_SR * FRAME_MS // 1000  # 480


def find_loopback(p: pyaudio.PyAudio) -> dict:
    wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    speakers = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
    if speakers.get("isLoopbackDevice"):
        return speakers
    for lb in p.get_loopback_device_info_generator():
        if speakers["name"] in lb["name"]:
            return lb
    raise RuntimeError(
        f"No encontré un dispositivo loopback para '{speakers['name']}'. "
        "Revisa que tu salida de audio predeterminada esté activa."
    )


class LoopbackListener:
    def __init__(self, on_segment):
        self.on_segment = on_segment  # recibe np.float32 mono 16 kHz
        self.vad = webrtcvad.Vad(config.VAD_AGGRESSIVENESS)
        self.q: queue.Queue = queue.Queue()
        self.p = None
        self.stream = None
        self.thread = None
        self.device_name = ""

    # ---------- ciclo de vida ----------
    def start(self):
        self.p = pyaudio.PyAudio()
        dev = find_loopback(self.p)
        self.device_name = dev["name"]
        self.rate = int(dev["defaultSampleRate"])
        self.channels = int(dev["maxInputChannels"])
        self.stream = self.p.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.rate,
            input=True,
            input_device_index=dev["index"],
            frames_per_buffer=int(self.rate * FRAME_MS / 1000),
            stream_callback=self._callback,
        )
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def stop(self):
        try:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
            if self.p:
                self.p.terminate()
        finally:
            self.stream = self.p = None
            self.q.put(None)

    def _callback(self, in_data, frame_count, time_info, status):
        self.q.put(in_data)
        return (None, pyaudio.paContinue)

    # ---------- procesamiento ----------
    def _to_16k_mono(self, data: bytes) -> np.ndarray:
        a = np.frombuffer(data, np.int16).astype(np.float32)
        if self.channels > 1:
            a = a.reshape(-1, self.channels).mean(axis=1)
        if self.rate != TARGET_SR:
            if self.rate % TARGET_SR == 0:
                f = self.rate // TARGET_SR
                n = len(a) // f * f
                a = a[:n].reshape(-1, f).mean(axis=1)
            else:
                n_out = int(len(a) * TARGET_SR / self.rate)
                a = np.interp(np.linspace(0, len(a), n_out, endpoint=False), np.arange(len(a)), a)
        return a

    def _worker(self):
        buf = np.zeros(0, np.float32)
        pre_roll = collections.deque(maxlen=10)       # 300 ms antes de que empiece la voz
        recent = collections.deque(maxlen=5)
        segment: list[np.ndarray] = []
        in_speech = False
        silence_ms = 0
        speech_ms = 0
        max_frames = config.MAX_SEGMENT_S * 1000 // FRAME_MS

        def flush():
            nonlocal segment, in_speech, silence_ms, speech_ms
            if speech_ms >= config.MIN_SPEECH_MS and segment:
                audio = np.concatenate(segment) / 32768.0
                self.on_segment(audio.astype(np.float32))
            segment, in_speech, silence_ms, speech_ms = [], False, 0, 0
            recent.clear()

        while True:
            try:
                data = self.q.get(timeout=0.3)
            except queue.Empty:
                # Cuando no suena nada, WASAPI deja de enviar audio: contamos eso como silencio.
                if in_speech:
                    silence_ms += 300
                    if silence_ms >= config.SILENCE_MS:
                        flush()
                continue
            if data is None:
                flush()
                return

            buf = np.concatenate([buf, self._to_16k_mono(data)])
            while len(buf) >= FRAME_SAMPLES:
                frame, buf = buf[:FRAME_SAMPLES], buf[FRAME_SAMPLES:]
                pcm = np.clip(frame, -32768, 32767).astype(np.int16).tobytes()
                is_speech = self.vad.is_speech(pcm, TARGET_SR)

                if not in_speech:
                    pre_roll.append(frame)
                    recent.append(is_speech)
                    if sum(recent) >= 3:
                        in_speech = True
                        segment = list(pre_roll)
                        speech_ms = sum(recent) * FRAME_MS
                        pre_roll.clear()
                else:
                    segment.append(frame)
                    if is_speech:
                        silence_ms = 0
                        speech_ms += FRAME_MS
                    else:
                        silence_ms += FRAME_MS
                    if silence_ms >= config.SILENCE_MS or len(segment) >= max_frames:
                        flush()
