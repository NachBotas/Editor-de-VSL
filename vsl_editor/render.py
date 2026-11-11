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


RAMPA = 0.6   # segundos que tarda un zoom en entrar/salir


def _estado_auto(nivel: float, cy_auto: float) -> tuple[float, float, float]:
    """Zoom automático: centrado en x; en y conserva la cara arriba (misma posición que antes)."""
    cy = cy_auto * (1 - 1 / nivel) + 1 / (2 * nivel)
    return (nivel, 0.5, cy)


def curva_zoom(plan_fx: dict, cfg: Config, fps: float, dur: float) -> str | None:
    """Construye un filtro `perspective` con zoom continuo.

    Prioridad: manuales > énfasis > automáticos. Cada cambio de estado (nivel, cx, cy) se
    interpola con smoothstep en RAMPA s (o 1 fotograma si el zoom manual pide "suave": false).
    """
    tramos = []   # (s, e, prio, estado, suave)
    for z in plan_fx.get("zooms", []):
        tramos.append((z["s"], z["e"], 1, _estado_auto(z["nivel"], cfg.zoom_centro_y), True))
    for z in plan_fx.get("enfasis", []):
        tramos.append((z["s"], z["e"], 2, _estado_auto(z["nivel"], cfg.zoom_centro_y), True))
    for z in plan_fx.get("manuales", []):
        if z.get("nivel", 1) > 1.0:
            tramos.append((z["s"], z["e"], 3, (z["nivel"], z.get("cx", 0.5), z.get("cy", 0.5)),
                           z.get("suave", True)))
    if not tramos:
        return None
    base = (1.0, 0.5, 0.5)
    puntos = sorted({0.0, dur} | {t for a, b, *_ in tramos for t in (a, b) if 0 <= t <= dur})

    def estado(t):
        act = [(p, a, est, sv) for a, b, p, est, sv in tramos if a <= t < b]
        if not act:
            return base, True
        p, a, est, sv = max(act, key=lambda x: (x[0], x[1]))
        return est, sv

    # tramos constantes
    seg = []
    for a, b in zip(puntos, puntos[1:]):
        if b - a < 1e-6:
            continue
        est, sv = estado((a + b) / 2)
        if seg and seg[-1][2] == est:
            seg[-1][1] = b
        else:
            seg.append([a, b, est, sv])
    # keyframes con rampa al inicio de cada tramo
    kf = [(0.0, seg[0][2])]
    for k in range(1, len(seg)):
        a, b, est, sv = seg[k]
        _, _, est_prev, sv_prev = seg[k - 1]
        suave = sv and sv_prev   # un zoom manual con "suave": false entra y sale de golpe
        r = min(RAMPA, 0.8 * (b - a)) if suave else 1.0 / fps
        t0 = max(a, kf[-1][0])
        kf.append((t0, kf[-1][1]))
        kf.append((t0 + r, est))

    def expr(idx: int) -> str:
        terms = []
        for (ta, ea), (tb, eb) in zip(kf, kf[1:]):
            va, vb = ea[idx], eb[idx]
            if tb - ta < 1e-6:
                continue
            if abs(va - vb) < 1e-6:
                terms.append(f"gte(T,{ta:.4f})*lt(T,{tb:.4f})*{va:.5f}")
            else:
                u = f"(T-{ta:.4f})/{tb - ta:.4f}"
                terms.append(f"gte(T,{ta:.4f})*lt(T,{tb:.4f})*({va:.5f}+({vb - va:.5f})*({u})*({u})*(3-2*({u})))")
        terms.append(f"gte(T,{kf[-1][0]:.4f})*{kf[-1][1][idx]:.5f}")
        return "+".join(terms)

    Z, CX, CY = (expr(i) for i in range(3))
    pre = f"st(1,in/{fps:.6f});st(0,{Z.replace('T', 'ld(1)')});st(2,{CX.replace('T', 'ld(1)')});" \
          f"st(3,{CY.replace('T', 'ld(1)')});"
    L = "clip(ld(2)*W-W/(2*ld(0)),0,W-W/ld(0))"
    A = "clip(ld(3)*H-H/(2*ld(0)),0,H-H/ld(0))"
    R, B = f"({L}+W/ld(0))", f"({A}+H/ld(0))"
    c = {"x0": L, "y0": A, "x1": R, "y1": A, "x2": L, "y2": B, "x3": R, "y3": B}
    return "perspective=" + ":".join(f"{k}='{pre}{v}'" for k, v in c.items()) + \
        ":interpolation=cubic:eval=frame"


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

    actual = "v0"
    # Zooms FLUIDOS: una sola curva continua (nivel + centro) que entra y sale con easing.
    persp = curva_zoom(plan_fx, cfg, fps, dur)
    if persp:
        lineas.append(f"[{actual}]{persp},setsar=1[vz]")
        actual = "vz"
    # Blanco y negro (tensión) sobre la imagen ya ampliada, con fundido corto
    bn = [(z["s"], z["e"]) for z in plan_fx.get("manuales", []) if z.get("bn")]
    if bn:
        lineas.append(f"[{actual}]split=2[bn0][bn1]")
        lineas.append("[bn1]hue=s=0,eq=contrast=1.18:brightness=-0.02[bn2]")
        en = _expr_intervalos(bn, eps)
        lineas.append(f"[bn0][bn2]overlay=0:0:enable='{en}'[vbn]")
        actual = "vbn"

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
