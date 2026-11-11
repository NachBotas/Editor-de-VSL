"""Subtítulos simples en la parte de abajo (ASS para quemar + SRT para plataformas)."""
from __future__ import annotations

from pathlib import Path

from .config import Config
from .cutplan import Mapa, norm
from .efectos import es_clave


def _hex_ass(rgb: str) -> str:
    rgb = rgb.lstrip("#")
    r, g, b = rgb[0:2], rgb[2:4], rgb[4:6]
    return f"&H00{b}{g}{r}&".upper()


def _limpiar(w: str, mayus: bool) -> str:
    w = w.replace("{", "(").replace("}", ")").replace("\\", "")
    return w.upper() if mayus else w


def construir_cues(palabras: list[dict], mapa: Mapa, cfg: Config) -> list[dict]:
    claves = {norm(k) for k in cfg.palabras_clave}
    vivas = []
    for w in palabras:
        if not w["keep"]:
            continue
        r = mapa.palabra(w)
        if r:
            vivas.append((w, r[0], r[1]))

    cues: list[dict] = []
    cur: list[tuple] = []

    def cerrar():
        if cur:
            cues.append({"s": cur[0][1], "e": cur[-1][2], "palabras": [
                {"w": x[0]["w"], "clave": es_clave(x[0], claves), "s": x[1], "e": x[2]} for x in cur]})

    for item in vivas:
        w, s, e = item
        if cur:
            chars = sum(len(x[0]["w"]) + 1 for x in cur) + len(w["w"])
            hueco = s - cur[-1][2]
            fin_prev = cur[-1][0]["w"].rstrip().endswith((".", "?", "!", "…", ":"))
            coma_prev = cur[-1][0]["w"].rstrip().endswith((",", ";")) and len(cur) >= 3
            if (len(cur) >= cfg.sub_max_palabras or chars > cfg.sub_max_caracteres
                    or hueco > 0.45 or fin_prev or coma_prev):
                cerrar()
                cur = []
        cur.append(item)
    cerrar()

    # Ajustar tiempos: sin solapes, duración mínima legible
    for a, b in zip(cues, cues[1:]):
        a["e"] = min(max(a["e"] + 0.12, a["s"] + 0.5), b["s"])
    if cues:
        cues[-1]["e"] = min(cues[-1]["e"] + 0.4, mapa.duracion)
    return cues


def _texto_cue(c: dict, cfg: Config, ass: bool) -> str:
    partes = []
    color = _hex_ass(cfg.sub_color_resaltado)
    for p in c["palabras"]:
        t = _limpiar(p["w"], cfg.sub_mayusculas)
        # Subtítulo limpio: sin puntos ni comas al final (se mantienen ¿? ¡!)
        t = t.rstrip(".,;:…") if t.rstrip(".,;:…") else t
        if ass and p["clave"]:
            t = f"{{\\c{color}}}{t}{{\\c&H00FFFFFF&}}"
        partes.append(t)
    return " ".join(partes)


def _t_ass(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _t_srt(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def escribir_ass(cues: list[dict], path: Path, w: int, h: int, cfg: Config) -> None:
    size = int(round(min(h * 0.052, w * 0.068)))
    margen_v = int(round(h * (0.075 if h >= w else 0.07)))
    if h > w * 1.3:      # vertical: subir para no chocar con la UI de reels/tiktok
        margen_v = int(round(h * 0.22))
    margen_h = int(round(w * 0.08))
    outline = max(2, round(size * 0.075))
    if cfg.sub_estilo == "caja":
        estilo = (f"Style: Default,Inter,{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
                  f"-1,0,0,0,100,100,0,0,3,{max(6, size // 5)},0,2,{margen_h},{margen_h},{margen_v},1")
    else:
        estilo = (f"Style: Default,Inter,{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,"
                  f"-1,0,0,0,100,100,0,0,1,{outline},{max(1, outline // 2)},2,{margen_h},{margen_h},{margen_v},1")
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{estilo}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    if cfg.sub_estilo == "pop":
        anim = r"{\fad(40,0)\fscx88\fscy88\t(0,110,\fscx100\fscy100)}"
    else:
        anim = r"{\fad(60,40)}"
    lineas = [f"Dialogue: 0,{_t_ass(c['s'])},{_t_ass(c['e'])},Default,,0,0,0,,{anim}{_texto_cue(c, cfg, True)}"
              for c in cues]
    path.write_text(cab + "\n".join(lineas) + "\n", encoding="utf-8")


def escribir_srt(cues: list[dict], path: Path, cfg: Config) -> None:
    bloques = [f"{i}\n{_t_srt(c['s'])} --> {_t_srt(c['e'])}\n{_texto_cue(c, cfg, False)}\n"
               for i, c in enumerate(cues, 1)]
    path.write_text("\n".join(bloques), encoding="utf-8")
