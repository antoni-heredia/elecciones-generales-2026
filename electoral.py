"""Reglas del Congreso: barrera del 3 % por circunscripción y D'Hondt, y quién se juega el último escaño."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from partidos import BLANCO, OTROS

UMBRAL = 0.03  # sobre votos válidos (incluye el voto en blanco), art. 163 LOREG
NO_ASIGNABLES = frozenset({OTROS, BLANCO})


def elegibles(votos: Mapping[str, float], umbral: float = UMBRAL) -> dict[str, float]:
    total = sum(max(0.0, v) for v in votos.values())
    if total <= 0:
        return {}
    return {p: v for p, v in votos.items() if p not in NO_ASIGNABLES and v > 0 and v / total >= umbral}


def dhondt(votos: Mapping[str, float], escanos: int) -> dict[str, int]:
    """Reparto D'Hondt. Los empates se resuelven a favor de quien tiene más votos (como la LOREG)."""
    ganados = {p: 0 for p in votos}
    for _ in range(escanos):
        mejor = max(votos, key=lambda p: (votos[p] / (ganados[p] + 1), votos[p]), default=None)
        if mejor is None:
            break
        ganados[mejor] += 1
    return ganados


@dataclass
class Frontera:
    """El último escaño que se reparte y el primero que se queda fuera en una circunscripción."""

    ultimo: str | None  # partido que se lleva el último escaño
    siguiente: str | None  # partido al que le tocaría el siguiente
    cociente_ultimo: float
    cociente_siguiente: float
    # Votos que le faltan a cada partido elegible (o casi) para quitarle el último escaño a otro.
    faltan: dict[str, float]
    # Votos que puede perder quien tiene el último escaño antes de perderlo.
    colchon: float


def frontera(votos: Mapping[str, float], escanos: int, umbral: float = UMBRAL) -> tuple[dict[str, int], Frontera]:
    total = sum(max(0.0, v) for v in votos.values())
    el = elegibles(votos, umbral)
    reparto = dhondt(el, escanos)
    cocientes = sorted(
        ((el[p] / k, p, k) for p in el for k in range(1, escanos + 2)), reverse=True
    )
    if not cocientes:
        return reparto, Frontera(None, None, 0.0, 0.0, {}, 0.0)
    q_ult, ultimo, s_ult = cocientes[escanos - 1]
    q_sig, siguiente, _ = cocientes[escanos] if len(cocientes) > escanos else (0.0, None, 0)
    # El rival que está más cerca de quitarle el último escaño (otro partido distinto).
    q_rival = next((q for q, p, _ in cocientes[escanos:] if p != ultimo), 0.0)

    faltan = {}
    for p, v in votos.items():
        if p in NO_ASIGNABLES or p == ultimo:
            continue
        s = reparto.get(p, 0)
        necesarios = q_ult * (s + 1) - v
        # Fuera de la barrera también hay que llegar al 3 % (con el total ya incrementado).
        if p not in el:
            necesarios = max(necesarios, (umbral * total - v) / (1 - umbral))
        faltan[p] = max(0.0, necesarios)
    colchon = el[ultimo] - q_rival * s_ult if ultimo else 0.0
    return reparto, Frontera(ultimo, siguiente, q_ult, q_sig, faltan, max(0.0, colchon))


def dhondt_matriz(votos: np.ndarray, escanos: int, umbral: float = UMBRAL,
                  asignable: np.ndarray | None = None) -> np.ndarray:
    """D'Hondt vectorizado para la simulación. `votos`: (n_sim, n_partidos) en cuota; devuelve escaños."""
    n_sim, n_par = votos.shape
    total = votos.sum(axis=1, keepdims=True)
    ok = votos / np.where(total > 0, total, 1) >= umbral
    if asignable is not None:
        ok &= asignable[None, :]
    v = np.where(ok, votos, 0.0)
    esc = np.zeros((n_sim, n_par), dtype=np.int16)
    filas = np.arange(n_sim)
    for _ in range(escanos):
        q = v / (esc + 1)
        esc[filas, q.argmax(axis=1)] += 1
    return esc
