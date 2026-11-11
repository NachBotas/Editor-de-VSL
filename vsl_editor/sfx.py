"""Biblioteca de efectos de sonido sintetizados (sin licencias de terceros).

Si pones tus propios .wav/.mp3 en assets/sfx/ con el mismo nombre (whoosh.wav,
pop.wav, ...) o con nombres nuevos, se usan en su lugar / se añaden.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

from .config import SFX_DIR
from .media import leer_audio

SR = 48000
_rng = np.random.default_rng(7)

# Dónde está el "golpe" de cada sonido (segundos): se alinea con el momento del evento
ANCLAS = {"whoosh": 0.28, "whoosh_suave": 0.22, "riser": 1.45, "swoosh_inverso": 0.5}


def _t(d: float) -> np.ndarray:
    return np.arange(int(SR * d)) / SR


def _norm(x: np.ndarray, pico: float = 0.9) -> np.ndarray:
    m = np.max(np.abs(x)) or 1.0
    return (x / m * pico).astype(np.float32)


def _barrido_ruido(d: float, f0: float, f1: float, q: float = 1.2) -> np.ndarray:
    """Ruido filtrado con un pasabanda que barre de f0 a f1 (en bloques)."""
    n = int(SR * d)
    ruido = _rng.standard_normal(n)
    out = np.zeros(n)
    bloque = 512
    zi = None
    for k in range(0, n, bloque):
        frac = k / n
        fc = f0 * (f1 / f0) ** frac
        bw = fc / q
        lo, hi = max(30, fc - bw / 2), min(SR / 2 - 100, fc + bw / 2)
        b, a = signal.butter(2, [lo, hi], btype="band", fs=SR)
        if zi is None or len(zi) != max(len(a), len(b)) - 1:
            zi = signal.lfilter_zi(b, a) * 0
        out[k:k + bloque], zi = signal.lfilter(b, a, ruido[k:k + bloque], zi=zi)
    return out


def whoosh(d: float = 0.55, suave: bool = False) -> np.ndarray:
    t = _t(d)
    x = _barrido_ruido(d, 300, 4500) + 0.6 * _barrido_ruido(d, 150, 1800)
    pico = 0.5
    env = np.where(t < pico * d, (t / (pico * d)) ** 2, np.exp(-(t - pico * d) * 9))
    x = x * env
    if suave:
        b, a = signal.butter(2, 3000, fs=SR)
        x = signal.lfilter(b, a, x)
    return _norm(x, 0.7 if suave else 0.85)


def pop(d: float = 0.12) -> np.ndarray:
    t = _t(d)
    f = 900 * np.exp(-t * 30) + 250
    fase = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(fase) * np.exp(-t * 45)
    x[: int(0.002 * SR)] *= np.linspace(0, 1, int(0.002 * SR))
    return _norm(x, 0.8)


def click(d: float = 0.05) -> np.ndarray:
    t = _t(d)
    x = _rng.standard_normal(len(t)) * np.exp(-t * 300) + 0.5 * np.sin(2 * np.pi * 2200 * t) * np.exp(-t * 200)
    return _norm(x, 0.6)


def ding(d: float = 1.2) -> np.ndarray:
    t = _t(d)
    x = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * dec)
            for f, a, dec in [(1318.5, 1.0, 3.5), (2637, 0.35, 5), (3955.5, 0.15, 7), (1975.5, 0.25, 4.5)])
    x[: int(0.003 * SR)] *= np.linspace(0, 1, int(0.003 * SR))
    return _norm(x, 0.7)


def cash(d: float = 0.9) -> np.ndarray:
    """Doble campanita estilo caja registradora."""
    a = ding(0.6)
    out = np.zeros(int(SR * d), np.float32)
    out[: len(a)] += a * 0.7
    k = int(0.09 * SR)
    b = ding(0.6)
    out[k:k + len(b)] += b[: len(out) - k]
    ruido = _rng.standard_normal(int(0.05 * SR)) * np.exp(-np.arange(int(0.05 * SR)) / SR * 80)
    out[: len(ruido)] += 0.3 * ruido
    return _norm(out, 0.75)


def impacto(d: float = 0.9) -> np.ndarray:
    t = _t(d)
    f = 45 + 90 * np.exp(-t * 18)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 5)
    golpe = _rng.standard_normal(len(t)) * np.exp(-t * 40)
    b, a = signal.butter(2, 2500, fs=SR)
    golpe = signal.lfilter(b, a, golpe)
    return _norm(sub + 0.5 * golpe, 0.95)


def riser(d: float = 1.6) -> np.ndarray:
    t = _t(d)
    x = _barrido_ruido(d, 200, 8000, q=2.0)
    tono = np.sin(2 * np.pi * np.cumsum(200 * (8 ** (t / d))) / SR) * 0.3
    env = (t / d) ** 2.2
    x = (x + tono) * env
    x[-int(0.02 * SR):] *= np.linspace(1, 0, int(0.02 * SR))
    return _norm(x, 0.8)


def swoosh_inverso(d: float = 0.6) -> np.ndarray:
    return _norm(whoosh(d)[::-1].copy(), 0.8)


def tecla(d: float = 0.06) -> np.ndarray:
    t = _t(d)
    x = _rng.standard_normal(len(t)) * np.exp(-t * 160)
    b, a = signal.butter(2, [1500, 6000], btype="band", fs=SR)
    return _norm(signal.lfilter(b, a, x), 0.5)


GENERADORES = {
    "whoosh": whoosh,
    "whoosh_suave": lambda: whoosh(0.4, suave=True),
    "pop": pop,
    "click": click,
    "ding": ding,
    "cash": cash,
    "impacto": impacto,
    "riser": riser,
    "swoosh_inverso": swoosh_inverso,
    "tecla": tecla,
}


def generar_biblioteca(forzar: bool = False) -> None:
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    for nombre, gen in GENERADORES.items():
        p = SFX_DIR / f"{nombre}.wav"
        if forzar or not p.exists():
            sf.write(p, gen(), SR, subtype="PCM_16")


SFX_USUARIO = SFX_DIR.parent / "sfx_usuario"


def cargar_biblioteca() -> dict[str, np.ndarray]:
    """Efectos sintetizados + los del usuario (assets/sfx_usuario, mismo nombre = reemplaza)."""
    generar_biblioteca()
    lib: dict[str, np.ndarray] = {}
    for carpeta in (SFX_DIR, SFX_USUARIO):
        if not carpeta.exists():
            continue
        for p in sorted(carpeta.iterdir()):
            if p.suffix.lower() in {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aif", ".aiff"}:
                y = leer_audio(p, SR)
                pico = float(np.max(np.abs(y))) or 1.0
                lib[p.stem] = (y / pico * 0.9).astype(np.float32)   # todos normalizados igual
                if p.stem not in ANCLAS:
                    k = int(np.argmax(np.abs(y)))
                    ANCLAS[p.stem] = k / SR if k / SR > 0.15 else 0.0   # golpe tardío (whoosh, riser)
    return lib
