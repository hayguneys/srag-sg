"""Resumo Executivo — visão consolidada SG / SRAG / COVID."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.helpers import (
    load_sg, load_srag_withna, load_esus_kpi, load_esus_incidencia,
    render_kpis, fmt_int, paho_year_week,
    embed_html_plot, DATA_DIR,
)

st.set_page_config(page_title="Resumo Executivo", page_icon="📋", layout="wide")
st.title("📋 Resumo Executivo — SG / SRAG / COVID")

# ============================================================
# SECTION 1 — KPI cards: eSUS-Notifica COVID
# ============================================================
st.markdown("## Casos COVID-19 — eSUS-Notifica")
st.caption("Notificações 2022–2026 (todas as datas disponíveis). Testes positivos = resultadofinal 'Positivo'.")

@st.cache_data(show_spinner="Calculando KPIs eSUS…")
def _compute_kpis():
    df = load_esus_kpi()
    df = df[df["datanotificacao"].dt.year.between(2022, 2026)].copy()

    br_total   = len(df)
    br_pos     = int((df["resultadofinal"] == "Positivo").sum())

    pe_df      = df[df["estadonotificacao"] == "Pernambuco"] if "estadonotificacao" in df.columns else pd.DataFrame()
    pe_total   = len(pe_df)
    pe_pos     = int((pe_df["resultadofinal"] == "Positivo").sum()) if not pe_df.empty else 0

    rec_df     = df[df["municipionotificacao"] == "Recife"] if "municipionotificacao" in df.columns else pd.DataFrame()
    rec_total  = len(rec_df)
    rec_pos    = int((rec_df["resultadofinal"] == "Positivo").sum()) if not rec_df.empty else 0

    return br_total, br_pos, pe_total, pe_pos, rec_total, rec_pos

br_total, br_pos, pe_total, pe_pos, rec_total, rec_pos = _compute_kpis()

_k1, _k2, _k3 = st.columns(3)
with _k1:
    st.markdown("#### Brasil")
    render_kpis([
        ("Casos notificados", fmt_int(br_total)),
        ("Testes positivos",  fmt_int(br_pos)),
    ])
with _k2:
    st.markdown("#### Pernambuco")
    render_kpis([
        ("Casos notificados", fmt_int(pe_total)),
        ("Testes positivos",  fmt_int(pe_pos)),
    ])
with _k3:
    st.markdown("#### Recife")
    render_kpis([
        ("Casos notificados", fmt_int(rec_total)),
        ("Testes positivos",  fmt_int(rec_pos)),
    ])

st.markdown("---")

# ============================================================
# SECTION 2 — Nowcasting + Forecasting
# ============================================================
st.markdown("## Nowcasting + Forecasting")
_fc1, _fc2 = st.columns(2)
with _fc1:
    st.markdown("#### SG — Síndrome Gripal")
    embed_html_plot("nowcasting_sg.html", height=520)
with _fc2:
    st.markdown("#### SRAG — Síndrome Respiratória Aguda Grave")
    embed_html_plot("nowcasting_srag.html", height=520)

st.markdown("---")

# ============================================================
# SECTION 3 — SRAG Death Heatmap (Recife)
# ============================================================
st.markdown("## Mapa de Calor — Óbitos SRAG por Bairro de Residência (Recife)")
st.caption("Calor proporcional ao nº de óbitos por bairro. ~82 % dos registros foram geolocalizados.")

@st.cache_data(show_spinner="Carregando lookup de bairros…")
def _load_lookup():
    p = DATA_DIR / "srag_bairro_lookup.csv"
    return pd.read_csv(p, encoding="utf-8") if p.exists() else None

@st.cache_data(show_spinner="Carregando óbitos SRAG…")
def _load_srag_deaths():
    df = load_srag_withna()
    df = df[df["ID_MUNICIP"] == "RECIFE"].copy()
    df["EVOLUCAO"]   = pd.to_numeric(df["EVOLUCAO"],   errors="coerce")
    df["NU_IDADE_N"] = pd.to_numeric(df["NU_IDADE_N"], errors="coerce")
    df = df[df["EVOLUCAO"] == 2].copy()
    if "NM_BAIRRO" in df.columns:
        df["NM_BAIRRO"] = df["NM_BAIRRO"].str.title()
    return df

_lookup  = _load_lookup()
_ob_srag = _load_srag_deaths()

if _lookup is None:
    st.warning("Lookup de bairros não encontrado (`data/srag_bairro_lookup.csv`).")
elif _ob_srag.empty:
    st.info("Nenhum óbito SRAG encontrado.")
else:
    import folium
    from folium.plugins import HeatMap
    import streamlit.components.v1 as _comp

    _ob_map = _ob_srag.copy()
    _ob_map["_raw"] = _ob_map["NM_BAIRRO"].str.strip().str.upper().fillna("")
    _lk = _lookup[["raw", "official", "lat", "lon"]].copy()
    _lk["raw"] = _lk["raw"].str.strip().str.upper()
    _ob_map = _ob_map.merge(_lk, left_on="_raw", right_on="raw", how="left")
    _ob_geo = _ob_map.dropna(subset=["lat", "lon"])

    if not _ob_geo.empty:
        _heat_df = _ob_geo.groupby(["official", "lat", "lon"]).size().reset_index(name="weight")
        _pct_loc = len(_ob_geo) / max(len(_ob_map), 1) * 100
        _max_w   = _heat_df["weight"].max()

        _fmap = folium.Map(location=[-8.054, -34.881], zoom_start=12, tiles="CartoDB positron")
        HeatMap(
            _heat_df[["lat", "lon", "weight"]].values.tolist(),
            min_opacity=0.35, max_val=_max_w, radius=28, blur=22,
            gradient={0.2: "#4C78A8", 0.5: "#F58518", 0.8: "#E45756", 1.0: "#9B0000"},
        ).add_to(_fmap)
        for _, _row in _heat_df.nlargest(15, "weight").iterrows():
            folium.CircleMarker(
                location=[_row["lat"], _row["lon"]],
                radius=max(4, min(18, _row["weight"] / _max_w * 18)),
                color="#E45756", fill=True, fill_opacity=0.7,
                tooltip=f"{_row['official']}: {int(_row['weight'])} óbitos",
            ).add_to(_fmap)
        _comp.html(_fmap._repr_html_(), height=520, scrolling=False)
        st.caption(
            f"{len(_ob_geo):,} de {len(_ob_map):,} óbitos geolocalizados ({_pct_loc:.0f}%) · "
            f"Top bairro: **{_heat_df.nlargest(1,'weight').iloc[0]['official']}** "
            f"({int(_heat_df['weight'].max())} óbitos)"
        )

st.markdown("---")

# ============================================================
# SECTION 4 — Incidence Heatmap (COVID / SG / SRAG)
# ============================================================
st.markdown("## Mapa de Ocorrência — Casos por Bairro de Residência (Recife)")
st.caption(
    "Combina notificações eSUS-COVID, casos SG e casos SRAG com bairro de residência. "
    "Período 2022–2026, cap SE16/2026. Intensidade proporcional ao nº de casos."
)

@st.cache_data(show_spinner="Consolidando casos por bairro…")
def _build_incidence():
    rows = []

    # --- eSUS (COVID) -------------------------------------------------------
    df_esus = load_esus_incidencia()
    if not df_esus.empty and "bairro" in df_esus.columns:
        _e = df_esus[df_esus["municipionotificacao"] == "Recife"].copy() if "municipionotificacao" in df_esus.columns else df_esus
        _e = _e[_e["datanotificacao"].dt.year.between(2022, 2026)].copy()
        _yr_e, _wk_e = paho_year_week(_e["datanotificacao"])
        _e = _e[~((_yr_e == 2026) & (_wk_e > 16))]
        _e["_bairro"] = _e["bairro"].str.strip().str.upper().fillna("")
        _e["_fonte"] = "eSUS-COVID"
        rows.append(_e[["_bairro", "_fonte"]])

    # --- SG -----------------------------------------------------------------
    df_sg = load_sg()
    df_sg = df_sg[df_sg["COD_MUNIC"] == 261160].copy()
    df_sg = df_sg[df_sg["DT_DIGITA"].dt.year.between(2022, 2026)].copy()
    _yr_sg, _wk_sg = paho_year_week(df_sg["DT_DIGITA"])
    df_sg = df_sg[~((_yr_sg == 2026) & (_wk_sg > 16))]
    if "NOM_BAIRRO" in df_sg.columns:
        df_sg["_bairro"] = df_sg["NOM_BAIRRO"].str.strip().str.upper().fillna("")
        df_sg["_fonte"] = "SG"
        rows.append(df_sg[["_bairro", "_fonte"]])

    # --- SRAG ---------------------------------------------------------------
    df_srag = load_srag_withna()
    df_srag = df_srag[df_srag["ID_MUNICIP"] == "RECIFE"].copy()
    df_srag = df_srag[df_srag["DT_DIGITA"].dt.year.between(2022, 2026)].copy()
    _yr_sr, _wk_sr = paho_year_week(df_srag["DT_DIGITA"])
    df_srag = df_srag[~((_yr_sr == 2026) & (_wk_sr > 16))]
    if "NM_BAIRRO" in df_srag.columns:
        df_srag["_bairro"] = df_srag["NM_BAIRRO"].str.strip().str.upper().fillna("")
        df_srag["_fonte"] = "SRAG"
        rows.append(df_srag[["_bairro", "_fonte"]])

    if not rows:
        return pd.DataFrame()
    combined = pd.concat(rows, ignore_index=True)
    combined = combined[combined["_bairro"] != ""]
    return combined.groupby("_bairro").size().reset_index(name="n_casos")

_incid = _build_incidence()

if _incid.empty:
    st.info("Sem dados de bairro de residência disponíveis.")
elif _lookup is None:
    st.warning("Lookup de bairros não encontrado.")
else:
    import folium
    from folium.plugins import HeatMap
    import streamlit.components.v1 as _comp2

    _lk2 = _lookup[["raw", "official", "lat", "lon"]].copy()
    _lk2["raw"] = _lk2["raw"].str.strip().str.upper()
    _inc_geo = _incid.merge(_lk2, left_on="_bairro", right_on="raw", how="left").dropna(subset=["lat", "lon"])

    if _inc_geo.empty:
        st.info("Nenhum bairro reconhecido no lookup geográfico.")
    else:
        _max_n   = _inc_geo["n_casos"].max()
        _pct_loc = len(_inc_geo) / max(len(_incid), 1) * 100

        _fmap2 = folium.Map(location=[-8.054, -34.881], zoom_start=12, tiles="CartoDB positron")
        HeatMap(
            _inc_geo[["lat", "lon", "n_casos"]].values.tolist(),
            min_opacity=0.3, max_val=_max_n, radius=30, blur=24,
            gradient={0.2: "#54A24B", 0.5: "#EECA3B", 0.8: "#F58518", 1.0: "#E45756"},
        ).add_to(_fmap2)
        for _, _row in _inc_geo.nlargest(15, "n_casos").iterrows():
            folium.CircleMarker(
                location=[_row["lat"], _row["lon"]],
                radius=max(4, min(20, _row["n_casos"] / _max_n * 20)),
                color="#E45756", fill=True, fill_opacity=0.65,
                tooltip=f"{_row['official']}: {int(_row['n_casos']):,} casos",
            ).add_to(_fmap2)
        _comp2.html(_fmap2._repr_html_(), height=540, scrolling=False)
        st.caption(
            f"{len(_inc_geo):,} bairros geolocalizados ({_pct_loc:.0f}% das entradas únicas) · "
            f"Top bairro: **{_inc_geo.nlargest(1,'n_casos').iloc[0]['official']}** "
            f"({int(_inc_geo['n_casos'].max()):,} casos combinados)"
        )

        # Bar chart of top 15 bairros
        _top15_inc = _inc_geo.nlargest(15, "n_casos")[["official", "n_casos"]].sort_values("n_casos")
        _fig_bar = px.bar(
            _top15_inc, x="n_casos", y="official", orientation="h",
            title="Top 15 Bairros — Casos Combinados (eSUS + SG + SRAG)",
            labels={"official": "", "n_casos": "Nº Casos"},
            color_discrete_sequence=["#E45756"],
        )
        _fig_bar.update_layout(
            yaxis=dict(autorange="reversed"),
            margin=dict(l=10, r=10, t=50, b=10),
            height=420,
            plot_bgcolor="white",
        )
        st.plotly_chart(_fig_bar, use_container_width=True)
