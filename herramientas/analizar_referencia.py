"""Análisis fotograma a fotograma de un video de referencia (para copiar su estilo de edición).

Uso:
    python herramientas/analizar_referencia.py entrada/ref/ref.mp4 trabajo/ref_analisis

Genera en la carpeta de salida:
    frames.csv   — métricas de CADA fotograma (luz, color, diferencia, escala/zoom, movimiento)
    planos.json  — planos detectados entre cortes, con tipo, duración, zoom y animación
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np

W, H = 320, 180


def metricas(video: Path, out: Path) -> list[dict]:
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    prev_g = prev_hist = None
    filas = []
    i = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        sm = cv2.resize(fr, (W, H), interpolation=cv2.INTER_AREA)
        g = cv2.cvtColor(sm, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(sm, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [16, 8, 8], [0, 180, 0, 256, 0, 256])
        cv2.normalize(hist, hist)
        f = {
            "i": i, "t": round(i / fps, 3),
            "luz": round(float(g.mean()), 2),
            "sat": round(float(hsv[..., 1].mean()), 2),
            "blanco": round(float((g > 235).mean()), 4),
            "negro": round(float((g < 30).mean()), 4),
            "dif": 0.0, "hist": 0.0, "escala": 1.0, "dx": 0.0, "dy": 0.0, "pix_cambio": 0.0,
        }
        if prev_g is not None:
            d = cv2.absdiff(g, prev_g)
            f["dif"] = round(float(d.mean()), 3)
            f["pix_cambio"] = round(float((d > 20).mean()), 4)
            f["hist"] = round(float(1 - cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)), 4)
            # Movimiento global (zoom / paneo) con flujo óptico de puntos
            pts = cv2.goodFeaturesToTrack(prev_g, 150, 0.01, 6)
            if pts is not None and len(pts) >= 12 and f["hist"] < 0.3:
                nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev_g, g, pts, None)
                a, b = pts[st == 1], nxt[st == 1]
                if len(a) >= 12:
                    M, inl = cv2.estimateAffinePartial2D(a, b, ransacReprojThreshold=1.0)
                    if M is not None and inl is not None and inl.mean() > 0.5:
                        f["escala"] = round(float(np.hypot(M[0, 0], M[1, 0])), 5)
                        f["dx"] = round(float(M[0, 2]), 3)
                        f["dy"] = round(float(M[1, 2]), 3)
        filas.append(f)
        prev_g, prev_hist = g, hist
        i += 1
        if i % 2500 == 0:
            print(f"  {i}/{total} fotogramas", flush=True)
    cap.release()
    with open(out / "frames.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        wr.writeheader()
        wr.writerows(filas)
    return filas


def planos(filas: list[dict], fps: float) -> list[dict]:
    # Corte duro: cambio grande de histograma o de píxeles en un solo fotograma
    cortes = [0]
    for f in filas[1:]:
        if (f["hist"] > 0.25 and f["pix_cambio"] > 0.15) or f["pix_cambio"] > 0.55:
            if f["i"] - cortes[-1] >= 3:
                cortes.append(f["i"])
    cortes.append(len(filas))
    out = []
    for a, b in zip(cortes, cortes[1:]):
        seg = filas[a:b]
        blanco = np.mean([x["blanco"] for x in seg])
        negro = np.mean([x["negro"] for x in seg])
        luz = np.mean([x["luz"] for x in seg])
        esc = np.prod([x["escala"] for x in seg[1:]]) if len(seg) > 1 else 1.0
        activos = sum(1 for x in seg[1:] if x["pix_cambio"] > 0.002)
        eventos = 0   # "apariciones" de elementos: ráfagas de cambio separadas por quietud
        en = False
        for x in seg[1:]:
            if x["pix_cambio"] > 0.004 and not en:
                eventos += 1
                en = True
            elif x["pix_cambio"] < 0.0005:
                en = False
        tipo = "slide" if blanco > 0.45 else ("camara" if luz < 110 else "imagen/otro")
        out.append({
            "ini": round(a / fps, 3), "fin": round(b / fps, 3), "dur": round((b - a) / fps, 3),
            "tipo": tipo, "blanco": round(float(blanco), 3), "negro": round(float(negro), 3),
            "luz": round(float(luz), 1), "zoom_total": round(float(esc), 4),
            "zoom_por_seg": round(float(esc ** (fps / max(1, len(seg) - 1))), 5),
            "pct_frames_con_movimiento": round(activos / max(1, len(seg) - 1), 3),
            "animaciones": eventos,
        })
    return out


def main():
    video, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    cap.release()
    filas = metricas(video, out)
    ps = planos(filas, fps)
    (out / "planos.json").write_text(json.dumps(ps, indent=1), encoding="utf-8")
    print(f"✔ {len(filas)} fotogramas, {len(ps)} planos → {out}")


if __name__ == "__main__":
    main()
