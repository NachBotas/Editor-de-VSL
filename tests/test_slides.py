"""Tests del motor de slides (sin video)."""
from vsl_editor.slides import RenderEscena, construir_escena, parsear, preparar_contador


def mt(v, fin=False):
    return float(v)


def test_marcado():
    runs = parsear("Gana **dinero** con __IA__ y ~~sin~~ ==éxito== !!no!!")
    estilos = {t: s for t, s in runs}
    assert estilos["dinero"]["bold"]
    assert estilos["IA"]["ul"]
    assert estilos["sin"]["tach"]


def test_contador():
    valor, fmt = preparar_contador("$25.000.000")
    assert valor == 25_000_000
    assert fmt(1234567) == "$1.234.567"
    assert preparar_contador("$1K-$4K") is None


def test_todas_las_escenas_renderizan():
    escenas = [
        {"tipo": "frase", "desde": 0, "hasta": 3, "emoji": "💰", "texto": "Gana __dinero__", "nota": "hoy"},
        {"tipo": "lista", "desde": 0, "hasta": 3, "titulo": "Sin:", "items": [{"texto": "**a**"}, {"texto": "b"}]},
        {"tipo": "flujo", "desde": 0, "hasta": 3, "nodos": [{"emoji": "🧠", "texto": "A"}, {"emoji": "💸", "texto": "B"}]},
        {"tipo": "cifra", "desde": 0, "hasta": 3, "valor": "10.000", "antes": "Más de"},
        {"tipo": "pasos", "desde": 0, "hasta": 3, "pasos": [{"texto": "Uno"}, {"texto": "Dos"}]},
        {"tipo": "comparacion", "desde": 0, "hasta": 3, "izq": {"titulo": "Mal", "items": ["x"]},
         "der": {"titulo": "Bien", "items": ["y"]}},
    ]
    for W, H in ((1920, 1080), (1080, 1920)):
        for esc in escenas:
            elems, t0, t1 = construir_escena(esc, W, H, mt)
            assert elems, esc["tipo"]
            r = RenderEscena(elems, t0, t1, W, H)
            for t in (0.0, 0.1, 1.5, 2.95):
                im = r.frame(t)
                assert im.size == (W, H)


def test_curva_zoom_fluida():
    """Los zooms entran y salen con rampa suave; con "suave": false, de golpe."""
    import re
    from vsl_editor.config import Config
    from vsl_editor.render import curva_zoom
    fx = {"zooms": [{"s": 2, "e": 5, "nivel": 1.1}],
          "manuales": [{"s": 7, "e": 9, "nivel": 1.5, "cx": 0.3, "cy": 0.3, "suave": False}]}
    f = curva_zoom(fx, Config(), 30.0, 10.0)
    x0 = re.search(r"x0='([^']*)'", f).group(1)
    reg = {}
    env = dict(gte=lambda a, b: float(a >= b), lt=lambda a, b: float(a < b),
               clip=lambda v, a, b: min(max(v, a), b), W=1920, H=1080,
               st=lambda i, v: reg.__setitem__(int(i), v) or v, ld=lambda i: reg[int(i)])

    def z(n):
        for p in x0.split(";")[:-1]:
            eval(p.replace("in", "IN"), {}, {**env, "IN": n})
        return reg[0]
    assert z(60) == 1.0 and abs(z(78) - 1.1) < 1e-6          # 2.0 s -> 2.6 s
    assert 1.0 < z(66) < 1.1                                  # a mitad de la rampa
    assert z(209) == 1.0 and abs(z(211) - 1.5) < 1e-6         # instantáneo
