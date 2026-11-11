"""Decide qué se corta: muletillas, tartamudeos, tomas falsas y silencios.

Trabaja sobre la lista de palabras de la transcripción. Cada palabra recibe
`keep` (bool) y `motivo` (por qué se quitó). Después se construyen los
segmentos de video a conservar, alineados a fotogramas.
"""
from __future__ import annotations

import math
import re
import unicodedata
from bisect import bisect_right
from dataclasses import dataclass

from rapidfuzz import fuzz

from .config import Config

MULETILLAS = {
    "eh", "ehh", "ehhh", "ehm", "ehmm", "em", "emm", "emmm", "mm", "mmm", "mmmm", "hmm",
    "hm", "mhm", "ah", "ahh", "aah", "um", "umm", "uh", "uhm", "eeh", "eem", "ehe",
}
# Solo son muletilla si van aisladas entre pausas (si no, son palabras normales)
MULETILLAS_AISLADAS = {"este", "esto", "bueno", "osea", "pues", "nada", "vale", "okay", "ok"}
# Frases con las que el presentador marca que va a repetir
FRASES_RETOMA = {
    "perdon", "perdona", "otra vez", "de nuevo", "repito", "corta", "corten", "espera",
    "vuelvo", "vuelvo a empezar", "lo repito", "empiezo de nuevo", "a ver otra vez",
    "no espera", "mal", "uy", "ups",
}


def norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w%$€]+", "", t)


def _fin_frase(w: str) -> bool:
    return w.rstrip().endswith((".", "?", "!", "…"))


# ---------------------------------------------------------------- marcado

def marcar(palabras: list[dict], cfg: Config) -> list[dict]:
    for i, w in enumerate(palabras):
        w["i"] = i
        w["n"] = norm(w["w"])
        w.setdefault("keep", True)
        w.setdefault("motivo", None)
        if w.get("manual"):          # decisiones manuales no se tocan
            continue
        w["keep"], w["motivo"] = True, None

    if cfg.quitar_muletillas:
        _muletillas(palabras)
    if cfg.quitar_repeticiones:
        _tartamudeos(palabras)
    if cfg.quitar_tomas_falsas:
        _tomas_falsas(palabras, cfg.umbral_toma)
    return palabras


def _quitar(w: dict, motivo: str) -> None:
    if w.get("manual"):
        return
    if w["keep"]:
        w["keep"], w["motivo"] = False, motivo


def _muletillas(ws: list[dict]) -> None:
    for i, w in enumerate(ws):
        if w["n"] in MULETILLAS:
            _quitar(w, "muletilla")
        elif w["n"] in MULETILLAS_AISLADAS:
            antes = w["s"] - ws[i - 1]["e"] if i > 0 else 1.0
            despues = ws[i + 1]["s"] - w["e"] if i + 1 < len(ws) else 1.0
            if antes > 0.30 and despues > 0.30:
                _quitar(w, "muletilla")


def _vivas(ws: list[dict]) -> list[dict]:
    return [w for w in ws if w["keep"]]


INTENSIFICADORES = {
    "muy", "mucho", "nunca", "jamas", "si", "no", "nada", "todo", "super", "mas", "cada", "otra",
    "very", "really", "so", "never", "no", "yes", "more", "super", "much", "insane", "incredible",
    "increible", "again", "over", "and", "y",
}
CONJUNCIONES = {"and", "y", "e", "after", "tras", "por", "by", "to", "a"}


def _es_retorica(vivas: list[dict], i: int, n: int) -> bool:
    """Repeticiones intencionales que un editor NO debe cortar.

    - Énfasis: "Insane. Insane. Insane.", "muy muy", "nunca, nunca"
    - "horas y horas", "día tras día", "paso a paso"
    - Una pausa marcada con puntuación entre las dos apariciones (ritmo deliberado)
    """
    a = vivas[i:i + n]
    toks = [w["n"] for w in a]
    if n == 1 and toks[0] in INTENSIFICADORES:
        return True
    if n == 2 and (toks[0] in CONJUNCIONES or toks[1] in CONJUNCIONES):
        return True
    if all(t in INTENSIFICADORES for t in toks):
        return True
    if a[-1]["w"].rstrip().endswith((",", ".", "!", "?", "…", ";")) and n <= 2:
        return True
    return False


VACIAS = {"el", "la", "los", "las", "un", "una", "de", "del", "que", "y", "a", "en", "es", "lo",
          "the", "a", "an", "of", "to", "and", "is", "it", "that", "in", "or", "o"}


NEGACIONES = {"no", "not", "non", "isnt", "arent", "dont", "doesnt", "wont", "cant", "never", "nunca",
              "ni", "tampoco", "jamas", "sin", "without"}


def _es_misma_idea(ta: list[str], tb: list[str]) -> bool:
    """¿B vuelve a decir lo mismo que A (toma fallida) o es una estructura paralela?

    Toma fallida: B repite casi todas las palabras con contenido de A
    ("...comete un error" → "...comete un error muy grave").
    Paralela/contraste: cambia la palabra clave o la polaridad
    ("the hard part ISN'T..." / "the hard part IS...", "the HOOK variations" / "the CTA...").
    """
    ventana = tb[:len(ta) + 3]
    if bool(NEGACIONES & set(ta)) != bool(NEGACIONES & set(ventana)):
        return False
    cont = [t for t in ta if t not in VACIAS and len(t) > 2] or ta
    cubiertas = sum(1 for t in cont if t in ventana)
    return cubiertas / len(cont) >= 0.8


def _final_repetido(ta: list[str], tb: list[str]) -> bool:
    return _es_misma_idea(ta, tb)


def _tartamudeos(ws: list[dict]) -> None:
    """'que que', 'lo que lo que' -> se queda la última aparición."""
    for n in (5, 4, 3, 2, 1):
        vivas = _vivas(ws)
        toks = [w["n"] for w in vivas]
        i = 0
        while i + 2 * n <= len(vivas):
            a, b = toks[i:i + n], toks[i + n:i + 2 * n]
            if a == b and all(a) and vivas[i + 2 * n - 1]["e"] - vivas[i]["s"] < 4 + n:
                fin_frase = vivas[i + n - 1]["w"].rstrip().endswith((".", "!", "?"))
                hueco = vivas[i + n]["s"] - vivas[i + n - 1]["e"]
                anadiplosis = n >= 2 and fin_frase and hueco < 0.3   # "...high ticket sales. High ticket sales is..."
                # una repetición que cruza un punto no es tartamudeo
                anadiplosis |= n >= 3 and any(w["w"].rstrip().endswith((".", "!", "?"))
                                              for w in vivas[i:i + n - 1])
                # "win-win": Whisper separa el guion ("win", "-win")
                anadiplosis |= n == 1 and vivas[i + 1]["w"].startswith("-")
                if (n == 1 and (a[0].isdigit() or len(a[0]) == 0)) or _es_retorica(vivas, i, n) or anadiplosis:
                    i += 1
                    continue
                for w in vivas[i:i + n]:
                    _quitar(w, "repeticion")
                i += n
            else:
                i += 1


@dataclass
class Frase:
    palabras: list[dict]

    @property
    def s(self) -> float:
        return self.palabras[0]["s"]

    @property
    def e(self) -> float:
        return self.palabras[-1]["e"]

    @property
    def toks(self) -> list[str]:
        return [w["n"] for w in self.palabras]

    @property
    def texto(self) -> str:
        return " ".join(self.toks)


def frases(ws: list[dict], gap: float = 0.5) -> list[Frase]:
    out: list[Frase] = []
    cur: list[dict] = []
    for w in _vivas(ws):
        if cur and (w["s"] - cur[-1]["e"] >= gap or _fin_frase(cur[-1]["w"])):
            out.append(Frase(cur))
            cur = []
        cur.append(w)
    if cur:
        out.append(Frase(cur))
    return out


def _sim(a: list[str], b: list[str]) -> float:
    return fuzz.ratio(" ".join(a), " ".join(b))


def _tomas_falsas(ws: list[dict], umbral: int) -> None:
    """Detecta cuando el presentador repite una frase (se equivocó y volvió a empezar).

    Siempre se conserva la ÚLTIMA toma, que normalmente es la buena.
    """
    cambiado = True
    vueltas = 0
    while cambiado and vueltas < 6:
        cambiado = False
        vueltas += 1
        fs = frases(ws)
        for k, A in enumerate(fs):
            if not A.palabras[0]["keep"]:
                continue
            ta = A.toks
            # 1) frase de "retoma" ("perdón", "otra vez") -> fuera
            if A.texto in FRASES_RETOMA or (len(ta) <= 3 and " ".join(ta) in FRASES_RETOMA):
                for w in A.palabras:
                    _quitar(w, "retoma")
                cambiado = True
                continue
            for j in range(k + 1, min(k + 4, len(fs))):
                B = fs[j]
                if B.s - A.e > 20:
                    break
                tb = B.toks
                medio = [w for f in fs[k + 1:j] for w in f.palabras]
                if len(medio) > 4:     # demasiado contenido entre ambas: no es retoma
                    break
                # 2) A completa ≈ comienzo de B  (repitió la frase entera)
                if len(ta) >= 2 and len(tb) >= max(2, len(ta) - 1):
                    s = max(_sim(ta, tb[:len(ta)]), _sim(ta, tb[:len(ta) + 1]),
                            _sim(ta, tb[:max(1, len(ta) - 1)]))
                    hueco = B.s - A.e
                    # Anáfora ("the way we buy, the way we work"): mismo arranque, final distinto
                    # y sin parar a respirar -> es retórica, no una toma fallida.
                    final_distinto = len(ta) >= 2 and len(tb) > len(ta) - 1 and \
                        ta[-1] != tb[len(ta) - 1] and _sim(ta[:-1], tb[:len(ta) - 1]) >= 95
                    anafora = (final_distinto or not _es_misma_idea(ta, tb)) and hueco < 0.45
                    # Anadiplosis: "...high ticket sales. High ticket sales is..." sin respirar
                    fin = A.palabras[-1]["w"].rstrip().endswith((".", "!", "?"))
                    anafora |= fin and hueco < 0.25 and len(ta) <= 6
                    if s >= umbral and not anafora:
                        for w in A.palabras + medio:
                            _quitar(w, "toma repetida")
                        cambiado = True
                        break
                # 3) final de A ≈ comienzo de B  (retomó a mitad de frase)
                if j == k + 1:
                    for L in range(min(len(ta), len(tb)) - 1, 2, -1):
                        if _sim(ta[-L:], tb[:L]) >= max(umbral, 85) and \
                                (_final_repetido(ta[-L:], tb) or B.s - A.e >= 0.45) and \
                                not (A.palabras[-1]["w"].rstrip().endswith((".", "!", "?"))
                                     and B.s - A.e < 0.25):
                            for w in A.palabras[-L:]:
                                _quitar(w, "toma repetida")
                            cambiado = True
                            break
                    if cambiado:
                        break
            # 4) dentro de la misma frase: "vamos a ver vamos a ver cómo..." ya lo cubre
            #    _tartamudeos; aquí cubrimos "lo que te quiero lo que te voy a decir"
            if not cambiado:
                cambiado |= _reinicio_interno(A, umbral)


def _reinicio_interno(A: Frase, umbral: int) -> bool:
    t = A.toks
    n = len(t)
    for L in range(min(6, n // 2), 2, -1):
        for i in range(0, n - 2 * L + 2):
            a = t[i:i + L]
            for j in range(i + L, min(i + L + 3, n - L + 1)):
                b = t[j:j + L]
                # Estructura paralela deliberada: hay una coma entre ambas apariciones
                # ("la forma en que compramos, la forma en que...") o el bloque ya es
                # repetitivo en sí mismo ("horas y horas y horas").
                pausa_deliberada = any(w["w"].rstrip().endswith((",", ";", ":"))
                                       for w in A.palabras[i:j]) or len(set(a)) < len(a)
                # Si lo que se quitaría no se vuelve a decir después, solo es toma
                # fallida cuando hay titubeo (pausa) antes de reiniciar.
                titubeo = A.palabras[j]["s"] - A.palabras[j - 1]["e"] >= 0.2
                if i > 0 and (t[i - 1] in NEGACIONES or A.palabras[i]["w"].startswith("-")):
                    continue   # "non-expert ... or expert ..." es un contraste
                paralela = not titubeo and not _es_misma_idea(t[i:j], t[j:j + (j - i) + 2])
                if a[:2] == b[:2] and _sim(a, b) >= max(umbral, 82) and not pausa_deliberada \
                        and not paralela:
                    for w in A.palabras[i:j]:
                        _quitar(w, "toma repetida")
                    return True
    return False


# ---------------------------------------------------------------- segmentos

def construir_segmentos(palabras: list[dict], duracion: float, fps: float,
                        cfg: Config, cortes_extra: list[list[float]] | None = None
                        ) -> list[dict]:
    """Devuelve segmentos [{s, e, fs, fe, corte}] del video ORIGINAL a conservar.

    `corte` describe por qué hay un corte ANTES de ese segmento: 'silencio' o 'quitado'.
    """
    pausa_max, pad_a, pad_d = cfg.resolver_ritmo()
    vivas = [w for w in palabras if w["keep"]]
    if not vivas:
        return []

    segs: list[dict] = []
    s = max(0.0, vivas[0]["s"] - pad_a)
    motivo_corte = "inicio"
    for a, b in zip(vivas, vivas[1:]):
        quitadas = [w for w in palabras[a["i"] + 1:b["i"]] if not w["keep"]]
        hueco = b["s"] - a["e"]
        if not quitadas and hueco <= pausa_max:
            continue
        if quitadas:
            fin = min(a["e"] + pad_d, max(a["e"], quitadas[0]["s"] - 0.02))
            ini = max(b["s"] - pad_a, min(b["s"], quitadas[-1]["e"] + 0.02))
            tipo = "quitado"
        else:
            fin = a["e"] + pad_d
            ini = b["s"] - pad_a
            tipo = "silencio"
        if ini <= fin:   # no compensa cortar
            continue
        segs.append({"s": s, "e": fin, "corte": motivo_corte})
        s, motivo_corte = ini, tipo
    segs.append({"s": s, "e": min(duracion, vivas[-1]["e"] + max(pad_d, 0.3)), "corte": motivo_corte})

    if cortes_extra:
        segs = _restar(segs, cortes_extra)

    # Alinear a fotogramas y fusionar solapes
    out: list[dict] = []
    max_f = int(math.floor(duracion * fps))
    for g in segs:
        fs_ = max(0, int(math.floor(g["s"] * fps + 1e-6)))
        fe_ = min(max_f, int(math.ceil(g["e"] * fps - 1e-6)))
        if fe_ - fs_ < 2:
            continue
        if out and fs_ <= out[-1]["fe"]:
            out[-1]["fe"] = max(out[-1]["fe"], fe_)
            continue
        out.append({"fs": fs_, "fe": fe_, "corte": g["corte"]})
    t = 0.0
    for g in out:
        g["s"], g["e"] = g["fs"] / fps, g["fe"] / fps
        g["os"] = t
        t += g["e"] - g["s"]
        g["oe"] = t
    return out


def _restar(segs: list[dict], cortes: list[list[float]]) -> list[dict]:
    out = []
    for g in segs:
        piezas = [(g["s"], g["e"], g["corte"])]
        for a, b in cortes:
            nuevas = []
            for s, e, c in piezas:
                if b <= s or a >= e:
                    nuevas.append((s, e, c))
                    continue
                if s < a:
                    nuevas.append((s, a, c))
                if b < e:
                    nuevas.append((b, e, "quitado"))
            piezas = nuevas
        out += [{"s": s, "e": e, "corte": c} for s, e, c in piezas]
    return out


class Mapa:
    """Convierte tiempos del video original al video editado."""

    def __init__(self, segs: list[dict]):
        self.segs = segs
        self.starts = [g["s"] for g in segs]

    def __call__(self, t: float) -> float | None:
        k = bisect_right(self.starts, t) - 1
        if k < 0:
            return None
        g = self.segs[k]
        if t > g["e"] + 1e-6:
            return None
        return g["os"] + (t - g["s"])

    def palabra(self, w: dict) -> tuple[float, float] | None:
        s = self(w["s"])
        if s is None:
            # la palabra empieza dentro de un hueco recortado: usar inicio del siguiente seg
            k = bisect_right(self.starts, w["s"])
            if k >= len(self.segs) or self.segs[k]["s"] > w["e"]:
                return None
            s = self.segs[k]["os"]
        k = bisect_right(self.starts, w["s"]) - 1
        k = max(k, 0)
        g = self.segs[k]
        e = self(w["e"])
        if e is None:
            e = g["oe"]
        return (s, max(e, s + 0.05))

    @property
    def duracion(self) -> float:
        return self.segs[-1]["oe"] if self.segs else 0.0
