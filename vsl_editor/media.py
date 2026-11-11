"""Utilidades de ffmpeg/ffprobe."""
from __future__ import annotations

import json
import re
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np


def run(cmd: list[str], quiet: bool = True, cwd: str | Path | None = None) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, capture_output=quiet, text=True, cwd=cwd)
    if res.returncode != 0:
        err = (res.stderr or "")[-3000:] if quiet else ""
        raise RuntimeError(f"Falló: {' '.join(map(str, cmd[:6]))} ...\n{err}")
    return res


def ffmpeg_major() -> int:
    out = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout
    m = re.search(r"ffmpeg version n?(\d+)", out)
    return int(m.group(1)) if m else 6


def probe(path: str | Path) -> dict:
    out = run([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", str(path),
    ]).stdout
    data = json.loads(out)
    v = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    if v is None:
        raise RuntimeError("El archivo no tiene pista de video")
    if a is None:
        raise RuntimeError("El archivo no tiene pista de audio")

    def frac(s: str | None) -> Fraction | None:
        try:
            f = Fraction(s)
            return f if f > 0 else None
        except Exception:
            return None

    fps = frac(v.get("avg_frame_rate")) or frac(v.get("r_frame_rate")) or Fraction(30)
    if fps > 120:  # timebases raros de algunos móviles
        fps = frac(v.get("r_frame_rate")) or Fraction(30)
    fps = _fps_estandar(fps)

    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    rot = int(v.get("tags", {}).get("rotate", rot))
    if abs(rot) % 180 == 90:
        w, h = h, w

    dur = float(data["format"].get("duration") or v.get("duration") or 0)
    return {"fps": fps, "fps_str": f"{fps.numerator}/{fps.denominator}",
            "width": w, "height": h, "duration": dur}


def _fps_estandar(fps: Fraction) -> Fraction:
    """Redondea a fps estándar si está muy cerca (VFR de móviles da 29.97x)."""
    estandar = [Fraction(24000, 1001), Fraction(24), Fraction(25), Fraction(30000, 1001),
                Fraction(30), Fraction(50), Fraction(60000, 1001), Fraction(60)]
    mejor = min(estandar, key=lambda s: abs(float(s) - float(fps)))
    return mejor if abs(float(mejor) - float(fps)) < 0.6 else fps.limit_denominator(1001)


def extraer_audio(src: str | Path, dst: str | Path, sr: int = 48000) -> None:
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1",
         "-ar", str(sr), "-c:a", "pcm_f32le", str(dst)])


def leer_audio(path: str | Path, sr: int = 48000) -> np.ndarray:
    """Decodifica cualquier audio a float32 mono con ffmpeg."""
    res = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le",
                          "-ac", "1", "-ar", str(sr), "-"], capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.decode(errors="ignore")[-2000:])
    return np.frombuffer(res.stdout, dtype=np.float32).copy()


def escapar_filtro(p: str | Path) -> str:
    """Escapa una ruta para usarla como valor dentro de un filtergraph."""
    s = str(p).replace("\\", "/")
    return "'" + s.replace("'", r"'\''").replace(":", r"\:") + "'"


def ts(seg: float) -> str:
    m, s = divmod(max(seg, 0), 60)
    return f"{int(m):02d}:{s:05.2f}"
