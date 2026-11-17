"""Descarga las páginas de Wikipedia y genera los CSV de data/.

    python scripts/actualizar_datos.py            # usa la caché de data/raw si existe
    python scripts/actualizar_datos.py --refrescar  # vuelve a descargar las encuestas (no los resultados)
    python scripts/actualizar_datos.py --todo       # vuelve a descargarlo todo
    python scripts/actualizar_datos.py --solo-encuestas  # baja y procesa solo las encuestas (la Action diaria)

Salidas:
    data/encuestas.csv              una fila por encuesta nacional (estimación de voto y escaños publicados)
    data/encuestas_subnacionales.csv  una fila por encuesta y partido en comunidades y provincias
    data/resultados_2023.csv        votos de 2023 por provincia y candidatura (código de partido)
    data/candidaturas_2026.csv      qué partidos se presentan en cada provincia en 2026
    data/europeas_2024.csv          % por provincia en las europeas de 2024 (para Podemos y SALF)
    data/andaluzas_2026.csv         % por provincia en las andaluzas de 2026 (para Adelante Andalucía)
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import date
from io import StringIO
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
from bs4 import BeautifulSoup

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from partidos import WIKI_COLUMNAS, codigo_candidatura  # noqa: E402

DATA = RAIZ / "data"
RAW = DATA / "raw"
WIKI = "https://en.wikipedia.org/wiki/"

PAGINAS_ENCUESTAS = {
    "encuestas_2026": "Opinion_polling_for_the_2026_Spanish_general_election",
    "encuestas_2023_2024": "Nationwide_opinion_polling_for_the_2026_Spanish_general_election_(2023–2024)",
    "encuestas_subnacionales": "Sub-national_opinion_polling_for_the_2026_Spanish_general_election",
}
PAGINAS_RESULTADOS = {
    "generales_2026": "2026_Spanish_general_election",
    "europeas_2024": "Results_breakdown_of_the_2024_European_Parliament_election_in_Spain",
    "andaluzas_2026": "2026_Andalusian_regional_election",
}
MESES = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}

PROVINCIAS = pd.read_csv(DATA / "provincias.csv", dtype={"cod": str})
WIKI_A_COD = dict(zip(PROVINCIAS.wiki.str.replace("_", " "), PROVINCIAS.cod))
# Nombres de las tablas resumen (europeas, andaluzas): inglés → código INE.
WIKI_A_COD |= {"Seville": "41", "Navarre": "31", "Biscay": "48", "Balearic Islands": "07"}


# --------------------------------------------------------------------------- descarga

def descargar(nombre: str, titulo: str, destino: Path, *, forzar: bool) -> Path:
    if destino.exists() and not forzar:
        return destino
    r = requests.get(WIKI + quote(titulo), headers={"User-Agent": "elecciones-generales-2026/1.0"}, timeout=60)
    r.raise_for_status()
    if "Wikimedia Error" in r.text[:500]:
        raise RuntimeError(f"Wikipedia ha rechazado {titulo} (demasiadas peticiones): espera y repite")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(r.text, encoding="utf-8")
    time.sleep(1.5)
    print(f"  descargado {nombre}")
    return destino


# --------------------------------------------------------------------------- encuestas nacionales

def _num(texto: str) -> float | None:
    m = re.search(r"-?\d+(?:[.,]\d+)?", texto.replace(",", ""))
    return float(m.group()) if m else None


def _celda_partido(texto: str) -> tuple[float | None, float | None, float | None]:
    """'31.8 126/137' → (31.8, 126, 137); '29.7 125' → (29.7, 125, 125); '? 10' → (None, 10, 10)."""
    t = texto.replace("\xa0", " ").strip()
    if not t or t in {"–", "—", "-"}:
        return None, None, None
    partes = t.split()
    pct = _num(partes[0]) if partes[0] not in {"?"} else None
    lo = hi = None
    if len(partes) > 1:
        m = re.match(r"(\d+)(?:/(\d+))?", partes[1])
        if m:
            lo = float(m.group(1))
            hi = float(m.group(2) or m.group(1))
    return pct, lo, hi


def _fin_trabajo_campo(texto: str) -> tuple[int, int] | None:
    """'12–16 Nov' → (16, 11); '27 Dec–3 Jan' → (3, 1); '31 Dec' → (31, 12)."""
    fin = re.split(r"[–-]", texto)[-1].strip()
    m = re.match(r"(\d{1,2})\s+([A-Z][a-z]{2})", fin)
    if not m or m.group(2) not in MESES:
        return None
    return int(m.group(1)), MESES[m.group(2)]


def _cabecera(tabla) -> list[str]:
    nombres = []
    for th in tabla.find("tr").find_all("th"):
        a = th.find("a", title=True)
        texto = a.get_text(" ", strip=True) if a and a.get_text(strip=True) else th.get_text(" ", strip=True)
        # Las columnas de partido llevan un logo: el nombre está en el título del enlace.
        if a and not a.get_text(strip=True):
            texto = a["title"]
        nombres.append(WIKI_COLUMNAS.get(texto, texto))
    return nombres


def _tabla_a_df(tabla) -> pd.DataFrame:
    """Expande rowspan/colspan. Una celda que abarca varios partidos (p. ej. FA+FV juntos) se queda solo en el
    primero y la columna `_combinado` lo anota ("FA+FV"), para no contar el mismo voto dos veces."""
    cabecera = _cabecera(tabla)
    n = len(cabecera)
    pendientes: dict[int, tuple[str, int, int]] = {}  # columna → (texto, filas que quedan, id de celda)
    filas = []
    for tr in tabla.find_all("tr")[1:]:
        celdas = iter(tr.find_all(["td", "th"]))
        fila: list[tuple[str, int]] = []
        col = 0
        while col < n:
            if col in pendientes:
                texto, quedan, ident = pendientes[col]
                fila.append((texto, ident))
                pendientes[col] = (texto, quedan - 1, ident) if quedan > 1 else None
                if pendientes[col] is None:
                    del pendientes[col]
                col += 1
                continue
            celda = next(celdas, None)
            if celda is None:
                break
            texto = re.sub(r"\[[^\]]*\]", "", celda.get_text(" ", strip=True))
            ancho = int(re.sub(r"\D", "", celda.get("colspan", "1")) or 1)
            alto = int(re.sub(r"\D", "", celda.get("rowspan", "1")) or 1)
            for k in range(ancho):
                fila.append((texto, id(celda)))
                if alto > 1:
                    pendientes[col + k] = (texto, alto - 1, id(celda))
            col += ancho
        if len(fila) < 3:
            continue
        fila += [("", 0)] * (n - len(fila))
        textos = [t for t, _ in fila[:n]]
        combinado = []
        for i in range(1, n):
            if fila[i][1] == fila[i - 1][1] and cabecera[i] in WIKI_COLUMNAS.values():
                textos[i] = ""
                if not combinado or combinado[-1][-1] != cabecera[i - 1]:
                    combinado.append([cabecera[i - 1]])
                combinado[-1].append(cabecera[i])
        filas.append(textos + [";".join("+".join(c) for c in combinado)])
    return pd.DataFrame(filas, columns=cabecera + ["_combinado"])


def encuestas_nacionales(html: str, anios: list[int]) -> pd.DataFrame:
    """Lee las tablas de 'Voting intention estimates'. `anios`: año de la fila más reciente de cada tabla."""
    sopa = BeautifulSoup(html, "lxml")
    # Las tablas de estimación son las únicas con columna de participación.
    tablas = [t for t in sopa.select("table.wikitable") if "Turnout" in _cabecera(t)]
    filas = []
    for tabla, anio in zip(tablas, anios):
        df = _tabla_a_df(tabla)
        mes_anterior = None
        for _, fila in df.iterrows():
            firma = re.sub(r"\[[^\]]*\]", "", fila.iloc[0]).strip()
            fecha = _fin_trabajo_campo(fila.get("Fieldwork date", ""))
            if not firma or firma.startswith("Polling firm") or fecha is None:
                continue
            dia, mes = fecha
            if mes_anterior is not None and mes > mes_anterior:
                anio -= 1  # las filas van de la más reciente a la más antigua
            mes_anterior = mes
            resultado = "election" in firma.lower()
            registro = {
                "encuestadora": firma.split("/")[0].strip(),
                "medio": firma.split("/", 1)[1].strip() if "/" in firma else "",
                "fin_campo": date(anio, mes, dia).isoformat(),
                "trabajo_campo": fila.get("Fieldwork date", ""),
                "muestra": _num(fila.get("Sample size", "")) if not resultado else None,
                "participacion": _num(fila.get("Turnout", "")),
                "tipo": "resultado" if resultado else "encuesta",
                "combinado": fila["_combinado"],
            }
            for col in df.columns:
                if col in WIKI_COLUMNAS.values():
                    pct, lo, hi = _celda_partido(fila[col])
                    registro[col] = pct
                    registro[f"{col}_esc_min"] = lo
                    registro[f"{col}_esc_max"] = hi
            filas.append(registro)
    return pd.DataFrame(filas)


# --------------------------------------------------------------------------- encuestas autonómicas/provinciales

def encuestas_subnacionales(html: str) -> pd.DataFrame:
    sopa = BeautifulSoup(html, "lxml")
    filas = []
    for tabla in sopa.select("table.wikitable"):
        h = tabla.find_previous(["h3", "h4"])
        ambito = h.get_text(strip=True) if h else ""
        df = _tabla_a_df(tabla)
        anio, mes_anterior = 2026, None
        for _, fila in df.iterrows():
            firma = re.sub(r"\[[^\]]*\]", "", fila.iloc[0]).strip()
            fecha = _fin_trabajo_campo(fila.get("Fieldwork date", ""))
            if not firma or fecha is None or firma.startswith("Polling firm"):
                continue
            dia, mes = fecha
            if mes_anterior is not None and mes > mes_anterior:
                anio -= 1
            mes_anterior = mes
            for col in df.columns[3:]:
                if col in {"Turnout", "Lead", "_combinado"}:
                    continue
                pct, lo, hi = _celda_partido(fila[col])
                if pct is None and lo is None:
                    continue
                filas.append({
                    "ambito": ambito,
                    "encuestadora": firma.split("/")[0].strip(),
                    "medio": firma.split("/", 1)[1].strip() if "/" in firma else "",
                    "fin_campo": date(anio, mes, dia).isoformat(),
                    "tipo": "resultado" if "election" in firma.lower() else "encuesta",
                    "combinado": fila["_combinado"],
                    "partido": WIKI_COLUMNAS.get(col, col),
                    "pct": pct,
                    "esc_min": lo,
                    "esc_max": hi,
                })
    return pd.DataFrame(filas)


# --------------------------------------------------------------------------- resultados por provincia

def _tablas_resultados(html: str) -> list[pd.DataFrame]:
    tablas = []
    for t in pd.read_html(StringIO(html)):
        if isinstance(t.columns, pd.MultiIndex) and ("Popular vote", "Votes") in t.columns:
            t = t.iloc[:, :7].copy()
            t.columns = ["x", "candidatura", "votos", "pct", "dif", "escanos", "dif_esc"]
            tablas.append(t)
    return tablas


def resultados_circunscripciones() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Primera tabla de cada página = candidaturas de 2026 (sin votos); segunda = resultados de 2023."""
    res, cand = [], []
    for _, prov in PROVINCIAS.iterrows():
        html = (RAW / "circunscripciones" / f"{prov.wiki}.html").read_text(encoding="utf-8")
        t26, t23 = _tablas_resultados(html)[:2]
        for nombre in t26.candidatura.dropna():
            if nombre in {"Total", "Valid votes"} or nombre.startswith(("Invalid", "Votes cast", "Abstentions",
                                                                         "Registered", "Sources", "Footnotes")):
                continue
            cand.append({"cod": prov.cod, "candidatura": re.sub(r"\d+$", "", nombre),
                         "partido": codigo_candidatura(nombre)})
        votos = dict(zip(t23.candidatura.astype(str), pd.to_numeric(t23.votos, errors="coerce")))
        validos = votos["Valid votes"]
        for nombre, v in votos.items():
            if nombre in {"Total", "Valid votes", "nan"} or pd.isna(v) or nombre.startswith(
                    ("Invalid", "Votes cast", "Abstentions", "Registered", "Sources", "Footnotes")):
                continue
            res.append({"cod": prov.cod, "candidatura": re.sub(r"\d+$", "", nombre),
                        "partido": codigo_candidatura(nombre), "votos": int(v)})
        res.append({"cod": prov.cod, "candidatura": "Valid votes", "partido": "_validos", "votos": int(validos)})
        censo = votos.get("Registered voters")
        res.append({"cod": prov.cod, "candidatura": "Registered voters", "partido": "_censo", "votos": int(censo)})
        censo26 = pd.to_numeric(t26.votos, errors="coerce")[t26.candidatura == "Registered voters"]
        if len(censo26) and not pd.isna(censo26.iloc[0]):
            cand.append({"cod": prov.cod, "candidatura": "Registered voters", "partido": "_censo",
                         "censo": int(censo26.iloc[0])})
    return pd.DataFrame(res), pd.DataFrame(cand)


def _tabla_por_circunscripcion(html: str, columna_clave: str, partidos: dict[str, str]) -> pd.DataFrame:
    for t in pd.read_html(StringIO(html)):
        if not isinstance(t.columns, pd.MultiIndex) or t.columns[0][0] != columna_clave:
            continue
        if "Almería" not in t.iloc[:, 0].astype(str).tolist():
            continue
        filas = []
        cols = list(t.columns)
        for _, fila in t.iterrows():
            cod = WIKI_A_COD.get(str(fila.iloc[0]))
            if not cod:
                continue
            for i, c in enumerate(cols):
                if c[-1] == "%" and c[0] in partidos:
                    v = pd.to_numeric(fila.iloc[i], errors="coerce")
                    filas.append({"cod": cod, "partido": partidos[c[0]], "pct": 0.0 if pd.isna(v) else float(v)})
        return pd.DataFrame(filas)
    raise RuntimeError("no encuentro la tabla por circunscripción")


# --------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refrescar", action="store_true", help="vuelve a descargar las encuestas")
    ap.add_argument("--todo", action="store_true", help="vuelve a descargarlo todo")
    ap.add_argument("--solo-encuestas", action="store_true",
                    help="baja de nuevo las encuestas y deja como están los CSV de resultados")
    args = ap.parse_args()

    for nombre, titulo in PAGINAS_ENCUESTAS.items():
        descargar(nombre, titulo, RAW / f"{nombre}.html", forzar=args.refrescar or args.todo or args.solo_encuestas)
    if not args.solo_encuestas:
        resultados(forzar=args.todo)
    encuestas()


def resultados(*, forzar: bool) -> None:
    for nombre, titulo in PAGINAS_RESULTADOS.items():
        descargar(nombre, titulo, RAW / f"{nombre}.html", forzar=forzar)
    for wiki in PROVINCIAS.wiki:
        descargar(wiki, f"{wiki}_(Congress_of_Deputies_constituency)", RAW / "circunscripciones" / f"{wiki}.html",
                  forzar=forzar)

    res, cand = resultados_circunscripciones()
    res.to_csv(DATA / "resultados_2023.csv", index=False)
    cand.to_csv(DATA / "candidaturas_2026.csv", index=False)
    print(f"resultados_2023.csv: {res[res.partido == '_validos'].votos.sum():,} votos válidos")

    eu = _tabla_por_circunscripcion((RAW / "europeas_2024.html").read_text(encoding="utf-8"), "Constituency",
                                    {"PP": "PP", "PSOE": "PSOE", "Vox": "Vox", "Sumar": "Sumar",
                                     "SALF": "SALF", "Podemos": "Podemos"})
    eu.to_csv(DATA / "europeas_2024.csv", index=False)
    an = _tabla_por_circunscripcion((RAW / "andaluzas_2026.html").read_text(encoding="utf-8"), "Constituency",
                                    {"AA": "AA"})
    an.to_csv(DATA / "andaluzas_2026.csv", index=False)
    print(f"europeas_2024.csv: {eu.cod.nunique()} provincias; andaluzas_2026.csv: {an.cod.nunique()} provincias")


def encuestas() -> None:
    enc = pd.concat([
        encuestas_nacionales((RAW / "encuestas_2026.html").read_text(encoding="utf-8"), [2026, 2026, 2025]),
        encuestas_nacionales((RAW / "encuestas_2023_2024.html").read_text(encoding="utf-8"), [2024, 2023]),
    ], ignore_index=True)
    enc = enc.drop_duplicates(subset=["encuestadora", "medio", "fin_campo", "PP", "PSOE"])
    enc.sort_values("fin_campo", ascending=False).to_csv(DATA / "encuestas.csv", index=False)
    print(f"encuestas.csv: {len(enc)} filas ({enc.fin_campo.min()} → {enc.fin_campo.max()})")

    sub = encuestas_subnacionales((RAW / "encuestas_subnacionales.html").read_text(encoding="utf-8"))
    sub.to_csv(DATA / "encuestas_subnacionales.csv", index=False)
    print(f"encuestas_subnacionales.csv: {len(sub)} filas, {sub.ambito.nunique()} ámbitos")


if __name__ == "__main__":
    main()
