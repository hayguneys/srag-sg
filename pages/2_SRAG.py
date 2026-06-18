"""SRAG (Síndrome Respiratória Aguda Grave) page."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.helpers import (
    load_srag_withna, render_kpis, fmt_int,
    embed_html_plot, render_ma_chart, render_forecast_table, paho_year_week,
    render_epiweek_slider, filter_epiweek, add_ma_overlay,
    render_seasonality_hist, unit_code_map, SRAG_EPIWEEK_MIN,
    period_compare_label, period_compare_se_label, format_kpi_delta,
    CLASSI_FIN_LABELS, CLASSI_FIN_COLORS, DATA_DIR, inject_test_frames,
)

st.set_page_config(page_title="SRAG", page_icon="🫁", layout="wide")
inject_test_frames()  # TEST: line frames around KPI cards
st.title("🫁 SRAG — Síndrome Respiratória Aguda Grave")
st.caption(
    "*Vigilância universal de Síndrome Respiratória Aguda Grave (SRAG): monitora "
    "casos hospitalizados e óbitos com o objetivo de identificar o comportamento da "
    "influenza e demais vírus respiratórios.*"
)

# --- Load data — município de residência = Recife (ID_MN_RESI) --------------
# Time axis throughout the page is DT_SIN_PRI (data dos primeiros sintomas).
df_all = load_srag_withna()
df_all = df_all[df_all["ID_MN_RESI"] == "RECIFE"].copy()

# Notification-unit column for SRAG: ID_UNIDADE (unidade de notificação),
# with CO_UNI_NOT as the unit code. Preset shortcuts substring-match the name.
_SRAG_UNIT_COL  = "ID_UNIDADE"
_SRAG_CODE_COL  = "CO_UNI_NOT"
_CLINICAS_SRAG = {
    "US 153 POLICLINICA E MATERNIDADE ARNALDO MARQUES":      "ARNALDO MARQUES",
    "US 159 POLICLINICA AGAMENON MAGALHAES":                 "US 159 POLICLINICA",
    "US 163 HOSPITAL DE PEDIATRIA HELENA MOURA":             "HELENA MOURA",
    "US 164 CENTRO DE REIDRATACAO E URG PED M CRAVO GAMA":  "CRAVO GAMA",
    "US 167 POLICLINICA E MATERNIDADE PROFESSOR BARROS LIMA":"BARROS LIMA",
    "US 169 POLICLINICA AMAURY COUTINHO":                    "AMAURY COUTINHO",
}


# Unidade de Notificação dropdown: preset shortcuts + a "Unidades municipais"
# section, then a second section listing EVERY notification unit (ID_UNIDADE)
# by full name with its unit code (CO_UNI_NOT). Streamlit's multiselect has no
# native option groups, so the section headers are decorative (no-op) options
# and the selection is resolved in _filtra_clinicas_srag.
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

# name -> unit code, and the full sorted list of notification-unit names.
_SRAG_UNIT_CODE = unit_code_map(df_all, _SRAG_UNIT_COL, _SRAG_CODE_COL)
_SRAG_UNIT_NAMES = sorted(k for k in _SRAG_UNIT_CODE if k not in _CLINICAS_SRAG)
_UNI_OPTIONS = (
    [_UNI_TODAS, _UNI_MUNI, _UNI_EXMUNI, _UNI_DIV]
    + list(_CLINICAS_SRAG.keys())
    + [_UNI_DIV2]
    + _SRAG_UNIT_NAMES
)


def _uni_label(opt):
    if opt in _UNI_LABELS:
        return _UNI_LABELS[opt]
    if opt in _CLINICAS_SRAG:
        return opt
    return opt


def _unidade_multiselect_srag(key):
    """Render the Unidade de Notificação selector (presets + full unit list)."""
    return st.multiselect(
        "Unidade de Notificação", _UNI_OPTIONS,
        default=[], key=key, format_func=_uni_label,
        placeholder="Todas as unidades",
    )


def _filtra_clinicas_srag(df, selecionadas):
    """Resolve the unidade selection (presets + clinics + named units) into a filter.

    Empty, "Todas as unidades", or only section headers => no filtering.
    """
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
        mask = mask | is_muni
        matched = True
    if _UNI_EXMUNI in sel:
        mask = mask | (~is_muni)
        matched = True
    _indiv_kw = [_CLINICAS_SRAG[c] for c in sel if c in _CLINICAS_SRAG]
    if _indiv_kw:
        mask = mask | _nm.apply(lambda x: any(k in x for k in _indiv_kw))
        matched = True
    # Exact full-name selections from the "Todas as unidades de notificação" list.
    _exact = {s.upper().strip() for s in sel if s in _SRAG_UNIT_CODE}
    if _exact:
        mask = mask | _nm.isin(_exact)
        matched = True

    if not matched:
        return df
    return df[mask].copy()


_FONTE_SRAG = "SESAU/SEVS/GGAM/GEVEPI/DDT/SIVEP-GRIPE"
_RECIFE_POP = 1_640_147

if st.session_state.pop("srag_goto_nowcasting", False):
    st.html("""<script>
    (function() {
        function clickTab() {
            var tabs = window.parent.document.querySelectorAll('[role="tab"]');
            if (tabs.length >= 3) { tabs[2].click(); }
            else { setTimeout(clickTab, 150); }
        }
        setTimeout(clickTab, 300);
    })();
    </script>""", unsafe_allow_javascript=True)

_SRAG_RACA_LABELS = {1: "Branca", 2: "Preta", 3: "Amarela", 4: "Parda", 5: "Indígena", 9: "Ignorado"}
_SRAG_CLASSI = {
    1: "SRAG por Influenza",
    2: "SRAG por outro vírus resp.",
    3: "SRAG por outro agente",
    4: "SRAG não especificado",
    5: "SRAG por COVID-19",
}
_SRAG_FAIXA_BINS = [
    ("1–4",   lambda a: (a >= 1)  & (a <= 4)),
    ("5–9",   lambda a: (a >= 5)  & (a <= 9)),
    ("10–19", lambda a: (a >= 10) & (a <= 19)),
    ("20–29", lambda a: (a >= 20) & (a <= 29)),
    ("30–39", lambda a: (a >= 30) & (a <= 39)),
    ("40–49", lambda a: (a >= 40) & (a <= 49)),
    ("50–59", lambda a: (a >= 50) & (a <= 59)),
    ("60+",   lambda a: a >= 60),
]


def _decode_srag(df):
    """Add decoded label columns used by the summary visuals."""
    _d = df.copy()
    _d["NU_IDADE_N"] = pd.to_numeric(_d["NU_IDADE_N"], errors="coerce")
    _d["CLASSI_FIN"] = pd.to_numeric(_d["CLASSI_FIN"], errors="coerce")
    _d["CS_RACA"]    = pd.to_numeric(_d["CS_RACA"],    errors="coerce")
    _d["DT_EVOLUCA"] = pd.to_datetime(_d["DT_EVOLUCA"], dayfirst=True, errors="coerce")
    _d["DT_SIN_PRI"]  = pd.to_datetime(_d["DT_SIN_PRI"],  errors="coerce")
    _d["SEXO_LABEL"]   = _d["CS_SEXO"].map({"M": "Masculino", "F": "Feminino", "I": "Ignorado"})
    _d["RACA_LABEL"]   = _d["CS_RACA"].map(_SRAG_RACA_LABELS)
    _d["CLASSI_LABEL"] = _d["CLASSI_FIN"].map(_SRAG_CLASSI)
    _d["NM_BAIRRO"]    = _d["NM_BAIRRO"].str.title()
    return _d


# ============================================================
# Summary grid — Por Sexo · Faixa Etária · Raça/Cor · Bairro.
# Integrated into the main Descritivo visuals and driven by the
# Casos / Óbitos toggle (df_view is already filtered accordingly).
# unidade is "Casos" or "Óbitos" for the chart value labels.
# ============================================================
def _render_srag_summary_grid(df_view, unidade):
    _ob = _decode_srag(df_view)
    if _ob.empty:
        st.info("Sem dados para os filtros selecionados.")
        return

    _r1a, _r1b, _r1d = st.columns(3)

    with _r1a:
        _sc = _ob["SEXO_LABEL"].value_counts().reset_index()
        _sc.columns = ["sexo", "n"]
        _sc = _sc[_sc["sexo"] != "Ignorado"]
        _fig_s = px.pie(
            _sc, names="sexo", values="n", title="Por Sexo",
            color="sexo",
            color_discrete_map={"Feminino": "#E45756", "Masculino": "#4C78A8"},
            hole=0.45,
        )
        _fig_s.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=320)
        st.plotly_chart(_fig_s, width='stretch')

    with _r1b:
        _faixa_order = [l for l, _ in _SRAG_FAIXA_BINS]
        _age_ob = _ob.dropna(subset=["NU_IDADE_N"]).copy()
        _age_ob["faixa"] = pd.NA  # ensure column exists (empty-frame safe)
        for _lbl, _msk in _SRAG_FAIXA_BINS:
            _age_ob.loc[_msk(_age_ob["NU_IDADE_N"]), "faixa"] = _lbl
        _age_ob = _age_ob.dropna(subset=["faixa"])
        _fc_age = (
            _age_ob["faixa"].value_counts()
            .reindex(_faixa_order)
            .fillna(0).reset_index()
        )
        _fc_age.columns = ["faixa", "n"]
        _fig_age = px.bar(
            _fc_age, x="faixa", y="n", title="Por Faixa Etária",
            labels={"faixa": "Faixa Etária", "n": unidade},
            color_discrete_sequence=["#72B7B2"],
            category_orders={"faixa": _faixa_order},
        )
        _fig_age.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=320)
        st.plotly_chart(_fig_age, width='stretch')

    with _r1d:
        _bc = _ob["NM_BAIRRO"].value_counts().reset_index()
        _bc.columns = ["bairro", "n"]
        st.markdown("**Por Bairro**")
        _bairro_h = max(280, len(_bc) * 22)
        _fig_bairro = px.bar(
            _bc, x="n", y="bairro", orientation="h",
            labels={"bairro": "", "n": unidade},
            color_discrete_sequence=["#F58518"],
        )
        _fig_bairro.update_layout(
            yaxis=dict(autorange="reversed"),
            margin=dict(l=10, r=10, t=10, b=10), height=_bairro_h,
        )
        with st.container(height=300, border=False):
            st.plotly_chart(_fig_bairro, width='stretch')
    st.caption(f"Fonte: {_FONTE_SRAG}")


# ============================================================
# Óbitos-only extras — hospital / classificação, weekly timeline,
# residence heatmap and the detailed table. df_view is already
# filtered to EVOLUCAO == 2 by the caller.
# ============================================================
def _render_srag_obitos_extras(df_view):
    _ob = _decode_srag(df_view)
    if _ob.empty:
        return

    # ---- Row 2: Hospital | Classificação Final -------------------------
    _r2a, _r2b = st.columns([2, 1])

    with _r2a:
        if "NM_UN_INTE" in _ob.columns:
            _hc = (
                _ob["NM_UN_INTE"].str.title()
                .value_counts().head(12).reset_index()
            )
            _hc.columns = ["hospital", "n"]
            _fig_h = px.bar(
                _hc, x="n", y="hospital", orientation="h",
                title="Hospital / Unidade de Internação (top 12)",
                labels={"hospital": "", "n": "Óbitos"},
                color_discrete_sequence=["#4C78A8"],
            )
            _fig_h.update_layout(
                yaxis=dict(autorange="reversed"),
                margin=dict(l=10, r=10, t=50, b=10), height=420,
            )
            st.plotly_chart(_fig_h, width='stretch')

    with _r2b:
        _cl = _ob["CLASSI_LABEL"].value_counts().reset_index()
        _cl.columns = ["classi", "n"]
        _fig_cl = px.bar(
            _cl, x="n", y="classi", orientation="h",
            title="Classificação Final",
            labels={"classi": "", "n": "Óbitos"},
            color_discrete_sequence=["#54A24B"],
        )
        _fig_cl.update_layout(
            yaxis=dict(autorange="reversed"),
            margin=dict(l=10, r=10, t=50, b=10), height=420,
        )
        st.plotly_chart(_fig_cl, width='stretch')

    st.caption(f"Fonte: {_FONTE_SRAG}")

    st.markdown("---")

    # ---- Timeline: óbitos por semana epidemiológica --------------------
    _ob_tl = _ob.dropna(subset=["DT_EVOLUCA"]).copy()
    _ob_tl = _ob_tl[_ob_tl["DT_EVOLUCA"].dt.year.between(2022, 2026)]
    _yr_tl, _wk_tl = paho_year_week(_ob_tl["DT_EVOLUCA"])
    _ob_tl = _ob_tl[~((_yr_tl == 2026) & (_wk_tl > 16))]
    _yr_tl2, _wk_tl2 = paho_year_week(_ob_tl["DT_EVOLUCA"])
    _ob_tl["semana"]      = "SE " + _wk_tl2.astype(str).str.zfill(2) + "/" + _yr_tl2.astype(str)
    _ob_tl["semana_sort"] = _yr_tl2 * 100 + _wk_tl2
    _tl_agg = _ob_tl.groupby(["semana", "semana_sort"]).size().reset_index(name="n")
    _tl_agg = _tl_agg.sort_values("semana_sort")
    _fig_tl = px.bar(
        _tl_agg, x="semana", y="n",
        title="Óbitos por Semana Epidemiológica",
        labels={"semana": "Semana Epidemiológica", "n": "Óbitos"},
        color_discrete_sequence=["#E45756"],
        category_orders={"semana": _tl_agg["semana"].tolist()},
    )
    _fig_tl.update_layout(
        xaxis_tickangle=-90,
        margin=dict(l=20, r=20, t=50, b=110),
        height=420,
        plot_bgcolor="white",
    )
    st.plotly_chart(_fig_tl, width='stretch')
    st.caption(f"Fonte: {_FONTE_SRAG}")

    st.markdown("---")

    # ---- Heatmap — residência dos óbitos ----------------------------------
    st.markdown("#### Mapa de Calor — Residência dos Óbitos (SRAG)")
    st.caption(
        "Localização aproximada por bairro de residência. "
        "82 % dos registros foram geolocaliz­ados. "
        "Calor proporcional ao nº de óbitos por bairro."
    )

    @st.cache_data(show_spinner="Carregando lookup de bairros…")
    def _load_lookup():
        _p = DATA_DIR / "srag_bairro_lookup.csv"
        if not _p.exists():
            return None
        return pd.read_csv(_p, encoding="utf-8")

    _lookup = _load_lookup()
    if _lookup is None:
        st.warning("Lookup de bairros não encontrado. Execute `data/geocode_bairros.py` primeiro.")
    else:
        import folium
        from folium.plugins import HeatMap
        # Join deaths with lookup on NM_BAIRRO (upper/stripped)
        _ob_map = _ob.copy()
        _ob_map["_raw"] = _ob_map["NM_BAIRRO"].str.strip().str.upper().fillna("")
        _lk = _lookup[["raw", "official", "lat", "lon"]].copy()
        _lk["raw"] = _lk["raw"].str.strip().str.upper()
        _ob_map = _ob_map.merge(_lk, left_on="_raw", right_on="raw", how="left")
        _ob_geo = _ob_map.dropna(subset=["lat", "lon"])

        if _ob_geo.empty:
            st.info("Sem dados geográficos para exibir.")
        else:
            # Aggregate by neighbourhood for weighted heatmap
            _heat_data_df = (
                _ob_geo.groupby(["official", "lat", "lon"])
                .size().reset_index(name="weight")
            )
            _pct_located = len(_ob_geo) / max(len(_ob_map), 1) * 100

            # Build folium map centred on Recife
            _fmap = folium.Map(
                location=[-8.054, -34.881],
                zoom_start=12,
                tiles="CartoDB positron",
            )

            # HeatMap layer
            _heat_points = _heat_data_df[["lat", "lon", "weight"]].values.tolist()
            _max_w = _heat_data_df["weight"].max()
            HeatMap(
                _heat_points,
                min_opacity=0.35,
                radius=28,
                blur=22,
                gradient={0.2: "#4C78A8", 0.5: "#F58518", 0.8: "#E45756", 1.0: "#9B0000"},
            ).add_to(_fmap)

            # Circle markers for top 15 bairros (with tooltip)
            _top15 = _heat_data_df.nlargest(15, "weight")
            for _, _row in _top15.iterrows():
                folium.CircleMarker(
                    location=[_row["lat"], _row["lon"]],
                    radius=max(4, min(18, _row["weight"] / _max_w * 18)),
                    color="#E45756",
                    fill=True,
                    fill_opacity=0.7,
                    tooltip=f"{_row['official']}: {int(_row['weight'])} óbitos",
                ).add_to(_fmap)

            import folium as _folium_fig
            _fmap_fig = _folium_fig.Figure(width="100%", height="520px")
            _fmap.add_to(_fmap_fig)
            st.iframe(_fmap_fig._repr_html_(), height=520)

            st.caption(
                f"{len(_ob_geo):,} de {len(_ob_map):,} óbitos geolocalizados "
                f"({_pct_located:.0f}%) · "
                f"Top bairro: **{_heat_data_df.nlargest(1,'weight').iloc[0]['official']}** "
                f"({int(_heat_data_df['weight'].max())} óbitos)"
            )
            st.caption(f"Fonte: {_FONTE_SRAG}")

    st.markdown("---")

    # ---- Detailed table ------------------------------------------------
    st.markdown("#### Tabela de Óbitos")
    _tbl_cols = {
        "DT_EVOLUCA":   "Data Óbito",
        "SEXO_LABEL":   "Sexo",
        "NU_IDADE_N":   "Idade",
        "RACA_LABEL":   "Raça/Cor",
        "NM_BAIRRO":    "Bairro",
        "NM_UN_INTE":   "Hospital Internação",
        "CLASSI_LABEL": "Classificação Final",
    }
    _tbl_ob = _ob[[c for c in _tbl_cols if c in _ob.columns]].rename(columns=_tbl_cols).copy()
    if "Data Óbito" in _tbl_ob.columns:
        _tbl_ob["Data Óbito"] = pd.to_datetime(_tbl_ob["Data Óbito"], errors="coerce").dt.strftime("%d/%m/%Y")
    if "Hospital Internação" in _tbl_ob.columns:
        _tbl_ob["Hospital Internação"] = _tbl_ob["Hospital Internação"].str.title()
    if "Idade" in _tbl_ob.columns:
        _tbl_ob["Idade"] = pd.to_numeric(_tbl_ob["Idade"], errors="coerce").astype("Int64")
    st.dataframe(_tbl_ob, width='stretch', hide_index=True)
    st.caption(f"Fonte: {_FONTE_SRAG}")


tab1, tab2, tab3 = st.tabs(["📊 Descritivo", "🦠 Testes", "📈 Nowcasting + Forecasting"])

# ============================================================
# TAB 1 — Descriptive
# ============================================================
with tab1:

    # ---- SE/Ano range slider, unit filter and Casos/Óbitos filter -----------
    _c_year, _c_unit, _c_evo = st.columns([2, 2, 2])
    with _c_year:
        _se_lo, _se_hi = render_epiweek_slider("srag_desc_se", start=SRAG_EPIWEEK_MIN)
    with _c_unit:
        _unit_filter = _unidade_multiselect_srag("srag_desc_unit")
    with _c_evo:
        _evo_filter = st.radio(
            "Evolução", ["Casos", "Óbitos"],
            horizontal=True, key="srag_desc_evolucao",
        )

    df_filt = filter_epiweek(df_all, "DT_SIN_PRI", _se_lo, _se_hi)
    df_filt = _filtra_clinicas_srag(df_filt, _unit_filter)

    # Previous period = same SE window shifted back one year
    _se_lo_prev = (_se_lo[0] - 1, _se_lo[1])
    _se_hi_prev = (_se_hi[0] - 1, _se_hi[1])
    df_prev = filter_epiweek(df_all, "DT_SIN_PRI", _se_lo_prev, _se_hi_prev)
    df_prev = _filtra_clinicas_srag(df_prev, _unit_filter)

    _show_obitos = _evo_filter == "Óbitos"

    _cmp = period_compare_label(_se_lo, _se_hi)
    _cmp_se = period_compare_se_label(_se_lo, _se_hi)

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

    # ---- KPIs with delta (previous period) -----------------------------------
    if _show_obitos:
        _kpi_base = df_filt[pd.to_numeric(df_filt["EVOLUCAO"], errors="coerce") == 2].copy()
        _kpi_base["NU_IDADE_N"] = pd.to_numeric(_kpi_base["NU_IDADE_N"], errors="coerce")
        _n_fem  = (_kpi_base["CS_SEXO"] == "F").sum()
        _n_masc = (_kpi_base["CS_SEXO"] == "M").sum()
        _avg_age = _kpi_base["NU_IDADE_N"].mean() if not _kpi_base.empty else 0
        _uti_pct = (
            (_kpi_base["UTI"] == 1).sum() / _kpi_base["UTI"].notna().sum() * 100
            if "UTI" in _kpi_base.columns and _kpi_base["UTI"].notna().sum() > 0 else 0
        )

        # Previous period
        _kpi_prev = df_prev[pd.to_numeric(df_prev["EVOLUCAO"], errors="coerce") == 2].copy()
        _n_fem_prev = (_kpi_prev["CS_SEXO"] == "F").sum()
        _n_masc_prev = (_kpi_prev["CS_SEXO"] == "M").sum()

        delta_total = format_kpi_delta(len(_kpi_base), len(_kpi_prev), _cmp)
        delta_fem   = format_kpi_delta(_n_fem, _n_fem_prev, _cmp)
        delta_masc  = format_kpi_delta(_n_masc, _n_masc_prev, _cmp)

        render_kpis([
            ("Total de óbitos", fmt_int(len(_kpi_base)), delta_total, _cmp_se),
            ("Feminino", fmt_int(_n_fem), delta_fem, _cmp_se),
            ("Masculino", fmt_int(_n_masc), delta_masc, _cmp_se),
            ("Idade média", f"{_avg_age:.1f} anos"),
            ("Internados em UTI", f"{_uti_pct:.1f}%"),
        ])
    else:
        total_cases  = len(df_filt)
        total_deaths = int((df_filt["EVOLUCAO"] == 2).sum()) if "EVOLUCAO" in df_filt.columns else 0

        # Previous period
        total_cases_prev = len(df_prev)
        total_deaths_prev = int((df_prev["EVOLUCAO"] == 2).sum()) if "EVOLUCAO" in df_prev.columns else 0

        delta_cases  = format_kpi_delta(total_cases, total_cases_prev, _cmp)
        delta_deaths = format_kpi_delta(total_deaths, total_deaths_prev, _cmp)

        render_kpis([
            ("Total de casos", fmt_int(total_cases), delta_cases, _cmp_se),
            ("Total de óbitos", fmt_int(total_deaths), delta_deaths, _cmp_se),
        ])

    st.markdown("---")

    # df_view drives every visual below; with Óbitos selected it is
    # filtered to EVOLUCAO == 2 so the same charts show deaths only.
    if _show_obitos:
        df_view = df_filt[pd.to_numeric(df_filt["EVOLUCAO"], errors="coerce") == 2].copy()
        _unidade = "Óbitos"
        _unit_lc = "óbitos"
    else:
        df_view = df_filt
        _unidade = "Casos"
        _unit_lc = "casos"

    # ---- Integrated summary grid: Sexo · Faixa · Raça/Cor · Bairro ----------
    st.markdown("#### Resumo — Por Sexo, Faixa Etária, Raça/Cor e Bairro")
    _render_srag_summary_grid(df_view, _unidade)

    st.markdown("---")

    # ---- Total por Faixa Etária / Sexo por Semana Epidemiológica ------------
    st.markdown(f"#### Total de {_unidade}")

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

    RACA_COLORS = {
        "Branca":   "#4C78A8",
        "Preta":    "#F58518",
        "Amarela":  "#E45756",
        "Parda":    "#72B7B2",
        "Indígena": "#54A24B",
        "Ignorado": "#B279A2",
    }

    _faixa_view = st.radio(
        "Visualização", ["Total", "Faixa Etária", "Sexo", "Raça/Cor"],
        horizontal=True, key="srag_faixa_view", label_visibility="collapsed",
    )

    if _faixa_view == "Total":
        _tot = df_view.dropna(subset=["DT_SIN_PRI"]).copy()
        _yr_t, _wk_t = paho_year_week(_tot["DT_SIN_PRI"])
        _tot["semana"]      = "SE " + _wk_t.astype(str).str.zfill(2) + "/" + _yr_t.astype(str)
        _tot["semana_sort"] = _yr_t * 100 + _wk_t
        _agg_t = _tot.groupby(["semana", "semana_sort"]).size().reset_index(name="n")
        _ord_t = _agg_t.sort_values("semana_sort")["semana"].tolist()
        _fig_t = px.bar(
            _agg_t, x="semana", y="n",
            title=f"Total de {_unidade} por Semana Epidemiológica",
            labels={"semana": "Semana Epidemiológica", "n": f"Nº {_unidade}"},
            category_orders={"semana": _ord_t},
        )
        _fig_t.update_traces(marker_color="#4C78A8", hovertemplate="%{x}<br>" + _unidade + ": %{y}<extra></extra>")
        _bar_layout(_fig_t)
        add_ma_overlay(_fig_t, _agg_t)
        st.plotly_chart(_fig_t, width='stretch')

    _age = df_view.copy()
    _age["NU_IDADE_N"] = pd.to_numeric(_age["NU_IDADE_N"], errors="coerce")
    _age = _age.dropna(subset=["DT_SIN_PRI", "NU_IDADE_N"])
    _age["faixa"] = pd.NA  # ensure column exists (empty-frame safe)
    for _label, _mask in FAIXA_BINS:
        _age.loc[_mask(_age["NU_IDADE_N"]), "faixa"] = _label
    _age = _age.dropna(subset=["faixa"])

    if _faixa_view == "Faixa Etária":
        if _age.empty:
            st.info("Sem dados de faixa etária.")
        else:
            _yr_a, _wk_a = paho_year_week(_age["DT_SIN_PRI"])
            _age["semana"]      = "SE " + _wk_a.astype(str).str.zfill(2) + "/" + _yr_a.astype(str)
            _age["semana_sort"] = _yr_a * 100 + _wk_a
            _agg_a = _age.groupby(["semana", "semana_sort", "faixa"]).size().reset_index(name="n")
            _ord_a = _agg_a[["semana","semana_sort"]].drop_duplicates().sort_values("semana_sort")["semana"].tolist()
            _fig_a = px.bar(
                _agg_a, x="semana", y="n", color="faixa",
                color_discrete_map=FAIXA_COLORS,
                title=f"Total de {_unidade} por Semana Epidemiológica",
                labels={"semana": "Semana Epidemiológica", "n": f"Nº {_unidade}", "faixa": "Faixa Etária"},
                category_orders={"semana": _ord_a, "faixa": [l for l, _ in FAIXA_BINS]},
            )
            _add_pct_hover(_fig_a, _agg_a, unit=_unit_lc)
            _bar_layout(_fig_a)
            add_ma_overlay(_fig_a, _agg_a)
            st.plotly_chart(_fig_a, width='stretch')
    elif _faixa_view == "Sexo":
        _sx = df_view.copy()
        _sx = _sx[_sx["CS_SEXO"].isin(["M", "F"])].dropna(subset=["DT_SIN_PRI"])
        _sx["SEXO_LABEL"] = _sx["CS_SEXO"].map({"M": "Masculino", "F": "Feminino"})
        if _sx.empty:
            st.info("Sem dados de sexo.")
        else:
            _yr_sx, _wk_sx = paho_year_week(_sx["DT_SIN_PRI"])
            _sx["semana"]      = "SE " + _wk_sx.astype(str).str.zfill(2) + "/" + _yr_sx.astype(str)
            _sx["semana_sort"] = _yr_sx * 100 + _wk_sx
            _agg_sx = _sx.groupby(["semana", "semana_sort", "SEXO_LABEL"]).size().reset_index(name="n")
            _ord_sx = _agg_sx[["semana","semana_sort"]].drop_duplicates().sort_values("semana_sort")["semana"].tolist()
            _fig_sx = px.bar(
                _agg_sx, x="semana", y="n", color="SEXO_LABEL",
                color_discrete_map={"Masculino": "#4C78A8", "Feminino": "#E45756"},
                title=f"{_unidade} por Sexo por Semana Epidemiológica",
                labels={"semana": "Semana Epidemiológica", "n": f"Nº {_unidade}", "SEXO_LABEL": "Sexo"},
                category_orders={"semana": _ord_sx},
            )
            _add_pct_hover(_fig_sx, _agg_sx, unit=_unit_lc)
            _bar_layout(_fig_sx)
            add_ma_overlay(_fig_sx, _agg_sx)
            st.plotly_chart(_fig_sx, width='stretch')
    elif _faixa_view == "Raça/Cor":
        _rc = df_view.dropna(subset=["DT_SIN_PRI"]).copy()
        _rc["RACA_LABEL"] = pd.to_numeric(_rc["CS_RACA"], errors="coerce").map(_SRAG_RACA_LABELS)
        _rc = _rc.dropna(subset=["RACA_LABEL"])
        if _rc.empty:
            st.info("Sem dados de raça/cor.")
        else:
            _yr_rc, _wk_rc = paho_year_week(_rc["DT_SIN_PRI"])
            _rc["semana"]      = "SE " + _wk_rc.astype(str).str.zfill(2) + "/" + _yr_rc.astype(str)
            _rc["semana_sort"] = _yr_rc * 100 + _wk_rc
            _agg_rc = _rc.groupby(["semana", "semana_sort", "RACA_LABEL"]).size().reset_index(name="n")
            _ord_rc = _agg_rc[["semana","semana_sort"]].drop_duplicates().sort_values("semana_sort")["semana"].tolist()
            _fig_rc = px.bar(
                _agg_rc, x="semana", y="n", color="RACA_LABEL",
                color_discrete_map=RACA_COLORS,
                title=f"Total de {_unidade} por Raça/Cor por Semana Epidemiológica",
                labels={"semana": "Semana Epidemiológica", "n": f"Nº {_unidade}", "RACA_LABEL": "Raça/Cor"},
                category_orders={"semana": _ord_rc, "RACA_LABEL": list(_SRAG_RACA_LABELS.values())},
            )
            _add_pct_hover(_fig_rc, _agg_rc, unit=_unit_lc)
            _bar_layout(_fig_rc)
            add_ma_overlay(_fig_rc, _agg_rc)
            st.plotly_chart(_fig_rc, width='stretch')
    st.caption(f"Fonte: {_FONTE_SRAG}")

    st.markdown("---")

    # ---- Taxa de Incidência por Semana Epidemiológica ----------------------
    st.markdown("#### Taxa de Incidência por Semana Epidemiológica (por 100.000 hab.)")

    _inc_base = df_view.dropna(subset=["DT_SIN_PRI"]).copy()
    if _inc_base.empty:
        st.info("Sem dados para calcular taxa de incidência.")
    else:
        if _faixa_view == "Total":
            _yr_inc, _wk_inc = paho_year_week(_inc_base["DT_SIN_PRI"])
            _inc_base["semana"]      = "SE " + _wk_inc.astype(str).str.zfill(2) + "/" + _yr_inc.astype(str)
            _inc_base["semana_sort"] = _yr_inc * 100 + _wk_inc
            _agg_inc = _inc_base.groupby(["semana", "semana_sort"]).size().reset_index(name="n")
            _agg_inc = _agg_inc.sort_values("semana_sort").reset_index(drop=True)
            _agg_inc["taxa"] = (_agg_inc["n"] / _RECIFE_POP * 100_000).round(2)
            _agg_inc["ma"]   = _agg_inc["taxa"].rolling(4, min_periods=1).mean().round(2)

            _fig_inc = go.Figure()
            _fig_inc.add_trace(go.Bar(
                x=_agg_inc["semana"], y=_agg_inc["taxa"],
                name="Taxa por SE", marker_color="#4C78A8",
                hovertemplate="%{x}<br>Taxa: %{y:.2f} por 100k<extra></extra>",
            ))
            _fig_inc.add_trace(go.Scatter(
                x=_agg_inc["semana"], y=_agg_inc["ma"],
                name="Média móvel 4 SE", mode="lines",
                line=dict(color="#E45756", width=2, dash="dot"),
                hovertemplate="%{x}<br>MM4: %{y:.2f}<extra></extra>",
            ))
            _fig_inc.update_layout(xaxis=dict(categoryorder="array", categoryarray=_agg_inc["semana"].tolist()))
        else:
            _inc_grp = _inc_base.copy()
            if _faixa_view == "Faixa Etária":
                _inc_grp["NU_IDADE_N"] = pd.to_numeric(_inc_grp["NU_IDADE_N"], errors="coerce")
                _inc_grp = _inc_grp.dropna(subset=["NU_IDADE_N"])
                _inc_grp["_grp"] = pd.NA
                for _lbl, _msk in FAIXA_BINS:
                    _inc_grp.loc[_msk(_inc_grp["NU_IDADE_N"]), "_grp"] = _lbl
                _inc_grp = _inc_grp.dropna(subset=["_grp"])
                _grp_order  = [l for l, _ in FAIXA_BINS]
                _grp_colors = FAIXA_COLORS
                _grp_label  = "Faixa Etária"
            elif _faixa_view == "Sexo":
                _inc_grp = _inc_grp[_inc_grp["CS_SEXO"].isin(["M", "F"])].copy()
                _inc_grp["_grp"] = _inc_grp["CS_SEXO"].map({"M": "Masculino", "F": "Feminino"})
                _grp_order  = ["Masculino", "Feminino"]
                _grp_colors = {"Masculino": "#4C78A8", "Feminino": "#E45756"}
                _grp_label  = "Sexo"
            else:  # Raça/Cor
                _inc_grp["_grp"] = pd.to_numeric(_inc_grp["CS_RACA"], errors="coerce").map(_SRAG_RACA_LABELS)
                _inc_grp = _inc_grp.dropna(subset=["_grp"])
                _grp_order  = list(_SRAG_RACA_LABELS.values())
                _grp_colors = RACA_COLORS
                _grp_label  = "Raça/Cor"

            _yr_inc, _wk_inc = paho_year_week(_inc_grp["DT_SIN_PRI"])
            _inc_grp["semana"]      = "SE " + _wk_inc.astype(str).str.zfill(2) + "/" + _yr_inc.astype(str)
            _inc_grp["semana_sort"] = _yr_inc * 100 + _wk_inc
            _agg_inc = _inc_grp.groupby(["semana", "semana_sort", "_grp"]).size().reset_index(name="n")
            _agg_inc["taxa"] = (_agg_inc["n"] / _RECIFE_POP * 100_000).round(2)
            _ord_inc     = _agg_inc[["semana","semana_sort"]].drop_duplicates().sort_values("semana_sort")["semana"].tolist()
            _present_inc = [l for l in _grp_order if l in _agg_inc["_grp"].unique()]

            _fig_inc = px.bar(
                _agg_inc, x="semana", y="taxa", color="_grp",
                color_discrete_map=_grp_colors,
                labels={"semana": "Semana Epidemiológica", "taxa": "Taxa por 100.000 hab.", "_grp": _grp_label},
                category_orders={"semana": _ord_inc, "_grp": _present_inc},
            )
            _ma_src = _agg_inc.groupby(["semana","semana_sort"])["taxa"].sum().reset_index().rename(columns={"taxa": "n"})
            add_ma_overlay(_fig_inc, _ma_src)

        _fig_inc.update_layout(
            barmode="stack",
            xaxis_tickangle=-90,
            yaxis=dict(title="Taxa por 100.000 hab.", rangemode="tozero"),
            legend=dict(orientation="h", y=-0.28, x=0.5, xanchor="center"),
            margin=dict(l=20, r=20, t=50, b=110),
            height=500,
            plot_bgcolor="white",
        )
        st.plotly_chart(_fig_inc, width='stretch')
        st.caption(
            f"Fonte: {_FONTE_SRAG} · Pop. IBGE Censo 2022 "
            f"(Recife: {_RECIFE_POP:,} hab.)".replace(",", ".")
        )

    st.markdown("---")

    # ---- Mapa por Distrito Sanitário ---------------------------------------
    _map_title = (
        "Óbitos por Distrito Sanitário" if _show_obitos
        else "Taxa de Incidência por Distrito Sanitário (por 100.000 hab.)"
    )
    st.markdown(f"#### {_map_title}")

    from utils.helpers import load_bairro_distrito, _folium_choropleth_distritos, _DISTRITO_NAMES

    @st.cache_data(show_spinner="Calculando incidência por distrito…")
    def _srag_dist_incidence(se_lo, se_hi, clinicas, obitos):
        _DS_POP = {
            "DS I": 57466, "DS II": 211471, "DS III": 193372, "DS IV": 234614,
            "DS V": 263748, "DS VI": 334271, "DS VII": 116463, "DS VIII": 228742,
        }
        bairro_ds = load_bairro_distrito()
        _d = load_srag_withna()
        _d = _d[_d["ID_MN_RESI"] == "RECIFE"].copy()
        _d = filter_epiweek(_d, "DT_SIN_PRI", se_lo, se_hi)
        if obitos:
            _d = _d[pd.to_numeric(_d["EVOLUCAO"], errors="coerce") == 2].copy()
        _d = _filtra_clinicas_srag(_d, list(clinicas))
        if "NM_BAIRRO" not in _d.columns:
            return pd.DataFrame()
        _d["bairro"] = _d["NM_BAIRRO"].str.upper().str.strip().fillna("")
        _d = _d[_d["bairro"] != ""]
        merged = _d.merge(bairro_ds, on="bairro", how="left").dropna(subset=["distrito"])
        agg = merged.groupby("distrito").size().reset_index(name="n")
        all_ds = pd.DataFrame({"distrito": list(_DISTRITO_NAMES.values())})
        result = all_ds.merge(agg, on="distrito", how="left")
        result["n"]    = result["n"].fillna(0).astype(int)
        result["pop"]  = result["distrito"].map(_DS_POP)
        result["taxa"] = (result["n"] / result["pop"] * 100_000).round(1)
        return result[result["n"] > 0].reset_index(drop=True)

    if _show_obitos:
        # Deaths are absolute counts only (no incidence rate per 100k).
        _srag_map_col = "n"
    else:
        _srag_map_view = st.radio(
            "Métrica", ["Taxa de incidência (por 100.000 hab.)", "Números absolutos"],
            horizontal=True, key="srag_map_metric", label_visibility="collapsed",
        )
        _srag_map_col = "taxa" if _srag_map_view.startswith("Taxa") else "n"

    _srag_dist = _srag_dist_incidence(_se_lo, _se_hi, tuple(_unit_filter), _show_obitos)
    if _srag_dist.empty:
        st.info("Sem dados de distrito para os filtros selecionados.")
    else:
        _srag_dist_plot = _srag_dist[["distrito", "n", "taxa"]].copy()
        st.iframe(_folium_choropleth_distritos(_srag_dist_plot, color_col=_srag_map_col), height=920)
        st.caption(f"Fonte: {_FONTE_SRAG}" + ("" if _show_obitos else " · Pop. IBGE Censo 2022."))

    # ---- Óbitos-only extras: hospital/classificação, timeline, heatmap, tabela
    if _show_obitos:
        st.markdown("---")
        _render_srag_obitos_extras(df_view)

# ============================================================
# TAB 2 — Tipos de Vírus
# ============================================================
with tab2:

    # ---- SE/Ano range slider and unit filter --------------------------------
    _t2_cy, _t2_cu = st.columns([2, 2])
    with _t2_cy:
        _t2_se_lo, _t2_se_hi = render_epiweek_slider("srag_test_se", start=SRAG_EPIWEEK_MIN)
    with _t2_cu:
        _t2_unit = _unidade_multiselect_srag("srag_test_unit")

    VIRUS_COLS = {
        "AN_PARA1": "Parainfluenza 1",
        "AN_PARA2": "Parainfluenza 2",
        "AN_PARA3": "Parainfluenza 3",
        "AN_ADENO": "Adenovírus",
        "AN_OUTRO": "Outro vírus respiratório",
        "AN_SARS2": "SARS-CoV-2",
        "AN_VSR":   "VSR",
    }
    VIRUS_COLORS = {
        "Parainfluenza 1":          "#4C78A8",
        "Parainfluenza 2":          "#F58518",
        "Parainfluenza 3":          "#E45756",
        "Adenovírus":               "#72B7B2",
        "Outro vírus respiratório": "#54A24B",
        "SARS-CoV-2":               "#EECA3B",
        "VSR":                      "#B279A2",
    }
    PCR_COLS = {
        "PCR_SARS2": "SARS-CoV-2",
        "PCR_VSR":   "VSR",
        "PCR_PARA1": "Parainfluenza 1",
        "PCR_PARA2": "Parainfluenza 2",
        "PCR_PARA3": "Parainfluenza 3",
        "PCR_PARA4": "Parainfluenza 4",
        "PCR_ADENO": "Adenovírus",
        "PCR_METAP": "Metapneumovírus",
        "PCR_BOCA":  "Bocavírus",
        "PCR_RINO":  "Rinovírus",
    }
    PCR_COLORS = {
        "SARS-CoV-2":     "#EECA3B",
        "VSR":            "#B279A2",
        "Parainfluenza 1":"#4C78A8",
        "Parainfluenza 2":"#F58518",
        "Parainfluenza 3":"#E45756",
        "Parainfluenza 4":"#72B7B2",
        "Adenovírus":     "#54A24B",
        "Metapneumovírus":"#FF9DA6",
        "Bocavírus":      "#9C9C9C",
        "Rinovírus":      "#BAB0AC",
    }

    _vbase = filter_epiweek(df_all, "DT_SIN_PRI", _t2_se_lo, _t2_se_hi)
    _vbase = _filtra_clinicas_srag(_vbase, _t2_unit)

    # ---- Total de Testes -----------------------------------
    st.markdown("### Total de Testes")

    _ttested_rows = []
    _tpos_rows    = []

    # PCR: POS_PCROUT / POS_PCRFLU — non-null = tested, value == 1 = positive
    for _pc in ["POS_PCROUT", "POS_PCRFLU"]:
        if _pc not in _vbase.columns:
            continue
        _tmp = _vbase[["DT_SIN_PRI", _pc]].copy()
        _tmp[_pc] = pd.to_numeric(_tmp[_pc], errors="coerce")
        _ttested_rows.append(_tmp[_tmp[_pc].notna()][["DT_SIN_PRI"]].copy())
        _tpos_rows.append(_tmp[_tmp[_pc] == 1][["DT_SIN_PRI"]].copy())

    # Antígeno: AN_* columns — value in {1,2,3} = tested, value == 1 = positive
    for _col in VIRUS_COLS:
        if _col not in _vbase.columns:
            continue
        _tmp = _vbase[["DT_SIN_PRI", _col]].copy()
        _tmp[_col] = pd.to_numeric(_tmp[_col], errors="coerce")
        _ttested_rows.append(_tmp[_tmp[_col].isin([1, 2, 3])][["DT_SIN_PRI"]].copy())
        _tpos_rows.append(_tmp[_tmp[_col] == 1][["DT_SIN_PRI"]].copy())

    if not _ttested_rows:
        st.info("Colunas de teste não encontradas.")
    else:
        _tall = pd.concat(_ttested_rows, ignore_index=True).dropna(subset=["DT_SIN_PRI"])
        _pall = pd.concat(_tpos_rows,    ignore_index=True).dropna(subset=["DT_SIN_PRI"])

        _yr_tt, _wk_tt = paho_year_week(_tall["DT_SIN_PRI"])
        _tall["semana"]      = "SE " + _wk_tt.astype(str).str.zfill(2) + "/" + _yr_tt.astype(str)
        _tall["semana_sort"] = _yr_tt * 100 + _wk_tt
        _tested_wk = _tall.groupby(["semana", "semana_sort"]).size().reset_index(name="total_tested")

        _yr_tp, _wk_tp = paho_year_week(_pall["DT_SIN_PRI"])
        _pall["semana"]      = "SE " + _wk_tp.astype(str).str.zfill(2) + "/" + _yr_tp.astype(str)
        _pall["semana_sort"] = _yr_tp * 100 + _wk_tp
        _pos_wk = _pall.groupby(["semana", "semana_sort"]).size().reset_index(name="total_pos")

        _tot = _tested_wk.merge(_pos_wk, on=["semana", "semana_sort"], how="left").fillna(0)
        _tot = _tot.sort_values("semana_sort").reset_index(drop=True)
        _tot["pct_pos"] = (_tot["total_pos"] / _tot["total_tested"] * 100).round(1)

        _pct_max = _tot["pct_pos"].max()
        _pct_axis_max = max(_pct_max * 1.15, 1)  # 15 % headroom; never collapse to 0

        _fig_tot = go.Figure()
        _fig_tot.add_trace(go.Bar(
            x=_tot["semana"],
            y=_tot["total_tested"],
            name="Total Testado",
            marker_color="#72B7B2",
            yaxis="y1",
            hovertemplate="%{x}<br>Total testado: %{y}<extra></extra>",
        ))
        _fig_tot.add_trace(go.Scatter(
            x=_tot["semana"],
            y=_tot["pct_pos"],
            name="Positividade (%)",
            mode="lines+markers",
            line=dict(color="#E45756", width=2),
            marker=dict(size=5),
            yaxis="y2",
            customdata=list(zip(_tot["total_pos"].astype(int), _tot["total_tested"].astype(int))),
            hovertemplate=(
                "%{x}<br>Positividade: %{y:.1f}%"
                "<br>(%{customdata[0]} positivos de %{customdata[1]} testados)"
                "<extra></extra>"
            ),
        ))
        _fig_tot.update_layout(
            title="Total de Testes Realizados e Taxa de Positividade por Semana Epidemiológica",
            xaxis=dict(
                title="Semana Epidemiológica",
                tickangle=-90,
                categoryorder="array",
                categoryarray=_tot["semana"].tolist(),
            ),
            yaxis=dict(title="Total de Testes Realizados", rangemode="tozero"),
            yaxis2=dict(
                overlaying="y",
                side="right",
                range=[0, _pct_axis_max],
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
        st.plotly_chart(_fig_tot, width='stretch')
        st.caption(f"Fonte: {_FONTE_SRAG}")

    st.markdown("---")
    st.markdown("### Positividade por Tipo de Vírus")

    ALL_VIRUS_COLORS = {
        "SARS-CoV-2":               "#EECA3B",
        "VSR":                      "#B279A2",
        "Parainfluenza 1":          "#4C78A8",
        "Parainfluenza 2":          "#F58518",
        "Parainfluenza 3":          "#E45756",
        "Parainfluenza 4":          "#72B7B2",
        "Adenovírus":               "#54A24B",
        "Metapneumovírus":          "#FF9DA6",
        "Outro vírus respiratório": "#9C9C9C",
        "Bocavírus":                "#BAB0AC",
        "Rinovírus":                "#636363",
    }

    _vrows = []
    for _col, _label in {**VIRUS_COLS, **PCR_COLS}.items():
        if _col not in _vbase.columns:
            continue
        _tmp = _vbase[["DT_SIN_PRI", _col]].copy()
        _tmp[_col] = pd.to_numeric(_tmp[_col], errors="coerce")
        _pos = _tmp[_tmp[_col] == 1][["DT_SIN_PRI"]].copy()
        _pos["virus"] = _label
        _vrows.append(_pos)

    if not _vrows:
        st.info("Nenhuma coluna de teste encontrada.")
    else:
        _vlong = pd.concat(_vrows, ignore_index=True).dropna(subset=["DT_SIN_PRI"])
        _yr_v, _wk_v = paho_year_week(_vlong["DT_SIN_PRI"])
        _vlong["semana"]      = "SE " + _wk_v.astype(str).str.zfill(2) + "/" + _yr_v.astype(str)
        _vlong["semana_sort"] = _yr_v * 100 + _wk_v

        _all_virus_labels = sorted(_vlong["virus"].unique())
        _virus_sel = st.selectbox(
            "Vírus", ["Todos os Vírus"] + _all_virus_labels,
            key="srag_virus_sel",
        )

        _vfilt = _vlong if _virus_sel == "Todos os Vírus" else _vlong[_vlong["virus"] == _virus_sel]
        _agg_v = _vfilt.groupby(["semana", "semana_sort", "virus"]).size().reset_index(name="n")
        _ord_v = _agg_v[["semana", "semana_sort"]].drop_duplicates().sort_values("semana_sort")["semana"].tolist()
        _virus_order = _all_virus_labels if _virus_sel == "Todos os Vírus" else [_virus_sel]
        _fig_v = px.bar(
            _agg_v, x="semana", y="n", color="virus",
            color_discrete_map=ALL_VIRUS_COLORS,
            title="Testes Positivos por Vírus e Semana Epidemiológica",
            labels={"semana": "Semana Epidemiológica", "n": "Nº Testes Positivos", "virus": "Vírus"},
            category_orders={"semana": _ord_v, "virus": _virus_order},
        )
        _add_pct_hover(_fig_v, _agg_v, unit="testes positivos")
        _bar_layout(_fig_v)
        st.plotly_chart(_fig_v, width='stretch')
        st.caption(f"Fonte: {_FONTE_SRAG}")

# ============================================================
# TAB 3 — Nowcasting + Forecasting
# ============================================================
with tab3:
    st.markdown("### Nowcasting + Forecasting — SRAG")
    st.caption(
        "Modelo INLA binomial negativo usando as variáveis: idade, atraso de notificação, casos por semana. "
        "Previsão de forecasting para as próximas 4 semanas depois da última data disponível."
    )
    embed_html_plot("nowcasting_srag.html", height=750, fix_legend=True)
    st.caption(f"Fonte: {_FONTE_SRAG}")

    st.markdown("---")
    st.markdown("### Média Móvel — Semanas Epidemiológicas 2026")
    st.caption("Média móvel de 4 semanas sobre casos semanais por semana de início dos sintomas (`DT_SIN_PRI`).")
    render_ma_chart(df_all, onset_col="DT_SIN_PRI", titulo="Média Móvel 4 sem. — SRAG")
    st.caption(f"Fonte: {_FONTE_SRAG}")

    st.markdown("---")
    st.markdown("### Sazonalidade — Média Histórica por Semana Epidemiológica")
    render_seasonality_hist(df_all, onset_col="DT_SIN_PRI",
                            titulo="Sazonalidade — SRAG (média por SE, todos os anos)")
    st.caption(f"Fonte: {_FONTE_SRAG}")

    st.markdown("---")
    st.markdown("### Semanas previstas")
    render_forecast_table("nowcasting_srag.html")
    st.caption(f"Fonte: {_FONTE_SRAG}")

