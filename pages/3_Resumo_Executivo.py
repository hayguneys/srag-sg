"""Resumo Executivo — visão consolidada SG / SRAG / COVID."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from utils.helpers import (
    load_sg, load_srag_withna, load_esus_kpi,
    fmt_int, paho_year_week,
    embed_html_plot,
    load_bairro_distrito, _folium_choropleth_distritos,
)

st.set_page_config(page_title="Resumo Executivo", page_icon="📋", layout="wide")
st.title("Resumo Executivo — SG / SRAG")

# ============================================================
# SECTION 1 — Pairs KPI: SG · SRAG · eSUS (2022–2026, Recife)
# ============================================================
st.markdown("## Resumo 2022–2026 — Recife")

@st.cache_data(show_spinner="Calculando KPIs…")
def _compute_all_kpis():
    n = lambda col, val: int((pd.to_numeric(col, errors="coerce") == val).sum())

    # ── SG ──────────────────────────────────────────────────
    sg = load_sg()
    sg = sg[sg["COD_MUNIC"] == 261160].copy()
    sg = sg[sg["DT_DIGITA"].dt.year.between(2022, 2026)]
    _yr, _wk = paho_year_week(sg["DT_DIGITA"])
    sg = sg[~((_yr == 2026) & (_wk > 16))]
    sg_total = len(sg)
    sg_pos = int((
        (pd.to_numeric(sg.get("IFI_RESUL"),   errors="coerce") == 1) |
        (pd.to_numeric(sg.get("POS_PCRFLU"),  errors="coerce") == 1) |
        (pd.to_numeric(sg.get("POS_PCROUT"),  errors="coerce") == 1)
    ).sum())

    # ── SRAG ────────────────────────────────────────────────
    srag = load_srag_withna()
    srag = srag[srag["ID_MUNICIP"] == "RECIFE"].copy()
    srag = srag[srag["DT_DIGITA"].dt.year.between(2022, 2026)]
    _yr2, _wk2 = paho_year_week(srag["DT_DIGITA"])
    srag = srag[~((_yr2 == 2026) & (_wk2 > 16))]
    srag_total = len(srag)
    srag_pos = int((
        (pd.to_numeric(srag.get("POS_PCRFLU"), errors="coerce") == 1) |
        (pd.to_numeric(srag.get("POS_PCROUT"), errors="coerce") == 1) |
        (pd.to_numeric(srag.get("AN_SARS2"),   errors="coerce") == 1) |
        (pd.to_numeric(srag.get("AN_VSR"),     errors="coerce") == 1)
    ).sum())

    # ── eSUS-Notifica ────────────────────────────────────────
    esus = load_esus_kpi()
    esus = esus[esus["datanotificacao"].dt.year.between(2022, 2026)]
    esus = esus[esus["municipionotificacao"] == "Recife"] if "municipionotificacao" in esus.columns else esus
    esus_total = len(esus)
    esus_pos   = int((esus["resultadofinal"] == "Positivo").sum())

    return sg_total, sg_pos, srag_total, srag_pos, esus_total, esus_pos

sg_total, sg_pos, srag_total, srag_pos, esus_total, esus_pos = _compute_all_kpis()

_k1, _k2, _k3 = st.columns(3)
with _k1:
    st.markdown("**SG — Síndrome Gripal**")
    st.metric("Ocorrências",      fmt_int(sg_total))
    st.metric("Testes positivos", fmt_int(sg_pos))
with _k2:
    st.markdown("**SRAG — Síndrome Respiratória Aguda Grave**")
    st.metric("Ocorrências",      fmt_int(srag_total))
    st.metric("Testes positivos", fmt_int(srag_pos))
with _k3:
    st.markdown("**eSUS-Notifica — COVID-19**")
    st.metric("Ocorrências",      fmt_int(esus_total))
    st.metric("Testes positivos", fmt_int(esus_pos))

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
# SECTION 3 — Casos por Distrito Sanitário (mapa interativo)
# ============================================================
st.markdown("## Casos por Distrito Sanitário (SG + SRAG)")

_DS_POP = {
    "DS I":    57466,
    "DS II":   211471,
    "DS III":  193372,
    "DS IV":   234614,
    "DS V":    263748,
    "DS VI":   334271,
    "DS VII":  116463,
    "DS VIII": 228742,
}

@st.cache_data(show_spinner="Agregando casos por distrito…")
def _build_distrito_data():
    bairro_ds = load_bairro_distrito()

    def _agg(df_bairro):
        df_bairro = df_bairro[df_bairro["bairro"] != ""]
        merged = df_bairro.merge(bairro_ds, on="bairro", how="left").dropna(subset=["distrito"])
        return merged.groupby("distrito").size().reset_index(name="n")

    # SG
    df_sg = load_sg()
    df_sg = df_sg[df_sg["COD_MUNIC"] == 261160].copy()
    df_sg = df_sg[df_sg["DT_DIGITA"].dt.year.between(2022, 2026)].copy()
    _yr_sg, _wk_sg = paho_year_week(df_sg["DT_DIGITA"])
    df_sg = df_sg[~((_yr_sg == 2026) & (_wk_sg > 16))]
    sg_dist = pd.DataFrame()
    if "NOM_BAIRRO" in df_sg.columns:
        df_sg["bairro"] = df_sg["NOM_BAIRRO"].str.upper().str.strip().fillna("")
        sg_dist = _agg(df_sg[["bairro"]]).rename(columns={"n": "sg"})

    # SRAG
    df_srag = load_srag_withna()
    df_srag = df_srag[df_srag["ID_MUNICIP"] == "RECIFE"].copy()
    df_srag = df_srag[df_srag["DT_DIGITA"].dt.year.between(2022, 2026)].copy()
    _yr_sr, _wk_sr = paho_year_week(df_srag["DT_DIGITA"])
    df_srag = df_srag[~((_yr_sr == 2026) & (_wk_sr > 16))]
    srag_dist = pd.DataFrame()
    if "NM_BAIRRO" in df_srag.columns:
        df_srag["bairro"] = df_srag["NM_BAIRRO"].str.upper().str.strip().fillna("")
        srag_dist = _agg(df_srag[["bairro"]]).rename(columns={"n": "srag"})

    if sg_dist.empty and srag_dist.empty:
        return pd.DataFrame()

    from utils.helpers import _DISTRITO_NAMES
    all_ds = pd.DataFrame({"distrito": list(_DISTRITO_NAMES.values())})
    result = all_ds.merge(sg_dist,   on="distrito", how="left") \
                   .merge(srag_dist, on="distrito", how="left")
    result["sg"]   = result["sg"].fillna(0).astype(int)
    result["srag"] = result["srag"].fillna(0).astype(int)
    result["n"]    = result["sg"] + result["srag"]
    result["pop"]  = result["distrito"].map(_DS_POP)
    result["taxa_sg"]   = (result["sg"]   / result["pop"] * 100_000).round(1)
    result["taxa_srag"] = (result["srag"] / result["pop"] * 100_000).round(1)
    result["taxa"]      = (result["n"]    / result["pop"] * 100_000).round(1)
    return result[result["n"] > 0].reset_index(drop=True)

_dist_data = _build_distrito_data()
if _dist_data.empty:
    st.info("Sem dados de distrito disponíveis.")
else:
    from utils.helpers import _folium_choropleth_distritos
    _view = st.radio(
        "Métrica",
        ["Taxa de incidência (por 100.000 hab.)", "Números absolutos"],
        horizontal=True,
        key="distrito_metric",
        label_visibility="collapsed",
    )
    _col = "taxa" if _view.startswith("Taxa") else "n"
    components.html(_folium_choropleth_distritos(_dist_data, color_col=_col), height=540, scrolling=False)
