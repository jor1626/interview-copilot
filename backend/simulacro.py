"""Simulacros de entrevista: convierte una lista de preguntas escrita por el usuario al formato de
simulacro/preguntas_<nombre>.txt y genera simulacro_<nombre>.wav con simulacro/generar_audio.ps1."""
import re
import subprocess
import unicodedata

import config

SCRIPT = config.SIMULACRO_DIR / "generar_audio.ps1"

# "1." "1)" "1-" "1:" "a)" "*" "-" "•" "·" "–" al inicio de la línea
_VINETA = re.compile(r"^\s*(?:\d{1,3}\s*[.)\-:]|[a-zA-Z]\)|[*\-•·–])\s*")
_INTRO = re.compile(r"^\s*>\s*")

SALUDO = ("Hola, buenos días. Muchas gracias por sacar el tiempo para esta entrevista. "
          "La idea hoy es conocerte un poco y hacerte algunas preguntas sobre tu experiencia.")
DESPEDIDA = "Perfecto, muchas gracias por tu tiempo. Te estaremos contactando en los próximos días."


def slug(nombre: str) -> str:
    t = unicodedata.normalize("NFD", nombre or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:40].strip("-") or "mi-simulacro"


def _rutas(s: str):
    return config.SIMULACRO_DIR / f"preguntas_{s}.txt", config.SIMULACRO_DIR / f"simulacro_{s}.wav"


def parsear(texto: str, saludo: bool = True) -> list[tuple[str, str]]:
    """Texto libre -> [("INTRO"|"P", frase)].
    - Cada viñeta o número inicia una pregunta; las líneas sin viñeta continúan la anterior.
      Si no hay ninguna viñeta, cada línea es una pregunta.
    - Las líneas que empiezan con '>' son frases del entrevistador sin pausa (transiciones).
    - Acepta también el formato del archivo (INTRO|... / P|...)."""
    lineas = [l.rstrip() for l in (texto or "").splitlines() if l.strip()]
    hay_vinetas = any(_VINETA.match(l) for l in lineas)
    items: list[list[str]] = []
    for l in lineas:
        if l.startswith(("INTRO|", "P|")):
            tipo, frase = l.split("|", 1)
            items.append([tipo, frase.strip()])
        elif _INTRO.match(l):
            items.append(["INTRO", _INTRO.sub("", l).strip()])
        elif _VINETA.match(l) or not hay_vinetas or not items:
            items.append(["P", _VINETA.sub("", l).strip()])
        else:
            items[-1][1] += " " + l.strip()  # continuación de la pregunta anterior
    items = [i for i in items if i[1]]
    if saludo and items and not any(t == "INTRO" for t, _ in items):
        items = [["INTRO", SALUDO], *items, ["INTRO", DESPEDIDA]]
    return [(t, f.replace("\n", " ")) for t, f in items]


def a_texto(items: list[tuple[str, str]]) -> str:
    """Formato del archivo -> texto editable en la app (numerado, '>' para transiciones)."""
    out, n = [], 0
    for tipo, frase in items:
        if tipo == "P":
            n += 1
            out.append(f"{n}. {frase}")
        else:
            out.append(f"> {frase}")
    return "\n".join(out)


def _leer(txt) -> list[tuple[str, str]]:
    items = []
    for l in txt.read_text(encoding="utf-8-sig").splitlines():
        if "|" in l:
            tipo, frase = l.split("|", 1)
            items.append(("P" if tipo.strip() == "P" else "INTRO", frase.strip()))
    return items


def _info(s: str) -> dict:
    txt, wav = _rutas(s)
    items = _leer(txt)
    return {"id": s, "preguntas": sum(t == "P" for t, _ in items),
            "txt": txt.name, "audio": f"/simulacro/{wav.name}?v={int(wav.stat().st_mtime)}" if wav.exists() else None,
            "actualizado": txt.stat().st_mtime}


def listar() -> list[dict]:
    ids = [p.stem.removeprefix("preguntas_") for p in config.SIMULACRO_DIR.glob("preguntas_*.txt")]
    return sorted((_info(s) for s in ids), key=lambda i: i["actualizado"], reverse=True)


def obtener(s: str) -> dict:
    txt, _ = _rutas(slug(s))
    if not txt.exists():
        raise FileNotFoundError("No existe ese simulacro.")
    return {**_info(slug(s)), "texto": a_texto(_leer(txt))}


def guardar_y_generar(nombre: str, texto: str, pausa: int = 18, saludo: bool = True) -> dict:
    """Escribe el .txt y genera el .wav (tarda de segundos a un par de minutos)."""
    items = parsear(texto, saludo)
    if not any(t == "P" for t, _ in items):
        raise ValueError("Escribe al menos una pregunta.")
    s = slug(nombre)
    txt, _ = _rutas(s)
    config.SIMULACRO_DIR.mkdir(exist_ok=True)
    txt.write_text("\n".join(f"{t}|{f}" for t, f in items) + "\n", encoding="utf-8")

    pausa = max(3, min(int(pausa), 120))
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
             "-Preguntas", txt.name, "-PausaPregunta", str(pausa)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("La generación del audio tardó demasiado.") from e
    if proc.returncode != 0:
        raise RuntimeError(f"No pude generar el audio: {(proc.stderr or proc.stdout).strip()[-400:]}")
    return obtener(s)


def eliminar(s: str) -> None:
    for p in _rutas(slug(s)):
        p.unlink(missing_ok=True)
