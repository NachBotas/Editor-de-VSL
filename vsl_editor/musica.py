"""Música de fondo generada por síntesis (sin derechos de autor, del largo exacto del video).

Estilos:
    mistica     — pad ambiental afinado a 528 Hz ("solfeggio"), dron grave y campanitas
                  cristalinas con reverberación amplia. Calma, apertura, "elevar la frecuencia".
    mistica432  — igual pero afinado a 432 Hz (más grave y cálido).
"""
from __future__ import annotations

import numpy as np
from scipy import signal

SR = 48000
ESTILOS = {"mistica": 528.0, "mistica432": 432.0}


def _reverb(x: np.ndarray, segundos: float = 5.0, mezcla: float = 0.55, semilla: int = 3) -> np.ndarray:
    """Reverb por convolución con una respuesta de sala sintética (ruido con decaimiento)."""
    rng = np.random.default_rng(semilla)
    n = int(SR * segundos)
    t = np.arange(n) / SR
    ir = rng.standard_normal(n) * np.exp(-t * 6.9 / segundos)
    b, a = signal.butter(2, 6000, fs=SR)          # sala "oscura"
    ir = signal.lfilter(b, a, ir)
    ir[: int(0.02 * SR)] *= np.linspace(0, 1, int(0.02 * SR))
    ir /= np.sqrt(np.sum(ir ** 2))
    mojado = signal.fftconvolve(x, ir)[: len(x)]
    return (1 - mezcla) * x + mezcla * mojado * 3


def _env(n: int, ataque: float, caida: float) -> np.ndarray:
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(ataque, 1e-3)) * np.minimum(1, (n / SR - t) / max(caida, 1e-3))
    return np.clip(e, 0, 1) ** 1.5


def _voz_pad(f: float, n: int, rng) -> np.ndarray:
    """Una nota de pad: varias senoidales levemente desafinadas + armónicos suaves (coro)."""
    t = np.arange(n) / SR
    x = np.zeros(n)
    for det in (-0.35, 0.0, 0.4):
        fase = rng.uniform(0, 2 * np.pi)
        ff = f * 2 ** (det / 1200 * 10)
        vib = 1 + 0.0015 * np.sin(2 * np.pi * rng.uniform(0.08, 0.2) * t)
        ph = 2 * np.pi * np.cumsum(ff * vib) / SR + fase
        x += np.sin(ph) + 0.25 * np.sin(2 * ph) + 0.08 * np.sin(3 * ph)
    return x / 3


def generar(duracion: float, estilo: str = "mistica", semilla: int = 7) -> np.ndarray:
    base = ESTILOS.get(estilo, 528.0)
    rng = np.random.default_rng(semilla)
    n = int(duracion * SR) + SR
    out = np.zeros(n)

    # Tónica una octava abajo de la frecuencia "sagrada" (528 -> 264 Hz) para que no moleste a la voz
    r = base / 2
    st = lambda k: r * 2 ** (k / 12)   # semitonos
    # Progresión lenta y luminosa (I - vi - IV - V add9), cada acorde ~8 s con fundido cruzado
    acordes = [
        [0, 7, 12, 16, 19], [-3, 4, 9, 12, 16], [-7, 0, 5, 9, 14], [-5, 2, 7, 11, 14],
    ]
    dur_ac = 8.0
    k = 0
    t0 = 0.0
    while t0 < duracion + 2:
        notas = acordes[k % len(acordes)]
        largo = int((dur_ac + 4) * SR)
        a = int(t0 * SR)
        seg = sum(_voz_pad(st(s), largo, rng) * (0.9 if s < 10 else 0.55) for s in notas)
        seg *= _env(largo, 3.5, 4.0)
        fin = min(n, a + largo)
        out[a:fin] += seg[: fin - a]
        t0 += dur_ac
        k += 1
    b, a_ = signal.butter(2, 4500, fs=SR)    # pad suave, sin agudos que tapen la voz
    out = signal.lfilter(b, a_, out)

    # Dron grave continuo (tónica y quinta, dos octavas abajo) con respiración lenta
    t = np.arange(n) / SR
    respira = 0.75 + 0.25 * np.sin(2 * np.pi * t / 14)
    dron = (np.sin(2 * np.pi * r / 2 * t) + 0.5 * np.sin(2 * np.pi * r * 0.75 * t)) * respira
    out += 0.22 * dron

    # Campanitas cristalinas (pentatónica, muy espaciadas)
    penta = [12, 14, 16, 19, 21, 24, 26, 28]
    tc = rng.uniform(1.5, 4.0)
    while tc < duracion:
        f = st(rng.choice(penta)) * 2
        largo = int(3.5 * SR)
        tt = np.arange(largo) / SR
        cam = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * f * 2.76 * tt)) * np.exp(-tt * 1.6)
        cam[: int(0.004 * SR)] *= np.linspace(0, 1, int(0.004 * SR))
        a = int(tc * SR)
        fin = min(n, a + largo)
        out[a:fin] += 1.1 * cam[: fin - a] * rng.uniform(0.5, 1.0)
        tc += rng.uniform(2.5, 6.0)

    out = _reverb(out, 5.0, 0.6)
    # Shimmer: capa muy suave una octava arriba, solo reverberada
    shimmer = _reverb(out, 7.0, 1.0, semilla=9)
    b, a_ = signal.butter(2, [1500, 7000], btype="band", fs=SR)
    out += 0.9 * signal.lfilter(b, a_, shimmer)

    out = out[: int(duracion * SR)]
    fi, fo = int(2.0 * SR), int(3.0 * SR)
    out[:fi] *= np.linspace(0, 1, fi)
    out[-fo:] *= np.linspace(1, 0, fo)
    return (out / (np.max(np.abs(out)) + 1e-9) * 0.8).astype(np.float32)
