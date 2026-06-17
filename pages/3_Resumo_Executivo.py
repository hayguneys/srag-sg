"""Resumo Executivo — visão consolidada SG / SRAG / COVID."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from utils.helpers import (
    load_srag_withna, load_esus_kpi,
    render_kpis, fmt_int, paho_year_week,
    embed_html_plot,
    render_epiweek_slider, filter_epiweek,
    load_bairro_distrito, _folium_choropleth_distritos, _DISTRITO_NAMES,
    unit_code_map, SRAG_EPIWEEK_MIN,
    period_compare_label, period_compare_se_label, format_kpi_delta,
    inject_test_frames,
)

st.set_page_config(page_title="Resumo Executivo", page_icon="📋", layout="wide")
inject_test_frames()
st.title("📋 Resumo Executivo — SG / SRAG / COVID")

# IBGE Censo 2022 — população residente por Distrito Sanitário (Recife)
_DS_POP = {
    "DS I": 57466, "DS II": 211471, "DS III": 193372, "DS IV": 234614,
    "DS V": 263748, "DS VI": 334271, "DS VII": 116463, "DS VIII": 228742,
}

# ============================================================
# Load data
# ============================================================
_srag_all = load_srag_withna()
_srag_all = _srag_all[_srag_all["ID_MN_RESI"] == "RECIFE"].copy()

_esus_all = load_esus_kpi()
_esus_rec = _esus_all[_esus_all["municipio"] == "Recife"].copy() if "municipio" in _esus_all.columns else _esus_all.copy()

# ============================================================
# Unit filter (SRAG units)
# ============================================================
_SRAG_UNIT_COL = "ID_UNIDADE"
_SRAG_CODE_COL = "CO_UNI_NOT"
_CLINICAS_SRAG = {
    "US 153 POLICLINICA E MATERNIDADE ARNALDO MARQUES":       "ARNALDO MARQUES",
    "US 159 POLICLINICA AGAMENON MAGALHAES":                  "US 159 POLICLINICA",
    "US 163 HOSPITAL DE PEDIATRIA HELENA MOURA":              "HELENA MOURA",
    "US 164 CENTRO DE REIDRATACAO E URG PED M CRAVO GAMA":   "CRAVO GAMA",
    "US 167 POLICLINICA E MATERNIDADE PROFESSOR BARROS LIMA": "BARROS LIMA",
    "US 169 POLICLINICA AMAURY COUTINHO":                     "AMAURY COUTINHO",
}
_UNI_TODAS  = "__todas__"
_UNI_MUNI   = "__municipais__"
_UNI_EXMUNI = "__exceto_municipais__"
_UNI_DIV    = "__sec_municipais__"
_UNI_DIV2   = "__sec_todas__"
_UNI_LABELS = {
    _UNI_TODAS:  "Todas as unidades",
    _UNI_MUNI:   "Todas as municipais",
    _UNI_EXMUNI: "Todas exceto municipais",
    _UNI_DIV:    "──────  Unidades municipais  ──────",
    _UNI_DIV2:   "──────  Todas as unidades de notificação  ──────",
}
_SRAG_UNIT_CODE  = unit_code_map(_srag_all, _SRAG_UNIT_COL, _SRAG_CODE_COL)
_SRAG_UNIT_NAMES = sorted(k for k in _SRAG_UNIT_CODE if k not in _CLINICAS_SRAG)
_UNI_OPTIONS = (
    [_UNI_TODAS, _UNI_MUNI, _UNI_EXMUNI, _UNI_DIV]
    + list(_CLINICAS_SRAG.keys())
    + [_UNI_DIV2]
    + _SRAG_UNIT_NAMES
)


def _uni_label(opt):
    return _UNI_LABELS.get(opt, opt)


def _filtra_clinicas_srag(df, selecionadas):
    if _SRAG_UNIT_COL not in df.columns:
        return df
    sel = [s for s in (selecionadas or []) if s not in (_UNI_DIV, _UNI_DIV2)]
    if not sel or _UNI_TODAS in sel:
        return df
    _nm = df[_SRAG_UNIT_COL].str.upper().str.strip().fillna("")
    _muni_kw = list(_CLINICAS_SRAG.values())
    is_muni = _nm.apply(lambda x: any(k in x for k in _muni_kw))
    mask = pd.Series(False, index=df.index)
    matched = False
    if _UNI_MUNI in sel:
        mask = mask | is_muni; matched = True
    if _UNI_EXMUNI in sel:
        mask = mask | (~is_muni); matched = True
    _indiv_kw = [_CLINICAS_SRAG[c] for c in sel if c in _CLINICAS_SRAG]
    if _indiv_kw:
        mask = mask | _nm.apply(lambda x: any(k in x for k in _indiv_kw)); matched = True
    _exact = {s.upper().strip() for s in sel if s in _SRAG_UNIT_CODE}
    if _exact:
        mask = mask | _nm.isin(_exact); matched = True
    if not matched:
        return df
    return df[mask].copy()


# ============================================================
# SECTION 1 — Filters + KPI cards
# ============================================================
_c_year, _c_unit = st.columns([2, 2])
with _c_year:
    _se_lo, _se_hi = render_epiweek_slider("resumo_se", start=SRAG_EPIWEEK_MIN)
with _c_unit:
    _unit_filter = st.multiselect(
        "Unidade de Notificação (SRAG)", _UNI_OPTIONS,
        default=[], key="resumo_unit", format_func=_uni_label,
        placeholder="Todas as unidades",
    )

# Apply filters — SRAG
_srag_filt = filter_epiweek(_srag_all, "DT_SIN_PRI", _se_lo, _se_hi)
_srag_filt = _filtra_clinicas_srag(_srag_filt, _unit_filter)

# Apply filters — eSUS (date only; no unit filter available)
_esus_filt = filter_epiweek(_esus_rec, "datanotificacao", _se_lo, _se_hi)

# Previous period (same SE window, one year back) for deltas
_se_lo_prev = (_se_lo[0] - 1, _se_lo[1])
_se_hi_prev = (_se_hi[0] - 1, _se_hi[1])
_srag_prev = filter_epiweek(_srag_all, "DT_SIN_PRI", _se_lo_prev, _se_hi_prev)
_srag_prev = _filtra_clinicas_srag(_srag_prev, _unit_filter)
_esus_prev = filter_epiweek(_esus_rec, "datanotificacao", _se_lo_prev, _se_hi_prev)

_cmp    = period_compare_label(_se_lo, _se_hi)
_cmp_se = period_compare_se_label(_se_lo, _se_hi)

_notif_srag       = len(_srag_filt)
_notif_srag_prev  = len(_srag_prev)
_obitos_srag      = int((pd.to_numeric(_srag_filt["EVOLUCAO"], errors="coerce") == 2).sum()) if "EVOLUCAO" in _srag_filt.columns else 0
_obitos_srag_prev = int((pd.to_numeric(_srag_prev["EVOLUCAO"], errors="coerce") == 2).sum()) if "EVOLUCAO" in _srag_prev.columns else 0
_notif_esus       = len(_esus_filt)
_notif_esus_prev  = len(_esus_prev)

render_kpis([
    ("Notificados SRAG",      fmt_int(_notif_srag),  format_kpi_delta(_notif_srag,  _notif_srag_prev,  _cmp), _cmp_se),
    ("Óbitos SRAG",           fmt_int(_obitos_srag), format_kpi_delta(_obitos_srag, _obitos_srag_prev, _cmp), _cmp_se),
    ("Atendimentos SG",       "—",                   None,                                                    None),
    ("Notificados SG (eSUS)", fmt_int(_notif_esus),  format_kpi_delta(_notif_esus,  _notif_esus_prev,  _cmp), _cmp_se),
])
st.caption(f"Fonte: SESAU/SEVS/GGAM/GEVEPI/DDT/SIVEP-GRIPE · SESAU/SEVS/GGAM/GEVEPI/DDT/ESUS-NOTIFICA")

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
# SECTION 3 — Taxa de Incidência por Distrito Sanitário (SRAG)
# ============================================================
st.markdown("## Taxa de Incidência por Distrito Sanitário — Recife")


@st.cache_data(show_spinner="Calculando incidência por distrito…")
def _build_distrito_data():
    bairro_ds = load_bairro_distrito()
    _sr = load_srag_withna()
    _sr = _sr[_sr["ID_MN_RESI"] == "RECIFE"].copy()
    _sr = _sr[_sr["DT_SIN_PRI"].dt.year.between(2022, 2026)].copy()
    _yr, _wk = paho_year_week(_sr["DT_SIN_PRI"])
    _sr = _sr[~((_yr == 2026) & (_wk > 16))]
    if "NM_BAIRRO" not in _sr.columns:
        return pd.DataFrame()
    _sr["bairro"] = _sr["NM_BAIRRO"].str.upper().str.strip().fillna("")
    _sr = _sr[_sr["bairro"] != ""]
    _sr = _sr.merge(bairro_ds, on="bairro", how="left").dropna(subset=["distrito"])
    agg = _sr.groupby("distrito").size().reset_index(name="n")
    base = pd.DataFrame({"distrito": list(_DISTRITO_NAMES.values())})
    out = base.merge(agg, on="distrito", how="left")
    out["n"]   = out["n"].fillna(0).astype(int)
    out["pop"] = out["distrito"].map(_DS_POP)
    out["taxa"] = (out["n"] / out["pop"] * 100_000).round(1)
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
        height=920, scrolling=False,
    )
    st.caption("Fonte: SESAU/SEVS/GGAM/GEVEPI/DDT/SIVEP-GRIPE · Pop. IBGE Censo 2022.")
