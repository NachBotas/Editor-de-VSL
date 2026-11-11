"""Editor automático de VSL.

Uso rápido:
    python -m vsl_editor editar entrada/video.mp4
    python -m vsl_editor analizar entrada/video.mp4     # solo plan + informe, sin render
    python -m vsl_editor render trabajo/video           # renderiza el plan (tras revisarlo)
    python -m vsl_editor quitar trabajo/video --desde 12.3 --hasta 15.8
    python -m vsl_editor restaurar trabajo/video --desde 12.3 --hasta 15.8
    python -m vsl_editor sfx-agregar trabajo/video --t 33.2 --sfx impacto
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from fractions import Fraction
from pathlib import Path

from . import audio as A
from .config import ROOT, Config
from .cutplan import Mapa, construir_segmentos, marcar
from .efectos import planificar
from .media import extraer_audio, probe, ts
from .render import capturas, renderizar
from .sfx import cargar_biblioteca, generar_biblioteca
from .subtitulos import construir_cues, escribir_ass, escribir_srt
from .transcribe import transcribir


CAMPOS_CORTE = {"quitar_muletillas", "quitar_repeticiones", "quitar_tomas_falsas", "umbral_toma"}


def _dir_trabajo(src: Path) -> Path:
    d = ROOT / "trabajo" / src.stem
    d.mkdir(parents=True, exist_ok=True)
    return d


def _guardar_plan(d: Path, plan: dict) -> None:
    info = dict(plan["info"])
    info["fps"] = str(info["fps"])
    datos = {**plan, "info": info}
    (d / "plan.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def _cargar_plan(d: Path) -> dict:
    plan = json.loads((d / "plan.json").read_text(encoding="utf-8"))
    plan["info"]["fps"] = Fraction(plan["info"]["fps"])
    return plan


# ------------------------------------------------------------------ pasos

def analizar(src: Path, cfg: Config, retranscribir: bool = False) -> Path:
    t0 = time.time()
    d = _dir_trabajo(src)
    info = probe(src)
    print(f"▶ {src.name}: {info['width']}x{info['height']} @ {float(info['fps']):.3f} fps, "
          f"{ts(info['duration'])}")

    raw = d / "audio_original.wav"
    if not raw.exists() or retranscribir:
        print("▶ Extrayendo audio")
        extraer_audio(src, raw)

    tr = d / "transcripcion.json"
    if tr.exists() and not retranscribir:
        palabras = json.loads(tr.read_text(encoding="utf-8"))
        print(f"▶ Transcripción en caché ({len(palabras)} palabras)")
    else:
        print("▶ Transcribiendo")
        palabras = transcribir(raw, cfg.modelo, cfg.idioma)
        tr.write_text(json.dumps(palabras, ensure_ascii=False), encoding="utf-8")

    print("▶ Detectando repeticiones, tomas falsas, muletillas y silencios")
    plan_prev = _cargar_plan(d) if (d / "plan.json").exists() else None
    if plan_prev and not retranscribir:
        # conservar decisiones manuales previas
        manual = {w["i"]: w for w in plan_prev["palabras"] if w.get("manual")}
        for i, w in manual.items():
            if i < len(palabras):
                palabras[i].update(keep=w["keep"], motivo=w["motivo"], manual=True)
    marcar(palabras, cfg)
    plan = {
        "fuente": str(src.resolve()),
        "info": info,
        "config": {**cfg.to_dict(), "preview": False},
        "palabras": palabras,
        "cortes_extra": plan_prev.get("cortes_extra", []) if plan_prev else [],
        "sfx_manual": plan_prev.get("sfx_manual", []) if plan_prev else [],
    }
    _guardar_plan(d, plan)
    _informe(d, plan)
    print(f"✔ Análisis listo en {time.time() - t0:.0f}s → {d.relative_to(ROOT)}/informe.md")
    return d


def _calcular(plan: dict, cfg: Config):
    info = plan["info"]
    segs = construir_segmentos(plan["palabras"], info["duration"], float(info["fps"]), cfg,
                               plan.get("cortes_extra"))
    mapa = Mapa(segs)
    fx = planificar(plan["palabras"], segs, mapa, cfg, plan.get("sfx_manual"))
    return segs, mapa, fx


def _informe(d: Path, plan: dict) -> None:
    cfg = Config.from_dict(plan["config"])
    segs, mapa, fx = _calcular(plan, cfg)
    ws = plan["palabras"]
    dur0 = plan["info"]["duration"]
    dur1 = mapa.duracion
    # Agrupar palabras quitadas consecutivas
    grupos = []
    for w in ws:
        if w["keep"]:
            continue
        if grupos and grupos[-1]["motivo"] == w["motivo"] and w["i"] == grupos[-1]["fin_i"] + 1:
            grupos[-1]["texto"] += " " + w["w"]
            grupos[-1]["fin_i"] = w["i"]
            grupos[-1]["e"] = w["e"]
        else:
            grupos.append({"motivo": w["motivo"], "texto": w["w"], "s": w["s"], "e": w["e"], "fin_i": w["i"]})
    cont: dict[str, int] = {}
    for g in grupos:
        cont[g["motivo"]] = cont.get(g["motivo"], 0) + 1
    silencios = sum(1 for g in segs if g["corte"] == "silencio")

    L = [f"# Informe de edición — {Path(plan['fuente']).name}", "",
         f"- Duración original: **{ts(dur0)}** → editada: **{ts(dur1)}** "
         f"({100 * (1 - dur1 / max(dur0, 0.01)):.0f}% más corto)",
         f"- Segmentos conservados: {len(segs)} · cortes por silencio: {silencios}",
         *[f"- {k}: {v}" for k, v in sorted(cont.items())],
         f"- Zooms punch-in: {len(fx['zooms'])} · zooms de énfasis: {len(fx['enfasis'])} · "
         f"efectos de sonido: {len(fx['eventos'])}", "",
         "## Fragmentos eliminados (tiempo del video ORIGINAL)", "",
         "Para recuperar alguno: `python -m vsl_editor restaurar "
         f"trabajo/{d.name} --desde S --hasta E`", "",
         "| Tiempo | Motivo | Texto |", "|---|---|---|"]
    for g in grupos:
        L.append(f"| {g['s']:.2f}–{g['e']:.2f} | {g['motivo']} | {g['texto']} |")
    L += ["", "## Guion final (lo que queda)", ""]
    frase = []
    for w in ws:
        if w["keep"]:
            frase.append(w["w"])
    L.append(" ".join(frase))
    L += ["", "## Efectos de sonido (tiempo del video EDITADO)", ""]
    L += [f"- {ts(e['t'])} {e['sfx']} ({e['db']} dB)" for e in fx["eventos"]] or ["- (ninguno)"]
    (d / "informe.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def render(d: Path, cfg_override: dict | None = None, salida: Path | None = None) -> Path:
    t0 = time.time()
    d = d.resolve()
    plan = _cargar_plan(d)
    cfg = Config.from_dict({**plan["config"], **(cfg_override or {})})
    # Si cambió la config de cortes, re-marcar respetando decisiones manuales
    cfg_override = dict(cfg_override or {})
    preview = cfg_override.pop("preview", False)
    if cfg_override:
        if CAMPOS_CORTE & cfg_override.keys():
            marcar(plan["palabras"], cfg)
        plan["config"] = {**cfg.to_dict(), "preview": False}
        _guardar_plan(d, plan)
        _informe(d, plan)
    cfg.preview = bool(preview)
    src = Path(plan["fuente"])
    info = plan["info"]
    segs, mapa, fx = _calcular(plan, cfg)
    if not segs:
        raise SystemExit("No hay nada que renderizar (¿todas las palabras eliminadas?)")

    print("▶ Limpiando voz" + f" ({cfg.limpieza_audio})")
    limpio = d / f"voz_limpia_{cfg.limpieza_audio}.wav"
    if not limpio.exists():
        A.limpiar_voz(d / "audio_original.wav", limpio, cfg.limpieza_audio)

    print("▶ Montando audio (cortes + SFX" + (" + música" if cfg.musica else "") + " + loudness)")
    audio_final = A.construir_audio(limpio, segs, fx["eventos"], cargar_biblioteca(), cfg, d)

    ass = None
    if cfg.subtitulos:
        print("▶ Subtítulos")
        cues = construir_cues(plan["palabras"], mapa, cfg)
        ass = d / "subtitulos.ass"
        escribir_ass(cues, ass, info["width"], info["height"], cfg)
        escribir_srt(cues, d / "subtitulos.srt", cfg)

    if salida is None:
        sufijo = "_preview" if cfg.preview else "_editado"
        salida = ROOT / "salida" / f"{src.stem}{sufijo}.mp4"
    salida.parent.mkdir(parents=True, exist_ok=True)
    print(f"▶ Renderizando video ({len(segs)} segmentos, {ts(mapa.duracion)})")
    renderizar(src, audio_final, salida, segs, info, fx, cfg, ass, d)
    if cfg.subtitulos:
        shutil.copy(d / "subtitulos.srt", salida.with_suffix(".srt"))
    try:
        capturas(salida, d / "capturas.jpg")
    except Exception as e:  # no crítico
        print(f"  (no se pudo generar la hoja de capturas: {e})")
    print(f"✔ Listo en {time.time() - t0:.0f}s → {salida}")
    return salida


def _rango(d: Path, desde: float, hasta: float, keep: bool) -> None:
    d = d.resolve()
    plan = _cargar_plan(d)
    n = 0
    for w in plan["palabras"]:
        if w["s"] >= desde - 0.05 and w["e"] <= hasta + 0.05:
            w.update(keep=keep, motivo=None if keep else "manual", manual=True)
            n += 1
    if not keep:
        plan.setdefault("cortes_extra", []).append([desde, hasta])
    else:
        plan["cortes_extra"] = [c for c in plan.get("cortes_extra", [])
                                if c[1] <= desde or c[0] >= hasta]
    _guardar_plan(d, plan)
    _informe(d, plan)
    print(f"✔ {'Restauradas' if keep else 'Quitadas'} {n} palabras en {desde}–{hasta}s")


# ------------------------------------------------------------------ CLI

def _args_config(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("edición")
    g.add_argument("--modelo", help="modelo Whisper: tiny|base|small|medium|large-v3")
    g.add_argument("--idioma")
    g.add_argument("--ritmo", choices=["rapido", "normal", "relajado"])
    g.add_argument("--pausa-max", type=float, dest="pausa_max")
    g.add_argument("--umbral-toma", type=int, dest="umbral_toma")
    g.add_argument("--sin-muletillas", dest="quitar_muletillas", action="store_false", default=None)
    g.add_argument("--sin-repeticiones", dest="quitar_repeticiones", action="store_false", default=None)
    g.add_argument("--sin-tomas", dest="quitar_tomas_falsas", action="store_false", default=None)
    g.add_argument("--audio", dest="limpieza_audio", choices=["ninguna", "suave", "estandar", "fuerte"])
    g.add_argument("--lufs", type=float)
    g.add_argument("--musica")
    g.add_argument("--musica-db", type=float, dest="musica_db")
    g.add_argument("--color", choices=["ninguno", "natural", "calido", "frio", "cine", "punch"])
    g.add_argument("--lut")
    g.add_argument("--denoise-video", action="store_true", default=None, dest="denoise_video")
    g.add_argument("--sin-zoom", dest="zoom", action="store_false", default=None)
    g.add_argument("--zoom-nivel", type=float, dest="zoom_nivel")
    g.add_argument("--zoom-centro-y", type=float, dest="zoom_centro_y")
    g.add_argument("--sin-subs", dest="subtitulos", action="store_false", default=None)
    g.add_argument("--sub-estilo", choices=["simple", "pop", "caja"], dest="sub_estilo")
    g.add_argument("--mayusculas", action="store_true", default=None, dest="sub_mayusculas")
    g.add_argument("--sin-sfx", dest="sfx", action="store_false", default=None)
    g.add_argument("--sfx-cortes", action="store_true", default=None, dest="sfx_en_cortes")
    g.add_argument("--claves", help="palabras clave extra separadas por coma")
    g.add_argument("--preview", action="store_true", default=None, help="render rápido 720p")
    g.add_argument("--crf", type=int)


def _override(ns: argparse.Namespace, base: Config | None = None) -> dict:
    campos = Config.__dataclass_fields__
    o = {k: v for k, v in vars(ns).items() if k in campos and v is not None}
    if getattr(ns, "claves", None):
        actuales = (base or Config()).palabras_clave
        o["palabras_clave"] = list(actuales) + [c.strip() for c in ns.claves.split(",") if c.strip()]
    return o


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="vsl_editor", description="Editor automático de VSL")
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("editar", help="análisis + render en un paso")
    e.add_argument("video", type=Path)
    e.add_argument("-o", "--salida", type=Path)
    e.add_argument("--retranscribir", action="store_true")
    _args_config(e)

    a = sub.add_parser("analizar", help="transcribe y genera plan.json + informe.md")
    a.add_argument("video", type=Path)
    a.add_argument("--retranscribir", action="store_true")
    _args_config(a)

    r = sub.add_parser("render", help="renderiza un plan ya analizado")
    r.add_argument("trabajo", type=Path)
    r.add_argument("-o", "--salida", type=Path)
    _args_config(r)

    for nombre, ayuda in (("quitar", "quitar un rango (tiempo original)"),
                          ("restaurar", "recuperar un rango eliminado")):
        q = sub.add_parser(nombre, help=ayuda)
        q.add_argument("trabajo", type=Path)
        q.add_argument("--desde", type=float, required=True)
        q.add_argument("--hasta", type=float, required=True)

    s = sub.add_parser("sfx-agregar", help="añadir un efecto en un instante (tiempo original)")
    s.add_argument("trabajo", type=Path)
    s.add_argument("--t", type=float, required=True)
    s.add_argument("--sfx", required=True)
    s.add_argument("--db", type=float, default=-16)

    sub.add_parser("sfx-generar", help="(re)genera la biblioteca de efectos")

    ns = p.parse_args(argv)
    if ns.cmd in ("editar", "analizar"):
        if not ns.video.exists():
            sys.exit(f"No existe {ns.video}")
        cfg = Config.from_dict(_override(ns))
        d = analizar(ns.video, cfg, ns.retranscribir)
        if ns.cmd == "editar":
            render(d, {"preview": bool(ns.preview)}, salida=ns.salida)
    elif ns.cmd == "render":
        render(ns.trabajo, _override(ns, Config.from_dict(_cargar_plan(ns.trabajo)["config"])), ns.salida)
    elif ns.cmd in ("quitar", "restaurar"):
        _rango(ns.trabajo, ns.desde, ns.hasta, keep=(ns.cmd == "restaurar"))
    elif ns.cmd == "sfx-agregar":
        plan = _cargar_plan(ns.trabajo)
        plan.setdefault("sfx_manual", []).append({"t": ns.t, "sfx": ns.sfx, "db": ns.db})
        _guardar_plan(ns.trabajo, plan)
        _informe(ns.trabajo, plan)
        print(f"✔ Añadido {ns.sfx} en {ns.t}s")
    elif ns.cmd == "sfx-generar":
        generar_biblioteca(forzar=True)
        print("✔ Biblioteca de SFX generada en assets/sfx/")


if __name__ == "__main__":
    main()
