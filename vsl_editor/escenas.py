"""Carga de escenas (slides), mapeo de tiempos y borrador automático desde la transcripción."""
from __future__ import annotations

import json
import re
from bisect import bisect_right
from pathlib import Path

from .cutplan import Mapa, frases, norm
from .slides import RenderEscena, construir_escena

# Palabra (normalizada, sin acentos) -> emoji. Se usa para el borrador automático.
EMOJIS = {
    "dinero": "💰", "plata": "💰", "ganar": "💸", "ganas": "💸", "ingresos": "💸", "pagan": "💸",
    "medico": "👨‍⚕️", "doctor": "👨‍⚕️", "tiempo": "⏰", "horas": "⏰", "anos": "📅", "meses": "📅",
    "dias": "📅", "error": "❌", "errores": "❌", "problema": "⚠️", "problemas": "⚠️",
    "solucion": "✅", "metodo": "🧠", "sistema": "⚙️", "secreto": "🔐", "secretos": "🔐",
    "gratis": "🎁", "regalo": "🎁", "regalar": "🎁", "bono": "🎁", "cliente": "🤝", "clientes": "🤝",
    "socio": "🤝", "ventas": "📈", "vender": "🛒", "venta": "🛒", "negocio": "💼", "empresa": "🏢",
    "casa": "🏠", "trabajo": "💼", "jefe": "👔", "ia": "🤖", "inteligencia": "🤖", "internet": "🌐",
    "redes": "📱", "instagram": "📱", "tiktok": "📱", "youtube": "▶️", "video": "🎥", "videos": "🎥",
    "contenido": "🎬", "audiencia": "👥", "seguidores": "👥", "comunidad": "👥", "personas": "👥",
    "gente": "👥", "experiencia": "🎓", "facil": "👌", "rapido": "⚡", "garantia": "🛡️",
    "resultados": "📊", "resultado": "📊", "crecer": "🚀", "escalar": "🚀", "exito": "🏆",
    "libertad": "🕊️", "familia": "👨‍👩‍👧", "miedo": "😨", "pregunta": "🤔", "idea": "💡",
    "paso": "👣", "pasos": "👣", "curso": "📚", "aprender": "📚", "oportunidad": "🚪",
    "boton": "👇", "clic": "👆", "hoy": "📆", "ahora": "⏳", "mundo": "🌍", "banco": "🏦",
    "deuda": "💳", "deudas": "💳", "tarjeta": "💳", "plan": "📋", "estrategia": "🎯",
    "objetivo": "🎯", "meta": "🎯", "producto": "📦", "productos": "📦", "mensaje": "💬",
    "email": "📧", "llamada": "📞", "alumnos": "👨‍🎓", "alumno": "👨‍🎓", "verdad": "💯",
    "mentira": "🤥", "nadie": "🙅", "nunca": "🚫", "importante": "❗", "atencion": "👀",
    "mira": "👀", "creador": "🧑‍💻", "creadores": "🧑‍💻", "computadora": "💻", "ordenador": "💻",
    "dropshipping": "🚚", "trading": "📉", "inversion": "📈", "invertir": "📈", "riesgo": "🎲",
    "suerte": "🍀", "fracaso": "📉", "futuro": "🔮", "cambio": "🔄", "vida": "🌱",
    "money": "💰", "time": "⏰", "business": "💼", "client": "🤝", "clients": "🤝", "sales": "📈",
    "audience": "👥", "creator": "🧑‍💻", "creators": "🧑‍💻", "product": "📦", "ai": "🤖",
}
RE_CIFRA = re.compile(r"(\$\s?\d[\d.,]*|\d[\d.,]*\s?(%|€|dolares|euros|usd|k\b|mil\b|millones))", re.I)


class MapaT:
    """Convierte segundos del video ORIGINAL (o 'w123' = palabra 123) al video editado."""

    def __init__(self, mapa: Mapa, palabras: list[dict]):
        self.m = mapa
        self.ws = palabras

    def __call__(self, v, fin: bool = False) -> float:
        if isinstance(v, str) and v.startswith("w"):
            w = self.ws[int(v[1:])]
            v = w["e"] if fin else w["s"]
        v = float(v)
        r = self.m(v)
        if r is not None:
            return r
        segs = self.m.segs
        k = bisect_right(self.m.starts, v)
        if fin:   # cae en un corte: termina al final del segmento anterior
            return segs[k - 1]["oe"] if k > 0 else 0.0
        return segs[k]["os"] if k < len(segs) else self.m.duracion


def cargar(d: Path) -> dict | None:
    p = d / "escenas.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def preparar(datos: dict, mapa: Mapa, palabras: list[dict], W: int, H: int, d: Path) -> list[RenderEscena]:
    mt = MapaT(mapa, palabras)
    estilo = datos.get("estilo", {})
    out = []
    for esc in datos.get("escenas", []):
        if esc.get("omitir"):
            continue
        if esc.get("tipo") == "imagen" and not Path(esc["archivo"]).is_absolute():
            esc = {**esc, "archivo": str((d / esc["archivo"]).resolve())}
        elems, t0, t1 = construir_escena(esc, W, H, mt)
        if t1 - t0 < 0.3:
            continue
        for e in elems:   # nada aparece fuera de su escena
            e.t = min(max(e.t, t0), t1 - 0.05)
        out.append(RenderEscena(elems, t0, t1, W, H, push=estilo.get("push_in", 1.035),
                                entrada=estilo.get("entrada", 1.06)))
    out.sort(key=lambda r: r.t0)
    # sin solapes
    for a, b in zip(out, out[1:]):
        if a.t1 > b.t0:
            a.t1 = b.t0
    return [r for r in out if r.t1 - r.t0 >= 0.3]


def intervalos(escenas: list[RenderEscena]) -> list[tuple[float, float]]:
    return [(e.t0, e.t1) for e in escenas]


def eventos_sfx(escenas: list[RenderEscena], datos: dict) -> list[dict]:
    """Whoosh suave al entrar una slide, pop muy suave en cada aparición, trazo en subrayados."""
    estilo = datos.get("estilo", {})
    if not estilo.get("sfx", True):
        return []
    ev = []
    for esc in escenas:
        ev.append({"t": esc.t0, "sfx": "whoosh_suave", "db": -27, "ancla": 0.22})
        ultimo = esc.t0
        for e in esc.elems:
            if e.t - ultimo < 0.25 or e.t <= esc.t0 + 0.05:
                continue
            if e.anim in ("pop", "contar"):
                ev.append({"t": e.t, "sfx": "pop", "db": -29})
                ultimo = e.t
    return ev


# ------------------------------------------------------------------ borrador automático

POCO_VISUALES = {"hoy", "ahora", "mira", "atencion", "paso", "pasos", "gente", "personas", "nunca",
                 "nadie", "verdad", "importante", "dias", "meses", "anos", "tiempo"}


def _emoji_para(toks: list[str]) -> str | None:
    """Prefiere sustantivos concretos (dinero, casa, cliente) a palabras de relleno (hoy, ahora)."""
    candidatos = [t for t in toks if t in EMOJIS]
    fuertes = [t for t in candidatos if t not in POCO_VISUALES]
    elegido = (fuertes or candidatos or [None])[0]
    return EMOJIS.get(elegido) if elegido else None


def _negritas(texto: str, toks_clave: set[str]) -> str:
    out = []
    for w in texto.split():
        if norm(w) in toks_clave and not w.startswith("**"):
            limpio = w.rstrip(".,;:!?")
            out.append(f"**{limpio}**" + w[len(limpio):])
        else:
            out.append(w)
    return " ".join(out)


def borrador(palabras: list[dict], claves: list[str], cobertura: float = 0.55) -> dict:
    """Propone escenas para ~`cobertura` del tiempo, priorizando frases con cifras,
    palabras clave y enumeraciones. Es un punto de partida para revisar a mano."""
    claves_n = {norm(k) for k in claves} | set(EMOJIS)
    fs = frases(palabras, gap=0.45)
    candidatas = []
    for f in fs:
        texto = " ".join(w["w"] for w in f.palabras)
        toks = f.toks
        dur = f.e - f.s
        if dur < 1.2 or len(toks) < 3:
            continue
        puntos = sum(1 for t in toks if t in claves_n) + (3 if RE_CIFRA.search(texto) else 0)
        candidatas.append((puntos / max(1.0, dur ** 0.5), f, texto))
    total = sum(f.e - f.s for f in fs) or 1
    elegidas, acum = [], 0.0
    for _, f, texto in sorted(candidatas, key=lambda c: -c[0]):
        if acum / total >= cobertura:
            break
        elegidas.append((f, texto))
        acum += f.e - f.s
    elegidas.sort(key=lambda x: x[0].s)

    escenas = []
    for k, (f, texto) in enumerate(elegidas):
        toks = f.toks
        texto = texto.strip()
        m = RE_CIFRA.search(texto)
        base = {"desde": round(f.s, 2), "hasta": round(f.e + 0.15, 2)}
        if m:
            cifra = m.group(0).strip()
            antes = texto[:m.start()].strip(" ,:")
            pal_cifra = next((w for w in f.palabras if cifra.split()[0].strip("$") in w["w"]), None)
            esc = {**base, "tipo": "cifra", "valor": cifra.rstrip(".,"),
                   "antes": _negritas(antes, claves_n) if antes else None,
                   "valor_en": round(pal_cifra["s"], 2) if pal_cifra else None,
                   "emoji": _emoji_para(toks)}
        else:
            # subrayar la palabra clave más importante (la última que aparezca)
            clave = [w for w in f.palabras if w["n"] in claves_n]
            txt = _negritas(texto, claves_n)
            sub_en = None
            if clave:
                w = clave[-1]
                limpio = w["w"].rstrip(".,;:!?")
                txt = txt.replace(f"**{limpio}**", f"__{limpio}__", 1)
                sub_en = round(w["s"], 2)
            esc = {**base, "tipo": "frase", "texto": txt, "emoji": _emoji_para(toks),
                   "subrayado_en": sub_en}
        escenas.append({k2: v for k2, v in esc.items() if v is not None})
    return {
        "estilo": {"push_in": 1.035, "entrada": 1.06, "sfx": True},
        "escenas": escenas,
    }


# ------------------------------------------------------------------ render / revisión

def renderizar_pista_escenas(escenas: list[RenderEscena], duracion: float, info: dict, carpeta: Path) -> Path:
    from .slides import renderizar_pista
    return renderizar_pista(escenas, duracion, float(info["fps"]), info["fps_str"],
                            info["width"], info["height"], carpeta)


def hoja_preview(escenas: list[RenderEscena], salida: Path, n: int | None = None) -> Path:
    """Mosaico para revisar: estado final de cada escena, o 5 momentos de la escena N."""
    from PIL import Image, ImageDraw
    if n:
        e = escenas[n - 1]
        tiempos = [(e, e.t0 + (e.t1 - e.t0) * f) for f in (0.02, 0.25, 0.5, 0.75, 0.99)]
    else:
        tiempos = [(e, e.t1 - 0.04) for e in escenas]
    W, H = escenas[0].W, escenas[0].H
    tw = 480
    th = int(H * tw / W)
    cols = min(4, len(tiempos))
    filas = (len(tiempos) + cols - 1) // cols
    hoja = Image.new("RGB", (cols * (tw + 6) + 6, filas * (th + 6) + 6), (60, 60, 60))
    for k, (e, t) in enumerate(tiempos):
        im = e.frame(t).resize((tw, th), Image.LANCZOS)
        ImageDraw.Draw(im).text((6, 4), f"#{escenas.index(e) + 1} {t:.1f}s", fill=(200, 0, 0))
        hoja.paste(im, (6 + (k % cols) * (tw + 6), 6 + (k // cols) * (th + 6)))
    hoja.save(salida, quality=90)
    return salida


def zooms_manuales(datos: dict | None, mapa: Mapa, palabras: list[dict]) -> list[dict]:
    """'zooms' de escenas.json (tiempos originales) -> intervalos en el video editado.

    {"desde": 600, "hasta": 640, "nivel": 1.4, "cx": 0.45, "cy": 0.45}
    cx/cy = punto del cuadro (0-1) que queda en el centro. Útil para encuadrar gráficos
    o pantallas y acercar la zona que se está explicando.
    """
    if not datos:
        return []
    mt = MapaT(mapa, palabras)
    out = []
    for z in datos.get("zooms", []):
        s, e = mt(z["desde"]), mt(z["hasta"], fin=True)
        if e - s > 0.1 and z.get("nivel", 1) > 1:
            out.append({"s": s, "e": e, "nivel": z["nivel"], "cx": z.get("cx", 0.5), "cy": z.get("cy", 0.5)})
    return out
