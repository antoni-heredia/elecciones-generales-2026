"""Generales del 29 de noviembre de 2026: promedio de encuestas, escaños por provincia y quién se juega cada uno."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import modelo
from graficos import TRANSPARENTE, hemiciclo, mapa_categorico, mapa_continuo, nombre
from partidos import BLOQUES, COLORES, MAYORIA, ORDEN, OTROS

st.set_page_config(page_title="Generales 2026 · encuestas y escaños", layout="wide", page_icon="🗳️")

FUENTE = (
    "Encuestas: [Wikipedia · Opinion polling for the 2026 Spanish general election]"
    "(https://en.wikipedia.org/wiki/Opinion_polling_for_the_2026_Spanish_general_election), que recoge las "
    "publicadas por cada encuestadora y medio. Resultados de 2023, europeas 2024 y andaluzas 2026: Wikipedia "
    "(datos del Ministerio del Interior y la Junta Electoral). Proyección propia: no la hace ninguna encuestadora."
)


# --------------------------------------------------------------------------- cálculos cacheados

@st.cache_data(show_spinner=False)
def calc_promedio(fecha, ventana, vida_media, excluir):
    pr = modelo.promedio(fecha, ventana, vida_media, tuple(excluir))
    return pr.voto, pr.encuestas, pr.dispersion


@st.cache_data(show_spinner=False)
def calc_escanos(voto: tuple, metodo: str, participacion: float | None):
    v = pd.Series(dict(voto))
    cuotas = modelo.proyectar(v, metodo)
    votos = modelo.votos_estimados(cuotas, participacion)
    esc, fr = modelo.escanos(votos)
    return cuotas, votos, esc, fr


@st.cache_data(show_spinner="Simulando 3.000 elecciones…")
def calc_simulacion(voto: tuple, disp: tuple, metodo: str, error_provincial: float):
    return modelo.simular(pd.Series(dict(voto)), pd.Series(dict(disp)), n=3000, metodo=metodo,
                          error_provincial=error_provincial)


@st.cache_data(show_spinner=False)
def calc_sensibilidad(voto: tuple, metodo: str):
    """Escaños que gana cada partido si sube 1 punto (quitándolo a los demás en proporción)."""
    v = pd.Series(dict(voto))
    _, _, esc0, _ = calc_escanos(voto, metodo, None)
    out = {}
    for p in v.index:
        w = v.copy()
        resto = w.drop(p).sum()
        w[w.index != p] *= (resto - 1) / resto
        w[p] += 1
        _, _, esc1, _ = calc_escanos(tuple(w.items()), metodo, None)
        out[p] = int(esc1[p].sum() - esc0[p].sum())
    return pd.Series(out)


def tupla(s: pd.Series) -> tuple:
    return tuple((k, float(v)) for k, v in s.items() if pd.notna(v))


# --------------------------------------------------------------------------- barra lateral

enc = modelo.encuestas()
encuestadoras = sorted(enc[enc.tipo == "encuesta"].encuestadora.unique())
ultima = enc.fin_campo.max().date()

with st.sidebar:
    st.header("Promedio")
    fecha = st.date_input("Encuestas hasta", ultima, min_value=pd.Timestamp("2023-09-01").date(), max_value=ultima)
    ventana = st.slider("Ventana (días)", 7, 60, 14)
    vida_media = st.slider("Vida media del peso (días)", 2, 30, 5,
                           help="Una encuesta de hace N días pesa la mitad que una de hoy.")
    excluir = st.multiselect("Excluir encuestadoras", encuestadoras, default=[],
                             help="El CIS suele dar al PSOE bastante más que el resto.")
    st.header("Escenario")
    escenario = st.radio("Votos de partida", ["Promedio", "Una encuesta", "A mano"], horizontal=True)
    st.header("Modelo")
    metodo = st.selectbox("Traslado a provincias", ["proporcional", "mixto", "uniforme"],
                          help="Proporcional: cada partido crece o cae en cada provincia en proporción a su voto "
                               "de 2023. Uniforme: suma los mismos puntos en todas. Mixto: la media.")
    participacion = st.slider("Participación (%)", 55, 80, 67,
                              help="Solo cambia los votos absolutos (cuántos faltan para un escaño), no el reparto.")
    error_provincial = st.slider("Error provincial en la simulación", 0.0, 0.25, 0.08, 0.01,
                                 help="Ruido relativo en cada provincia, además del error nacional.")

voto_prom, sel, disp = calc_promedio(fecha, ventana, vida_media, excluir)
if voto_prom.empty:
    st.error("No hay encuestas en esa ventana.")
    st.stop()

voto = voto_prom.copy()
titulo_escenario = f"Promedio de {len(sel)} encuestadoras ({fecha - timedelta(days=ventana - 1):%d/%m}–{fecha:%d/%m})"
if escenario == "Una encuesta":
    recientes = enc[(enc.tipo == "encuesta") & (enc.fin_campo <= pd.Timestamp(fecha))].head(80)
    etiquetas = {i: f"{r.encuestadora} / {r.medio} · {r.trabajo_campo} {r.fin_campo:%Y}" for i, r in recientes.iterrows()}
    with st.sidebar:
        i = st.selectbox("Encuesta", list(etiquetas), format_func=etiquetas.get)
    voto = modelo.completar(modelo.voto_de_encuesta(enc.loc[i]).reindex(ORDEN))
    titulo_escenario = etiquetas[i]
elif escenario == "A mano":
    with st.sidebar:
        st.caption("Parte del promedio. Lo que no sume 100 va a «otros».")
        voto = pd.Series({p: st.number_input(nombre(p), 0.0, 60.0, float(round(voto_prom.get(p, 0.0), 1)), 0.1,
                                             key=f"mano_{p}") for p in ORDEN})
    titulo_escenario = "Escenario a mano"

voto = modelo.completar(voto.reindex(ORDEN))
cuotas, votos, esc, fr = calc_escanos(tupla(voto), metodo, participacion / 100)
total = esc.sum()
prov = modelo.provincias()

# --------------------------------------------------------------------------- cabecera

st.title("Generales 2026: encuestas y escaños")
st.caption(f"Elecciones el **29 de noviembre de 2026** · {titulo_escenario} · traslado {metodo}")

cols = st.columns(6)
principales = total.sort_values(ascending=False).head(6)
for c, (p, n) in zip(cols, principales.items()):
    c.metric(f"{nombre(p)} · {voto[p]:.1f} %", f"{n} esc.")

tabs = st.tabs(["Resumen", "Mapa", "Escaños en juego", "Provincia", "Encuestas", "Autonómicas",
                "Simulación", "Cómo se hace"])

# --------------------------------------------------------------------------- resumen

with tabs[0]:
    izq, der = st.columns([3, 2])
    with izq:
        st.plotly_chart(hemiciclo(total.to_dict()), width="stretch")
    with der:
        tabla = pd.DataFrame({
            "Partido": [nombre(p) for p in ORDEN],
            "Voto %": voto.reindex(ORDEN).round(1).values,
            "Escaños": total.reindex(ORDEN).values,
            "Rango encuestas": [
                f"{int(sel[f'{p}_esc_min'].min())}–{int(sel[f'{p}_esc_max'].max())}"
                if f"{p}_esc_min" in sel and sel[f"{p}_esc_min"].notna().any() else "" for p in ORDEN],
        }).sort_values("Escaños", ascending=False)
        st.dataframe(tabla, hide_index=True, width="stretch", height=530)

    st.subheader("Bloques")
    filas = []
    for b, ps in BLOQUES.items():
        n = int(total.reindex(ps).fillna(0).sum())
        filas.append({"Bloque": b, "Escaños": n, "Partidos": ", ".join(nombre(p) for p in ps)})
    bl = pd.DataFrame(filas)
    fig = go.Figure(go.Bar(x=bl.Escaños, y=bl.Bloque, orientation="h", text=bl.Escaños,
                           marker_color=["#1d84ce", "#3a6fb0", "#5a5fa0", "#e30613", "#b8203a"]))
    fig.add_vline(x=MAYORIA, line_dash="dash", annotation_text="176")
    fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(autorange="reversed"), **TRANSPARENTE)
    st.plotly_chart(fig, width="stretch")
    with st.expander("Arma tu mayoría"):
        socios = st.multiselect("Partidos", ORDEN, default=["PP", "Vox"], format_func=nombre)
        n = int(total.reindex(socios).fillna(0).sum())
        st.metric("Suman", f"{n} escaños", f"{n - MAYORIA:+d} sobre la mayoría absoluta")

# --------------------------------------------------------------------------- mapa

def hover_provincia(cod: str) -> str:
    e = esc.loc[cod]
    partes = [f"{nombre(p)} {int(e[p])}" for p in e.sort_values(ascending=False).index if e[p] > 0]
    f = fr.loc[cod]
    return (f"<b>{prov.loc[cod, 'provincia']}</b> ({prov.loc[cod, 'escanos_2026']} esc.)<br>" + "<br>".join(partes)
            + f"<br>Último escaño: {nombre(f.ultimo)}<br>Siguiente: {nombre(f.siguiente)}"
            + f"<br>Más cerca de quitarlo: {nombre(f.rival)} (le faltan {f.faltan_pp:.2f} pp)")


hover = pd.Series({c: hover_provincia(c) for c in esc.index})

with tabs[1]:
    que = st.radio("Pintar", ["Partido más votado", "Último escaño", "Siguiente escaño",
                              "Quién puede quitar el último", "Escaños de un partido", "Voto de un partido"],
                   horizontal=True)
    df = pd.DataFrame(index=esc.index)
    if que == "Partido más votado":
        df["p"] = cuotas[ORDEN].idxmax(axis=1)
        fig = mapa_categorico(df, "p", hover)
    elif que == "Último escaño":
        df["p"] = fr.ultimo
        fig = mapa_categorico(df, "p", hover)
        st.caption("Partido que se lleva el último escaño que se reparte en cada provincia.")
    elif que == "Siguiente escaño":
        df["p"] = fr.siguiente
        fig = mapa_categorico(df, "p", hover)
        st.caption("Partido al que le tocaría el escaño siguiente si la provincia tuviera uno más: el que está "
                   "en la puerta.")
    elif que == "Quién puede quitar el último":
        df["p"] = fr.rival
        fig = mapa_categorico(df, "p", hover)
        st.caption("El partido al que le faltan menos votos para arrebatar el último escaño.")
    else:
        p = st.selectbox("Partido", [p for p in ORDEN if total[p] > 0 or voto[p] > 1], format_func=nombre)
        if que == "Escaños de un partido":
            fig = mapa_continuo(esc[p], hover, COLORES[p], "escaños")
        else:
            fig = mapa_continuo((cuotas[p] * 100).round(1).where(cuotas[p] > 0), hover, COLORES[p], "% voto")
    st.plotly_chart(fig, width="stretch")

    st.subheader("Escaños por provincia")
    tabla = esc.loc[:, (esc.sum() > 0)].copy()
    tabla.columns = [nombre(c) for c in tabla.columns]
    tabla.insert(0, "Provincia", prov.provincia.reindex(tabla.index))
    tabla.insert(1, "Total", prov.escanos_2026.reindex(tabla.index))
    st.dataframe(tabla.sort_values("Total", ascending=False), hide_index=True, width="stretch")

# --------------------------------------------------------------------------- escaños en juego

with tabs[2]:
    st.markdown("En cada provincia, el **último escaño** es el que se reparte con el cociente D'Hondt más bajo. "
                "**Faltan** son los votos que necesita el rival más cercano para quitárselo (sin que nadie más "
                "cambie); **colchón**, los que puede perder quien lo tiene antes de perderlo.")
    t = fr.copy()
    t["Último"] = t.ultimo.map(nombre)
    t["Siguiente"] = t.siguiente.map(nombre)
    t["Rival"] = t.rival.map(nombre)
    t["Faltan (votos)"] = t.faltan_votos.round(0).astype("Int64")
    t["Faltan (pp)"] = t.faltan_pp.round(2)
    t["Colchón (votos)"] = t.colchon_votos.round(0).astype("Int64")
    t["Colchón (pp)"] = t.colchon_pp.round(2)
    t["Provincia"] = t.provincia
    t["Escaños"] = t.escanos
    margen = st.slider("Disputado si faltan menos de (pp)", 0.1, 3.0, 0.5, 0.1)
    disputados = t[t.faltan_pp < margen].sort_values("faltan_pp")
    c1, c2, c3 = st.columns(3)
    c1.metric("Escaños disputados", len(disputados))
    c2.metric("Votos que los decidirían", f"{int(disputados.faltan_votos.sum()):,}".replace(",", "."))
    c3.metric(f"El más ajustado · le faltan {disputados['Faltan (votos)'].iloc[0]} votos" if len(disputados)
              else "El más ajustado", disputados.Provincia.iloc[0] if len(disputados) else "—")
    st.dataframe(t.sort_values("faltan_pp")[["Provincia", "Escaños", "Último", "Colchón (votos)", "Colchón (pp)",
                                             "Rival", "Faltan (votos)", "Faltan (pp)", "Siguiente"]],
                 hide_index=True, width="stretch", height=420)

    st.subheader("Qué se juega cada partido")
    pierde = disputados.ultimo.value_counts()
    gana = disputados.rival.value_counts()
    jj = pd.DataFrame({"Puede ganar": gana, "Puede perder": pierde}).fillna(0).astype(int)
    jj = jj.reindex([p for p in ORDEN if p in jj.index])
    fig = go.Figure()
    fig.add_trace(go.Bar(y=[nombre(p) for p in jj.index], x=jj["Puede ganar"], orientation="h", name="Puede ganar",
                         marker_color=[COLORES[p] for p in jj.index]))
    fig.add_trace(go.Bar(y=[nombre(p) for p in jj.index], x=-jj["Puede perder"], orientation="h",
                         name="Puede perder", marker_color=[COLORES[p] for p in jj.index], opacity=0.45))
    fig.update_layout(barmode="relative", height=60 + 28 * len(jj), margin=dict(l=0, r=0, t=10, b=0),
                      xaxis_title="← escaños que puede perder · escaños que puede ganar →", **TRANSPARENTE)
    st.plotly_chart(fig, width="stretch")

    st.subheader("Un punto más")
    sens = calc_sensibilidad(tupla(voto), metodo).reindex(ORDEN)
    st.caption("Escaños que ganaría cada partido con 1 punto más de voto nacional, restado al resto en proporción.")
    st.dataframe(pd.DataFrame({"Partido": [nombre(p) for p in sens.index], "Escaños +1 pp": sens.values})
                 .sort_values("Escaños +1 pp", ascending=False), hide_index=True)

# --------------------------------------------------------------------------- provincia

with tabs[3]:
    cod = st.selectbox("Provincia", prov.sort_values("provincia").index, format_func=lambda c: prov.loc[c, "provincia"])
    n = int(prov.loc[cod, "escanos_2026"])
    v = votos.loc[cod]
    c1, c2 = st.columns([2, 3])
    with c1:
        d = pd.DataFrame({"Partido": [nombre(p) for p in v.index], "% voto": (cuotas.loc[cod] * 100).round(2).values,
                          "Votos": v.round(0).astype(int).values,
                          "Escaños": [int(esc.loc[cod].get(p, 0)) for p in v.index]})
        st.dataframe(d[d["% voto"] > 0].sort_values("% voto", ascending=False), hide_index=True,
                     width="stretch")
        f = fr.loc[cod]
        st.markdown(f"**Último escaño:** {nombre(f.ultimo)} (colchón {f.colchon_votos:,.0f} votos)  \n"
                    f"**Siguiente:** {nombre(f.siguiente)}  \n"
                    f"**Más cerca de quitarlo:** {nombre(f.rival)}, le faltan {f.faltan_votos:,.0f} votos "
                    f"({f.faltan_pp:.2f} pp)".replace(",", "."))
    with c2:
        validos = v.sum()
        el = {p: x for p, x in v.items() if p in ORDEN and x / validos >= 0.03}
        filas = [{"Partido": nombre(p), "p": p, "Divisor": k, "Cociente": x / k} for p, x in el.items()
                 for k in range(1, n + 3)]
        q = pd.DataFrame(filas).sort_values("Cociente", ascending=False).head(n + 3).reset_index(drop=True)
        q["Escaño"] = [f"{i + 1}" if i < n else f"({i + 1})" for i in range(len(q))]
        fig = go.Figure(go.Bar(x=q.Escaño, y=q.Cociente, marker_color=[COLORES[p] for p in q.p],
                               marker_opacity=[1 if i < n else 0.35 for i in range(len(q))], text=q.Partido,
                               hovertemplate="%{text}<br>%{y:,.0f}<extra></extra>"))
        fig.update_layout(title="Cocientes D'Hondt (los atenuados se quedan fuera)", height=380,
                          margin=dict(l=0, r=0, t=40, b=0), **TRANSPARENTE)
        st.plotly_chart(fig, width="stretch")
        faltan = pd.Series(f.faltan).sort_values().head(6)
        st.caption("Votos que le faltan a cada uno para el último escaño: " + " · ".join(
            f"{nombre(p)} {x:,.0f}".replace(",", ".") for p, x in faltan.items()))

# --------------------------------------------------------------------------- encuestas

with tabs[4]:
    desde = st.select_slider("Desde", ["2023-07-23", "2024-01-01", "2025-01-01", "2026-01-01", "2026-09-01"],
                             value="2025-01-01")
    e = enc[(enc.tipo == "encuesta") & (enc.fin_campo >= desde)].copy()
    largo = e.melt(id_vars=["fin_campo", "encuestadora", "medio"], value_vars=[p for p in ORDEN + ["Sumar"]
                   if p in e], var_name="partido", value_name="voto").dropna()
    principales_p = ["PP", "PSOE", "Vox", "FA", "Sumar", "Podemos", "SALF", "ERC", "Junts", "FV", "AA"]
    largo = largo[largo.partido.isin(principales_p)]
    fig = go.Figure()
    for p in principales_p:
        x = largo[largo.partido == p].sort_values("fin_campo")
        if x.empty:
            continue
        col = COLORES.get(p, "#e51c55")
        fig.add_trace(go.Scatter(x=x.fin_campo, y=x.voto, mode="markers", marker=dict(size=4, color=col, opacity=0.3),
                                 name=nombre(p), legendgroup=p, showlegend=False,
                                 text=x.encuestadora, hovertemplate="%{text}: %{y}%<extra></extra>"))
        tendencia = x.set_index("fin_campo").voto.rolling("21D").mean()
        fig.add_trace(go.Scatter(x=tendencia.index, y=tendencia.values, mode="lines", line=dict(color=col, width=2.5),
                                 name=nombre(p), legendgroup=p, hoverinfo="skip"))
    fig.add_vline(x=pd.Timestamp("2026-11-29"), line_dash="dot", annotation_text="29-N")
    fig.update_layout(height=480, yaxis_title="% voto", margin=dict(l=0, r=0, t=10, b=0),
                      legend=dict(orientation="h", y=-0.15), **TRANSPARENTE)
    st.plotly_chart(fig, width="stretch")
    st.caption(f"{len(e)} encuestas desde {desde}. Línea: media móvil de 21 días. Sumar se separa en Frente Amplio, "
               "Compromís y Podemos desde octubre de 2026.")

    st.subheader("Las que entran en el promedio")
    v_sel = sel.copy()
    filas = []
    for _, r in v_sel.iterrows():
        vv = modelo.completar(modelo.voto_de_encuesta(r).reindex(ORDEN))
        _, _, e_r, _ = calc_escanos(tupla(vv), metodo, None)
        t_r = e_r.sum()
        fila = {"Encuestadora": f"{r.encuestadora} / {r.medio}", "Campo": r.trabajo_campo, "Peso %": round(100 * r.peso, 1)}
        for p in ["PP", "PSOE", "Vox", "FA", "Podemos", "SALF"]:
            pub = f"{int(r[f'{p}_esc_min'])}" if pd.notna(r.get(f"{p}_esc_min")) else "?"
            if pd.notna(r.get(f"{p}_esc_max")) and r[f"{p}_esc_max"] != r[f"{p}_esc_min"]:
                pub += f"–{int(r[f'{p}_esc_max'])}"
            fila[nombre(p)] = f"{r[p]:.1f} % · {pub} / {t_r[p]}" if pd.notna(r[p]) else ""
        filas.append(fila)
    st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")
    st.caption("Cada celda: voto · escaños que publica la encuesta / escaños que salen con este modelo.")

    st.subheader("Sesgo de cada encuestadora")
    ref = enc[(enc.tipo == "encuesta") & (enc.fin_campo > pd.Timestamp(fecha) - timedelta(days=60))
              & (enc.fin_campo <= pd.Timestamp(fecha))]
    sesgo = (ref.groupby("encuestadora")[["PP", "PSOE", "Vox", "FA"]].mean() - voto_prom.reindex(["PP", "PSOE", "Vox", "FA"]))
    sesgo["n"] = ref.groupby("encuestadora").size()
    st.dataframe(sesgo.round(1).sort_values("PSOE"), width="stretch")
    st.caption("Diferencia media (pp) de cada encuestadora con el promedio en los últimos 60 días.")

# --------------------------------------------------------------------------- autonómicas

with tabs[5]:
    sub = modelo.encuestas_subnacionales()
    sub = sub[(sub.tipo == "encuesta") & (sub.fin_campo <= pd.Timestamp(fecha))]
    ambitos = sorted(sub.ambito.unique())
    nombres_es = {"Andalusia": "Andalucía", "Aragon": "Aragón", "Balearic Islands": "Baleares",
                  "Basque Country": "País Vasco", "Canary Islands": "Canarias", "Castile and León": "Castilla y León",
                  "Castilla–La Mancha": "Castilla-La Mancha", "Catalonia": "Cataluña", "Navarre": "Navarra",
                  "Valencian Community": "Comunidad Valenciana", "Murcia": "Región de Murcia", "Biscay": "Bizkaia"}
    amb = st.selectbox("Comunidad o provincia", ambitos, format_func=lambda a: nombres_es.get(a, a))
    s = sub[sub.ambito == amb]
    ult = s.sort_values("fin_campo").groupby(["encuestadora", "partido"]).tail(1)
    ult = ult[ult.fin_campo > ult.fin_campo.max() - timedelta(days=45)]
    piv = ult.pivot_table(index=["encuestadora", "fin_campo"], columns="partido", values="pct")
    esc_piv = ult.pivot_table(index=["encuestadora", "fin_campo"], columns="partido", values="esc_min")
    st.markdown("**Voto (%)**")
    st.dataframe(piv.sort_index(level=1, ascending=False).round(1), width="stretch")
    st.markdown("**Escaños que publican**")
    st.dataframe(esc_piv.sort_index(level=1, ascending=False), width="stretch")
    # Comparación con el modelo en las provincias de ese ámbito.
    ccaa = {"Andalusia": "Andalucía", "Aragon": "Aragón", "Asturias": "Asturias", "Balearic Islands": "Baleares",
            "Basque Country": "País Vasco", "Canary Islands": "Canarias", "Cantabria": "Cantabria",
            "Castile and León": "Castilla y León", "Castilla–La Mancha": "Castilla-La Mancha", "Catalonia": "Cataluña",
            "Extremadura": "Extremadura", "Galicia": "Galicia", "La Rioja": "La Rioja", "Madrid": "Madrid",
            "Murcia": "Murcia", "Navarre": "Navarra", "Valencian Community": "Comunidad Valenciana"}
    if amb in ccaa:
        cods = prov.index[prov.ccaa == ccaa[amb]]
        m_voto = (votos.loc[cods].sum() / votos.loc[cods].sum().sum() * 100)
        m_esc = esc.loc[cods].sum()
        comp = pd.DataFrame({"Modelo %": m_voto.reindex(ORDEN).round(1), "Modelo esc.": m_esc.reindex(ORDEN)})
        comp = comp[(comp["Modelo %"] > 0.5)]
        comp["Encuestas %"] = piv.mean().reindex(comp.index).round(1)
        comp["Encuestas esc."] = esc_piv.mean().reindex(comp.index).round(1)
        comp.index = [nombre(p) for p in comp.index]
        st.markdown("**Modelo nacional frente a las encuestas de aquí**")
        st.dataframe(comp, width="stretch")

# --------------------------------------------------------------------------- simulación

with tabs[6]:
    sim = calc_simulacion(tupla(voto), tupla(disp), metodo, error_provincial)
    st.markdown("3.000 elecciones simuladas: en cada una el voto nacional de cada partido se mueve con un error "
                "del tamaño de la dispersión entre encuestadoras más un error histórico, y cada provincia añade "
                "su propio ruido.")
    probs = []
    for b, ps in BLOQUES.items():
        n_b = sim[[p for p in ps if p in sim]].sum(axis=1)
        probs.append({"Bloque": b, "Prob. ≥176": f"{(n_b >= MAYORIA).mean():.0%}",
                      "Mediana": int(n_b.median()), "Intervalo 80 %": f"{int(n_b.quantile(.1))}–{int(n_b.quantile(.9))}"})
    c1, c2 = st.columns([3, 2])
    with c1:
        st.dataframe(pd.DataFrame(probs), hide_index=True, width="stretch")
    with c2:
        primero = sim[ORDEN].idxmax(axis=1).value_counts(normalize=True)
        st.metric("Prob. de que el PP sea primero", f"{primero.get('PP', 0):.0%}")
        st.metric("Prob. de que el PSOE sea primero", f"{primero.get('PSOE', 0):.0%}")
    resumen = sim.describe(percentiles=[.1, .5, .9]).T
    resumen = resumen[resumen["max"] > 0]
    fig = go.Figure()
    for p in resumen.sort_values("50%").index:
        fig.add_trace(go.Box(x=sim[p], name=nombre(p), marker_color=COLORES[p], boxpoints=False, orientation="h"))
    fig.update_layout(height=520, showlegend=False, xaxis_title="escaños", margin=dict(l=0, r=0, t=10, b=0),
                      **TRANSPARENTE)
    st.plotly_chart(fig, width="stretch")
    b = st.selectbox("Distribución de", list(BLOQUES))
    n_b = sim[[p for p in BLOQUES[b] if p in sim]].sum(axis=1)
    fig = px.histogram(n_b, nbins=60)
    fig.add_vline(x=MAYORIA - 0.5, line_dash="dash", annotation_text="176")
    fig.update_layout(height=280, showlegend=False, xaxis_title="escaños", yaxis_title="simulaciones",
                      margin=dict(l=0, r=0, t=10, b=0), **TRANSPARENTE)
    st.plotly_chart(fig, width="stretch")

# --------------------------------------------------------------------------- metodología

with tabs[7]:
    st.markdown(f"""
**Promedio.** Se toma la última encuesta de cada encuestadora con trabajo de campo en la ventana elegida. Pesa
más si es reciente (vida media configurable) y si tiene más muestra (raíz cuadrada, entre 400 y 5.000). Si una
encuesta da a dos partidos juntos (p. ej. Frente Amplio y Compromís), no cuenta para ninguno de los dos. Los
partidos que una encuesta no estima (con «?») salen del resto.

**Base por provincia.** El voto de 2023 en cada provincia, adaptado a las candidaturas de 2026:
- Sumar 2023 se reparte entre **Frente Amplio** y **Podemos** según la proporción entre los dos en las europeas
  de 2024 en esa provincia. En la Comunidad Valenciana todo va a **Compromís: Front Valencià** (incluye a Podem);
  en Canarias Nueva Canarias se suma a la UPC (Frente Amplio).
- **UPN** se suma al PP en Navarra (van juntos).
- **SALF** toma su voto provincial de las europeas de 2024; **Adelante Andalucía**, de las andaluzas de 2026.
- Un partido que no presenta lista en una provincia tiene 0 votos allí (listas de 2026 de Wikipedia).

**Traslado.** *Proporcional*: cada partido conserva su forma territorial y se escala hasta su promedio nacional
(con un ajuste iterativo para que cada provincia sume 100 %). *Uniforme*: suma los mismos puntos en cada
provincia donde se presenta. *Mixto*: la media de los dos.

**Reparto.** Barrera del 3 % de los votos válidos (incluido el blanco) en cada provincia y D'Hondt con los escaños
de 2026 (Madrid gana uno y Cádiz pierde uno). Ceuta y Melilla eligen un diputado cada una.

**Último y siguiente escaño.** Con los cocientes D'Hondt ordenados, el último escaño es el n-ésimo cociente y el
siguiente, el (n+1)-ésimo. *Faltan* = votos que necesita un partido para que su próximo cociente supere al del
último escaño (y, si está por debajo, pasar el 3 %); *colchón* = votos que puede perder el que tiene el último
escaño antes de que lo adelante el mejor cociente de otro partido.

**Limitaciones.** Los partidos pequeños con escaño posible que no recogen las encuestas nacionales (Teruel Existe,
UPL, Soria ¡Ya!…) van en «otros» y no reciben escaños. El voto se reparte con patrones de 2023/2024: no recoge
cambios territoriales nuevos salvo los que hagas con el escenario a mano.

{FUENTE}
""")

st.divider()
st.caption(FUENTE + " · Código: [github.com/antoni-heredia/elecciones-generales-2026]"
           "(https://github.com/antoni-heredia/elecciones-generales-2026)")
