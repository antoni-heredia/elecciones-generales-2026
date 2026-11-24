# Generales 2026: encuestas y escaños

Panel Streamlit para las elecciones generales del **29 de noviembre de 2026**: promedio de todas las encuestas
publicadas, proyección de escaños **provincia a provincia** con D'Hondt, mapa de España y qué partido se juega el
último (y el siguiente) escaño en cada circunscripción.

Hermano de [elecciones-andalucia-2026](https://github.com/antoni-heredia/elecciones-andalucia-2026).

## Qué hay

| Pestaña | |
|---|---|
| Resumen | Hemiciclo, voto y escaños por partido (con el rango que publican las encuestas), bloques y calculadora de mayorías |
| Mapa | Partido más votado, último escaño, siguiente escaño, quién puede quitar el último, escaños o voto de un partido |
| Escaños en juego | En cada provincia: quién tiene el último escaño, con cuántos votos de colchón, y cuántos le faltan al rival más cercano. Qué puede ganar o perder cada partido y cuántos escaños da un punto más |
| Provincia | Votos, escaños y cocientes D'Hondt de una circunscripción |
| Encuestas | Evolución desde julio de 2023, encuestas del promedio (escaños publicados frente a los del modelo) y sesgo de cada encuestadora |
| Autonómicas | Encuestas por comunidad y provincia frente a lo que da el modelo nacional |
| Simulación | 3.000 elecciones simuladas: probabilidad de mayoría absoluta de cada bloque y de quién queda primero |

Escenarios: el promedio, cualquier encuesta concreta o porcentajes a mano.

<!-- foto:inicio -->
## Foto a 23/11/2026

Promedio de 29 encuestadoras (16/11–23/11), traslado proporcional:

| Partido | Voto % | Escaños |
|---|---:|---:|
| PP | 31.1 | 125 |
| PSOE | 29.4 | 118 |
| Vox | 17.8 | 64 |
| ERC | 2.7 | 11 |
| Frente Amplio | 5.5 | 8 |
| EH Bildu | 1.5 | 7 |
| Junts | 1.2 | 4 |
| Adelante Andalucía | 1.8 | 4 |
| Compromís: Front Valencià | 1.5 | 3 |
| PNV | 0.8 | 3 |
| BNG | 0.9 | 2 |
| Coalición Canaria | 0.4 | 1 |
| Podemos | 1.0 | 0 |
| Se Acabó La Fiesta | 1.9 | 0 |

PP + Vox suman 189 (mediana de la simulación: 188; ≥176 en el 92 % de las simulaciones).

Últimos escaños más ajustados:

| Provincia | Último escaño | Rival | Le faltan (votos) | (pp) |
|---|---|---|---:|---:|
| Murcia | Vox | PSOE | 2.644 | 0.34 |
| Cáceres | PSOE | PP | 1.056 | 0.38 |
| Madrid | Vox | Frente Amplio | 19.052 | 0.50 |
| Segovia | PP | Vox | 502 | 0.56 |
| Valencia | Vox | Compromís: Front Valencià | 10.904 | 0.73 |
| Barcelona | Vox | Junts | 23.060 | 0.83 |
| Palencia | PP | Vox | 891 | 0.92 |
| Sevilla | Adelante Andalucía | Frente Amplio | 10.477 | 0.96 |
<!-- foto:fin -->

Se actualiza sola tres veces al día (GitHub Actions: `.github/workflows/actualizar.yml`).

## Usarlo

```sh
pip install -r requirements.txt
python scripts/actualizar_datos.py --solo-encuestas   # baja las encuestas nuevas y regenera data/encuestas*.csv
python scripts/foto_readme.py                        # actualiza la foto del README
streamlit run app.py
```

O con Docker: `docker build -t generales . && docker run -p 127.0.0.1:8501:8501 generales`.

## Datos (`data/`)

| Fichero | Contenido | Fuente |
|---|---|---|
| `encuestas.csv` | 650 encuestas nacionales (jul. 2023 → hoy): voto y escaños publicados | [Wikipedia](https://en.wikipedia.org/wiki/Opinion_polling_for_the_2026_Spanish_general_election) ([2023–2024](https://en.wikipedia.org/wiki/Nationwide_opinion_polling_for_the_2026_Spanish_general_election_(2023%E2%80%932024))) |
| `encuestas_subnacionales.csv` | Encuestas de 17 comunidades y 12 provincias | [Wikipedia](https://en.wikipedia.org/wiki/Sub-national_opinion_polling_for_the_2026_Spanish_general_election) |
| `resultados_2023.csv` | Votos de 2023 por provincia y candidatura, válidos y censo | Páginas de cada circunscripción en Wikipedia (datos del Ministerio del Interior) |
| `candidaturas_2026.csv` | Listas que se presentan en cada provincia en 2026 y censo | Ídem |
| `europeas_2024.csv` | % por provincia en las europeas de 2024 | [Wikipedia](https://en.wikipedia.org/wiki/Results_breakdown_of_the_2024_European_Parliament_election_in_Spain) |
| `andaluzas_2026.csv` | % de Adelante Andalucía por provincia | [Wikipedia](https://en.wikipedia.org/wiki/2026_Andalusian_regional_election) |
| `provincias.csv` | Códigos INE, comunidad y escaños de 2026 (Madrid 38, Cádiz 8) | [Wikipedia](https://en.wikipedia.org/wiki/2026_Spanish_general_election) |
| `provincias.geojson` | Contornos de provincias | [click_that_hood](https://github.com/codeforgermany/click_that_hood) |

`scripts/actualizar_datos.py` guarda las páginas en `data/raw/` (no va al repo) y solo vuelve a bajar las
encuestas con `--refrescar`.

## Modelo

1. **Promedio**: la última encuesta de cada encuestadora en la ventana (14 días por defecto), con peso por
   antigüedad (vida media 5 días) y por raíz de la muestra. Se puede excluir encuestadoras (p. ej. el CIS).
2. **Base provincial**: voto de 2023 adaptado a 2026. Sumar se reparte entre Frente Amplio y Podemos con la
   proporción de las europeas de 2024; en la Comunidad Valenciana pasa entero a Compromís: Front Valencià; Nueva
   Canarias se suma a la UPC; UPN al PP; SALF sale de las europeas y Adelante Andalucía de las andaluzas de 2026.
   Quien no presenta lista en una provincia tiene 0 votos allí.
3. **Traslado**: proporcional (cada partido escala su voto en todas sus provincias hasta su promedio nacional),
   uniforme (mismos puntos en todas) o mixto.
4. **Reparto**: barrera del 3 % en cada provincia y D'Hondt.
5. **Simulación**: error nacional por partido (dispersión entre encuestadoras + error histórico) y ruido provincial.

Límites: los partidos pequeños que las encuestas nacionales no recogen (Teruel Existe, UPL, Soria ¡Ya!…) van a
«otros» y no pueden ganar escaño, y los patrones territoriales son los de 2023/2024.

No es una predicción oficial ni está vinculada a ninguna encuestadora.
