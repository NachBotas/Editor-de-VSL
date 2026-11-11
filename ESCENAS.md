# Slides explicativas — formato de `escenas.json`

Las slides se superponen al presentador en los tramos indicados, con fondo blanco,
texto + emojis + dibujos (flechas, subrayados, tachados) que **aparecen cuando se dice
la palabra**. Durante una slide se ocultan los subtítulos (el texto ya está en pantalla).

Archivo: `trabajo/VIDEO/escenas.json`. Los tiempos son del **video ORIGINAL**
(los de `transcripcion.json`); también vale `"w123"` = palabra nº 123. El editor los
convierte solo al video ya cortado.

## Marcado de texto (en cualquier campo de texto)

| Marca | Efecto |
|---|---|
| `**palabra**` | negrita |
| `__palabra__` | negrita + subrayado rojo a mano que se dibuja solo |
| `~~palabra~~` | tachado rojo que se dibuja solo |
| `==palabra==` | negrita verde (positivo) |
| `!!palabra!!` | negrita roja (negativo) |

## Tipos de escena

```jsonc
{"estilo": {"push_in": 1.035, "entrada": 1.06, "sfx": true},
 "escenas": [
  // Frase clave: emoji grande + frase + nota manuscrita
  {"tipo": "frase", "desde": 12.3, "hasta": 15.0, "emoji": "👨‍⚕️",
   "titulo": "opcional, gris, arriba",
   "texto": "Cobra __como un médico__", "texto_en": 12.5, "subrayado_en": 13.4,
   "nota": "Sin experiencia previa.", "nota_en": 14.2},

  // Lista que se construye ítem a ítem
  {"tipo": "lista", "desde": 16, "hasta": 21, "titulo": "Todo sin:",
   "items": [{"icono": "🙅", "texto": "**Mostrar** tu cara", "en": 16.8},
             {"icono": "🎥", "texto": "**Crear** contenido", "en": 18.0}]},

  // Flujo con flechas que se dibujan (A → B → C)
  {"tipo": "flujo", "desde": 30, "hasta": 35, "titulo": "opcional", "curva": 0.0,
   "nodos": [{"emoji": "🧑‍💻", "texto": "Creador", "en": 30.2},
             {"emoji": "📦", "texto": "Producto", "en": 31.5},
             {"emoji": "💰", "texto": "**Dinero**", "en": 33.0}]},

  // Cifra con contador animado y subrayado
  {"tipo": "cifra", "desde": 40, "hasta": 44, "emoji": "💰", "antes": "1.000 × $25.000 =",
   "valor": "$25.000.000", "valor_en": 41.2, "contar": true, "nota": "al año"},

  // Pasos numerados 1-2-3
  {"tipo": "pasos", "desde": 50, "hasta": 56, "titulo": "El sistema en **3 pasos**",
   "pasos": [{"emoji": "🔍", "texto": "**Encontrar**", "en": 50.5},
             {"emoji": "🛠️", "texto": "**Construir**", "en": 52.0},
             {"emoji": "🚀", "texto": "**Lanzar**", "en": 53.6}]},

  // Comparación: lo malo (rojo, ❌) vs lo bueno (verde, ✅)
  {"tipo": "comparacion", "desde": 60, "hasta": 68,
   "izq": {"titulo": "Dropshipping", "en": 60.2, "items": ["Inversión alta", "Meses de pruebas"]},
   "der": {"titulo": "Nuestro método", "en": 63.0, "items": [{"texto": "**$0** de inversión", "en": 64}]}},

  // Imagen o captura (ruta relativa a la carpeta de trabajo) con pie
  {"tipo": "imagen", "desde": 70, "hasta": 74, "archivo": "captura_ventas.png",
   "texto": "**$6.000** en una semana"}
 ]}
```

## Zooms manuales (gráficos, pantallas, encuadres)

```jsonc
"zooms": [
  // encuadre base de una grabación de pantalla: quita dock y barras, conserva la burbuja
  {"desde": 129.6, "hasta": 187.2, "nivel": 1.18, "cx": 0.424, "cy": 0.424},
  // acercamiento a la zona que se está explicando (cx, cy = punto del cuadro, 0–1)
  {"desde": 133.5, "hasta": 139.3, "nivel": 1.75, "cx": 0.42, "cy": 0.47}
]
```

Opciones de cada zoom: `"bn": true` (blanco y negro con contraste, para frases de tensión),
`"sfx": "Woosh"` y `"db": -15` (efecto al entrar el zoom).

Los zooms manuales quedan por encima de los automáticos; las slides, por encima de todo.

## Efectos de sonido de las slides

Cada aparición lleva su efecto (≈1 por segundo). Se usan los efectos de `assets/sfx_usuario/`
(el pack del usuario) y, si falta alguno, los sintetizados. Se puede cambiar el mapa en `estilo`:

```jsonc
"estilo": {"sfx_mapa": {"entrada": ["Woosh", -15], "item": ["Finger Snap", -15],
                        "tach": ["Flicker Text-Animation", -6], "positivo": ["Sun Shine", -16]}}
```

Roles: `entrada`, `entrada_grande` (escena con `"grande": true`), `emoji`, `item`, `tach`, `ul`,
`flecha`, `contar` (riser que culmina al terminar de contar), `aterriza`, `positivo`
(escena con `"positivo": true`).

## Emojis

Se usan los emojis de **Apple (iPhone)** en 160 px (`herramientas/instalar_emojis_apple.sh`, lo
corre `setup.sh`). Algunos emojis nuevos solo existen en 64 px: elegir alternativas que estén en
160 px (`python -c "from vsl_editor.slides import _apple; print(_apple('🧠').size)"`).

Cualquier escena admite `"omitir": true` para desactivarla sin borrarla.

## Criterios de diseño (aprendidos del VSL de referencia)

1. **Una idea por slide**, 3–15 palabras. La slide resume; no transcribe.
2. **Negrita solo en 1–3 palabras** y un único subrayado rojo en la promesa o la cifra.
3. **Cada elemento aparece cuando se dice** (`en` = inicio de esa palabra).
4. Listas y flujos **se construyen** ítem a ítem: crean expectativa.
5. Volver al presentador cada ~20–40 s (gancho, historia, emoción y llamada a la acción a cámara).
6. Números → `cifra` con contador. Procesos → `flujo` o `pasos`. Antes/después → `comparacion`.
7. Corregir en el texto de la slide los errores de transcripción.

## Comandos

```bash
python -m vsl_editor escenas-auto trabajo/VIDEO [--cobertura 0.5]   # borrador automático
python -m vsl_editor escenas-preview trabajo/VIDEO                   # estado final de cada slide
python -m vsl_editor escenas-preview trabajo/VIDEO --n 3             # 5 momentos de la slide 3
python -m vsl_editor render trabajo/VIDEO --preview
python -m vsl_editor render trabajo/VIDEO --sin-slides               # sin slides
```
