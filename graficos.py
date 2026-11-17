"""Hemiciclo y mapa de provincias (Plotly)."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from partidos import COLORES, ORDEN, PARTIDOS

DATA = Path(__file__).resolve().parent / "data"
# Canarias se dibuja al suroeste de la Península, como en los mapas electorales habituales.
DESPLAZAMIENTO_CANARIAS = (6.5, 7.6)
TRANSPARENTE = dict(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")


def nombre(p: str) -> str:
    return PARTIDOS.get(p, {}).get("nombre", p)


# --------------------------------------------------------------------------- hemiciclo

def _asientos(n: int, filas: int) -> list[tuple[float, float]]:
    radios = [0.42 + 0.58 * k / (filas - 1) for k in range(filas)]
    total_r = sum(radios)
    por_fila = [round(n * r / total_r) for r in radios]
    por_fila[-1] += n - sum(por_fila)
    puntos = []
    for r, m in zip(radios, por_fila):
        for j in range(m):
            ang = math.pi * (1 - j / (m - 1)) if m > 1 else math.pi / 2
            puntos.append((ang, r))
    puntos.sort(key=lambda a: (-a[0], a[1]))
    return [(r * math.cos(a), r * math.sin(a)) for a, r in puntos]


def hemiciclo(escanos: dict[str, int], titulo: str = "") -> go.Figure:
    orden = [p for p in ORDEN if escanos.get(p, 0) > 0]
    lista = [p for p in orden for _ in range(int(escanos[p]))]
    pos = _asientos(len(lista), 12)
    fig = go.Figure()
    for p in orden:
        idx = [i for i, q in enumerate(lista) if q == p]
        fig.add_trace(go.Scatter(
            x=[pos[i][0] for i in idx], y=[pos[i][1] for i in idx], mode="markers",
            marker=dict(size=7.5, color=COLORES[p], line=dict(width=0)),
            name=f"{nombre(p)} · {escanos[p]}", hovertemplate=f"{nombre(p)}: {escanos[p]} escaños<extra></extra>",
        ))
    fig.add_annotation(x=0, y=0.08, text=f"<b>{sum(escanos.values())}</b>", showarrow=False, font=dict(size=22))
    fig.add_annotation(x=0, y=-0.02, text="mayoría: 176", showarrow=False, font=dict(size=12))
    fig.update_layout(
        title=titulo, height=380, margin=dict(l=0, r=0, t=30 if titulo else 0, b=0),
        xaxis=dict(visible=False, scaleanchor="y", fixedrange=True), yaxis=dict(visible=False, fixedrange=True),
        legend=dict(orientation="h", y=-0.05), **TRANSPARENTE,
    )
    return fig


# --------------------------------------------------------------------------- mapa

@lru_cache
def geojson() -> dict:
    g = json.loads((DATA / "provincias.geojson").read_text(encoding="utf-8"))
    dx, dy = DESPLAZAMIENTO_CANARIAS

    def mover(coords):
        if isinstance(coords[0], (int, float)):
            return [coords[0] + dx, coords[1] + dy]
        return [mover(c) for c in coords]

    for f in g["features"]:
        f["id"] = f["properties"]["cod_prov"]
        if f["id"] in {"35", "38"}:
            f["geometry"]["coordinates"] = mover(f["geometry"]["coordinates"])
    return g


@lru_cache
def centroides() -> dict[str, tuple[float, float]]:
    out = {}
    for f in geojson()["features"]:
        pts = []

        def recoger(c):
            if isinstance(c[0], (int, float)):
                pts.append(c)
            else:
                for x in c:
                    recoger(x)

        recoger(f["geometry"]["coordinates"])
        out[f["id"]] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    return out


def _marco(fig: go.Figure) -> None:
    fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator")
    # Recuadro de Canarias.
    dx, dy = DESPLAZAMIENTO_CANARIAS
    x0, x1, y0, y1 = -18.4 + dx, -13.2 + dx, 27.5 + dy, 29.6 + dy
    fig.add_trace(go.Scattergeo(lon=[x0, x1, x1, x0, x0], lat=[y0, y0, y1, y1, y0], mode="lines",
                                line=dict(width=1, color="#999"), hoverinfo="skip", showlegend=False))
    fig.update_layout(height=680, margin=dict(l=0, r=0, t=0, b=0), **TRANSPARENTE,
                      geo=dict(bgcolor="rgba(0,0,0,0)"))


def mapa_categorico(df: pd.DataFrame, columna: str, hover: pd.Series, leyenda: str = "") -> go.Figure:
    """Pinta cada provincia del color del partido de `columna`. `df` indexado por código INE."""
    fig = go.Figure()
    g = geojson()
    cen = centroides()
    for p in [p for p in ORDEN if p in set(df[columna])]:
        sub = df[df[columna] == p]
        fig.add_trace(go.Choropleth(
            geojson=g, locations=sub.index, z=[1] * len(sub), colorscale=[[0, COLORES[p]], [1, COLORES[p]]],
            showscale=False, marker_line_color="white", marker_line_width=0.6,
            text=hover.reindex(sub.index), hovertemplate="%{text}<extra></extra>", showlegend=False,
        ))
        # Los choropleth no salen en la leyenda: un punto vacío por partido.
        fig.add_trace(go.Scattergeo(lon=[None], lat=[None], mode="markers", name=f"{nombre(p)} · {len(sub)}",
                                    marker=dict(size=12, symbol="square", color=COLORES[p])))
    # Ceuta y Melilla son muy pequeñas: un punto encima para que se vean.
    pequenas = [c for c in ("51", "52") if c in df.index]
    fig.add_trace(go.Scattergeo(
        lon=[cen[c][0] for c in pequenas], lat=[cen[c][1] for c in pequenas], mode="markers",
        marker=dict(size=11, color=[COLORES.get(df.loc[c, columna], "#ccc") for c in pequenas],
                    line=dict(width=1, color="white")),
        text=hover.reindex(pequenas), hovertemplate="%{text}<extra></extra>", showlegend=False,
    ))
    _marco(fig)
    fig.update_layout(legend=dict(title=leyenda, orientation="h", y=0.02, x=0.5, xanchor="center"))
    return fig


def mapa_continuo(valores: pd.Series, hover: pd.Series, color: str, titulo: str) -> go.Figure:
    g = geojson()
    cen = centroides()
    fig = go.Figure(go.Choropleth(
        geojson=g, locations=valores.index, z=valores.values, colorscale=[[0, "#f4f4f4"], [1, color]],
        zmin=0, marker_line_color="white", marker_line_width=0.6, text=hover.reindex(valores.index),
        hovertemplate="%{text}<extra></extra>", colorbar=dict(title=titulo, thickness=12, len=0.6),
    ))
    pequenas = [c for c in ("51", "52") if c in valores.index]
    fig.add_trace(go.Scattergeo(
        lon=[cen[c][0] for c in pequenas], lat=[cen[c][1] for c in pequenas], mode="markers",
        marker=dict(size=11, color=valores.reindex(pequenas), colorscale=[[0, "#f4f4f4"], [1, color]],
                    cmin=0, cmax=float(valores.max() or 1), line=dict(width=1, color="#888")),
        text=hover.reindex(pequenas), hovertemplate="%{text}<extra></extra>", showlegend=False,
    ))
    _marco(fig)
    return fig
