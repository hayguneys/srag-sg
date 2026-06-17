"""SG (Síndrome Gripal) page."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.helpers import (
    load_sg, load_sg_srag_linked, render_kpis, fmt_int,
    render_ma_chart, paho_year_week,
    render_epiweek_slider, filter_epiweek, add_ma_overlay,
    render_seasonality_hist, unit_code_map, SG_EPIWEEK_MIN,
    period_compare_label, period_compare_se_label, format_kpi_delta,
    CLASSI_FIN_LABELS, CLASSI_FIN_COLORS, inject_test_frames,
)


st.set_page_config(page_title="SG", page_icon="🤧", layout="wide")
inject_test_frames()  # TEST: line frames around KPI cards
st.title("🤧 SG — Síndrome Gripal")
st.caption(
    "*Vigilância sentinela de Síndrome Gripal (SG): tem como objetivo principal "
    "identificar os vírus respiratórios circulantes e permitir o monitoramento da "
    "demanda de atendimento por essa doença.*"
)

# --- Load data — filter to Recife municipality of residence (COD_MUNRES) -----
df_all = load_sg()
df_all = df_all[df_all["COD_MUNRES"] == 261160].copy()

# Per-clinic selector: full NOME_UNIDA -> substring matched against NOME_UNIDA.
_CLINICAS_SG = {
    "US 153 POLICLINICA E MATERNIDADE ARNALDO MARQUES":      "ARNALDO MARQUES",
    "US 159 POLICLINICA AGAMENON MAGALHAES":                 "AGAMENON",
    "US 163 HOSPITAL DE PEDIATRIA HELENA MOURA":             "HELENA MOURA",
    "US 164 CENTRO DE REIDRATACAO E URG PED M CRAVO GAMA":  "CRAVO GAMA",
    "US 167 POLICLINICA E MATERNIDADE PROFESSOR BARROS LIMA":"BARROS LIMA",
    "US 169 POLICLINICA AMAURY COUTINHO":                    "AMAURY COUTINHO",
}


# Unidade de Notificação dropdown: preset shortcuts + a "Unidades municipais"
# section, then a second section listing EVERY notification unit (NOME_UNIDA)
# by full name with its unit code (COD_UNID). Streamlit's multiselect has no
# native option groups, so the section headers are decorative (no-op) options
# and the selection is resolved in _filtra_clinicas_sg.
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
    _UNI_DIV2:   "──────  Demais unidades  ──────",
}

# name -> unit code, and the full sorted list of notification-unit names.
_SG_UNIT_CODE = unit_code_map(df_all, "NOME_UNIDA", "COD_UNID")
_SG_UNIT_NAMES = sorted(k for k in _SG_UNIT_CODE if k not in _CLINICAS_SG)
_UNI_OPTIONS = (
    [_UNI_TODAS, _UNI_MUNI, _UNI_EXMUNI, _UNI_DIV]
    + list(_CLINICAS_SG.keys())
    + [_UNI_DIV2]
    + _SG_UNIT_NAMES
)


def _uni_label(opt):
    if opt in _UNI_LABELS:
        return _UNI_LABELS[opt]
    if opt in _CLINICAS_SG:
        return opt
    return opt


def _unidade_multiselect(key):
    """Render the Unidade de Notificação selector (presets + full unit list)."""
    return st.multiselect(
        "Unidade de Notificação", _UNI_OPTIONS,
        default=[], key=key, format_func=_uni_label,
        placeholder="Todas as unidades",
    )


def _filtra_clinicas_sg(df, selecionadas):
    """Resolve the unidade selection (presets + clinics + named units) into a filter.

    Empty, "Todas as unidades", or only section headers => no filtering.
    """
    if "NOME_UNIDA" not in df.columns:
        return df
    sel = [s for s in (selecionadas or []) if s not in (_UNI_DIV, _UNI_DIV2)]
    if not sel or _UNI_TODAS in sel:
        return df

    _nm = df["NOME_UNIDA"].str.upper().str.strip().fillna("")
    _muni_kw = list(_CLINICAS_SG.values())
    is_muni = _nm.apply(lambda x: any(k in x for k in _muni_kw))

    mask = pd.Series(False, index=df.index)
    matched = False
    if _UNI_MUNI in sel:
        mask = mask | is_muni
        matched = True
    if _UNI_EXMUNI in sel:
        mask = mask | (~is_muni)
        matched = True
    _indiv_kw = [_CLINICAS_SG[c] for c in sel if c in _CLINICAS_SG]
    if _indiv_kw:
        mask = mask | _nm.apply(lambda x: any(k in x for k in _indiv_kw))
        matched = True
    # Exact full-name selections from the "Todas as unidades de notificação" list.
    _exact = {s.upper().strip() for s in sel if s in _SG_UNIT_CODE}
    if _exact:
        mask = mask | _nm.isin(_exact)
        matched = True

    if not matched:
        return df
    return df[mask].copy()

_FONTE_SG   = "SESAU/SEVS/GGAM/GEVEPI/DDT/SIVEP-GRIPE"
_FONTE_PROG = "SESAU/SEVS/GGAM/GEVEPI/DDT/SIVEP-GRIPE"

# Recife total population (IBGE Censo 2022) for incidence rate per 100k
_RECIFE_POP = 1_640_147



if st.session_state.pop("sg_goto_nowcasting", False):
    import streamlit.components.v1 as components
    components.html("""<script>
    (function() {
        function clickTab() {
            var tabs = window.parent.document.querySelectorAll('[role="tab"]');
            if (tabs.length >= 3) { tabs[2].click(); }
            else { setTimeout(clickTab, 150); }
        }
        setTimeout(clickTab, 300);
    })();
    </script>""", height=0)

tab1, tab2, tab3, tab4 = st.tabs(["📊 Descritivo", "🧪 Testes", "📈 Nowcasting + Forecasting", "Progressão para SRAG"])

# ============================================================
# TAB 1 — Descriptive
# ============================================================
with tab1:

    # ---- SE/Ano range slider and unit filter --------------------------------
    _c_year, _c_unit = st.columns([2, 2])
    with _c_year:
        _se_lo, _se_hi = render_epiweek_slider("sg_desc_se", start=SG_EPIWEEK_MIN)
    with _c_unit:
        _unit_filter = _unidade_multiselect("sg_desc_unit")

    df_filt = filter_epiweek(df_all, "DT_PRISINT", _se_lo, _se_hi)
    df_filt = _filtra_clinicas_sg(df_filt, _unit_filter)

    # ---- KPIs with delta (same SE range, previous year) ----------------------
    total_cases = len(df_filt)
    vac_flu  = int((df_filt["VACINA"] == 1).sum())      if "VACINA"     in df_filt.columns else 0

    # Previous period = same SE window shifted back one year
    _se_lo_prev = (_se_lo[0] - 1, _se_lo[1])
    _se_hi_prev = (_se_hi[0] - 1, _se_hi[1])
    df_prev = filter_epiweek(df_all, "DT_PRISINT", _se_lo_prev, _se_hi_prev)
    df_prev = _filtra_clinicas_sg(df_prev, _unit_filter)

    total_cases_prev = len(df_prev)
    vac_flu_prev = int((df_prev["VACINA"] == 1).sum()) if "VACINA" in df_prev.columns else 0

    _cmp = period_compare_label(_se_lo, _se_hi)
    _cmp_se = period_compare_se_label(_se_lo, _se_hi)
    delta_total = format_kpi_delta(total_cases, total_cases_prev, _cmp)
    delta_vac   = format_kpi_delta(vac_flu, vac_flu_prev, _cmp)

    render_kpis([
        ("Total de casos", fmt_int(total_cases), delta_total, _cmp_se),
        ("Vacinação Influenza", fmt_int(vac_flu), delta_vac, _cmp_se),
    ])

    st.markdown("---")

    def _bar_layout(fig):
        fig.update_layout(
            barmode="stack",
            xaxis_tickangle=-90,
            legend=dict(orientation="h", y=-0.28, x=0.5, xanchor="center"),
            margin=dict(l=20, r=20, t=50, b=110),
            height=580,
        )

    def _add_pct_hover(fig, agg: pd.DataFrame, unit: str = "casos"):
        totals = agg.groupby("semana")["n"].transform("sum")
        agg = agg.copy()
        agg["pct"] = (agg["n"] / totals * 100).round(1)
        color_col = [c for c in agg.columns if c not in ("semana", "semana_sort", "n", "pct")][0]
        for trace in fig.data:
            rows = agg[agg[color_col] == trace.name].set_index("semana")
            pct_vals = [rows.loc[x, "pct"] if x in rows.index else float("nan")
                        for x in trace.x]
            trace.customdata = [[p] for p in pct_vals]
            trace.hovertemplate = (
                "%{x}<br>"
                f"{trace.name}: " + f"%{{y}} {unit} (%{{customdata[0]:.1f}}%)"
                "<extra></extra>"
            )

    FAIXA_BINS = [
        ("1–4",   lambda a: (a >= 1)  & (a <= 4)),
        ("5–9",   lambda a: (a >= 5)  & (a <= 9)),
        ("10–19", lambda a: (a >= 10) & (a <= 19)),
        ("20–29", lambda a: (a >= 20) & (a <= 29)),
        ("30–39", lambda a: (a >= 30) & (a <= 39)),
        ("40–49", lambda a: (a >= 40) & (a <= 49)),
        ("50–59", lambda a: (a >= 50) & (a <= 59)),
        ("60+",   lambda a: a >= 60),
    ]
    FAIXA_COLORS = {
        "1–4":   "#4C78A8",
        "5–9":   "#F58518",
        "10–19": "#E45756",
        "20–29": "#72B7B2",
        "30–39": "#54A24B",
        "40–49": "#EECA3B",
        "50–59": "#B279A2",
        "60+":   "#FF9DA6",
    }

    # ---- Resumo — perfil dos casos (sexo, faixa etária, bairro) -----------------
    st.markdown("#### Perfil dos Casos")

    _rc1, _rc2, _rc3 = st.columns(3)

    with _rc1:
        _sum_sx = df_filt.copy()
        _sum_sx["SEXO"] = pd.to_numeric(_sum_sx["SEXO"], errors="coerce")
        _sum_sx = _sum_sx[_sum_sx["SEXO"].isin([1, 2])]
        _sum_sx["_sexo"] = _sum_sx["SEXO"].astype(int).map({1: "Masculino", 2: "Feminino"})
        _sum_sx_cnt = _sum_sx["_sexo"].value_counts().reset_index()
        _sum_sx_cnt.columns = ["sexo", "n"]
        if _sum_sx_cnt.empty:
            st.info("Sem dados de sexo.")
        else:
            _fig_sum_sx = px.pie(
                _sum_sx_cnt, names="sexo", values="n", title="Por Sexo", hole=0.45,
                color="sexo",
                color_discrete_map={"Feminino": "#E45756", "Masculino": "#4C78A8"},
            )
            _fig_sum_sx.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=320)
            st.plotly_chart(_fig_sum_sx, width='stretch')

    with _rc2:
        _sum_age = df_filt.copy()
        _sum_age["IDADE"] = pd.to_numeric(_sum_age["IDADE"], errors="coerce")
        _sum_age = _sum_age.dropna(subset=["IDADE"])
        _sum_age["faixa"] = pd.NA  # ensure column exists (empty-frame safe)
        for _lbl, _msk in FAIXA_BINS:
            _sum_age.loc[_msk(_sum_age["IDADE"]), "faixa"] = _lbl
        _sum_age = _sum_age.dropna(subset=["faixa"])
        _sum_age_order = [l for l, _ in FAIXA_BINS]
        _sum_age_cnt = (
            _sum_age["faixa"].value_counts().reindex(_sum_age_order).fillna(0).reset_index()
        )
        _sum_age_cnt.columns = ["faixa", "n"]
        if _sum_age_cnt["n"].sum() == 0:
            st.info("Sem dados de faixa etária.")
        else:
            _fig_sum_age = px.bar(
                _sum_age_cnt, x="faixa", y="n", title="Por Faixa Etária",
                labels={"faixa": "Faixa Etária", "n": "Casos"},
                color_discrete_sequence=["#72B7B2"],
                category_orders={"faixa": _sum_age_order},
            )
            _fig_sum_age.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=320)
            st.plotly_chart(_fig_sum_age, width='stretch')

    with _rc3:
        _sum_bairro = (
            df_filt["NOM_BAIRRO"].str.title().value_counts().reset_index()
        ) if "NOM_BAIRRO" in df_filt.columns else pd.DataFrame()
        if _sum_bairro.empty:
            st.info("Sem dados de bairro.")
        else:
            _sum_bairro.columns = ["bairro", "n"]
            st.markdown("**Por Bairro**")
            # one bar per bairro (sorted desc), scrollable within a fixed-height box
            _bairro_h = max(280, len(_sum_bairro) * 22)
            _fig_sum_bairro = px.bar(
                _sum_bairro, x="n", y="bairro", orientation="h",
                labels={"bairro": "", "n": "Casos"},
                color_discrete_sequence=["#F58518"],
            )
            _fig_sum_bairro.update_layout(
                yaxis=dict(autorange="reversed"),
                margin=dict(l=10, r=10, t=10, b=10), height=_bairro_h,
            )
            with st.container(height=300, border=False):
                st.plotly_chart(_fig_sum_bairro, width='stretch')

    st.caption(f"Fonte: {_FONTE_SG}")

    # ---- Faixa Etária — all cases ----------------------------------------
    st.markdown("---")
    st.markdown("#### Total de Casos")

    _faixa_view = st.radio(
        "Visualização", ["Total", "Faixa Etária", "Sexo"],
        horizontal=True, key="sg_faixa_view", label_visibility="collapsed",
    )

    if _faixa_view == "Total":
        _tot = df_filt.dropna(subset=["DT_PRISINT"]).copy()
        _yr_t, _wk_t = paho_year_week(_tot["DT_PRISINT"])
        _tot["semana"]      = "SE " + _wk_t.astype(str).str.zfill(2) + "/" + _yr_t.astype(str)
        _tot["semana_sort"] = _yr_t * 100 + _wk_t
        _agg_t = _tot.groupby(["semana", "semana_sort"]).size().reset_index(name="n")
        _ord_t = _agg_t.sort_values("semana_sort")["semana"].tolist()
        _fig_t = px.bar(
            _agg_t, x="semana", y="n",
            title="Total de Casos por Semana Epidemiológica",
            labels={"semana": "Semana Epidemiológica", "n": "Nº Casos"},
            category_orders={"semana": _ord_t},
        )
        _fig_t.update_traces(marker_color="#4C78A8", hovertemplate="%{x}<br>Casos: %{y}<extra></extra>")
        _bar_layout(_fig_t)
        add_ma_overlay(_fig_t, _agg_t)
        st.plotly_chart(_fig_t, width='stretch')

    _age = df_filt.copy()
    _age["IDADE"] = pd.to_numeric(_age["IDADE"], errors="coerce")
    _age = _age.dropna(subset=["DT_PRISINT", "IDADE"])
    _age["faixa"] = pd.NA  # ensure column exists (empty-frame safe)
    for _label, _mask in FAIXA_BINS:
        _age.loc[_mask(_age["IDADE"]), "faixa"] = _label
    _age = _age.dropna(subset=["faixa"])

    if _faixa_view == "Faixa Etária":
        if _age.empty:
            st.info("Sem dados de faixa etária.")
        else:
            _yr_a, _wk_a = paho_year_week(_age["DT_PRISINT"])
            _age["semana"]      = "SE " + _wk_a.astype(str).str.zfill(2) + "/" + _yr_a.astype(str)
            _age["semana_sort"] = _yr_a * 100 + _wk_a
            _agg_a = _age.groupby(["semana", "semana_sort", "faixa"]).size().reset_index(name="n")
            _ord_a = _agg_a[["semana","semana_sort"]].drop_duplicates().sort_values("semana_sort")["semana"].tolist()
            _fig_a = px.bar(
                _agg_a, x="semana", y="n", color="faixa",
                color_discrete_map=FAIXA_COLORS,
                title="Total de Casos por Semana Epidemiológica",
                labels={"semana": "Semana Epidemiológica", "n": "Nº Casos", "faixa": "Faixa Etária"},
                category_orders={"semana": _ord_a, "faixa": [l for l, _ in FAIXA_BINS]},
            )
            _add_pct_hover(_fig_a, _agg_a)
            _bar_layout(_fig_a)
            add_ma_overlay(_fig_a, _agg_a)
            st.plotly_chart(_fig_a, width='stretch')
    elif _faixa_view == "Sexo":
        _sx = df_filt.dropna(subset=["DT_PRISINT"]).copy()
        _sx["SEXO"] = pd.to_numeric(_sx["SEXO"], errors="coerce")
        _sx = _sx[_sx["SEXO"].isin([1, 2])]
        _sx["SEXO_LABEL"] = _sx["SEXO"].astype(int).map({1: "Masculino", 2: "Feminino"})
        if _sx.empty:
            st.info("Sem dados de sexo.")
        else:
            _yr_sx, _wk_sx = paho_year_week(_sx["DT_PRISINT"])
            _sx["semana"]      = "SE " + _wk_sx.astype(str).str.zfill(2) + "/" + _yr_sx.astype(str)
            _sx["semana_sort"] = _yr_sx * 100 + _wk_sx
            _agg_sx = _sx.groupby(["semana", "semana_sort", "SEXO_LABEL"]).size().reset_index(name="n")
            _ord_sx = _agg_sx[["semana","semana_sort"]].drop_duplicates().sort_values("semana_sort")["semana"].tolist()
            _fig_sx = px.bar(
                _agg_sx, x="semana", y="n", color="SEXO_LABEL",
                color_discrete_map={"Masculino": "#4C78A8", "Feminino": "#E45756"},
                title="Casos por Sexo por Semana Epidemiológica",
                labels={"semana": "Semana Epidemiológica", "n": "Nº Casos", "SEXO_LABEL": "Sexo"},
                category_orders={"semana": _ord_sx},
            )
            _add_pct_hover(_fig_sx, _agg_sx)
            _bar_layout(_fig_sx)
            add_ma_overlay(_fig_sx, _agg_sx)
            st.plotly_chart(_fig_sx, width='stretch')
    st.caption(f"Fonte: {_FONTE_SG}")

    # ---- FIN_FLU — Influenza type (A segmented by FIN_SUBT subtypes) ------------
    st.markdown("---")
    st.markdown("#### Tipo de Influenza ")

    # Influenza A is broken down into its FIN_SUBT subtypes; Influenza B stays
    # a single category. Influenza A rows without a mapped subtype fall back to
    # a generic "Influenza A" bucket so no case is dropped.
    FIN_SUBT_LABELS = {
        1: "Influenza A (H1N1)pdm09",
        4: "Influenza A não subtipado",
        6: "Influenza A (H3N2)",
        7: "Influenza A não subtipado",  # merged with code 4
        8: "Inconclusivo",
    }
    FLU_COMBINED_COLORS = {
        "Influenza A (H1N1)pdm09":   "#E45756",
        "Influenza A (H3N2)":        "#F58518",
        "Influenza A não subtipado": "#9C9C9C",
        "Inconclusivo":              "#B279A2",
        "Influenza A":               "#D62728",
        "Influenza B":               "#4C78A8",
    }
    FLU_COMBINED_ORDER = [
        "Influenza A (H1N1)pdm09",
        "Influenza A (H3N2)",
        "Influenza A não subtipado",
        "Inconclusivo",
        "Influenza B",
    ]

    if "FIN_FLU" not in df_filt.columns:
        st.warning("Coluna FIN_FLU não encontrada.")
    else:
        _flu = df_filt.copy()
        _flu["FIN_FLU"] = pd.to_numeric(_flu["FIN_FLU"], errors="coerce")
        _flu = _flu.dropna(subset=["DT_PRISINT", "FIN_FLU"])
        _flu["FIN_FLU"] = _flu["FIN_FLU"].astype(int)
        _flu = _flu[_flu["FIN_FLU"].isin([1, 2])]
        _flu["FIN_SUBT"] = pd.to_numeric(_flu.get("FIN_SUBT"), errors="coerce")
        _sub_label = _flu["FIN_SUBT"].map(FIN_SUBT_LABELS)
        _flu["FLU_LABEL"] = _sub_label.where(_flu["FIN_FLU"] == 1, "Influenza B")
        _flu.loc[(_flu["FIN_FLU"] == 1) & _flu["FLU_LABEL"].isna(), "FLU_LABEL"] = "Influenza A não subtipado"

        if _flu.empty:
            st.info("Sem dados de tipo de influenza para os filtros selecionados.")
        else:
            _yr_f, _wk_f = paho_year_week(_flu["DT_PRISINT"])
            _flu["semana"]      = "SE " + _wk_f.astype(str).str.zfill(2) + "/" + _yr_f.astype(str)
            _flu["semana_sort"] = _yr_f * 100 + _wk_f
            _agg_f = _flu.groupby(["semana", "semana_sort", "FLU_LABEL"]).size().reset_index(name="n")
            _ord_f = _agg_f[["semana","semana_sort"]].drop_duplicates().sort_values("semana_sort")["semana"].tolist()
            _present = [l for l in FLU_COMBINED_ORDER if l in _agg_f["FLU_LABEL"].unique()]
            _fig_f = px.bar(
                _agg_f, x="semana", y="n", color="FLU_LABEL",
                color_discrete_map=FLU_COMBINED_COLORS,
                title="Tipo de Influenza por Semana Epidemiológica",
                labels={"semana": "Semana Epidemiológica", "n": "Nº Casos", "FLU_LABEL": "Tipo / Subtipo"},
                category_orders={"semana": _ord_f, "FLU_LABEL": _present},
            )
            _add_pct_hover(_fig_f, _agg_f)
            _bar_layout(_fig_f)
            _tot_f = _agg_f.groupby(["semana", "semana_sort"])["n"].sum().reset_index()
            add_ma_overlay(_fig_f, _tot_f)
            st.plotly_chart(_fig_f, width='stretch')
            st.caption(f"Fonte: {_FONTE_SG}")

    # ---- Tipo de Vírus -------------------------------------------------------
    st.markdown("---")
    st.markdown("#### Tipo de Vírus")

    # Influenza shown as subtypes/types (reuses FIN_SUBT_LABELS from above).
    # All other viruses grouped by IFI+PCR columns (deduplicated per patient).
    _SG_VIRUS_GROUPS = {
        "VSR":             ["IFI_VRS",   "PCR_VRS"],
        "SARS-CoV-2":      ["IFI_SARS2", "PCR_SARS2"],
        "Adenovírus":      ["IFI_ADENO", "PCR_ADENO"],
        "Parainfluenza 1": ["IFI_PARA1", "PCR_PARA1"],
        "Parainfluenza 2": ["IFI_PARA2", "PCR_PARA2"],
        "Parainfluenza 3": ["IFI_PARA3", "PCR_PARA3"],
        "Parainfluenza 4": ["IFI_PARA4", "PCR_PARA4"],
        "Metapneumovírus": ["PCR_METAP"],
        "Rinovírus":       ["PCR_RINO"],
        "Bocavírus":       ["PCR_BOCA"],
    }
    _SG_VIRUS_COLORS = {
        # Influenza subtypes (same palette as Tipo de Influenza chart)
        "Influenza A (H1N1)pdm09":   "#E45756",
        "Influenza A (H3N2)":        "#F58518",
        "Influenza A não subtipado": "#9C9C9C",
        "Influenza B":               "#4C78A8",
        "Inconclusivo":              "#BAB0AC",
        # Other viruses
        "VSR":             "#B279A2",
        "SARS-CoV-2":      "#54A24B",
        "Adenovírus":      "#72B7B2",
        "Parainfluenza 1": "#FF9DA6",
        "Parainfluenza 2": "#EECA3B",
        "Parainfluenza 3": "#8FBC8F",
        "Parainfluenza 4": "#B0C4DE",
        "Metapneumovírus": "#DEB887",
        "Rinovírus":       "#636363",
        "Bocavírus":       "#20B2AA",
    }
    _SG_VIRUS_ORDER = [
        "Influenza A (H1N1)pdm09", "Influenza A (H3N2)",
        "Influenza A não subtipado", "Influenza B", "Inconclusivo",
        "VSR", "SARS-CoV-2", "Adenovírus",
        "Parainfluenza 1", "Parainfluenza 2", "Parainfluenza 3", "Parainfluenza 4",
        "Metapneumovírus", "Rinovírus", "Bocavírus",
    ]

    _vrows = []

    # Influenza: subtype via FIN_FLU / FIN_SUBT (same logic as Tipo de Influenza)
    if "FIN_FLU" in df_filt.columns:
        _flu_v = df_filt.copy()
        _flu_v["FIN_FLU"] = pd.to_numeric(_flu_v["FIN_FLU"], errors="coerce")
        _flu_v = _flu_v[_flu_v["FIN_FLU"].isin([1, 2]) & _flu_v["DT_PRISINT"].notna()].copy()
        if not _flu_v.empty:
            _flu_v["FIN_SUBT"] = pd.to_numeric(_flu_v.get("FIN_SUBT"), errors="coerce")
            _sub_lbl = _flu_v["FIN_SUBT"].map(FIN_SUBT_LABELS)
            _flu_v["virus"] = _sub_lbl.where(_flu_v["FIN_FLU"] == 1, "Influenza B")
            _flu_v.loc[(_flu_v["FIN_FLU"] == 1) & _flu_v["virus"].isna(), "virus"] = "Influenza A não subtipado"
            _vrows.append(_flu_v[["DT_PRISINT", "virus"]].copy())

    # Other viruses: IFI + PCR deduplicated per patient per label
    for _vlabel, _vcols in _SG_VIRUS_GROUPS.items():
        _avail = [c for c in _vcols if c in df_filt.columns]
        if not _avail:
            continue
        _vmask = pd.concat(
            [pd.to_numeric(df_filt[c], errors="coerce") >= 1 for c in _avail], axis=1
        ).any(axis=1)
        _vtmp = df_filt.loc[_vmask & df_filt["DT_PRISINT"].notna(), ["DT_PRISINT"]].copy()
        _vtmp["virus"] = _vlabel
        _vrows.append(_vtmp)

    if not _vrows:
        st.info("Sem dados de tipo de vírus para os filtros selecionados.")
    else:
        _vlong = pd.concat(_vrows, ignore_index=True)
        _yr_v, _wk_v = paho_year_week(_vlong["DT_PRISINT"])
        _vlong["semana"]      = "SE " + _wk_v.astype(str).str.zfill(2) + "/" + _yr_v.astype(str)
        _vlong["semana_sort"] = _yr_v * 100 + _wk_v
        _agg_v = _vlong.groupby(["semana", "semana_sort", "virus"]).size().reset_index(name="n")
        _ord_v = _agg_v[["semana", "semana_sort"]].drop_duplicates().sort_values("semana_sort")["semana"].tolist()
        _present_v = [l for l in _SG_VIRUS_ORDER if l in _agg_v["virus"].unique()]
        _fig_v = px.bar(
            _agg_v, x="semana", y="n", color="virus",
            color_discrete_map=_SG_VIRUS_COLORS,
            title="Tipo de Vírus por Semana Epidemiológica",
            labels={"semana": "Semana Epidemiológica", "n": "Nº Casos", "virus": "Vírus"},
            category_orders={"semana": _ord_v, "virus": _present_v},
        )
        _add_pct_hover(_fig_v, _agg_v)
        _bar_layout(_fig_v)
        _tot_v = _agg_v.groupby(["semana", "semana_sort"])["n"].sum().reset_index()
        add_ma_overlay(_fig_v, _tot_v)
        st.plotly_chart(_fig_v, width='stretch')
        st.caption(f"Fonte: {_FONTE_SG}")


# ============================================================
# TAB 2 — Taxas de Positividade
# ============================================================
with tab2:

    # ---- SE/Ano range slider and unit filter --------------------------------
    _t2_cy, _t2_cu = st.columns([2, 2])
    with _t2_cy:
        _t2_se_lo, _t2_se_hi = render_epiweek_slider("sg_test_se", start=SG_EPIWEEK_MIN)
    with _t2_cu:
        _t2_unit = _unidade_multiselect("sg_test_unit")

    _df_t2 = filter_epiweek(df_all, "DT_PRISINT", _t2_se_lo, _t2_se_hi)
    _df_t2 = _filtra_clinicas_sg(_df_t2, _t2_unit)

    # ---- Total de Testes ----------------------------------------
    st.markdown("### Total de Testes")

    _sg_base = _df_t2.dropna(subset=["DT_PRISINT"]).copy()

    _tot_rows, _pos_rows = [], []

    if "IFI" in _sg_base.columns and "IFI_RESUL" in _sg_base.columns:
        _ifi = _sg_base.copy()
        _ifi["IFI"]       = pd.to_numeric(_ifi["IFI"],       errors="coerce")
        _ifi["IFI_RESUL"] = pd.to_numeric(_ifi["IFI_RESUL"], errors="coerce")
        _tot_rows.append(_ifi[_ifi["IFI"] == 1][["DT_PRISINT"]].copy())
        _pos_rows.append(_ifi[(_ifi["IFI"] == 1) & (_ifi["IFI_RESUL"] == 1)][["DT_PRISINT"]].copy())

    if "PCR_RESUL" in _sg_base.columns and "POS_PCRFLU" in _sg_base.columns:
        _pcr = _sg_base.copy()
        _pcr["PCR_RESUL"]  = pd.to_numeric(_pcr["PCR_RESUL"],  errors="coerce")
        _pcr["POS_PCRFLU"] = pd.to_numeric(_pcr["POS_PCRFLU"], errors="coerce")
        _tot_rows.append(_pcr[_pcr["PCR_RESUL"] == 1][["DT_PRISINT"]].copy())
        _pos_rows.append(_pcr[(_pcr["PCR_RESUL"] == 1) & (_pcr["POS_PCRFLU"] == 1)][["DT_PRISINT"]].copy())

    if not _tot_rows:
        st.info("Sem dados de testes para o período.")
    else:
        _tall_sg = pd.concat(_tot_rows, ignore_index=True).dropna(subset=["DT_PRISINT"])
        _pall_sg = pd.concat(_pos_rows, ignore_index=True).dropna(subset=["DT_PRISINT"])

        _yr_tt, _wk_tt = paho_year_week(_tall_sg["DT_PRISINT"])
        _tall_sg["semana"]      = "SE " + _wk_tt.astype(str).str.zfill(2) + "/" + _yr_tt.astype(str)
        _tall_sg["semana_sort"] = _yr_tt * 100 + _wk_tt
        _tested_wk_sg = _tall_sg.groupby(["semana", "semana_sort"]).size().reset_index(name="total_tested")

        _yr_tp, _wk_tp = paho_year_week(_pall_sg["DT_PRISINT"])
        _pall_sg["semana"]      = "SE " + _wk_tp.astype(str).str.zfill(2) + "/" + _yr_tp.astype(str)
        _pall_sg["semana_sort"] = _yr_tp * 100 + _wk_tp
        _pos_wk_sg = _pall_sg.groupby(["semana", "semana_sort"]).size().reset_index(name="total_pos")

        _tot_sg = _tested_wk_sg.merge(_pos_wk_sg, on=["semana", "semana_sort"], how="left").fillna(0)
        _tot_sg = _tot_sg.sort_values("semana_sort").reset_index(drop=True)
        _tot_sg["pct_pos"] = (_tot_sg["total_pos"] / _tot_sg["total_tested"] * 100).round(1)

        _pct_axis_max_sg = max(_tot_sg["pct_pos"].max() * 1.15, 1)

        _fig_tot_sg = go.Figure()
        _fig_tot_sg.add_trace(go.Bar(
            x=_tot_sg["semana"],
            y=_tot_sg["total_tested"],
            name="Total Testado",
            marker_color="#72B7B2",
            yaxis="y1",
            hovertemplate="%{x}<br>Total testado: %{y}<extra></extra>",
        ))
        _fig_tot_sg.add_trace(go.Scatter(
            x=_tot_sg["semana"],
            y=_tot_sg["pct_pos"],
            name="Positividade (%)",
            mode="lines+markers",
            line=dict(color="#E45756", width=2),
            marker=dict(size=5),
            yaxis="y2",
            customdata=list(zip(
                _tot_sg["total_pos"].astype(int),
                _tot_sg["total_tested"].astype(int),
            )),
            hovertemplate=(
                "%{x}<br>Positividade: %{y:.1f}%"
                "<br>(%{customdata[0]} positivos de %{customdata[1]} testados)"
                "<extra></extra>"
            ),
        ))
        _fig_tot_sg.update_layout(
            title="Total de Testes Realizados e Taxa de Positividade por Semana Epidemiológica",
            xaxis=dict(
                title="Semana Epidemiológica",
                tickangle=-90,
                categoryorder="array",
                categoryarray=_tot_sg["semana"].tolist(),
            ),
            yaxis=dict(title="Total de Testes Realizados", rangemode="tozero"),
            yaxis2=dict(
                overlaying="y",
                side="right",
                range=[0, _pct_axis_max_sg],
                showticklabels=False,
                showgrid=False,
                zeroline=False,
                title="",
            ),
            legend=dict(orientation="h", y=-0.28, x=0.5, xanchor="center"),
            margin=dict(l=20, r=60, t=50, b=110),
            height=580,
            plot_bgcolor="white",
        )
        st.plotly_chart(_fig_tot_sg, width='stretch')
        st.caption(f"Fonte: {_FONTE_SG}")

    st.markdown("---")
    st.markdown("### Positividade por Tipo de Vírus")

    _T2_VIRUS_GROUPS = {
        "VSR":             ["IFI_VRS",   "PCR_VRS"],
        "SARS-CoV-2":      ["IFI_SARS2", "PCR_SARS2"],
        "Adenovírus":      ["IFI_ADENO", "PCR_ADENO"],
        "Parainfluenza 1": ["IFI_PARA1", "PCR_PARA1"],
        "Parainfluenza 2": ["IFI_PARA2", "PCR_PARA2"],
        "Parainfluenza 3": ["IFI_PARA3", "PCR_PARA3"],
        "Parainfluenza 4": ["IFI_PARA4", "PCR_PARA4"],
        "Metapneumovírus": ["PCR_METAP"],
        "Rinovírus":       ["PCR_RINO"],
        "Bocavírus":       ["PCR_BOCA"],
    }
    _T2_VIRUS_COLORS = {
        "Influenza A (H1N1)pdm09":   "#E45756",
        "Influenza A (H3N2)":        "#F58518",
        "Influenza A não subtipado": "#9C9C9C",
        "Influenza B":               "#4C78A8",
        "Inconclusivo":              "#BAB0AC",
        "VSR":             "#B279A2",
        "SARS-CoV-2":      "#54A24B",
        "Adenovírus":      "#72B7B2",
        "Parainfluenza 1": "#FF9DA6",
        "Parainfluenza 2": "#EECA3B",
        "Parainfluenza 3": "#8FBC8F",
        "Parainfluenza 4": "#B0C4DE",
        "Metapneumovírus": "#DEB887",
        "Rinovírus":       "#636363",
        "Bocavírus":       "#20B2AA",
    }
    _T2_VIRUS_ORDER = [
        "Influenza A (H1N1)pdm09", "Influenza A (H3N2)",
        "Influenza A não subtipado", "Influenza B", "Inconclusivo",
        "VSR", "SARS-CoV-2", "Adenovírus",
        "Parainfluenza 1", "Parainfluenza 2", "Parainfluenza 3", "Parainfluenza 4",
        "Metapneumovírus", "Rinovírus", "Bocavírus",
    ]

    _sg_vrows = []

    # Influenza subtypes via FIN_FLU / FIN_SUBT
    if "FIN_FLU" in _df_t2.columns:
        _flu_t2 = _df_t2.copy()
        _flu_t2["FIN_FLU"] = pd.to_numeric(_flu_t2["FIN_FLU"], errors="coerce")
        _flu_t2 = _flu_t2[_flu_t2["FIN_FLU"].isin([1, 2]) & _flu_t2["DT_PRISINT"].notna()].copy()
        if not _flu_t2.empty:
            _flu_t2["FIN_SUBT"] = pd.to_numeric(_flu_t2.get("FIN_SUBT"), errors="coerce")
            _sub_lbl_t2 = _flu_t2["FIN_SUBT"].map(FIN_SUBT_LABELS)
            _flu_t2["virus"] = _sub_lbl_t2.where(_flu_t2["FIN_FLU"] == 1, "Influenza B")
            _flu_t2.loc[(_flu_t2["FIN_FLU"] == 1) & _flu_t2["virus"].isna(), "virus"] = "Influenza A não subtipado"
            _sg_vrows.append(_flu_t2[["DT_PRISINT", "virus"]].copy())

    # Other viruses: IFI + PCR deduplicated per patient per label
    for _t2lbl, _t2cols in _T2_VIRUS_GROUPS.items():
        _avail2 = [c for c in _t2cols if c in _df_t2.columns]
        if not _avail2:
            continue
        _vmask2 = pd.concat(
            [pd.to_numeric(_df_t2[c], errors="coerce") >= 1 for c in _avail2], axis=1
        ).any(axis=1)
        _vtmp2 = _df_t2.loc[_vmask2 & _df_t2["DT_PRISINT"].notna(), ["DT_PRISINT"]].copy()
        _vtmp2["virus"] = _t2lbl
        _sg_vrows.append(_vtmp2)

    if not _sg_vrows:
        st.info("Nenhuma coluna de teste encontrada.")
    else:
        _sg_vlong = pd.concat(_sg_vrows, ignore_index=True).dropna(subset=["DT_PRISINT"])
        _yr_sgv, _wk_sgv = paho_year_week(_sg_vlong["DT_PRISINT"])
        _sg_vlong["semana"]      = "SE " + _wk_sgv.astype(str).str.zfill(2) + "/" + _yr_sgv.astype(str)
        _sg_vlong["semana_sort"] = _yr_sgv * 100 + _wk_sgv

        _sg_all_virus = [l for l in _T2_VIRUS_ORDER if l in _sg_vlong["virus"].unique()]
        _sg_virus_sel = st.selectbox(
            "Vírus", ["Todos os Vírus"] + _sg_all_virus,
            key="sg_virus_sel",
        )

        _sg_vfilt = _sg_vlong if _sg_virus_sel == "Todos os Vírus" else _sg_vlong[_sg_vlong["virus"] == _sg_virus_sel]
        _sg_agg_v = _sg_vfilt.groupby(["semana", "semana_sort", "virus"]).size().reset_index(name="n")
        _sg_ord_v = _sg_agg_v[["semana", "semana_sort"]].drop_duplicates().sort_values("semana_sort")["semana"].tolist()
        _sg_virus_order = _sg_all_virus if _sg_virus_sel == "Todos os Vírus" else [_sg_virus_sel]
        _sg_fig_v = px.bar(
            _sg_agg_v, x="semana", y="n", color="virus",
            color_discrete_map=_T2_VIRUS_COLORS,
            title="Testes Positivos por Vírus e Semana Epidemiológica",
            labels={"semana": "Semana Epidemiológica", "n": "Nº Testes Positivos", "virus": "Vírus"},
            category_orders={"semana": _sg_ord_v, "virus": _sg_virus_order},
        )
        _add_pct_hover(_sg_fig_v, _sg_agg_v, unit="testes positivos")
        _bar_layout(_sg_fig_v)
        st.plotly_chart(_sg_fig_v, width='stretch')
        st.caption(f"Fonte: {_FONTE_SG}")


# ============================================================
# TAB 3 — Nowcasting + Forecasting
# ============================================================
with tab3:
    st.markdown("### Média Móvel — Semanas Epidemiológicas 2026")
    st.caption("Média móvel de 4 semanas sobre casos semanais por semana de início dos sintomas (`DT_PRISINT`).")
    render_ma_chart(df_all, onset_col="DT_PRISINT", titulo="Média Móvel 4 sem. — SG (ILI)")
    st.caption(f"Fonte: {_FONTE_SG}")

    st.markdown("---")
    st.markdown("### Sazonalidade — Média Histórica por Semana Epidemiológica")
    render_seasonality_hist(df_all, onset_col="DT_PRISINT",
                            titulo="Sazonalidade — SG (média por SE, todos os anos)")
    st.caption(f"Fonte: {_FONTE_SG}")

# ============================================================
# TAB 4 — Progressão SG → SRAG
# ============================================================
with tab4:
    st.markdown("### Progressão para SRAG — Recife")
    st.caption(
        "Casos de SG (município de residência = Recife) que progrediram para SRAG "
        "no mesmo episódio clínico: par com início dos sintomas (SG → SRAG) em "
        "até 30 dias."
    )

    _prog = load_sg_srag_linked()

    if _prog.empty:
        st.info("Arquivo de progressão não encontrado (`data/sg_srag_linked.parquet`).")
    else:
        _prog = _prog.copy()
        _prog["_sexo"]  = pd.to_numeric(_prog["sg_SEXO"], errors="coerce").map({1: "Masculino", 2: "Feminino"})
        _prog["_idade"] = pd.to_numeric(_prog["sg_IDADE"], errors="coerce")

        _n_fem    = (_prog["_sexo"] == "Feminino").sum()
        _n_masc   = (_prog["_sexo"] == "Masculino").sum()
        _avg_age  = _prog["_idade"].mean()
        _n_obito  = (_prog["srag_evolucao_label"] == "Obito").sum() if "srag_evolucao_label" in _prog.columns else 0
        _avg_gap  = _prog["gap_dias"].mean() if "gap_dias" in _prog.columns else float("nan")

        render_kpis([
            ("Total de progressões",      fmt_int(len(_prog))),
            ("Feminino",                  fmt_int(_n_fem)),
            ("Masculino",                 fmt_int(_n_masc)),
            ("Idade média (SG)",          f"{_avg_age:.1f} anos"),
            ("Óbitos (SRAG)",             fmt_int(_n_obito)),
            ("Intervalo médio (≤30 dias)", f"{_avg_gap:.1f} dias"),
        ])

        st.markdown("---")

        _c1, _c2, _c3, _c4 = st.columns(4)

        with _c1:
            _sx = _prog["_sexo"].value_counts().reset_index()
            _sx.columns = ["sexo", "n"]
            _sx = _sx[_sx["sexo"].isin(["Masculino", "Feminino"])]
            _fig_sx = px.pie(
                _sx, names="sexo", values="n", title="Por Sexo", hole=0.45,
                color="sexo",
                color_discrete_map={"Feminino": "#E45756", "Masculino": "#4C78A8"},
            )
            _fig_sx.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=320)
            st.plotly_chart(_fig_sx, width='stretch')

        with _c2:
            _PROG_FAIXA_BINS = [
                ("1–4",   lambda a: (a >= 1)  & (a <= 4)),
                ("5–9",   lambda a: (a >= 5)  & (a <= 9)),
                ("10–19", lambda a: (a >= 10) & (a <= 19)),
                ("20–29", lambda a: (a >= 20) & (a <= 29)),
                ("30–39", lambda a: (a >= 30) & (a <= 39)),
                ("40–49", lambda a: (a >= 40) & (a <= 49)),
                ("50–59", lambda a: (a >= 50) & (a <= 59)),
                ("60+",   lambda a: a >= 60),
            ]
            _PROG_FAIXA_ORDER = [l for l, _ in _PROG_FAIXA_BINS]
            _age_p = _prog.dropna(subset=["_idade"]).copy()
            _age_p["faixa"] = pd.NA  # ensure column exists (empty-frame safe)
            for _lbl, _msk in _PROG_FAIXA_BINS:
                _age_p.loc[_msk(_age_p["_idade"]), "faixa"] = _lbl
            _age_p = _age_p.dropna(subset=["faixa"])
            _age_cnt = _age_p["faixa"].value_counts().reindex(_PROG_FAIXA_ORDER).fillna(0).reset_index()
            _age_cnt.columns = ["faixa", "n"]
            _fig_age_p = px.bar(
                _age_cnt, x="faixa", y="n", title="Por Faixa Etária (SG)",
                labels={"faixa": "Faixa Etária", "n": "Casos"},
                color_discrete_sequence=["#72B7B2"],
                category_orders={"faixa": _PROG_FAIXA_ORDER},
            )
            _fig_age_p.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=320)
            st.plotly_chart(_fig_age_p, width='stretch')

        with _c3:
            _bairro_p = (
                _prog["sg_NOM_BAIRRO"].str.title().value_counts().head(10).reset_index()
            ) if "sg_NOM_BAIRRO" in _prog.columns else pd.DataFrame()
            if not _bairro_p.empty:
                _bairro_p.columns = ["bairro", "n"]
                _fig_bairro_p = px.bar(
                    _bairro_p, x="n", y="bairro", orientation="h",
                    title="Por Bairro (top 10)",
                    labels={"bairro": "", "n": "Casos"},
                    color_discrete_sequence=["#F58518"],
                )
                _fig_bairro_p.update_layout(
                    yaxis=dict(autorange="reversed"),
                    margin=dict(l=10, r=10, t=50, b=10), height=320,
                )
                st.plotly_chart(_fig_bairro_p, width='stretch')

        with _c4:
            if "srag_evolucao_label" in _prog.columns:
                _ev = _prog["srag_evolucao_label"].fillna("Sem registro").value_counts().reset_index()
                _ev.columns = ["evolucao", "n"]
                _fig_ev = px.pie(
                    _ev, names="evolucao", values="n", title="Evolução (SRAG)", hole=0.45,
                    color_discrete_map={
                        "Cura": "#54A24B", "Obito": "#E45756",
                        "Obito por outras causas": "#F58518",
                        "Ignorado": "#9C9C9C", "Sem registro": "#CCCCCC",
                    },
                )
                _fig_ev.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=320)
                st.plotly_chart(_fig_ev, width='stretch')

        st.caption(f"Fonte: {_FONTE_PROG}")

        st.markdown("---")

        st.markdown("#### Intervalo entre início dos sintomas SG e SRAG")
        if "gap_faixa" in _prog.columns:
            _gap_order = ["0-7d", "8-14d", "15-30d"]
            _gap_cnt = _prog["gap_faixa"].value_counts().reindex(_gap_order).fillna(0).reset_index()
            _gap_cnt.columns = ["intervalo", "n"]
            _fig_gap = px.bar(
                _gap_cnt, x="intervalo", y="n",
                title="Dias entre início dos sintomas SG e SRAG",
                labels={"intervalo": "Intervalo", "n": "Casos"},
                color_discrete_sequence=["#B279A2"],
                category_orders={"intervalo": _gap_order},
            )
            _fig_gap.update_layout(margin=dict(l=20, r=20, t=50, b=60), height=340, plot_bgcolor="white")
            st.plotly_chart(_fig_gap, width='stretch')
            st.caption(f"Fonte: {_FONTE_PROG}")

        st.markdown("---")

        st.markdown("#### Tabela de Casos")
        _tbl_p = _prog[[c for c in [
            "sg_DT_PRISINT", "srag_DT_SIN_PRI", "gap_dias",
            "_sexo", "_idade", "sg_NOM_BAIRRO",
            "sg_classi_label", "srag_classi_label",
            "srag_evolucao_label", "srag_NM_UN_INTE",
        ] if c in _prog.columns]].copy()
        _tbl_p = _tbl_p.rename(columns={
            "sg_DT_PRISINT":       "Data SG",
            "srag_DT_SIN_PRI":     "Data SRAG",
            "gap_dias":            "Intervalo (dias)",
            "_sexo":               "Sexo",
            "_idade":              "Idade (SG)",
            "sg_NOM_BAIRRO":       "Bairro",
            "sg_classi_label":     "Classificação SG",
            "srag_classi_label":   "Classificação SRAG",
            "srag_evolucao_label": "Evolução SRAG",
            "srag_NM_UN_INTE":     "Hospital (SRAG)",
        })
        for _dc in ["Data SG", "Data SRAG"]:
            if _dc in _tbl_p.columns:
                _tbl_p[_dc] = pd.to_datetime(_tbl_p[_dc], errors="coerce").dt.strftime("%d/%m/%Y")
        if "Bairro" in _tbl_p.columns:
            _tbl_p["Bairro"] = _tbl_p["Bairro"].str.title()
        if "Hospital (SRAG)" in _tbl_p.columns:
            _tbl_p["Hospital (SRAG)"] = _tbl_p["Hospital (SRAG)"].str.title()
        st.dataframe(_tbl_p, width='stretch', hide_index=True)
        st.caption(f"Fonte: {_FONTE_PROG}")
