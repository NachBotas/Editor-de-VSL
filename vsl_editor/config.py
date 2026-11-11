"""Configuración por defecto del editor de VSL.

Todo se puede sobreescribir desde la CLI o guardándolo en el plan.json
(clave "config") para que el render use exactamente lo mismo que el análisis.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONTS_DIR = ASSETS / "fonts"
SFX_DIR = ASSETS / "sfx"
RNNOISE_MODEL = ASSETS / "rnnoise" / "sh.rnnn"
LUTS_DIR = ASSETS / "luts"

# Ritmo de edición: cuánto silencio se deja entre frases.
RITMOS = {
    #            pausa_max  pad_antes pad_despues
    "rapido":   (0.30, 0.07, 0.10),
    "normal":   (0.45, 0.10, 0.15),
    "relajado": (0.70, 0.14, 0.22),
}

PALABRAS_CLAVE_ES = [
    "gratis", "secreto", "secretos", "garantia", "garantizado", "garantizada",
    "dinero", "resultados", "resultado", "nunca", "siempre", "error", "errores",
    "problema", "solucion", "metodo", "sistema", "descubre", "descubrir",
    "increible", "exclusivo", "exclusiva", "oferta", "descuento", "bono", "bonus",
    "regalo", "rapido", "facil", "comprobado", "probado", "importante", "atencion",
    "cuidado", "verdad", "mentira", "millones", "miles", "libertad", "ahora",
]


@dataclass
class Config:
    # Transcripción
    modelo: str = "small"            # tiny | base | small | medium | large-v3
    idioma: str = "es"

    # Cortes
    ritmo: str = "normal"
    pausa_max: float | None = None   # si es None se toma del ritmo
    pad_antes: float | None = None
    pad_despues: float | None = None
    quitar_muletillas: bool = True
    quitar_repeticiones: bool = True
    quitar_tomas_falsas: bool = True
    umbral_toma: int = 80            # similitud (0-100) para considerar "toma repetida"

    # Audio
    limpieza_audio: str = "estandar"  # ninguna | suave | estandar | fuerte
    lufs: float = -16.0
    musica: str | None = None        # ruta a un mp3/wav, o un estilo generado: "mistica", "mistica432"
    musica_db: float = -24.0         # volumen de la música bajo la voz

    # Video / color
    color: str = "natural"           # ninguno | natural | calido | frio | cine | punch
    lut: str | None = None
    denoise_video: bool = False
    nitidez: bool = True

    # Animaciones
    zoom: bool = True
    zoom_nivel: float = 1.08         # punch-in en cortes
    zoom_enfasis: float = 1.16       # zoom en palabras clave
    zoom_centro_y: float = 0.40      # 0 = arriba, 0.5 = centro (la cara suele estar arriba)
    zoom_intervalo_min: float = 2.5
    enfasis_intervalo_min: float = 7.0
    fundido: bool = True

    # Slides explicativas (escenas.json)
    slides: bool = True

    # Subtítulos
    subtitulos: bool = True
    sub_estilo: str = "simple"       # simple | pop | caja
    sub_mayusculas: bool = False
    sub_max_palabras: int = 6
    sub_max_caracteres: int = 34
    sub_color_resaltado: str = "FFD400"  # RGB hex de las palabras clave

    # Efectos de sonido
    sfx: bool = True
    sfx_en_cortes: bool = False
    sfx_db: float = 0.0              # ganancia extra para TODOS los efectos (+6 = el doble de fuerte)      # whoosh suave en cada cambio de zoom
    palabras_clave: list[str] = field(default_factory=lambda: list(PALABRAS_CLAVE_ES))

    # Render
    crf: int = 18
    preset: str = "medium"
    preview: bool = False

    def resolver_ritmo(self) -> tuple[float, float, float]:
        base = RITMOS.get(self.ritmo, RITMOS["normal"])
        return (
            self.pausa_max if self.pausa_max is not None else base[0],
            self.pad_antes if self.pad_antes is not None else base[1],
            self.pad_despues if self.pad_despues is not None else base[2],
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        validos = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**validos)
