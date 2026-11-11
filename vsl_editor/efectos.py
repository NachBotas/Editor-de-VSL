"""Animaciones (zooms punch-in / énfasis), eventos de SFX y corrección de color."""
from __future__ import annotations

import re

from .config import LUTS_DIR, Config
from .cutplan import Mapa, norm
from .media import escapar_filtro
from .sfx import ANCLAS

RE_NUMERO = re.compile(r"(\d|%|\$|€|dolares|euros|pesos)")
PALABRAS_DINERO = {"dinero", "dolares", "euros", "pesos", "millones", "miles", "ganar", "ingresos", "gratis"}


def es_clave(w: dict, claves: set[str]) -> bool:
    n = w.get("n") or norm(w["w"])
    return n in claves or bool(RE_NUMERO.search(w["w"].lower()))


def planificar(palabras: list[dict], segs: list[dict], mapa: Mapa, cfg: Config,
               sfx_manual: list[dict] | None = None,
               bloqueos: list[tuple[float, float]] | None = None) -> dict:
    """Calcula zooms (en tiempo de SALIDA) y eventos de sonido."""
    claves = {norm(k) for k in cfg.palabras_clave}
    dur = mapa.duracion
    zooms: list[dict] = []     # {s, e, nivel}
    eventos: list[dict] = []   # {t, sfx, db, ancla}

    # 1) Punch-in alterno en los cortes (disimula los jump cuts)
    if cfg.zoom:
        nivel = 1.0
        ultimo = 0.0
        tramo_ini = 0.0
        for g in segs[1:]:
            t = g["os"]
            largo = g["oe"] - g["os"]
            minimo = 1.2 if g["corte"] == "quitado" else cfg.zoom_intervalo_min
            if t - ultimo >= minimo and largo >= 0.8:
                if nivel > 1.0:
                    zooms.append({"s": tramo_ini, "e": t, "nivel": nivel})
                nivel = cfg.zoom_nivel if nivel == 1.0 else 1.0
                tramo_ini, ultimo = t, t
                if cfg.sfx and cfg.sfx_en_cortes:
                    eventos.append({"t": t, "sfx": "whoosh_suave", "db": -26, "ancla": ANCLAS["whoosh_suave"]})
        if nivel > 1.0:
            zooms.append({"s": tramo_ini, "e": dur, "nivel": nivel})

    # 2) Énfasis en palabras clave: zoom fuerte + whoosh, o pop/ding si está muy seguido
    ultimo_enf = -99.0
    ultimo_sfx = -99.0
    enfasis: list[dict] = []
    for w in palabras:
        if not w["keep"] or not es_clave(w, claves):
            continue
        r = mapa.palabra(w)
        if r is None:
            continue
        s, e = r
        if bloqueos and any(a - 0.3 <= s <= b for a, b in bloqueos):
            continue   # durante una slide el énfasis lo hace la propia slide
        n = w.get("n") or norm(w["w"])
        if cfg.zoom and s - ultimo_enf >= cfg.enfasis_intervalo_min and s > 1.0:
            enfasis.append({"s": max(0, s - 0.04), "e": min(dur, e + 1.1), "nivel": cfg.zoom_enfasis})
            ultimo_enf = s
            if cfg.sfx:
                eventos.append({"t": s, "sfx": "whoosh", "db": -20, "ancla": ANCLAS["whoosh"]})
                ultimo_sfx = s
        elif cfg.sfx and s - ultimo_sfx >= 3.0:
            dinero = n in PALABRAS_DINERO or bool(RE_NUMERO.search(w["w"].lower()))
            eventos.append({"t": s, "sfx": "cash" if dinero else "pop", "db": -22 if dinero else -19})
            ultimo_sfx = s

    for ev in sfx_manual or []:
        t = mapa(ev["t"]) if ev.get("tiempo") != "salida" else ev["t"]
        if t is not None:
            eventos.append({"t": t, "sfx": ev["sfx"], "db": ev.get("db", -16),
                            "ancla": ev.get("ancla", ANCLAS.get(ev["sfx"], 0.0))})

    eventos.sort(key=lambda x: x["t"])
    return {"zooms": zooms, "enfasis": enfasis, "eventos": eventos}


# ---------------------------------------------------------------- color

COLOR = {
    "ninguno": [],
    "natural": ["eq=contrast=1.04:saturation=1.08:gamma=1.0",
                "curves=master='0/0.02 0.5/0.5 1/0.98'"],
    "calido": ["colorbalance=rs=0.03:bs=-0.03:rm=0.03:bm=-0.03:rh=0.02:bh=-0.02",
               "eq=contrast=1.06:saturation=1.10",
               "curves=master='0/0.02 0.25/0.23 0.75/0.78 1/0.98'"],
    "frio": ["colorbalance=rs=-0.02:bs=0.03:rm=-0.02:bm=0.02",
             "eq=contrast=1.06:saturation=1.0"],
    "cine": ["curves=master='0/0.04 0.25/0.21 0.75/0.80 1/0.96'",
             "colorbalance=rs=-0.04:gs=-0.01:bs=0.05:rh=0.05:gh=0.01:bh=-0.04",
             "eq=saturation=0.95:contrast=1.03"],
    "punch": ["eq=contrast=1.10:saturation=1.18:gamma=0.98", "vibrance=intensity=0.15",
              "curves=master='0/0 0.25/0.22 0.75/0.79 1/1'"],
}


def cadena_color(cfg: Config) -> list[str]:
    f: list[str] = []
    if cfg.denoise_video:
        f.append("hqdn3d=1.5:1.5:5:5")
    f += COLOR.get(cfg.color, COLOR["natural"])
    if cfg.lut:
        from pathlib import Path
        p = Path(cfg.lut)
        if not p.exists():
            p = LUTS_DIR / cfg.lut
        f.append(f"lut3d=file={escapar_filtro(p)}")
    if cfg.nitidez:
        f.append("unsharp=5:5:0.45:5:5:0.0")
    return f
