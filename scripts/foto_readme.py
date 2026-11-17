"""Reescribe en el README la foto del día (promedio, escaños y últimos escaños más ajustados).

    python scripts/foto_readme.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import modelo  # noqa: E402
from graficos import nombre  # noqa: E402
from partidos import BLOQUES, MAYORIA  # noqa: E402

INICIO, FIN = "<!-- foto:inicio -->", "<!-- foto:fin -->"


def foto() -> str:
    pr = modelo.promedio()
    voto = modelo.completar(pr.voto)
    votos = modelo.votos_estimados(modelo.proyectar(voto))
    esc, fr = modelo.escanos(votos)
    total = esc.sum()
    sim = modelo.simular(voto, pr.dispersion, n=3000)
    pp_vox = sim[BLOQUES["PP + Vox"]].sum(axis=1)
    desde, hasta = pr.encuestas.fin_campo.min(), pr.encuestas.fin_campo.max()

    lineas = [
        f"## Foto a {hasta:%d/%m/%Y}",
        "",
        f"Promedio de {len(pr.encuestas)} encuestadoras ({desde:%d/%m}–{hasta:%d/%m}), traslado proporcional:",
        "",
        "| Partido | Voto % | Escaños |",
        "|---|---:|---:|",
    ]
    for p in total.sort_values(ascending=False).index:
        if total[p] > 0 or voto[p] >= 1:
            lineas.append(f"| {nombre(p)} | {voto[p]:.1f} | {total[p]} |")
    lineas += [
        "",
        f"PP + Vox suman {int(total[BLOQUES['PP + Vox']].sum())} (mediana de la simulación: {int(pp_vox.median())}; "
        f"≥{MAYORIA} en el {(pp_vox >= MAYORIA).mean():.0%} de las simulaciones).".replace("%", " %"),
        "",
        "Últimos escaños más ajustados:",
        "",
        "| Provincia | Último escaño | Rival | Le faltan (votos) | (pp) |",
        "|---|---|---|---:|---:|",
    ]
    for _, r in fr.sort_values("faltan_pp").head(8).iterrows():
        lineas.append(f"| {r.provincia} | {nombre(r.ultimo)} | {nombre(r.rival)} | "
                      f"{r.faltan_votos:,.0f} | {r.faltan_pp:.2f} |".replace(",", "."))
    return "\n".join(lineas)


def main() -> None:
    readme = RAIZ / "README.md"
    texto = readme.read_text(encoding="utf-8")
    nuevo = re.sub(f"{INICIO}.*?{FIN}", f"{INICIO}\n{foto()}\n{FIN}", texto, flags=re.S)
    readme.write_text(nuevo, encoding="utf-8")


if __name__ == "__main__":
    main()
