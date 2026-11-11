"""Tests del detector de cortes (no necesitan Whisper ni video)."""
from vsl_editor.config import Config
from vsl_editor.cutplan import Mapa, construir_segmentos, marcar


def frase(texto, t0, dur_palabra=0.3, gap=0.05):
    ws, t = [], t0
    for w in texto.split():
        ws.append({"w": w, "s": round(t, 3), "e": round(t + dur_palabra, 3), "p": 1.0})
        t += dur_palabra + gap
    return ws, t


def construir(*partes):
    ws, t = [], 0.0
    for p in partes:
        if isinstance(p, float):
            t += p
            continue
        f, t = frase(p, t)
        ws += f
    return ws


def quitadas(ws):
    return " ".join(w["w"] for w in ws if not w["keep"])


def test_toma_repetida_conserva_la_ultima():
    ws = construir("hoy te voy a mostrar el método", 1.0, "hoy te voy a mostrar el método que uso.")
    marcar(ws, Config())
    assert quitadas(ws) == "hoy te voy a mostrar el método"


def test_retoma_con_perdon():
    ws = construir("la mayoría comete un error", 0.8, "perdón", 0.8,
                   "la mayoría comete un error muy grave.")
    marcar(ws, Config())
    assert quitadas(ws) == "la mayoría comete un error perdón"


def test_muletillas_y_tartamudeo():
    ws = construir("y lo mejor es que que funciona", 0.6, "eh", 0.6, "siempre.")
    marcar(ws, Config())
    assert quitadas(ws) == "que eh"


def test_frases_distintas_no_se_cortan():
    ws = construir("Esto es importante.", 0.5, "Esto es lo que necesitas saber.")
    marcar(ws, Config())
    assert quitadas(ws) == ""


def test_segmentos_alineados_y_mapa():
    ws = construir("hola a todos.", 2.0, "bienvenidos al video.")
    marcar(ws, Config())
    segs = construir_segmentos(ws, 10.0, 30.0, Config())
    assert len(segs) == 2                      # el silencio de 2 s se corta
    for g in segs:
        assert abs(g["s"] * 30 - round(g["s"] * 30)) < 1e-6
    m = Mapa(segs)
    assert m.duracion < 10.0 - 1.5
    assert m(ws[0]["s"]) is not None


def test_repeticiones_retoricas_se_conservan():
    for texto in ["eso es increíble. increíble. increíble.", "trabajé horas y horas en esto",
                  "es muy muy fácil", "nunca, nunca te rindas"]:
        ws = construir(texto)
        marcar(ws, Config())
        assert quitadas(ws) == "", texto


def test_anafora_no_es_toma_repetida():
    ws, t = frase("la forma en que compramos,", 0.0)
    ws2, _ = frase("la forma en que trabajamos.", t + 0.1)
    ws = ws + ws2
    marcar(ws, Config())
    assert quitadas(ws) == ""


def test_contraste_y_paralelos_se_conservan():
    casos = [
        ("lo difícil no es conseguir clientes.", "lo difícil es conseguir que te respondan."),
        ("tiene las variaciones del gancho.", "tiene las variaciones del cierre."),
    ]
    for a, b in casos:
        ws, t = frase(a, 0.0)
        ws2, _ = frase(b, t + 0.05)
        ws = ws + ws2
        marcar(ws, Config())
        assert quitadas(ws) == "", (a, b)


def test_reinicio_con_titubeo_se_corta():
    ws, t = frase("lo que te quiero", 0.0)
    ws2, _ = frase("lo que te voy a decir hoy.", t + 0.3)
    ws = ws + ws2
    marcar(ws, Config())
    assert quitadas(ws) == "lo que te quiero"
