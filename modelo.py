"""De las encuestas nacionales a votos y escaños por provincia.

1. Promedio de encuestas: la última de cada encuestadora dentro de una ventana, ponderada por tamaño de muestra y
   antigüedad.
2. Base provincial: resultado de 2023 adaptado a las candidaturas de 2026 (Sumar se reparte entre Frente Amplio,
   Podemos y Compromís; SALF sale de las europeas de 2024 y Adelante Andalucía de las andaluzas de 2026).
3. Traslado a provincias: cada partido mantiene su "forma" territorial de la base y se escala hasta sumar el
   promedio nacional (proporcional), o se suma la misma diferencia en todas sus provincias (uniforme).
4. D'Hondt con barrera del 3 % en cada circunscripción.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from electoral import dhondt_matriz, frontera
from partidos import BLANCO, ORDEN, OTROS

DATA = Path(__file__).resolve().parent / "data"
COLUMNAS = ORDEN + [OTROS, BLANCO]


# --------------------------------------------------------------------------- datos

@lru_cache
def provincias() -> pd.DataFrame:
    return pd.read_csv(DATA / "provincias.csv", dtype={"cod": str}).set_index("cod")


@lru_cache
def encuestas() -> pd.DataFrame:
    df = pd.read_csv(DATA / "encuestas.csv", parse_dates=["fin_campo"])
    return df


@lru_cache
def encuestas_subnacionales() -> pd.DataFrame:
    return pd.read_csv(DATA / "encuestas_subnacionales.csv", parse_dates=["fin_campo"])


@lru_cache
def candidaturas() -> pd.DataFrame:
    return pd.read_csv(DATA / "candidaturas_2026.csv", dtype={"cod": str})


@lru_cache
def base_provincial() -> pd.DataFrame:
    """Votos de referencia por provincia (filas) y partido de 2026 (columnas), sobre el censo de votos de 2023."""
    res = pd.read_csv(DATA / "resultados_2023.csv", dtype={"cod": str})
    eu = pd.read_csv(DATA / "europeas_2024.csv", dtype={"cod": str}).pivot(index="cod", columns="partido",
                                                                            values="pct").fillna(0) / 100
    an = pd.read_csv(DATA / "andaluzas_2026.csv", dtype={"cod": str}).set_index("cod").pct / 100
    v23 = res[~res.partido.str.startswith("_")].pivot_table(index="cod", columns="partido", values="votos",
                                                            aggfunc="sum").fillna(0)
    validos = res[res.partido == "_validos"].set_index("cod").votos
    corren = candidaturas().groupby("cod").partido.apply(set)

    filas = {}
    for cod in provincias().index:
        v = v23.loc[cod]
        presentes = corren.get(cod, set())
        b = dict.fromkeys(COLUMNAS, 0.0)
        for p in ["PP", "PSOE", "Vox", "ERC", "Junts", "Bildu", "PNV", "BNG", "CC"]:
            b[p] = v.get(p, 0.0)
        b["PP"] += v.get("UPN", 0.0)  # en 2026 van juntos en Navarra (UPN–PP)
        # Sumar de 2023 (y Nueva Canarias, que en 2026 va en la UPC con Sumar y Podemos).
        izq = v.get("Sumar", 0.0) + v.get("NC", 0.0)
        if "FV" in presentes:
            b["FV"] = izq
        elif {"FA", "Podemos"} <= presentes:
            r = eu.loc[cod, "Podemos"] / max(eu.loc[cod, "Podemos"] + eu.loc[cod, "Sumar"], 1e-9)
            b["Podemos"], b["FA"] = izq * r, izq * (1 - r)
        elif "FA" in presentes:
            b["FA"] = izq
        elif "Podemos" in presentes:
            b["Podemos"] = izq
        b["SALF"] = eu.loc[cod].get("SALF", 0.0) * validos[cod]
        b["AA"] = an.get(cod, 0.0) * validos[cod]
        b[BLANCO] = v.get(BLANCO, 0.0)
        codificados = sum(v.get(p, 0.0) for p in v.index if p != OTROS)
        b[OTROS] = max(validos[cod] - codificados, 0.0)
        for p in ORDEN:
            if p not in presentes:
                b[p] = 0.0
        filas[cod] = b
    base = pd.DataFrame.from_dict(filas, orient="index")[COLUMNAS]
    # Cuotas por provincia (cada fila suma 1) y peso de cada provincia en el total nacional.
    base = base.div(base.sum(axis=1), axis=0)
    base["_peso"] = validos / validos.sum()
    return base


# --------------------------------------------------------------------------- promedio de encuestas

@dataclass
class Promedio:
    voto: pd.Series  # % por partido
    encuestas: pd.DataFrame  # las que entran, con su peso
    dispersion: pd.Series  # desviación típica entre encuestadoras (pp)


def partidos_2026(enc: pd.DataFrame) -> pd.DataFrame:
    """Pasa encuestas antiguas a las candidaturas de 2026: Sumar → Frente Amplio + Compromís (según la base) y
    UPN → PP."""
    enc = enc.copy()
    base = base_provincial()
    nac = base[COLUMNAS].mul(base._peso, axis=0).sum()
    r_fv = nac["FV"] / (nac["FA"] + nac["FV"])
    if "Sumar" in enc:
        viejo = enc.FA.isna() & enc.FV.isna() & enc.Sumar.notna()
        enc.loc[viejo, "FA"] = enc.loc[viejo, "Sumar"] * (1 - r_fv)
        enc.loc[viejo, "FV"] = enc.loc[viejo, "Sumar"] * r_fv
    if "combinado" in enc:  # FA+FV en una sola cifra: se separa con la misma proporción
        junto = enc.combinado.fillna("").str.contains("FA+FV", regex=False)
        enc.loc[junto, "FV"] = enc.loc[junto, "FA"] * r_fv
        enc.loc[junto, "FA"] = enc.loc[junto, "FA"] * (1 - r_fv)
    if "UPN" in enc:
        enc["PP"] = enc.PP + enc.UPN.fillna(0)
    return enc


def promedio(fecha: date | None = None, ventana: int = 14, vida_media: float = 5.0,
             excluir: tuple[str, ...] = ()) -> Promedio:
    enc = partidos_2026(encuestas())
    enc = enc[enc.tipo == "encuesta"]
    hasta = pd.Timestamp(fecha or enc.fin_campo.max().date())
    desde = hasta - timedelta(days=ventana)
    sel = enc[(enc.fin_campo <= hasta) & (enc.fin_campo > desde) & ~enc.encuestadora.isin(excluir)]
    # Solo la última de cada encuestadora (40dB, Electomanía… publican trackings casi diarios).
    sel = sel.sort_values("fin_campo").groupby("encuestadora").tail(1).copy()
    edad = (hasta - sel.fin_campo).dt.days
    muestra = sel.muestra.fillna(1000).clip(400, 5000)
    sel["peso"] = np.sqrt(muestra) * 0.5 ** (edad / vida_media)
    sel["peso"] /= sel.peso.sum()
    voto, disp = {}, {}
    for p in ORDEN:
        if p not in sel:
            continue
        # Las que dan a varios partidos juntos (p. ej. FA+FV) no cuentan para ninguno de ellos.
        junto = sel.combinado.fillna("").str.split(r"[+;]", regex=True).apply(lambda c: p in c)
        x = sel.loc[~junto, [p, "peso"]].dropna()
        if x.empty:
            continue
        voto[p] = float(np.average(x[p], weights=x.peso))
        disp[p] = float(x[p].std()) if len(x) > 2 else np.nan
    return Promedio(pd.Series(voto), sel.sort_values("fin_campo", ascending=False), pd.Series(disp))


def voto_de_encuesta(fila: pd.Series) -> pd.Series:
    fila = partidos_2026(fila.to_frame().T.infer_objects()).iloc[0]
    return pd.Series({p: float(fila[p]) for p in ORDEN if p in fila and pd.notna(fila[p])})


def completar(voto: pd.Series) -> pd.Series:
    """Rellena los partidos que la encuesta no estima (p. ej. regionales con '?') con su peso en la base."""
    base = base_provincial()
    nacional = base[COLUMNAS].mul(base._peso, axis=0).sum() * 100
    out = voto.copy()
    for p in ORDEN:
        if p not in out or pd.isna(out[p]):
            out[p] = nacional[p]
    return out[ORDEN]


# --------------------------------------------------------------------------- traslado a provincias

def proyectar(voto: pd.Series, metodo: str = "proporcional") -> pd.DataFrame:
    """Cuota de voto (0-1) por provincia y partido a partir del % nacional `voto`."""
    base = base_provincial()
    peso = base._peso.to_numpy()
    s = base[COLUMNAS].to_numpy()
    objetivo = completar(voto).to_numpy() / 100
    i_bl, i_ot = COLUMNAS.index(BLANCO), COLUMNAS.index(OTROS)
    blanco = float(peso @ s[:, i_bl])
    objetivo = np.append(objetivo, [max(1 - objetivo.sum() - blanco, 0.005), blanco])

    def nacional(m):
        return peso @ m

    if metodo in ("proporcional", "mixto"):
        prop = s.copy()
        for _ in range(50):  # ajuste iterativo: escala cada partido y renormaliza cada provincia
            nat = nacional(prop)
            prop *= np.where(nat > 0, objetivo / np.where(nat > 0, nat, 1), 0)
            prop /= prop.sum(axis=1, keepdims=True)
    if metodo in ("uniforme", "mixto"):
        presente = s > 0
        cobertura = peso @ presente
        dif = (objetivo - nacional(s)) / np.where(cobertura > 0, cobertura, 1)
        uni = np.where(presente, np.clip(s + dif, 0.0005, None), 0)
        uni[:, i_ot] = np.clip(s[:, i_ot] + dif[i_ot], 0.001, None)
        uni /= uni.sum(axis=1, keepdims=True)
    m = {"proporcional": lambda: prop, "uniforme": lambda: uni, "mixto": lambda: (prop + uni) / 2}[metodo]()
    return pd.DataFrame(m, index=base.index, columns=COLUMNAS)


# --------------------------------------------------------------------------- escaños

def votos_estimados(cuotas: pd.DataFrame, participacion: float | None = None) -> pd.DataFrame:
    """Pasa cuotas a votos usando el censo de 2026 y la participación (por defecto, la de 2023 en cada provincia)."""
    res = pd.read_csv(DATA / "resultados_2023.csv", dtype={"cod": str})
    validos23 = res[res.partido == "_validos"].set_index("cod").votos
    censo23 = res[res.partido == "_censo"].set_index("cod").votos
    c26 = candidaturas()
    censo26 = c26[c26.partido == "_censo"].set_index("cod").censo.reindex(censo23.index).fillna(censo23)
    tasa = validos23 / censo23
    if participacion is not None:
        tasa = tasa * participacion / (validos23.sum() / censo23.sum())
    return cuotas.mul(censo26 * tasa, axis=0)


def escanos(votos: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Escaños por provincia y la frontera (último/siguiente escaño) de cada una."""
    prov = provincias()
    filas, fronteras = {}, []
    for cod, v in votos.iterrows():
        n = int(prov.loc[cod, "escanos_2026"])
        reparto, f = frontera(v.to_dict(), n)
        filas[cod] = reparto
        total = v.sum()
        rival = min(f.faltan, key=f.faltan.get) if f.faltan else None
        fronteras.append({
            "cod": cod, "provincia": prov.loc[cod, "provincia"], "escanos": n,
            "ultimo": f.ultimo, "siguiente": f.siguiente,
            "rival": rival, "faltan_votos": f.faltan.get(rival, np.nan) if rival else np.nan,
            "faltan_pp": 100 * f.faltan.get(rival, np.nan) / total if rival else np.nan,
            "colchon_votos": f.colchon, "colchon_pp": 100 * f.colchon / total,
            "faltan": f.faltan,
        })
    esc = pd.DataFrame.from_dict(filas, orient="index").reindex(columns=ORDEN).fillna(0).astype(int)
    return esc, pd.DataFrame(fronteras).set_index("cod")


# --------------------------------------------------------------------------- simulación

def simular(voto: pd.Series, dispersion: pd.Series | None = None, n: int = 2000, error_provincial: float = 0.08,
            metodo: str = "proporcional", semilla: int = 29) -> pd.DataFrame:
    """Monte Carlo: error nacional por partido (≈ dispersión entre encuestadoras + error histórico) y ruido
    provincial. Devuelve los escaños totales de cada simulación (n filas × partidos)."""
    rng = np.random.default_rng(semilla)
    v = completar(voto)
    disp = (dispersion if dispersion is not None else pd.Series(dtype=float)).reindex(ORDEN).fillna(0.5)
    sigma = np.sqrt(disp.to_numpy() ** 2 + (0.05 * v.to_numpy()) ** 2 + 0.3 ** 2)
    nacional = np.clip(v.to_numpy()[None, :] + rng.normal(0, 1, (n, len(ORDEN))) * sigma, 0.05, None)
    # Las cuotas provinciales salen del promedio y se reescalan por partido según el error nacional simulado.
    cuotas = proyectar(v, metodo)
    factor = nacional / v.to_numpy()[None, :]
    prov = provincias()
    asignable = np.array([c in ORDEN for c in COLUMNAS])
    total = np.zeros((n, len(ORDEN)), dtype=np.int32)
    for cod, fila in cuotas.iterrows():
        base = fila.to_numpy()[None, :].repeat(n, axis=0)
        base[:, : len(ORDEN)] *= factor * np.exp(rng.normal(0, error_provincial, (n, len(ORDEN))))
        esc = dhondt_matriz(base, int(prov.loc[cod, "escanos_2026"]), asignable=asignable)
        total += esc[:, : len(ORDEN)]
    return pd.DataFrame(total, columns=ORDEN)
