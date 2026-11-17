# Interview Copilot

Escucha al entrevistador (el audio que suena en tu PC), lo transcribe localmente y Claude
te sugiere qué responder en tiempo real, con **puntos clave** y un **guion** para leer.

- Transcripción: faster-whisper (`small`, CPU, local y gratis)
- Respuestas: Claude Code en modo headless con **tu sesión de claude.ai** (sin API key)
- Interfaz: http://127.0.0.1:8000

## Primer uso

1. Asegúrate de haber iniciado sesión en Claude Code al menos una vez:
   abre una terminal, escribe `claude`, inicia sesión con tu cuenta y sal con `/exit`.
2. Llena la carpeta `perfil/`:
   - `cv.md` (o pon tu CV como `cv.pdf` y borra `cv.md`)
   - `puesto.md` con la oferta de trabajo
   - `notas.md` (opcional) con historias, pretensión salarial, etc.
   Los archivos que empiecen con `_` se ignoran.
3. Doble clic en **`iniciar.bat`**. La primera vez instala dependencias y descarga Whisper (~500 MB).

## Durante la entrevista

1. **Usa audífonos.** Así el micrófono no capta al entrevistador y la app escucha la
   salida de audio predeterminada de Windows (donde suena Zoom / Meet / Teams).
2. Pulsa **▶ Escuchar** antes de que empiece la llamada.
3. Cuando el entrevistador termina una pregunta (~1 s de silencio), aparece la respuesta.
   - Si Claude decide que algo no era pregunta, lo ignora. Haz **clic en la frase** de la
     transcripción para forzar una respuesta.
   - También puedes **escribir** una pregunta abajo.
4. Desactiva **Auto-responder** si prefieres elegir tú qué responder (gasta menos cupo).

## Practicar con un simulacro

Antes de una entrevista real puedes ensayar con una entrevista simulada que la voz de Windows lee en voz alta:

1. Genera el audio (tarda unos segundos):
   ```powershell
   powershell -ExecutionPolicy Bypass -File simulacro\generar_audio.ps1
   ```
2. Abre la app, pulsa **▶ Escuchar** y reproduce `simulacro\simulacro_fullstack.wav`.
   Tras cada pregunta hay 18 s de silencio para que leas la sugerencia y respondas en voz alta.

Para practicar con las preguntas de tu vacante, copia `simulacro/preguntas_fullstack.txt`
(p. ej. a `preguntas_mi_vacante.txt`), edítalo y genera el audio con
`-Preguntas preguntas_mi_vacante.txt`. Cada línea es `INTRO|texto` (transición del entrevistador)
o `P|texto` (pregunta, seguida de la pausa). Con `-PausaPregunta 30` tienes más tiempo para responder.

## Ajustes (`backend/config.py`)

| Ajuste | Para qué |
|---|---|
| `WHISPER_MODEL` | `base` si va lento, `medium` si transcribe mal y tienes paciencia |
| `SILENCE_MS` | Súbelo (1200) si corta las preguntas a la mitad; bájalo para más rapidez |
| `CLAUDE_MODEL` | `sonnet` (rápido) u `opus` (mejor calidad, más lento y gasta más cupo) |

Si cambias el perfil con la app abierta, pulsa **↻ Perfil**.

## Problemas comunes

- **No aparece transcripción:** revisa que el audio de la llamada salga por el dispositivo
  predeterminado de Windows (el nombre aparece al pasar el mouse sobre "● Escuchando").
- **Claude no responde:** mira `logs/claude_stderr.log`. Normalmente es que no has iniciado sesión
  con `claude` o se agotó el cupo de tu plan.
