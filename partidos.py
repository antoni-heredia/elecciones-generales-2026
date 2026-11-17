"""Partidos de las generales de 2026: códigos, nombres, colores y cómo se reconocen en las fuentes."""

from __future__ import annotations

import re

# Orden izquierda → derecha (aprox.) para el hemiciclo y las tablas.
PARTIDOS: dict[str, dict[str, str]] = {
    "Podemos": {"nombre": "Podemos", "color": "#6b2e68"},
    "Bildu": {"nombre": "EH Bildu", "color": "#a4c400"},
    "BNG": {"nombre": "BNG", "color": "#76b3dd"},
    "FA": {"nombre": "Frente Amplio", "color": "#e51c55"},
    "FV": {"nombre": "Compromís: Front Valencià", "color": "#f28c00"},
    "ERC": {"nombre": "ERC", "color": "#ffb232"},
    "AA": {"nombre": "Adelante Andalucía", "color": "#0e9e57"},
    "PSOE": {"nombre": "PSOE", "color": "#e30613"},
    "PNV": {"nombre": "PNV", "color": "#1f6b2a"},
    "Junts": {"nombre": "Junts", "color": "#00c7ae"},
    "CC": {"nombre": "Coalición Canaria", "color": "#f6d000"},
    "PP": {"nombre": "PP", "color": "#1d84ce"},
    "SALF": {"nombre": "Se Acabó La Fiesta", "color": "#4a4a4a"},
    "Vox": {"nombre": "Vox", "color": "#63be21"},
}
OTROS = "Otros"
BLANCO = "Blanco"
ORDEN = list(PARTIDOS)
COLORES = {p: d["color"] for p, d in PARTIDOS.items()} | {OTROS: "#bdbdbd", BLANCO: "#e0e0e0"}

# Bloques para sumar escaños (176 = mayoría absoluta).
BLOQUES: dict[str, list[str]] = {
    "PP + Vox": ["PP", "Vox"],
    "PP + Vox + SALF": ["PP", "Vox", "SALF"],
    "PP + Vox + SALF + CC": ["PP", "Vox", "SALF", "CC"],
    "Investidura de 2023": ["PSOE", "FA", "FV", "Podemos", "ERC", "Junts", "Bildu", "PNV", "BNG", "CC"],
    "PSOE + izquierda y nacionalistas (sin Junts)": [
        "PSOE", "FA", "FV", "Podemos", "ERC", "Bildu", "PNV", "BNG", "AA",
    ],
}
MAYORIA = 176

# Cabeceras de las tablas de Wikipedia (título del enlace del logo) → código.
WIKI_COLUMNAS = {
    "PP": "PP",
    "PSOE": "PSOE",
    "Vox": "Vox",
    "FA": "FA",
    "FV": "FV",
    "Sumar": "Sumar",
    "ERC": "ERC",
    "Junts": "Junts",
    "EH Bildu": "Bildu",
    "PNV": "PNV",
    "BNG": "BNG",
    "CCa": "CC",
    "UPN": "UPN",
    "Adelante Andalucía (2021)": "AA",
    "Podemos": "Podemos",
    "Se Acabó La Fiesta": "SALF",
    "Aliança.cat": "AC",
}

# Candidaturas por circunscripción (nombre largo de Wikipedia) → código. El orden importa: primera que encaje.
_CANDIDATURAS: list[tuple[str, str]] = [
    (r"Blank ballots", BLANCO),
    (r"\bUPN[–-]PP\b", "PP"),
    (r"Navarrese People's Union", "UPN"),
    (r"\(PP\)", "PP"),
    (r"PSOE|\bPSC\b", "PSOE"),
    (r"\(Vox\)", "Vox"),
    (r"Valencian Front", "FV"),
    (r"Broad Front|Front Ampli|Frente Amplio|Aramés|Canarian People's Unity", "FA"),
    (r"\(Podemos\)", "Podemos"),
    (r"\(SALF\)", "SALF"),
    (r"Adelante Andalucía|Forward Andalusia", "AA"),
    (r"\(ERC", "ERC"),
    (r"\(JxCat\)|\(Junts\)", "Junts"),
    (r"EH Bildu", "Bildu"),
    (r"PNV|Basque Nationalist Party", "PNV"),
    (r"\(BNG\)|Galician Nationalist Bloc", "BNG"),
    (r"CCa\)|Canarian Coalition", "CC"),
    (r"New Canaries", "NC"),
    # 2023: Sumar se presentó con varias marcas (Sumar–ECP, Sumar–Compromís, Més–Sumar, Sumar Canarias…).
    (r"Sumar", "Sumar"),
]


def codigo_candidatura(nombre: str) -> str:
    for patron, codigo in _CANDIDATURAS:
        if re.search(patron, nombre):
            return codigo
    return OTROS
