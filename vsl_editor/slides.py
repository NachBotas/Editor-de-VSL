"""Motor de slides explicativas sobre fondo blanco (estilo VSL "whiteboard").

Las escenas se describen en `trabajo/VIDEO/escenas.json` (ver ESCENAS.md). Cada elemento
aparece sincronizado con la palabra en que se dice, con animación "pop", los subrayados y
flechas se dibujan solos, las cifras cuentan hacia arriba y toda la slide tiene un
push-in suave para que nunca esté quieta.

Marcado dentro de cualquier texto:
    **negrita**   __subrayado rojo a mano__   ~~tachado rojo~~
    ==verde (positivo)==   !!rojo (negativo)!!
"""
from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import FONTS_DIR

EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
NEGRO = (17, 17, 17)
GRIS = (95, 95, 95)
ROJO = (226, 35, 35)
VERDE = (22, 163, 74)
AZUL = (59, 110, 246)
FONDO = (255, 255, 255)


# ------------------------------------------------------------------ fuentes

@lru_cache(maxsize=64)
def fuente(tam: int, peso: int = 400, mano: bool = False) -> ImageFont.FreeTypeFont:
    ruta = FONTS_DIR / ("Caveat.ttf" if mano else "Outfit.ttf")
    try:
        f = ImageFont.truetype(str(ruta), tam)
        f.set_variation_by_axes([peso])
        return f
    except Exception:
        return ImageFont.truetype(str(FONTS_DIR / "Inter-Bold.otf"), tam)


@lru_cache(maxsize=256)
def emoji(char: str, alto: int) -> Image.Image:
    f = ImageFont.truetype(EMOJI_FONT, 109)
    tmp = Image.new("RGBA", (109 * max(2, len(char)) + 40, 160), (0, 0, 0, 0))
    ImageDraw.Draw(tmp).text((10, 10), char, font=f, embedded_color=True)
    bb = tmp.getbbox()
    if not bb:
        return Image.new("RGBA", (alto, alto), (0, 0, 0, 0))
    tmp = tmp.crop(bb)
    r = alto / tmp.height
    return tmp.resize((max(1, int(tmp.width * r)), alto), Image.LANCZOS)


# ------------------------------------------------------------------ texto enriquecido

RE_MARCA = re.compile(r"(\*\*.+?\*\*|__.+?__|~~.+?~~|==.+?==|!!.+?!!)")


def parsear(texto: str) -> list[tuple[str, dict]]:
    runs = []
    for parte in RE_MARCA.split(texto):
        if not parte:
            continue
        st = {"bold": False, "color": None, "ul": False, "tach": False}
        for marca, cambios in (("**", {"bold": True}), ("__", {"bold": True, "ul": True}),
                               ("~~", {"tach": True}), ("==", {"bold": True, "color": VERDE}),
                               ("!!", {"bold": True, "color": ROJO})):
            if parte.startswith(marca) and parte.endswith(marca) and len(parte) > 4:
                parte = parte[2:-2]
                st.update(cambios)
                break
        runs.append((parte, st))
    return runs


@dataclass
class Bloque:
    img: Image.Image
    decor: list[tuple[str, tuple[int, int, int, int]]] = field(default_factory=list)  # (tipo, caja)


def texto_rico(texto: str, tam: int, ancho_max: int, color=NEGRO, peso=400, peso_bold=700,
               alinear="centro", interlineado=1.25, mano=False) -> Bloque:
    """Renderiza texto con marcado, con salto de línea, y devuelve dónde van subrayados/tachados."""
    palabras: list[tuple[str, dict]] = []
    for txt, st in parsear(texto):
        trozos = re.split(r"(\s+)", txt)
        for tz in trozos:
            if tz == "":
                continue
            palabras.append((tz, st))

    def f_de(st):
        return fuente(tam, peso_bold if st["bold"] else peso, mano)

    def ancho(tz, st):
        return f_de(st).getlength(tz)

    # líneas
    lineas: list[list[tuple[str, dict]]] = [[]]
    actual = 0.0
    for tz, st in palabras:
        w = ancho(tz, st)
        if tz.isspace():
            if lineas[-1]:
                lineas[-1].append((" ", st))
                actual += ancho(" ", st)
            continue
        if actual + w > ancho_max and lineas[-1]:
            while lineas[-1] and lineas[-1][-1][0] == " ":
                lineas[-1].pop()
            lineas.append([])
            actual = 0.0
        lineas[-1].append((tz, st))
        actual += w
    while lineas[-1] and lineas[-1][-1][0] == " ":
        lineas[-1].pop()

    asc, desc = fuente(tam, peso, mano).getmetrics()
    alto_linea = int((asc + desc) * interlineado)
    anchos = [sum(ancho(t, s) for t, s in ln) for ln in lineas]
    W = int(max(anchos) if anchos else 1) + 8
    pad_inf = int(tam * 0.35)
    H = alto_linea * len(lineas) + pad_inf
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    decor = []
    for k, ln in enumerate(lineas):
        x = (W - anchos[k]) / 2 if alinear == "centro" else 0
        y = k * alto_linea
        tramos: dict[str, list] = {"ul": [], "tach": []}
        for tz, st in ln:
            f = f_de(st)
            w = f.getlength(tz)
            d.text((x, y), tz, font=f, fill=st["color"] or color)
            for tipo in ("ul", "tach"):
                if st[tipo] and tz != " ":
                    tramos[tipo].append([x, x + w])
            x += w
        for tipo, spans in tramos.items():
            # fusionar palabras consecutivas en un solo trazo
            fus = []
            for a, b in spans:
                if fus and a - fus[-1][1] < tam * 0.5:
                    fus[-1][1] = b
                else:
                    fus.append([a, b])
            for a, b in fus:
                if tipo == "ul":
                    yy = y + asc + int(tam * 0.12)
                else:
                    yy = y + int(asc * 0.62)
                decor.append((tipo, (int(a), int(yy), int(b), int(yy))))
    return Bloque(img, decor)


# ------------------------------------------------------------------ trazos a mano

def trazo(largo: int, grosor: int, color=ROJO, tipo="ul", semilla: int = 0) -> Image.Image:
    """Subrayado / tachado con aspecto de rotulador (levemente curvo e irregular)."""
    ss = 3
    L = max(4, largo) * ss
    g = max(2, grosor) * ss
    alto = g * 6
    img = Image.new("RGBA", (L + g * 2, alto), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pts = []
    n = 24
    for k in range(n + 1):
        u = k / n
        curva = math.sin(u * math.pi) * g * (0.9 if tipo == "ul" else 0.4)
        ond = math.sin(u * 7 + semilla) * g * 0.25
        inclin = (u - 0.5) * g * (1.2 if tipo == "ul" else -0.6)
        pts.append((g + u * L, alto / 2 + curva * 0.5 + ond + inclin))
    d.line(pts, fill=color, width=g, joint="curve")
    r = g // 2
    for p in (pts[0], pts[-1]):
        d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=color)
    return img.resize((img.width // ss, img.height // ss), Image.LANCZOS)


def flecha(largo: int, grosor: int, color=ROJO, curva: float = 0.0) -> Image.Image:
    ss = 3
    L, g = largo * ss, max(2, grosor) * ss
    cab = g * 4
    alto = int(max(cab * 2.5, abs(curva) * L * 0.6 + cab * 2.5))
    img = Image.new("RGBA", (L + cab, alto), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cy = alto / 2
    pts = []
    for k in range(31):
        u = k / 30
        pts.append((cab / 2 + u * (L - cab), cy - math.sin(u * math.pi) * curva * L * 0.25))
    d.line(pts, fill=color, width=g, joint="curve")
    x1, y1 = pts[-1]
    ang = math.atan2(pts[-1][1] - pts[-2][1], pts[-1][0] - pts[-2][0])
    for s in (+1, -1):
        a = ang + math.pi + s * 0.55
        d.line([(x1, y1), (x1 + math.cos(a) * cab, y1 + math.sin(a) * cab)], fill=color, width=g)
        r = g // 2
        xe, ye = x1 + math.cos(a) * cab, y1 + math.sin(a) * cab
        d.ellipse((xe - r, ye - r, xe + r, ye + r), fill=color)
    return img.resize((img.width // ss, img.height // ss), Image.LANCZOS)


def tarjeta(w: int, h: int, color=(244, 244, 246), radio: int = 24, borde=None) -> Image.Image:
    ss = 2
    img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=radio * ss,
                                          fill=color, outline=borde, width=3 * ss if borde else 0)
    return img.resize((w, h), Image.LANCZOS)


def insignia(num: str, tam: int) -> Image.Image:
    img = tarjeta(tam, tam, color=(225, 233, 252), radio=tam // 4, borde=(150, 175, 240))
    d = ImageDraw.Draw(img)
    f = fuente(int(tam * 0.55), 700)
    w = f.getlength(num)
    asc, desc = f.getmetrics()
    d.text(((tam - w) / 2, (tam - asc - desc) / 2 + tam * 0.02), num, font=f, fill=AZUL)
    return img


# ------------------------------------------------------------------ elementos

@dataclass
class Elem:
    img: Image.Image
    x: int
    y: int
    t: float                 # aparición (segundos del video EDITADO)
    anim: str = "pop"        # pop | trazo | corte | fade | contar
    dur: float = 0.28
    contar: tuple | None = None   # (valor_final, fmt_fn, tam, peso, color)

    @property
    def cx(self):
        return self.x + self.img.width / 2

    @property
    def cy(self):
        return self.y + self.img.height / 2


def _ease_back(p: float) -> float:
    c1 = 1.9
    c3 = c1 + 1
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2


def _ease_out(p: float) -> float:
    return 1 - (1 - p) ** 3


RE_NUM = re.compile(r"^(?P<pre>[^\d]*)(?P<num>\d{1,3}(?:[.,]\d{3})+|\d+)(?P<post>[^\d]*)$")


def preparar_contador(texto: str):
    """'$25.000.000' -> (25000000, fn(v)->'$12.345.678'). None si no es una cifra simple."""
    m = RE_NUM.match(texto.strip())
    if not m:
        return None
    num = m.group("num")
    sep = "." if "." in num else ("," if "," in num else "")
    valor = int(re.sub(r"[.,]", "", num))
    if valor < 10:
        return None

    def fmt(v: float) -> str:
        n = int(round(v))
        s = f"{n:,}".replace(",", sep) if sep else str(n)
        return f"{m.group('pre')}{s}{m.group('post')}"
    return valor, fmt


# ------------------------------------------------------------------ diseños

class Lienzo:
    """Coloca elementos de una escena. Coordenadas en píxeles del video final."""

    def __init__(self, W: int, H: int):
        self.W, self.H = W, H
        # escala base: diseñado para 1920x1080; en vertical se agranda (se ve en el móvil)
        self.u = min(W / 1920, H / 1080) if W >= H else W / 1080 * 1.55
        self.vertical = H > W * 1.2
        self.elems: list[Elem] = []

    def px(self, v: float) -> int:
        return int(round(v * self.u))

    def add(self, img, x, y, t, anim="pop", dur=None, **kw):
        e = Elem(img, int(x), int(y), t, anim, dur if dur is not None else
                 {"pop": 0.30, "trazo": 0.38, "corte": 0.0, "fade": 0.25, "contar": 0.9}[anim], **kw)
        self.elems.append(e)
        return e

    def texto(self, texto, cx, y, t, tam=64, ancho=None, color=NEGRO, peso=400, alinear="centro",
              mano=False, anim="pop", t_decor=None, centrar_y=False):
        b = texto_rico(texto, self.px(tam), ancho or int(self.W * 0.78), color=color, peso=peso,
                       alinear=alinear, mano=mano)
        x = cx - b.img.width / 2 if alinear == "centro" else cx
        if centrar_y:
            y = y - b.img.height / 2
        self.add(b.img, x, y, t, anim)
        for k, (tipo, (a, yy, bb, _)) in enumerate(b.decor):
            tr = trazo(bb - a + self.px(10), max(3, self.px(7 if tipo == "ul" else 6)),
                       ROJO, tipo, semilla=k)
            self.add(tr, x + a - self.px(5), y + yy - tr.height / 2,
                     (t_decor if t_decor is not None else t + 0.35) + k * 0.1, "trazo")
        return b.img.height


def _t(spec: dict, clave: str, por_defecto: float, mapa_t) -> float:
    v = spec.get(clave)
    return mapa_t(v) if v is not None else por_defecto


def construir_escena(esc: dict, W: int, H: int, mapa_t) -> tuple[list[Elem], float, float]:
    """Devuelve (elementos, inicio, fin) en tiempo del video editado."""
    t0 = mapa_t(esc["desde"])
    t1 = mapa_t(esc["hasta"], fin=True)
    L = Lienzo(W, H)
    tipo = esc.get("tipo", "frase")
    cx = W / 2
    getattr(_DISENOS, tipo, _DISENOS.frase)(L, esc, t0, mapa_t, cx)
    return L.elems, t0, t1


class _DISENOS:
    @staticmethod
    def _bloque_vertical(L: Lienzo, partes: list[tuple[int, callable]]):
        """Centra verticalmente un grupo de partes de alto conocido."""
        gap = L.px(34)
        total = sum(h for h, _ in partes) + gap * (len(partes) - 1)
        y = (L.H - total) / 2 - L.px(10)
        for h, dibujar in partes:
            dibujar(y)
            y += h + gap

    @staticmethod
    def frase(L: Lienzo, e: dict, t0, mt, cx):
        partes = []
        if e.get("emoji"):
            em = emoji(e["emoji"], L.px(e.get("emoji_tam", 170)))
            te = _t(e, "emoji_en", t0, mt)
            partes.append((em.height, lambda y, em=em, te=te: L.add(em, cx - em.width / 2, y, te)))
        if e.get("titulo"):
            b = texto_rico(e["titulo"], L.px(52), int(L.W * 0.8), color=GRIS)
            partes.append((b.img.height, lambda y, b=b: L.texto(e["titulo"], cx, y, t0, 52, color=GRIS)))
        tam = e.get("tam", 74 if len(re.sub(r"[*_~=!]", "", e.get("texto", ""))) < 60 else 62)
        if e.get("texto"):
            b = texto_rico(e["texto"], L.px(tam), int(L.W * 0.8))
            tt = _t(e, "texto_en", t0, mt)
            td = _t(e, "subrayado_en", tt + 0.35, mt)
            partes.append((b.img.height, lambda y, tt=tt, td=td: L.texto(e["texto"], cx, y, tt, tam, t_decor=td)))
        if e.get("nota"):
            b = texto_rico(e["nota"], L.px(62), int(L.W * 0.8), mano=True, color=(55, 55, 55))
            tn = _t(e, "nota_en", t0 + 0.8, mt)
            partes.append((b.img.height, lambda y, tn=tn: L.texto(e["nota"], cx, y, tn, 62, mano=True,
                                                                  color=(55, 55, 55), peso=600)))
        _DISENOS._bloque_vertical(L, partes)

    @staticmethod
    def cifra(L: Lienzo, e: dict, t0, mt, cx):
        partes = []
        if e.get("emoji"):
            em = emoji(e["emoji"], L.px(150))
            partes.append((em.height, lambda y, em=em: L.add(em, cx - em.width / 2, y, _t(e, "emoji_en", t0, mt))))
        if e.get("antes"):
            b = texto_rico(e["antes"], L.px(64), int(L.W * 0.85))
            partes.append((b.img.height, lambda y: L.texto(e["antes"], cx, y, _t(e, "antes_en", t0, mt), 64)))
        valor = e.get("valor", "")
        tv = _t(e, "valor_en", t0 + (0.6 if e.get("antes") else 0), mt)
        # el número grande se ajusta para caber siempre en pantalla
        tam_v = 150
        while tam_v > 50 and fuente(L.px(tam_v), 800).getlength(valor) > L.W * 0.86:
            tam_v -= 6
        f = fuente(L.px(tam_v), 800)
        alto_v = sum(f.getmetrics()) + L.px(40)

        def dibujar_valor(y):
            cont = preparar_contador(valor) if e.get("contar", True) else None
            img = texto_rico(f"**{valor}**", L.px(tam_v), int(L.W * 0.95), peso_bold=800).img
            x = cx - img.width / 2
            if cont:
                L.add(img, x, y, tv, "contar", contar=(cont[0], cont[1], L.px(tam_v), 800, NEGRO))
            else:
                L.add(img, x, y, tv, "pop")
            tr = trazo(int(img.width * 0.98), L.px(9), ROJO, "ul", semilla=3)
            L.add(tr, x, y + alto_v - L.px(52 * tam_v / 150), tv + (0.95 if cont else 0.35), "trazo")
        partes.append((alto_v, dibujar_valor))
        if e.get("nota"):
            b = texto_rico(e["nota"], L.px(62), int(L.W * 0.8), mano=True)
            partes.append((b.img.height, lambda y: L.texto(e["nota"], cx, y, _t(e, "nota_en", tv + 1.0, mt), 62,
                                                          mano=True, color=(55, 55, 55), peso=600)))
        _DISENOS._bloque_vertical(L, partes)

    @staticmethod
    def lista(L: Lienzo, e: dict, t0, mt, cx):
        items = e.get("items", [])
        tam = e.get("tam", 60 if len(items) <= 4 else 50)
        icono_h = L.px(tam * 1.45)
        filas = []
        ancho_txt = int(L.W * (0.62 if not L.vertical else 0.7))
        for it in items:
            b = texto_rico(it["texto"], L.px(tam), ancho_txt, alinear="izq")
            filas.append((it, b, max(icono_h, b.img.height)))
        gap = L.px(tam * 0.9)
        titulo_h = 0
        if e.get("titulo"):
            bt = texto_rico(e["titulo"], L.px(54), int(L.W * 0.8), color=GRIS)
            titulo_h = bt.img.height + L.px(50)
        total = titulo_h + sum(h for _, _, h in filas) + gap * (len(filas) - 1)
        y = (L.H - total) / 2
        if e.get("titulo"):
            L.texto(e["titulo"], cx, y, t0, 54, color=GRIS)
            y += titulo_h
        iconos = [emoji(it.get("icono") or e.get("icono") or "✅", icono_h) for it, _, _ in filas]
        col = max((im.width for im in iconos), default=icono_h)   # columna fija para los iconos
        ancho_fila = max((col + L.px(30) + b.img.width for _, b, _ in filas), default=0)
        x0 = cx - ancho_fila / 2
        for k, ((it, b, h), em) in enumerate(zip(filas, iconos)):
            t = mt(it["en"]) if it.get("en") is not None else t0 + 0.2 + k * 0.9
            L.add(em, x0 + (col - em.width) / 2, y + (h - icono_h) / 2, t)
            L.texto(it["texto"], x0 + col + L.px(30), y + (h - b.img.height) / 2 + L.px(4), t + 0.06,
                    tam, ancho=ancho_txt, alinear="izq")
            y += h + gap

    @staticmethod
    def flujo(L: Lienzo, e: dict, t0, mt, cx):
        nodos = e.get("nodos", [])
        n = max(1, len(nodos))
        em_h = L.px(e.get("emoji_tam", 150 if n <= 3 else 120))
        tam = 52 if n <= 3 else 44
        y_top = L.H * 0.36
        if e.get("titulo"):
            L.texto(e["titulo"], cx, L.H * 0.14, t0, 58)
            y_top = L.H * 0.40
        if L.vertical:   # en vertical, de arriba a abajo
            lab_h = int(sum(fuente(L.px(tam), 700).getmetrics()) * 1.3)
            hueco_flecha = L.px(130)
            bloque = n * (em_h + L.px(14) + lab_h) + (n - 1) * hueco_flecha
            y = (L.H - bloque) / 2
            for k, nd in enumerate(nodos):
                t = mt(nd["en"]) if nd.get("en") is not None else t0 + k * 1.0
                if k:
                    fl = flecha(hueco_flecha - L.px(30), L.px(7), ROJO).rotate(-90, expand=True)
                    L.add(fl, cx - fl.width / 2, y + L.px(15), t - 0.25, "trazo")
                    y += hueco_flecha
                em = emoji(nd.get("emoji", "⭐"), em_h)
                L.add(em, cx - em.width / 2, y, t)
                L.texto(nd.get("texto", ""), cx, y + em_h + L.px(14), t + 0.06, tam)
                y += em_h + L.px(14) + lab_h
            return
        ancho = L.W * 0.86
        celda = ancho / n
        for k, nd in enumerate(nodos):
            t = mt(nd["en"]) if nd.get("en") is not None else t0 + k * 1.0
            xc = (L.W - ancho) / 2 + celda * (k + 0.5)
            em = emoji(nd.get("emoji", "⭐"), em_h)
            L.add(em, xc - em.width / 2, y_top, t)
            L.texto(nd.get("texto", ""), xc, y_top + em_h + L.px(22), t + 0.06, tam, ancho=int(celda * 0.92))
            if k:
                largo = int(celda - em_h - L.px(70))
                fl = flecha(largo, L.px(7), e.get("color_flecha") and ROJO or ROJO, curva=e.get("curva", 0.0))
                L.add(fl, xc - celda / 2 - fl.width / 2, y_top + em_h / 2 - fl.height / 2, t - 0.25, "trazo")

    @staticmethod
    def pasos(L: Lienzo, e: dict, t0, mt, cx):
        ps = e.get("pasos", [])
        n = max(1, len(ps))
        ancho = L.W * 0.82
        celda = ancho / n
        bad = L.px(110)
        y = L.H * 0.30
        if e.get("titulo"):
            L.texto(e["titulo"], cx, L.H * 0.12, t0, 60)
            y = L.H * 0.36
        for k, p in enumerate(ps):
            t = mt(p["en"]) if p.get("en") is not None else t0 + k * 1.0
            xc = (L.W - ancho) / 2 + celda * (k + 0.5)
            L.add(insignia(str(p.get("num", k + 1)), bad), xc - bad / 2, y, t)
            yy = y + bad + L.px(30)
            if p.get("emoji"):
                em = emoji(p["emoji"], L.px(110))
                L.add(em, xc - em.width / 2, yy, t + 0.08)
                yy += em.height + L.px(20)
            L.texto(p.get("texto", ""), xc, yy, t + 0.12, 54, ancho=int(celda * 0.9))
            if k:
                pts = [(xc - celda + bad / 2 + L.px(20), y + bad / 2), (xc - bad / 2 - L.px(20), y + bad / 2)]
                largo = int(pts[1][0] - pts[0][0])
                if largo > 20:
                    fl = flecha(largo, L.px(5), (160, 160, 170), curva=0.35)
                    L.add(fl, pts[0][0], y + bad / 2 - fl.height / 2 - L.px(30), t - 0.25, "trazo")

    @staticmethod
    def comparacion(L: Lienzo, e: dict, t0, mt, cx):
        lados = [("izq", (254, 226, 226), "❌", ROJO), ("der", (220, 252, 231), "✅", VERDE)]
        vert = L.vertical
        cw = L.W - L.px(60) if vert else L.W / 2 - L.px(45)
        ch = L.H / 2 - L.px(45) if vert else L.H * 0.80
        tam_item = 56
        for k, (lado, fondo, ic, col) in enumerate(lados):
            sp = e.get(lado, {})
            if not sp:
                continue
            t = mt(sp["en"]) if sp.get("en") is not None else t0 + k * 1.5
            x0 = L.px(30) if vert else L.px(30) + k * (cw + L.px(30))
            y0 = (L.px(30) + k * (ch + L.px(30))) if vert else L.H * 0.10
            L.add(tarjeta(int(cw), int(ch), fondo, radio=L.px(36)), x0, y0, t, "fade")
            items = sp.get("items", [])
            alto_items = len(items) * L.px(tam_item * 1.9)
            alto_tit = L.px(64 * 1.6)
            y = y0 + (ch - alto_tit - alto_items) / 2
            L.texto(f"**{sp.get('titulo', '')}**", x0 + cw / 2, y, t + 0.05, 68, color=col,
                    ancho=int(cw * 0.88))
            y += alto_tit + L.px(20)
            for j, it in enumerate(items):
                ti = mt(it["en"]) if isinstance(it, dict) and it.get("en") is not None else t + 0.4 + j * 0.7
                txt = it["texto"] if isinstance(it, dict) else it
                em = emoji(it.get("icono", ic) if isinstance(it, dict) else ic, L.px(tam_item * 1.25))
                L.add(em, x0 + L.px(60), y, ti)
                h = L.texto(txt, x0 + L.px(60) + em.width + L.px(26), y + L.px(6), ti + 0.05, tam_item,
                            ancho=int(cw - em.width - L.px(130)), alinear="izq")
                y += max(h, em.height) + L.px(tam_item * 0.6)

    @staticmethod
    def imagen(L: Lienzo, e: dict, t0, mt, cx):
        ruta = Path(e["archivo"])
        img = Image.open(ruta).convert("RGBA")
        alto_max = L.H * (0.62 if e.get("texto") else 0.78)
        r = min(alto_max / img.height, L.W * 0.82 / img.width)
        img = img.resize((int(img.width * r), int(img.height * r)), Image.LANCZOS)
        # sombra suave + borde redondeado
        marco = tarjeta(img.width + L.px(16), img.height + L.px(16), (230, 230, 234), radio=L.px(18))
        y = (L.H - img.height) / 2 - (L.px(60) if e.get("texto") else 0)
        L.add(marco, cx - marco.width / 2, y - L.px(8), t0, "fade")
        L.add(img, cx - img.width / 2, y, t0, "pop")
        if e.get("texto"):
            L.texto(e["texto"], cx, y + img.height + L.px(40), _t(e, "texto_en", t0 + 0.3, mt), 56)


# ------------------------------------------------------------------ render por fotograma

class RenderEscena:
    def __init__(self, elems: list[Elem], t0: float, t1: float, W: int, H: int, push: float = 1.035,
                 entrada: float = 1.06):
        self.elems = sorted(elems, key=lambda e: e.t)
        self.t0, self.t1, self.W, self.H = t0, t1, W, H
        self.push, self.entrada = push, entrada
        self._cache_key = None
        self._cache_img = None

    def _componer(self, t: float) -> Image.Image:
        activos = [e for e in self.elems if t >= e.t - 1e-6]
        animando = any(t < e.t + e.dur for e in activos)
        clave = len(activos)
        if not animando and self._cache_key == clave:
            return self._cache_img
        lienzo = Image.new("RGB", (self.W, self.H), FONDO)
        for e in activos:
            p = 1.0 if e.dur <= 0 else min(1.0, (t - e.t) / e.dur)
            img, x, y = e.img, e.x, e.y
            if p < 1.0:
                if e.anim == "pop":
                    s = 0.55 + 0.45 * _ease_back(p)
                    w, h = max(1, int(img.width * s)), max(1, int(img.height * s))
                    img = img.resize((w, h), Image.BILINEAR)
                    x, y = e.cx - w / 2, e.cy - h / 2
                    img = _alpha(img, min(1.0, p * 3))
                elif e.anim == "trazo":
                    w = max(1, int(img.width * _ease_out(p)))
                    img = img.crop((0, 0, w, img.height))
                elif e.anim == "fade":
                    img = _alpha(img, _ease_out(p))
                elif e.anim == "contar" and e.contar:
                    valor, fmt, tam, peso, col = e.contar
                    txt = fmt(valor * _ease_out(p))
                    b = texto_rico(f"**{txt}**", tam, self.W, peso_bold=peso, color=col).img
                    img, x = b, e.cx - b.width / 2
            lienzo.paste(img, (int(x), int(y)), img)
        if not animando:
            self._cache_key, self._cache_img = clave, lienzo
        return lienzo

    def frame(self, t: float) -> Image.Image:
        img = self._componer(t)
        dur = max(0.01, self.t1 - self.t0)
        u = min(1.0, max(0.0, (t - self.t0) / dur))
        z = 1 + (self.push - 1) * u
        pe = min(1.0, (t - self.t0) / 0.28)
        z *= 1 + (self.entrada - 1) * (1 - _ease_out(pe))
        if abs(z - 1) < 1e-4:
            return img
        cw, ch = self.W / z, self.H / z
        x0, y0 = (self.W - cw) / 2, (self.H - ch) / 2
        return img.resize((self.W, self.H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))


def _alpha(img: Image.Image, a: float) -> Image.Image:
    if a >= 0.999:
        return img
    r, g, b, al = img.split()
    al = al.point(lambda v: int(v * a))
    return Image.merge("RGBA", (r, g, b, al))


# ------------------------------------------------------------------ pista de slides

def _encode(cmd_out: list[str], W: int, H: int, fps_str: str):
    return subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", fps_str, "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
         "-pix_fmt", "yuv420p", "-r", fps_str, *cmd_out],
        stdin=subprocess.PIPE)


def renderizar_pista(escenas: list[RenderEscena], duracion: float, fps: float, fps_str: str,
                     W: int, H: int, carpeta: Path) -> Path:
    """Genera una pista de video del largo total: slides donde hay escena, negro en el resto.

    Los huecos los genera ffmpeg directamente (rapidísimo); solo se dibujan los fotogramas
    de las escenas. Luego se unen con el demuxer concat.
    """
    carpeta.mkdir(parents=True, exist_ok=True)
    for p in carpeta.glob("*.mp4"):
        p.unlink()
    total = int(round(duracion * fps))
    piezas = []
    cursor = 0
    for k, esc in enumerate(sorted(escenas, key=lambda e: e.t0)):
        f0 = max(cursor, int(round(esc.t0 * fps)))
        f1 = min(total, int(round(esc.t1 * fps)))
        if f1 - f0 < 2:
            continue
        if f0 > cursor:
            hueco = carpeta / f"h{k:03d}.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                            f"color=c=black:s={W}x{H}:r={fps_str}", "-frames:v", str(f0 - cursor),
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p",
                            str(hueco)], check=True)
            piezas.append(hueco)
        clip = carpeta / f"s{k:03d}.mp4"
        proc = _encode([str(clip)], W, H, fps_str)
        for fr in range(f0, f1):
            proc.stdin.write(esc.frame(fr / fps).tobytes())
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError("Falló el render de una escena")
        piezas.append(clip)
        cursor = f1
        print(f"  · escena {k + 1}/{len(escenas)} ({(f1 - f0) / fps:.1f}s)", flush=True)
    if cursor < total:
        hueco = carpeta / "h_fin.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                        f"color=c=black:s={W}x{H}:r={fps_str}", "-frames:v", str(total - cursor),
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p",
                        str(hueco)], check=True)
        piezas.append(hueco)
    lista = carpeta / "lista.txt"
    lista.write_text("".join(f"file '{p.name}'\n" for p in piezas), encoding="utf-8")
    return lista
