# Editor de VSL — instrucciones para Claude

En este repositorio Claude actúa como **editor profesional de VSL** (Video Sales Letters).
Responde siempre en español. El objetivo de cada edición: un video ágil, sin errores,
sin silencios muertos, con audio limpio y subtítulos legibles, que retenga al espectador
hasta la llamada a la acción.

## Puesta en marcha (cada sesión nueva)

```bash
./setup.sh
```

Instala ffmpeg, faster-whisper, limpieza de audio, fuentes y genera los SFX.

## Cómo conseguir el video

1. Archivo subido a la sesión → copiarlo a `entrada/`.
2. Enlace de Google Drive → `gdown --fuzzy "<enlace>" -O entrada/` (o el conector de Google Drive).
3. Otros enlaces (Dropbox, YouTube, Vimeo, URL directa) → `yt-dlp -o "entrada/%(title)s.%(ext)s" "<enlace>"` o `curl -L`.

## Flujo de trabajo de edición (seguirlo siempre)

1. **Analizar**: `python -m vsl_editor analizar entrada/VIDEO.mp4 [opciones]`
   - Usa `--modelo medium` (o `large-v3` si hay GPU/tiempo) para videos importantes:
     transcribe mejor y detecta mejor las repeticiones.
2. **Revisar el plan con criterio de editor** (este es el paso que marca la diferencia):
   - Leer `trabajo/VIDEO/informe.md`: tabla de fragmentos eliminados + guion final.
   - Leer el guion final como lo haría el espectador. Comprobar:
     - ¿Se eliminó algo que era intencional (repetición retórica, énfasis "nunca, nunca")?
       → `python -m vsl_editor restaurar trabajo/VIDEO --desde S --hasta E`
     - ¿Quedó alguna toma mala, frase a medias, divagación o error de contenido que
       los detectores no vieron? → `python -m vsl_editor quitar trabajo/VIDEO --desde S --hasta E`
       (los tiempos son del video ORIGINAL; buscarlos en `trabajo/VIDEO/transcripcion.json`).
     - Si hay dos tomas de la misma frase, se conserva la ÚLTIMA. Si la primera era mejor,
       restaurar la primera y quitar la segunda.
   - Momentos clave (precio, garantía, revelación, CTA) → reforzar con SFX:
     `python -m vsl_editor sfx-agregar trabajo/VIDEO --t 123.4 --sfx impacto --db -14`
3. **Diseñar las slides explicativas** (lo más importante del estilo VSL — ver `ESCENAS.md`):
   - Leer el guion final y decidir qué ideas se ilustran con slide (fondo blanco, emoji,
     flechas, subrayados, cifras con contador, listas que se construyen) y qué tramos van
     a cámara (gancho, historia, emoción, CTA).
   - Escribir `trabajo/VIDEO/escenas.json` A MANO con criterio (se puede partir de
     `python -m vsl_editor escenas-auto trabajo/VIDEO`, pero el borrador es literal y elige
     emojis genéricos: reescribir los textos como resúmenes cortos y elegir emojis concretos).
   - Cada elemento con `"en"` = segundo exacto en que se dice esa palabra (`transcripcion.json`).
   - Revisar con `python -m vsl_editor escenas-preview trabajo/VIDEO` (Read de la imagen).
4. **Preview rápida**: `python -m vsl_editor render trabajo/VIDEO --preview`
   - Revisar `trabajo/VIDEO/capturas.jpg` (mosaico) y extraer fotogramas concretos con
     `ffmpeg -ss T -i salida/VIDEO_preview.mp4 -frames:v 1 f.jpg` para verlos (Read).
   - Comprobar que los subtítulos no tapan nada importante, que el zoom no corta la cabeza
     (ajustar `--zoom-centro-y`), que el color se ve natural.
5. **Render final**: `python -m vsl_editor render trabajo/VIDEO` → `salida/VIDEO_editado.mp4`
   (+ `.srt` para subir a plataformas).
6. **Entregar**: resumir al usuario duración antes/después, qué se cortó, decisiones tomadas
   y enlazar el archivo. Si el usuario lo quiere en Drive, subirlo con el conector.

## Opciones útiles

| Necesidad | Opción |
|---|---|
| Más ritmo / menos pausas | `--ritmo rapido` (o `--pausa-max 0.25`) |
| Más natural, conversacional | `--ritmo relajado` |
| Ruido fuerte (ventilador, calle, eco) | `--audio fuerte` |
| Audio ya limpio de estudio | `--audio suave` |
| Look de color | `--color natural|calido|frio|cine|punch|ninguno`, o `--lut archivo.cube` |
| Grano/ruido de cámara | `--denoise-video` |
| Subtítulos | `--sub-estilo simple|pop|caja`, `--mayusculas`, `--sin-subs` |
| Palabras resaltadas | `--claves "curso,mentoría,97 dólares"` |
| Zoom | `--sin-zoom`, `--zoom-nivel 1.1`, `--zoom-centro-y 0.35` |
| SFX | `--sin-sfx`, `--sfx-cortes` (whoosh suave en cada corte) |
| Música de fondo con ducking | `--musica ruta.mp3 --musica-db -24` |
| Detección de tomas más/menos agresiva | `--umbral-toma 70` (más) / `90` (menos) |
| Transcripción más precisa | `--modelo medium` + `--retranscribir` |

Las opciones de `analizar` se guardan en `plan.json` y las usa `render`. A `render` se le
pueden pasar opciones nuevas para cambiarlas sin re-transcribir.

## Arquitectura (vsl_editor/)

- `transcribe.py` — faster-whisper con timestamps por palabra (prompt con muletillas para que no las "limpie").
- `cutplan.py` — detecta muletillas, tartamudeos ("que que"), tomas repetidas (se queda la última),
  frases de retoma ("perdón", "otra vez"), y construye segmentos alineados a fotogramas.
- `audio.py` — limpieza de voz (detección de zumbido 50/60 Hz, RNNoise, denoise FFT, EQ de voz,
  de-esser, compresor, expansor), montaje con micro-fundidos, SFX, música con ducking, loudnorm -16 LUFS.
- `efectos.py` — zooms punch-in alternos en los cortes, zoom de énfasis en palabras clave, presets de color.
- `subtitulos.py` — subtítulos ASS abajo (palabras clave en color) + SRT.
- `sfx.py` — biblioteca de efectos sintetizados (whoosh, pop, click, ding, cash, impacto, riser...).
  Se pueden añadir .wav propios en `assets/sfx/` y usarlos por nombre.
- `slides.py` — motor de slides: diseños (frase, lista, flujo, cifra, pasos, comparación, imagen),
  texto con marcado, trazos a mano, animaciones (pop, dibujo de trazos, contador, push-in).
- `escenas.py` — carga `escenas.json`, convierte tiempos al video editado, SFX de slides, borrador automático.
- `render.py` — un único pase de ffmpeg (select + color + overlays de zoom + ass + fades).

Carpetas `entrada/`, `salida/` y `trabajo/` no se suben a git (videos pesados).
