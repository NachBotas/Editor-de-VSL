# Editor de VSL automático

Edita Video Sales Letters de forma automática y profesional:

- ✂️ **Cortes inteligentes**: elimina silencios, muletillas (eh, mmm, este…), tartamudeos
  ("que que") y **tomas repetidas** (cuando te equivocas y repites la frase se queda la última toma).
- 🎙️ **Audio limpio**: quita zumbido eléctrico, ruido de fondo, ecualiza la voz, de-esser,
  compresión y normaliza a -16 LUFS (estándar para web/redes).
- 🎨 **Color**: presets `natural`, `calido`, `frio`, `cine`, `punch` o tu propio LUT `.cube`.
- 🎬 **Animaciones**: zooms punch-in en los cortes (disimulan los jump cuts) y zoom de énfasis
  en palabras clave, fundido de entrada/salida.
- 🔊 **Efectos de sonido**: whoosh en los zooms, pop/cash en palabras clave y números, y los
  que quieras añadir a mano (impacto, ding, riser…).
- 💬 **Subtítulos simples abajo**, con las palabras clave resaltadas, + archivo `.srt`.
- Funciona en horizontal (16:9) y vertical (9:16).

## Instalación

```bash
./setup.sh
```

## Uso

```bash
# Todo en un paso
python -m vsl_editor editar entrada/mi_vsl.mp4

# Flujo profesional: analizar → revisar → preview → final
python -m vsl_editor analizar entrada/mi_vsl.mp4 --modelo medium
cat trabajo/mi_vsl/informe.md            # qué se va a cortar y guion final
python -m vsl_editor restaurar trabajo/mi_vsl --desde 81.2 --hasta 84.0   # recuperar algo
python -m vsl_editor quitar trabajo/mi_vsl --desde 120 --hasta 131.5      # cortar algo más
python -m vsl_editor sfx-agregar trabajo/mi_vsl --t 245.3 --sfx impacto   # efecto manual
python -m vsl_editor render trabajo/mi_vsl --preview   # 720p rápido para revisar
python -m vsl_editor render trabajo/mi_vsl             # final → salida/mi_vsl_editado.mp4
```

Ver todas las opciones: `python -m vsl_editor editar --help` (también resumidas en `CLAUDE.md`).
