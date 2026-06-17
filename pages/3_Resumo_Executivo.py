"""Resumo Executivo — visão consolidada SG / SRAG / COVID."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from utils.helpers import (
    load_sg, load_srag_withna, load_esus_kpi,
    render_kpis, fmt_int, paho_year_week,
    embed_html_plot,
    load_bairro_distrito, _folium_choropleth_distritos, _DISTRITO_NAMES,
)

st.set_page_config(page_title="Resumo Executivo", page_icon="📋", layout="wide")
st.title("📋 Resumo Executivo — SG / SRAG / COVID")

# IBGE Censo 2022 — população residente por Distrito Sanitário (Recife)
_DS_POP = {
    "DS I": 57466, "DS II": 211471, "DS III": 193372, "DS IV": 234614,
    "DS V": 263748, "DS VI": 334271, "DS VII": 116463, "DS VIII": 228742,
}

# ============================================================
# SECTION 1 — KPI cards: eSUS-Notifica COVID
# ============================================================
st.markdown("## Casos COVID-19")
st.caption("Notificações 2022–2026 (todas as datas disponíveis). Testes positivos = resultadofinal 'Positivo'.")

@st.cache_data(show_spinner="Calculando KPIs eSUS…")
def _compute_kpis():
    df = load_esus_kpi()
    df = df[df["datanotificacao"].dt.year.between(2022, 2026)].copy()
    rec_df    = df[df["municipionotificacao"] == "Recife"] if "municipionotificacao" in df.columns else df
    rec_total = len(rec_df)
    rec_pos   = int((rec_df["resultadofinal"] == "Positivo").sum())
    return rec_total, rec_pos

rec_total, rec_pos = _compute_kpis()

st.markdown("#### Recife")
render_kpis([
    ("Casos notificados", fmt_int(rec_total)),
    ("Testes positivos",  fmt_int(rec_pos)),
])
st.caption("Fonte: BRASIL. Ministério da Saúde. eSUS-Notifica. Brasília, 2026.")

st.markdown("---")

# ============================================================
# SECTION 2 — Nowcasting + Forecasting (SRAG only)
# ============================================================
st.markdown("## Nowcasting + Forecasting")
st.markdown("#### SRAG — Síndrome Respiratória Aguda Grave")
embed_html_plot("nowcasting_srag.html", height=520, fix_legend=True)
st.caption("Fonte: BRASIL. Ministério da Saúde. SIVEP-GRIPE. Banco de Dados de Síndromes Respiratórias Agudas Graves. Brasília, 2026.")

st.markdown("---")

# ============================================================
# SECTION 3 — Taxa de Incidência por Distrito Sanitário (SG + SRAG)
# ============================================================
st.markdown("## Taxa de Incidência por Distrito Sanitário — Recife")
st.caption(
    "Casos SG + SRAG com bairro de residência em Recife, agregados por Distrito "
    "Sanitário (DS I–DS VIII). Período 2022–2026, cap SE16/2026. "
    "Taxa por 100.000 habitantes — população IBGE Censo 2022."
)


@st.cache_data(show_spinner="Calculando incidência por distrito…")
def _build_distrito_data():
    bairro_ds = load_bairro_distrito()

    # --- SG (município de residência = Recife, data dos primeiros sintomas) --
    _sg = load_sg()
    _sg = _sg[_sg["COD_MUNRES"] == 261160].copy()
    _sg = _sg[_sg["DT_PRISINT"].dt.year.between(2022, 2026)].copy()
    _yr, _wk = paho_year_week(_sg["DT_PRISINT"])
    _sg = _sg[~((_yr == 2026) & (_wk > 16))]
    if "NOM_BAIRRO" in _sg.columns:
        _sg["bairro"] = _sg["NOM_BAIRRO"].str.upper().str.strip().fillna("")
        _sg = _sg[_sg["bairro"] != ""]
        _sg = _sg.merge(bairro_ds, on="bairro", how="left").dropna(subset=["distrito"])
        sg_agg = _sg.groupby("distrito").size().reset_index(name="sg")
    else:
        sg_agg = pd.DataFrame(columns=["distrito", "sg"])

    # --- SRAG (município de residência = Recife, data dos primeiros sintomas) --
    _sr = load_srag_withna()
    _sr = _sr[_sr["ID_MN_RESI"] == "RECIFE"].copy()
    _sr = _sr[_sr["DT_SIN_PRI"].dt.year.between(2022, 2026)].copy()
    _yr2, _wk2 = paho_year_week(_sr["DT_SIN_PRI"])
    _sr = _sr[~((_yr2 == 2026) & (_wk2 > 16))]
    if "NM_BAIRRO" in _sr.columns:
        _sr["bairro"] = _sr["NM_BAIRRO"].str.upper().str.strip().fillna("")
        _sr = _sr[_sr["bairro"] != ""]
        _sr = _sr.merge(bairro_ds, on="bairro", how="left").dropna(subset=["distrito"])
        srag_agg = _sr.groupby("distrito").size().reset_index(name="srag")
    else:
        srag_agg = pd.DataFrame(columns=["distrito", "srag"])

    # --- combine ----------------------------------------------------------
    base = pd.DataFrame({"distrito": list(_DISTRITO_NAMES.values())})
    out = base.merge(sg_agg, on="distrito", how="left").merge(srag_agg, on="distrito", how="left")
    out["sg"]   = out["sg"].fillna(0).astype(int)
    out["srag"] = out["srag"].fillna(0).astype(int)
    out["n"]    = out["sg"] + out["srag"]
    out["pop"]  = out["distrito"].map(_DS_POP)
    out["taxa_sg"]   = (out["sg"]   / out["pop"] * 100_000).round(1)
    out["taxa_srag"] = (out["srag"] / out["pop"] * 100_000).round(1)
    out["taxa"]      = (out["n"]    / out["pop"] * 100_000).round(1)
    return out[out["n"] > 0].reset_index(drop=True)


_dist_data = _build_distrito_data()

if _dist_data.empty:
    st.info("Sem dados de distrito disponíveis.")
else:
    _view = st.radio(
        "Métrica",
        ["Taxa de incidência (por 100.000 hab.)", "Números absolutos"],
        horizontal=True, key="resumo_distrito_metric", label_visibility="collapsed",
    )
    _col = "taxa" if _view.startswith("Taxa") else "n"
    components.html(
        _folium_choropleth_distritos(_dist_data, color_col=_col),
        height=540, scrolling=False,
    )
    st.caption(
        "Fonte: BRASIL. Ministério da Saúde. SIVEP-GRIPE. Banco de Dados de Síndrome "
        "Gripal e Síndromes Respiratórias Agudas Graves. Brasília, 2026. · "
        "População: IBGE, Censo Demográfico 2022."
    )
