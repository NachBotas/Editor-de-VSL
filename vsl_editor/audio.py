"""Limpieza de voz, montaje del audio cortado, efectos, música y loudness."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import soundfile as sf

from .config import RNNOISE_MODEL, Config
from .media import escapar_filtro, leer_audio, run

SR = 48000


def analizar_ruido(y: np.ndarray) -> dict:
    """Detecta zumbido eléctrico (50/60 Hz) y el piso de ruido en las pausas."""
    win = int(0.05 * SR)
    n = len(y) // win
    if n < 10:
        return {"hum": None, "piso": None}
    rms = np.sqrt(np.mean(y[: n * win].reshape(n, win) ** 2, axis=1)) + 1e-9
    umbral = np.percentile(rms, 15)
    quietos = np.where(rms <= umbral * 1.5)[0]
    piso = float(np.median(rms[quietos]))
    # espectro de los tramos silenciosos
    trozos = [y[k * win:(k + 1) * win] for k in quietos[:400]]
    hum = None
    if trozos:
        seg = np.concatenate(trozos)
        X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
        fr = np.fft.rfftfreq(len(seg), 1 / SR)

        def energia(f):
            return sum(X[(fr > h * f - 3) & (fr < h * f + 3)].sum() for h in (1, 2, 3))

        def fondo(f):
            return sum(X[(fr > h * f + 8) & (fr < h * f + 20)].mean() * 6 for h in (1, 2, 3)) + 1e-12

        mejores = {f: energia(f) / fondo(f) for f in (50, 60)}
        f0 = max(mejores, key=mejores.get)
        if mejores[f0] > 8:
            hum = f0
    return {"hum": hum, "piso": piso}


def _cadena_voz(nivel: str, ruido: dict | None = None) -> str:
    rnn = escapar_filtro(RNNOISE_MODEL)
    ruido = ruido or {}
    notch = []
    if ruido.get("hum"):
        f0 = ruido["hum"]
        notch = [f"bandreject=f={f0 * h}:t=q:w={8 if h == 1 else 12}" for h in range(1, 7)]
    comun_eq = [
        "equalizer=f=120:t=q:w=1.0:g=1.0",     # cuerpo
        "equalizer=f=300:t=q:w=1.2:g=-2.5",    # quitar barro / sala
        "equalizer=f=3800:t=q:w=1.0:g=2.0",    # presencia / inteligibilidad
        "treble=g=1.5:f=9000",                  # aire
    ]
    if nivel == "suave":
        filtros = [*notch, "highpass=f=70", f"arnndn=m={rnn}:mix=0.6", *comun_eq[1:3],
                   "acompressor=threshold=0.1:ratio=2.5:attack=10:release=150:makeup=1.3"]
    elif nivel == "fuerte":
        filtros = [*notch, "highpass=f=85", "highpass=f=85", "lowpass=f=15000", f"arnndn=m={rnn}:mix=1.0",
                   "afftdn=nr=12:nf=-42:tn=1", *comun_eq,
                   "deesser=i=0.45:m=0.5:f=0.5:s=o",
                   "acompressor=threshold=0.07:ratio=3.5:attack=6:release=100:makeup=1.8"]
    else:  # estandar
        filtros = [*notch, "highpass=f=75", "highpass=f=75", f"arnndn=m={rnn}:mix=0.85",
                   "afftdn=nr=6:nf=-45:tn=1", *comun_eq,
                   "deesser=i=0.35:m=0.5:f=0.5:s=o",
                   "acompressor=threshold=0.089:ratio=3:attack=8:release=120:makeup=1.5"]
    piso = ruido.get("piso")
    if piso and nivel != "suave":
        # Expansor suave: baja el ruido residual en las pausas sin cortar colas de palabras
        filtros.append(f"agate=threshold={min(0.05, piso * 4):.5f}:ratio=2:range=0.3"
                       f":attack=3:release=180:knee=4")
    filtros.append("alimiter=limit=0.95:level=disabled")
    return ",".join(filtros)


def limpiar_voz(raw_wav: Path, out_wav: Path, nivel: str) -> None:
    if nivel == "ninguna":
        run(["ffmpeg", "-y", "-v", "error", "-i", str(raw_wav), "-c:a", "pcm_f32le", str(out_wav)])
        return
    src = raw_wav
    if nivel == "fuerte":
        import noisereduce as nr
        y = leer_audio(raw_wav, SR)
        y = nr.reduce_noise(y=y, sr=SR, stationary=True, prop_decrease=0.75, n_jobs=-1)
        src = out_wav.with_name("pre_nr.wav")
        sf.write(src, y.astype(np.float32), SR, subtype="FLOAT")
    ruido = analizar_ruido(leer_audio(src, SR))
    if ruido["hum"]:
        print(f"  · zumbido eléctrico detectado a {ruido['hum']} Hz → filtrado")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af", _cadena_voz(nivel, ruido),
         "-ar", str(SR), "-ac", "1", "-c:a", "pcm_f32le", str(out_wav)])


def cortar(y: np.ndarray, segs: list[dict], fade_ms: float = 6.0) -> np.ndarray:
    """Concatena los segmentos con micro-fundidos para que no haya clics."""
    nf = int(SR * fade_ms / 1000)
    rampa = np.linspace(0, 1, nf, dtype=np.float32)
    trozos = []
    for g in segs:
        a = int(round(g["s"] * SR))
        b = int(round(g["e"] * SR))
        largo = b - a
        t = np.zeros(largo, dtype=np.float32)
        disp = y[a:min(b, len(y))]
        t[:len(disp)] = disp
        if largo > 2 * nf:
            t[:nf] *= rampa
            t[-nf:] *= rampa[::-1]
        trozos.append(t)
    return np.concatenate(trozos) if trozos else np.zeros(0, np.float32)


def a_lufs(y: np.ndarray, objetivo: float) -> np.ndarray:
    import pyloudnorm as pyln
    if len(y) < SR:
        return y
    medido = pyln.Meter(SR).integrated_loudness(y.astype(np.float64))
    if not np.isfinite(medido):
        return y
    return (y * 10 ** ((objetivo - medido) / 20)).astype(np.float32)


def mezclar_sfx(y: np.ndarray, eventos: list[dict], biblioteca: dict[str, np.ndarray],
                extra_db: float = 0.0) -> np.ndarray:
    out = y.copy()
    for ev in eventos:
        clip = biblioteca.get(ev["sfx"])
        if clip is None:
            continue
        # "ancla": segundos dentro del clip que deben caer en t (p.ej. el pico del whoosh)
        from .sfx import ANCLAS
        inicio = int(round((ev["t"] - ev.get("ancla", ANCLAS.get(ev["sfx"], 0.0))) * SR))
        g = 10 ** ((ev.get("db", -18) + extra_db) / 20)
        c = clip * g
        if inicio < 0:
            c, inicio = c[-inicio:], 0
        fin = min(len(out), inicio + len(c))
        if fin > inicio:
            out[inicio:fin] += c[:fin - inicio]
    return out


def mezclar_musica(voz: np.ndarray, ruta: str, db: float) -> np.ndarray:
    from . import musica
    if ruta in musica.ESTILOS:     # música generada por síntesis, del largo exacto
        print(f"  · componiendo música '{ruta}' ({len(voz) / SR:.0f}s)")
        m = musica.generar(len(voz) / SR, ruta)
    else:
        m = leer_audio(ruta, SR)
    if len(m) == 0:
        return voz
    reps = int(np.ceil(len(voz) / len(m)))
    m = np.tile(m, reps)[:len(voz)]
    m = a_lufs(m, -16.0)
    # Ducking: baja la música cuando hay voz (envolvente RMS suavizada)
    win = int(0.05 * SR)
    env = np.sqrt(np.convolve(voz ** 2, np.ones(win) / win, mode="same"))
    habla = (env > 0.01).astype(np.float32)
    suav = int(0.3 * SR)
    habla = np.convolve(habla, np.ones(suav) / suav, mode="same")
    ganancia = 10 ** ((db + (1 - np.clip(habla, 0, 1)) * 6) / 20)  # +6 dB en pausas
    m = m * ganancia
    # fundidos
    fi, fo = int(1.0 * SR), int(2.5 * SR)
    m[:fi] *= np.linspace(0, 1, min(fi, len(m)))
    m[-fo:] *= np.linspace(1, 0, min(fo, len(m)))
    return voz + m.astype(np.float32)


def loudnorm_final(in_wav: Path, out_wav: Path, lufs: float) -> None:
    """Normalización EBU R128 en dos pasadas + true peak -1.5 dB, salida estéreo."""
    base = f"loudnorm=I={lufs}:TP=-1.5:LRA=11"
    res = run(["ffmpeg", "-hide_banner", "-i", str(in_wav), "-af", base + ":print_format=json",
               "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", res.stderr, re.S)
    filtro = base
    if m:
        d = json.loads(m.group(0))
        filtro = (f"{base}:measured_I={d['input_i']}:measured_TP={d['input_tp']}"
                  f":measured_LRA={d['input_lra']}:measured_thresh={d['input_thresh']}"
                  f":offset={d['target_offset']}:linear=true")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(in_wav), "-af", filtro, "-ar", str(SR),
         "-ac", "2", "-c:a", "pcm_s16le", str(out_wav)])


def construir_audio(clean_wav: Path, segs: list[dict], eventos: list[dict],
                    biblioteca: dict, cfg: Config, trabajo: Path) -> Path:
    y = leer_audio(clean_wav, SR)
    voz = cortar(y, segs)
    voz = a_lufs(voz, cfg.lufs)
    mezcla = mezclar_sfx(voz, eventos, biblioteca, cfg.sfx_db) if cfg.sfx else voz
    if cfg.musica:
        mezcla = mezclar_musica(mezcla, cfg.musica, cfg.musica_db)
    pico = float(np.max(np.abs(mezcla))) if len(mezcla) else 1.0
    if pico > 0.99:
        mezcla = mezcla / pico * 0.99
    tmp = trabajo / "mezcla.wav"
    sf.write(tmp, mezcla.astype(np.float32), SR, subtype="FLOAT")
    final = trabajo / "audio_final.wav"
    loudnorm_final(tmp, final, cfg.lufs)
    return final
