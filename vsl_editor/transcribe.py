"""Transcripción con marcas de tiempo por palabra (faster-whisper)."""
from __future__ import annotations

import os
from pathlib import Path

# El prompt con muletillas hace que Whisper las transcriba en vez de "limpiarlas",
# así podemos detectarlas y cortarlas.
PROMPTS = {
    "es": "Eh... bueno, mmm, entonces, este... o sea, eh, vamos a ver. Mmm, ¿vale? Eh.",
    "en": "Um, uh... so, like, you know, um, I mean... uh, okay.",
}


def _dispositivo() -> tuple[str, str]:
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def transcribir(wav: str | Path, modelo: str = "small", idioma: str = "es") -> list[dict]:
    from faster_whisper import WhisperModel

    device, compute = _dispositivo()
    print(f"  · Whisper '{modelo}' en {device} ({compute})")
    model = WhisperModel(modelo, device=device, compute_type=compute,
                         cpu_threads=os.cpu_count() or 4)
    from .media import leer_audio
    audio = leer_audio(wav, 16000)   # decodificamos con ffmpeg (evita depender de PyAV)
    segmentos, info = model.transcribe(
        audio,
        language=idioma,
        word_timestamps=True,
        beam_size=5,
        condition_on_previous_text=False,   # evita bucles y que "corrija" repeticiones
        initial_prompt=PROMPTS.get(idioma),
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400, "speech_pad_ms": 200},
    )
    palabras: list[dict] = []
    ultimo = 0.0
    for seg in segmentos:
        for w in seg.words or []:
            texto = w.word.strip()
            if not texto or not any(c.isalnum() for c in texto):
                continue
            palabras.append({
                "w": texto,
                "s": round(float(w.start), 3),
                "e": round(float(max(w.end, w.start + 0.02)), 3),
                "p": round(float(w.probability), 3),
            })
        if seg.end - ultimo >= 60:
            print(f"  · transcrito hasta {seg.end / 60:.1f} min", flush=True)
            ultimo = seg.end
    # Garantiza orden y que no se solapen
    palabras.sort(key=lambda x: x["s"])
    for a, b in zip(palabras, palabras[1:]):
        if a["e"] > b["s"]:
            a["e"] = max(a["s"] + 0.02, b["s"])
    return palabras
