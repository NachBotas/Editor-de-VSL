"""Render final con ffmpeg: cortes + color + zooms + subtítulos + audio mezclado."""
from __future__ import annotations

from pathlib import Path

from .config import FONTS_DIR, Config
from .efectos import cadena_color
from .media import escapar_filtro, ffmpeg_major, run


def _expr_intervalos(intervalos: list[tuple[float, float]], eps: float) -> str:
    if not intervalos:
        return "0"
    return "+".join(f"gte(t,{a - eps:.4f})*lt(t,{b - eps:.4f})" for a, b in intervalos)


def construir_grafo(segs: list[dict], info: dict, plan_fx: dict, cfg: Config,
                    ass_path: Path | None, slides_int: list[tuple[float, float]] | None = None) -> str:
    fps = float(info["fps"])
    eps = 0.5 / fps
    W, H = info["width"], info["height"]
    dur = segs[-1]["oe"]
    lineas = []

    sel = _expr_intervalos([(g["s"], g["e"]) for g in segs], eps)
    cadena = [f"setpts=PTS-STARTPTS", f"fps={info['fps_str']}", f"select='{sel}'",
              "setpts=N/FRAME_RATE/TB", f"scale={W}:{H}:flags=lanczos", "setsar=1",
              "format=yuv420p"]
    cadena += cadena_color(cfg)
    lineas.append(f"[0:v]{','.join(cadena)}[v0]")

    # Zooms: una rama por nivel, superpuesta solo en sus intervalos
    capas: list[tuple[float, list[tuple[float, float]]]] = []
    niveles: dict[float, list] = {}
    for z in plan_fx.get("zooms", []) + plan_fx.get("enfasis", []):
        niveles.setdefault(round(z["nivel"], 3), []).append((z["s"], z["e"]))
    for nivel in sorted(niveles):      # el nivel más alto queda encima
        if nivel > 1.0:
            capas.append((nivel, niveles[nivel]))

    actual = "v0"
    if capas:
        n = len(capas) + 1
        salidas = "".join(f"[b{k}]" for k in range(n))
        lineas.append(f"[{actual}]split={n}{salidas}")
        actual = "b0"
        cy = cfg.zoom_centro_y
        for k, (nivel, ints) in enumerate(capas, 1):
            cw = int(round(W / nivel / 2)) * 2
            ch = int(round(H / nivel / 2)) * 2
            lineas.append(f"[b{k}]crop={cw}:{ch}:(iw-{cw})/2:(ih-{ch})*{cy},"
                          f"scale={W}:{H}:flags=lanczos,setsar=1[z{k}]")
            en = _expr_intervalos(ints, eps)
            lineas.append(f"[{actual}][z{k}]overlay=0:0:enable='{en}'[o{k}]")
            actual = f"o{k}"

    if slides_int:
        # Pista de slides (entrada 2) por encima del presentador en sus intervalos
        lineas.append(f"[2:v]setpts=PTS-STARTPTS,fps={info['fps_str']},scale={W}:{H},setsar=1,"
                      f"format=yuv420p[sl]")
        en = _expr_intervalos(slides_int, eps)
        lineas.append(f"[{actual}][sl]overlay=0:0:enable='{en}':eof_action=pass[os]")
        actual = "os"

    final = []
    if ass_path is not None:
        final.append(f"ass={escapar_filtro(ass_path)}:fontsdir={escapar_filtro(FONTS_DIR)}")
    if cfg.fundido:
        final.append("fade=t=in:st=0:d=0.25")
        final.append(f"fade=t=out:st={max(0, dur - 0.5):.3f}:d=0.5")
    if cfg.preview:
        final.append("scale=-2:'min(720,ih)'")
    final.append("format=yuv420p")
    lineas.append(f"[{actual}]{','.join(final)}[vout]")
    return ";\n".join(lineas)


def renderizar(src: Path, audio: Path, salida: Path, segs: list[dict], info: dict,
               plan_fx: dict, cfg: Config, ass_path: Path | None, trabajo: Path,
               slides: tuple[Path, list] | None = None) -> None:
    grafo = construir_grafo(segs, info, plan_fx, cfg, ass_path, slides[1] if slides else None)
    entrada_slides = ["-f", "concat", "-safe", "0", "-i", str(slides[0])] if slides else []
    script = trabajo / "grafo.txt"
    script.write_text(grafo, encoding="utf-8")
    flag = ["-/filter_complex", str(script)] if ffmpeg_major() >= 7 else ["-filter_complex_script", str(script)]
    preset = "veryfast" if cfg.preview else cfg.preset
    crf = 26 if cfg.preview else cfg.crf
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stats", "-stats_period", "5",
           "-i", str(src), "-i", str(audio), *entrada_slides, *flag,
           "-map", "[vout]", "-map", "1:a",
           "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-profile:v", "high",
           "-pix_fmt", "yuv420p", "-r", info["fps_str"],
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-movflags", "+faststart", "-shortest", str(salida)]
    run(cmd, quiet=False)


def capturas(video: Path, salida: Path, n: int = 12, ancho: int = 480) -> None:
    """Hoja de contacto (mosaico) para revisar visualmente el resultado."""
    from .media import probe
    d = probe(video)["duration"]
    paso = max(d / (n + 1), 0.1)
    cols = 4
    filas = (n + cols - 1) // cols
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vf",
         f"fps=1/{paso:.3f},scale={ancho}:-2,tile={cols}x{filas}:padding=4:margin=4",
         "-frames:v", "1", str(salida)])
