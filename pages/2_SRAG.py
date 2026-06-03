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
    embed_html_plot, render_ma_chart, load_nowcast_table, paho_year_week,
    CLASSI_FIN_LABELS, CLASSI_FIN_COLORS, DATA_DIR,
)

st.set_page_config(page_title="SRAG", page_icon="🫁", layout="wide")
st.title("🫁 SRAG — Síndrome Respiratória Aguda Grave")

# --- Load data — filter to Recife notification municipality (ID_MUNICIP) ----
df_all = load_srag_withna()
df_all = df_all[df_all["ID_MUNICIP"] == "RECIFE"].copy()

_UNIDADES_KW_SRAG = ["BARROS LIMA", "ARNALDO MARQUES", "AMAURY COUTINHO", "AGAMENON"]

_FONTE_SRAG = "BRASIL. Ministério da Saúde. SIVEP-GRIPE. Banco de Dados de Síndromes Respiratórias Agudas Graves. Brasília, 2026."
_RECIFE_POP = 1_640_147

if st.session_state.pop("srag_goto_nowcasting", False):
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

tab1, tab2, tab3, tab4 = st.tabs(["📊 Descritivo", "🦠 Testes", "📈 Nowcasting + Forecasting", "Óbitos"])

# ============================================================
# TAB 1 — Descriptive
# ============================================================
with tab1:

    # ---- Year slider and unit filter ----------------------------------------
    _c_year, _c_unit = st.columns([2, 2])
    with _c_year:
        _year_lo, _year_hi = st.slider(
            "Período (ano)", 2022, 2026, (2022, 2026), step=1, key="srag_desc_year",
        )
    with _c_unit:
        _unit_filter = st.radio(
            "Unidade de internação", ["Todas", "Unidades Municipais"],
            horizontal=True, key="srag_desc_unit",
        )

    df_filt = df_all[df_all["DT_DIGITA"].dt.year.between(_year_lo, _year_hi)].copy()
    if _unit_filter == "Unidades Municipais" and "NM_UN_INTE" in df_filt.columns:
        _nm = df_filt["NM_UN_INTE"].str.upper().str.strip().fillna("")
        df_filt = df_filt[_nm.apply(lambda x: any(kw in x for kw in _UNIDADES_KW_SRAG))].copy()
    _yr_f, _wk_f = paho_year_week(df_filt["DT_DIGITA"])
    if _year_hi == 2026:
        df_filt = df_filt[~((_yr_f == 2026) & (_wk_f > 16))]

    # ---- KPIs --------------------------------------------------------------
    total_cases  = len(df_filt)
    total_deaths = int((df_filt["EVOLUCAO"] == 2).sum()) if "EVOLUCAO" in df_filt.columns else 0

    render_kpis([
        ("Total de casos",  fmt_int(total_cases)),
        ("Período",         f"{_year_lo} – {_year_hi}"),
        ("Total de óbitos", fmt_int(total_deaths)),
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

    # ---- Faixa Etária — all cases ----------------------------------------
    st.markdown("#### Casos por Faixa Etária")

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

    _faixa_view = st.radio(
        "Visualização", ["Faixa Etária", "Sexo"],
        horizontal=True, key="srag_faixa_view",
    )

    _age = df_filt.copy()
    _age["NU_IDADE_N"] = pd.to_numeric(_age["NU_IDADE_N"], errors="coerce")
    _age = _age.dropna(subset=["DT_DIGITA", "NU_IDADE_N"])
    for _label, _mask in FAIXA_BINS:
        _age.loc[_mask(_age["NU_IDADE_N"]), "faixa"] = _label
    _age = _age.dropna(subset=["faixa"])

    if _age.empty:
        st.info("Sem dados de faixa etária.")
    elif _faixa_view == "Faixa Etária":
        _yr_a, _wk_a = paho_year_week(_age["DT_DIGITA"])
        _age["semana"]      = "SE " + _wk_a.astype(str).str.zfill(2) + "/" + _yr_a.astype(str)
        _age["semana_sort"] = _yr_a * 100 + _wk_a
        _agg_a = _age.groupby(["semana", "semana_sort", "faixa"]).size().reset_index(name="n")
        _ord_a = _agg_a[["semana","semana_sort"]].drop_duplicates().sort_values("semana_sort")["semana"].tolist()
        _fig_a = px.bar(
            _agg_a, x="semana", y="n", color="faixa",
            color_discrete_map=FAIXA_COLORS,
            title="Casos por Faixa Etária por Semana Epidemiológica",
            labels={"semana": "Semana Epidemiológica", "n": "Nº Casos", "faixa": "Faixa Etária"},
            category_orders={"semana": _ord_a, "faixa": [l for l, _ in FAIXA_BINS]},
        )
        _add_pct_hover(_fig_a, _agg_a)
        _bar_layout(_fig_a)
        st.plotly_chart(_fig_a, use_container_width=True)
    else:
        _sx = _age.copy()
        _sx = _sx[_sx["CS_SEXO"].isin(["M", "F"])]
        _sx["SEXO_LABEL"] = _sx["CS_SEXO"].map({"M": "Masculino", "F": "Feminino"})
        if _sx.empty:
            st.info("Sem dados de sexo.")
        else:
            _yr_sx, _wk_sx = paho_year_week(_sx["DT_DIGITA"])
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
            st.plotly_chart(_fig_sx, use_container_width=True)

    st.markdown("---")

    # ---- Raça/Cor ------------------------------------------------------------
    st.markdown("#### Casos por Raça/Cor")

    _RACA_LABELS_SR = {1: "Branca", 2: "Preta", 3: "Amarela", 4: "Parda", 5: "Indígena", 9: "Ignorado"}
    _RACA_COLORS_SR = {
        "Branca": "#4C78A8", "Parda": "#F58518", "Preta": "#E45756",
        "Amarela": "#EECA3B", "Indígena": "#54A24B", "Ignorado": "#9C9C9C",
    }

    _raca_sr = df_filt.copy()
    _raca_sr["CS_RACA"] = pd.to_numeric(_raca_sr["CS_RACA"], errors="coerce")
    _raca_sr = _raca_sr.dropna(subset=["DT_DIGITA", "CS_RACA"])
    _raca_sr["RACA_LABEL"] = _raca_sr["CS_RACA"].astype(int).map(_RACA_LABELS_SR)
    _raca_sr = _raca_sr.dropna(subset=["RACA_LABEL"])

    if _raca_sr.empty:
        st.info("Sem dados de raça/cor.")
    else:
        _yr_rc, _wk_rc = paho_year_week(_raca_sr["DT_DIGITA"])
        _raca_sr["semana"]      = "SE " + _wk_rc.astype(str).str.zfill(2) + "/" + _yr_rc.astype(str)
        _raca_sr["semana_sort"] = _yr_rc * 100 + _wk_rc
        _agg_rc = _raca_sr.groupby(["semana", "semana_sort", "RACA_LABEL"]).size().reset_index(name="n")
        _ord_rc = _agg_rc[["semana","semana_sort"]].drop_duplicates().sort_values("semana_sort")["semana"].tolist()
        _fig_rc = px.bar(
            _agg_rc, x="semana", y="n", color="RACA_LABEL",
            color_discrete_map=_RACA_COLORS_SR,
            title="Casos por Raça/Cor por Semana Epidemiológica",
            labels={"semana": "Semana Epidemiológica", "n": "Nº Casos", "RACA_LABEL": "Raça/Cor"},
            category_orders={"semana": _ord_rc},
        )
        _add_pct_hover(_fig_rc, _agg_rc)
        _bar_layout(_fig_rc)
        st.plotly_chart(_fig_rc, use_container_width=True)
        st.caption(f"Fonte: {_FONTE_SRAG}")

    st.markdown("---")

    # ---- Mapa de Taxa de Incidência por Distrito Sanitário -------------------
    st.markdown("#### Taxa de Incidência por Distrito Sanitário (por 100.000 hab.)")

    import streamlit.components.v1 as _cmp
    from utils.helpers import load_bairro_distrito, _folium_choropleth_distritos, _DISTRITO_NAMES

    @st.cache_data(show_spinner="Calculando incidência por distrito…")
    def _srag_dist_incidence(year_lo, year_hi, unit):
        _DS_POP = {
            "DS I": 57466, "DS II": 211471, "DS III": 193372, "DS IV": 234614,
            "DS V": 263748, "DS VI": 334271, "DS VII": 116463, "DS VIII": 228742,
        }
        bairro_ds = load_bairro_distrito()
        _d = load_srag_withna()
        _d = _d[_d["ID_MUNICIP"] == "RECIFE"].copy()
        _d = _d[_d["DT_DIGITA"].dt.year.between(year_lo, year_hi)].copy()
        _yr, _wk = paho_year_week(_d["DT_DIGITA"])
        _d = _d[~((_yr == 2026) & (_wk > 16))]
        if unit == "Unidades Municipais" and "NM_UN_INTE" in _d.columns:
            _nm = _d["NM_UN_INTE"].str.upper().str.strip().fillna("")
            _d = _d[_nm.apply(lambda x: any(kw in x for kw in _UNIDADES_KW_SRAG))].copy()
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

    _srag_map_view = st.radio(
        "Métrica", ["Taxa de incidência (por 100.000 hab.)", "Números absolutos"],
        horizontal=True, key="srag_map_metric", label_visibility="collapsed",
    )
    _srag_dist = _srag_dist_incidence(_year_lo, _year_hi, _unit_filter)
    if _srag_dist.empty:
        st.info("Sem dados de distrito para os filtros selecionados.")
    else:
        _srag_map_col = "taxa" if _srag_map_view.startswith("Taxa") else "n"
        _srag_dist_plot = _srag_dist[["distrito", "n", "taxa"]].copy()
        _cmp.html(_folium_choropleth_distritos(_srag_dist_plot, color_col=_srag_map_col), height=520, scrolling=False)
        st.caption(f"Fonte: {_FONTE_SRAG} · Pop. IBGE Censo 2022.")

    st.markdown("---")
    st.markdown("#### Internações por Faixa Etária")

    AGE_BINS = [
        ("1–4",   lambda a: (a >= 1)  & (a <= 4)),
        ("5–9",   lambda a: (a >= 5)  & (a <= 9)),
        ("10–19", lambda a: (a >= 10) & (a <= 19)),
        ("20–29", lambda a: (a >= 20) & (a <= 29)),
        ("30–39", lambda a: (a >= 30) & (a <= 39)),
        ("40–49", lambda a: (a >= 40) & (a <= 49)),
        ("50–59", lambda a: (a >= 50) & (a <= 59)),
        ("60+",   lambda a: a >= 60),
    ]
    AGE_COLORS = {
        "1–4":   "#4C78A8",
        "5–9":   "#F58518",
        "10–19": "#E45756",
        "20–29": "#72B7B2",
        "30–39": "#54A24B",
        "40–49": "#EECA3B",
        "50–59": "#B279A2",
        "60+":   "#FF9DA6",
    }

    if "HOSPITAL" not in df_filt.columns:
        st.warning("Coluna HOSPITAL não encontrada.")
    else:
        hosp = df_filt.copy()
        hosp["HOSPITAL"] = pd.to_numeric(hosp["HOSPITAL"], errors="coerce")
        hosp["NU_IDADE_N"] = pd.to_numeric(hosp["NU_IDADE_N"], errors="coerce")
        hosp = hosp[hosp["HOSPITAL"] == 1].dropna(subset=["DT_DIGITA", "NU_IDADE_N"])

        _epi_yr_h, _epi_wk_h = paho_year_week(hosp["DT_DIGITA"])
        hosp["semana"]      = "SE " + _epi_wk_h.astype(str).str.zfill(2) + "/" + _epi_yr_h.astype(str)
        hosp["semana_sort"] = _epi_yr_h * 100 + _epi_wk_h

        for label, mask_fn in AGE_BINS:
            hosp.loc[mask_fn(hosp["NU_IDADE_N"]), "faixa"] = label

        hosp = hosp.dropna(subset=["faixa"])

        if hosp.empty:
            st.info("Sem internações registradas com os filtros selecionados.")
        else:
            agg_h = (
                hosp.groupby(["semana", "semana_sort", "faixa"])
                    .size().reset_index(name="n")
            )
            semana_order_h = (
                agg_h[["semana", "semana_sort"]]
                .drop_duplicates()
                .sort_values("semana_sort")["semana"]
                .tolist()
            )
            faixa_order = [label for label, _ in AGE_BINS]

            fig_h = px.bar(
                agg_h, x="semana", y="n", color="faixa",
                color_discrete_map=AGE_COLORS,
                title="Internações por Faixa Etária — SRAG",
                labels={"semana": "Semana Epidemiológica",
                        "n": "Nº Internações",
                        "faixa": "Faixa Etária"},
                category_orders={
                    "semana": semana_order_h,
                    "faixa":  faixa_order,
                },
            )
            _add_pct_hover(fig_h, agg_h, unit="internações")
            _bar_layout(fig_h)
            st.plotly_chart(fig_h, use_container_width=True)

# ============================================================
# TAB 2 — Tipos de Vírus
# ============================================================
with tab2:

    # ---- Year slider and unit filter ----------------------------------------
    _t2_cy, _t2_cu = st.columns([2, 2])
    with _t2_cy:
        _t2_year_lo, _t2_year_hi = st.slider(
            "Período (ano)", 2022, 2026, (2022, 2026), step=1, key="srag_test_year",
        )
    with _t2_cu:
        _t2_unit = st.radio(
            "Unidade de internação", ["Todas", "Unidades Municipais"],
            horizontal=True, key="srag_test_unit",
        )

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

    _vbase = df_all[df_all["DT_DIGITA"].dt.year.between(_t2_year_lo, _t2_year_hi)].copy()
    if _t2_unit == "Unidades Municipais" and "NM_UN_INTE" in _vbase.columns:
        _nm_vb = _vbase["NM_UN_INTE"].str.upper().str.strip().fillna("")
        _vbase = _vbase[_nm_vb.apply(lambda x: any(kw in x for kw in _UNIDADES_KW_SRAG))].copy()
    if _t2_year_hi == 2026:
        _yr_vb, _wk_vb = paho_year_week(_vbase["DT_DIGITA"])
        _vbase = _vbase[~((_yr_vb == 2026) & (_wk_vb > 16))]

    # ---- Total de Testes (Antigeno + PCR) -----------------------------------
    st.markdown("### Total de Testes — Antígeno + PCR")
    st.caption(
        "Total de testes realizados"
        "e taxa de positividade por semana epidemiológica."
    )

    _total_view = st.radio(
        "Tipo de Teste", ["Total", "PCR", "Antígeno"],
        horizontal=True, key="srag_total_toggle",
    )

    _ttested_rows = []
    _tpos_rows    = []

    if _total_view in ("PCR", "Total"):
        # POS_PCROUT / POS_PCRFLU: non-null = tested, value == 1 = positive
        for _pc in ["POS_PCROUT", "POS_PCRFLU"]:
            if _pc not in _vbase.columns:
                continue
            _tmp = _vbase[["DT_DIGITA", _pc]].copy()
            _tmp[_pc] = pd.to_numeric(_tmp[_pc], errors="coerce")
            _ttested_rows.append(_tmp[_tmp[_pc].notna()][["DT_DIGITA"]].copy())
            _tpos_rows.append(_tmp[_tmp[_pc] == 1][["DT_DIGITA"]].copy())

    if _total_view in ("Antígeno", "Total"):
        # AN_* columns: value in {1,2,3} = tested, value == 1 = positive
        for _col in VIRUS_COLS:
            if _col not in _vbase.columns:
                continue
            _tmp = _vbase[["DT_DIGITA", _col]].copy()
            _tmp[_col] = pd.to_numeric(_tmp[_col], errors="coerce")
            _ttested_rows.append(_tmp[_tmp[_col].isin([1, 2, 3])][["DT_DIGITA"]].copy())
            _tpos_rows.append(_tmp[_tmp[_col] == 1][["DT_DIGITA"]].copy())

    if not _ttested_rows:
        st.info("Colunas de teste não encontradas.")
    else:
        _tall = pd.concat(_ttested_rows, ignore_index=True).dropna(subset=["DT_DIGITA"])
        _pall = pd.concat(_tpos_rows,    ignore_index=True).dropna(subset=["DT_DIGITA"])

        _yr_tt, _wk_tt = paho_year_week(_tall["DT_DIGITA"])
        _tall["semana"]      = "SE " + _wk_tt.astype(str).str.zfill(2) + "/" + _yr_tt.astype(str)
        _tall["semana_sort"] = _yr_tt * 100 + _wk_tt
        _tested_wk = _tall.groupby(["semana", "semana_sort"]).size().reset_index(name="total_tested")

        _yr_tp, _wk_tp = paho_year_week(_pall["DT_DIGITA"])
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
            title=f"Total de Testes Realizados e Taxa de Positividade — {_total_view}",
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
        st.plotly_chart(_fig_tot, use_container_width=True)

    st.markdown("---")
    st.markdown("### Teste Antigênico — Positividade por Tipo de Vírus")
    st.caption("Conta testes positivos  por vírus por semana de digitação (2022–2026).")

    _vrows = []
    for _col, _label in VIRUS_COLS.items():
        if _col not in _vbase.columns:
            continue
        _tmp = _vbase[["DT_DIGITA", _col]].copy()
        _tmp[_col] = pd.to_numeric(_tmp[_col], errors="coerce")
        _pos = _tmp[_tmp[_col] == 1][["DT_DIGITA"]].copy()
        _pos["virus"] = _label
        _vrows.append(_pos)

    if not _vrows:
        st.info("Nenhuma coluna de teste antigênico encontrada.")
    else:
        _vlong = pd.concat(_vrows, ignore_index=True).dropna(subset=["DT_DIGITA"])
        _yr_v, _wk_v = paho_year_week(_vlong["DT_DIGITA"])
        _vlong["semana"]      = "SE " + _wk_v.astype(str).str.zfill(2) + "/" + _yr_v.astype(str)
        _vlong["semana_sort"] = _yr_v * 100 + _wk_v
        _agg_v = _vlong.groupby(["semana", "semana_sort", "virus"]).size().reset_index(name="n")
        _ord_v = _agg_v[["semana","semana_sort"]].drop_duplicates().sort_values("semana_sort")["semana"].tolist()
        _fig_v = px.bar(
            _agg_v, x="semana", y="n", color="virus",
            color_discrete_map=VIRUS_COLORS,
            title="Testes Antigênicos Positivos por Vírus e Semana Epidemiológica",
            labels={"semana": "Semana Epidemiológica", "n": "Nº Testes Positivos", "virus": "Vírus"},
            category_orders={"semana": _ord_v, "virus": list(VIRUS_COLS.values())},
        )
        _add_pct_hover(_fig_v, _agg_v, unit="testes positivos")
        _bar_layout(_fig_v)
        st.plotly_chart(_fig_v, use_container_width=True)

    st.markdown("---")
    st.markdown("### PCR — Positividade por Tipo de Vírus")
    st.caption("Conta testes PCR positivos por vírus por semana de digitação (2022–2026).")

    _prows = []
    for _col, _label in PCR_COLS.items():
        if _col not in _vbase.columns:
            continue
        _tmp = _vbase[["DT_DIGITA", _col]].copy()
        _tmp[_col] = pd.to_numeric(_tmp[_col], errors="coerce")
        _pos = _tmp[_tmp[_col] == 1][["DT_DIGITA"]].copy()
        _pos["virus"] = _label
        _prows.append(_pos)

    if not _prows:
        st.info("Nenhuma coluna de PCR encontrada.")
    else:
        _plong = pd.concat(_prows, ignore_index=True).dropna(subset=["DT_DIGITA"])
        _yr_p, _wk_p = paho_year_week(_plong["DT_DIGITA"])
        _plong["semana"]      = "SE " + _wk_p.astype(str).str.zfill(2) + "/" + _yr_p.astype(str)
        _plong["semana_sort"] = _yr_p * 100 + _wk_p
        _agg_p = _plong.groupby(["semana", "semana_sort", "virus"]).size().reset_index(name="n")
        _ord_p = _agg_p[["semana","semana_sort"]].drop_duplicates().sort_values("semana_sort")["semana"].tolist()
        _fig_p = px.bar(
            _agg_p, x="semana", y="n", color="virus",
            color_discrete_map=PCR_COLORS,
            title="Testes PCR Positivos por Vírus e Semana Epidemiológica",
            labels={"semana": "Semana Epidemiológica", "n": "Nº Testes Positivos", "virus": "Vírus"},
            category_orders={"semana": _ord_p, "virus": list(PCR_COLS.values())},
        )
        _add_pct_hover(_fig_p, _agg_p, unit="testes positivos")
        _bar_layout(_fig_p)
        st.plotly_chart(_fig_p, use_container_width=True)

# ============================================================
# TAB 3 — Nowcasting + Forecasting
# ============================================================
with tab3:
    st.markdown("### Nowcasting + Forecasting — SRAG")
    st.caption(
        "Modelo INLA estruturado por idade (`bins_age = '10 years'`), "
        "`wdw = 230` semanas, `K = 4` semanas de forecast."
    )
    embed_html_plot("nowcasting_srag.html", height=750)

    st.markdown("---")
    st.markdown("### Média Móvel — Semanas Epidemiológicas 2026")
    st.caption("Média móvel de 4 semanas sobre casos semanais por semana de início dos sintomas (`DT_SIN_PRI`).")
    render_ma_chart(df_all, onset_col="DT_SIN_PRI", titulo="Média Móvel 4 sem. — SRAG")

    st.markdown("---")
    st.markdown("###Semanas previstas")
    _tbl = load_nowcast_table("nowcasting_srag.html")
    if _tbl is not None:
        _fc = _tbl[_tbl["Tipo"] == "Forecast"].copy()
        _fc["Data"] = _fc["Data"].dt.strftime("%d/%m/%Y")
        st.dataframe(_fc.drop(columns=["Tipo"]), use_container_width=True, hide_index=True)
    else:
        st.info("Dados de nowcasting não disponíveis.")

# ============================================================
# TAB 4 — Óbitos
# ============================================================
with tab4:
    st.markdown("### Óbitos — SRAG")
    st.caption("Pacientes com `EVOLUCAO = 2` (óbito) no banco SRAG.")

    RACA_LABELS = {1: "Branca", 2: "Preta", 3: "Amarela", 4: "Parda", 5: "Indígena", 9: "Ignorado"}
    CLASSI_SRAG = {
        1: "SRAG por Influenza",
        2: "SRAG por outro vírus resp.",
        3: "SRAG por outro agente",
        4: "SRAG não especificado",
        5: "SRAG por COVID-19",
    }

    _ob = df_all.copy()
    _ob["EVOLUCAO"]   = pd.to_numeric(_ob["EVOLUCAO"],   errors="coerce")
    _ob["NU_IDADE_N"] = pd.to_numeric(_ob["NU_IDADE_N"], errors="coerce")
    _ob["CLASSI_FIN"] = pd.to_numeric(_ob["CLASSI_FIN"], errors="coerce")
    _ob["CS_RACA"]    = pd.to_numeric(_ob["CS_RACA"],    errors="coerce")
    _ob = _ob[_ob["EVOLUCAO"] == 2].copy()

    # Date columns
    _ob["DT_EVOLUCA"] = pd.to_datetime(_ob["DT_EVOLUCA"], dayfirst=True, errors="coerce")
    _ob["DT_DIGITA"]  = pd.to_datetime(_ob["DT_DIGITA"],  errors="coerce")

    # Decoded labels
    _ob["SEXO_LABEL"]   = _ob["CS_SEXO"].map({"M": "Masculino", "F": "Feminino", "I": "Ignorado"})
    _ob["RACA_LABEL"]   = _ob["CS_RACA"].map(RACA_LABELS)
    _ob["CLASSI_LABEL"] = _ob["CLASSI_FIN"].map(CLASSI_SRAG)
    _ob["NM_BAIRRO"]    = _ob["NM_BAIRRO"].str.title()

    # ---- Unidades municipais filter ----------------------------------------
    _UNIDADES_KW = ["BARROS LIMA", "ARNALDO MARQUES", "AMAURY COUTINHO", "AGAMENON"]
    _UNIDADES_DISPLAY = [
        "US 167 — Policlínica Prof. Barros Lima",
        "US 153 — Policlínica Arnaldo Marques",
        "US 169 — Policlínica Amaury Coutinho",
        "US 159 / Hospital Agamenon Magalhães",
    ]
    _ob_filter = st.radio(
        "Filtro de unidade",
        ["Todos", "Unidades Municipais"],
        horizontal=True,
        key="srag_ob_unit_filter",
    )
    if _ob_filter == "Unidades Municipais":
        _nm_up = _ob["NM_UN_INTE"].str.upper().str.strip().fillna("")
        _unit_mask = _nm_up.apply(lambda x: any(kw in x for kw in _UNIDADES_KW))
        _ob = _ob[_unit_mask].copy()
        st.caption(
            "Filtrado para: " + " · ".join(_UNIDADES_DISPLAY)
        )

    if _ob.empty:
        st.info("Nenhum óbito encontrado.")
    else:
        # ---- KPIs ----------------------------------------------------------
        _n_fem  = (_ob["CS_SEXO"] == "F").sum()
        _n_masc = (_ob["CS_SEXO"] == "M").sum()
        _avg_age = _ob["NU_IDADE_N"].mean()
        _uti_pct = (
            (_ob["UTI"] == 1).sum() / _ob["UTI"].notna().sum() * 100
            if "UTI" in _ob.columns and _ob["UTI"].notna().sum() > 0 else 0
        )
        render_kpis([
            ("Total de óbitos", fmt_int(len(_ob))),
            ("Feminino",        fmt_int(_n_fem)),
            ("Masculino",       fmt_int(_n_masc)),
            ("Idade média",     f"{_avg_age:.1f} anos"),
            ("Internados em UTI", f"{_uti_pct:.1f}%"),
        ])

        st.markdown("---")

        # ---- Row 1: Sexo | Faixa Etária | Raça/Cor | Bairro ---------------
        _r1a, _r1b, _r1c, _r1d = st.columns(4)

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
            st.plotly_chart(_fig_s, use_container_width=True)

        with _r1b:
            _OB_FAIXA_BINS = [
                ("1–4",   lambda a: (a >= 1)  & (a <= 4)),
                ("5–9",   lambda a: (a >= 5)  & (a <= 9)),
                ("10–19", lambda a: (a >= 10) & (a <= 19)),
                ("20–29", lambda a: (a >= 20) & (a <= 29)),
                ("30–39", lambda a: (a >= 30) & (a <= 39)),
                ("40–49", lambda a: (a >= 40) & (a <= 49)),
                ("50–59", lambda a: (a >= 50) & (a <= 59)),
                ("60+",   lambda a: a >= 60),
            ]
            _OB_FAIXA_ORDER = [l for l, _ in _OB_FAIXA_BINS]
            _age_ob = _ob.dropna(subset=["NU_IDADE_N"]).copy()
            for _lbl, _msk in _OB_FAIXA_BINS:
                _age_ob.loc[_msk(_age_ob["NU_IDADE_N"]), "faixa"] = _lbl
            _age_ob = _age_ob.dropna(subset=["faixa"])
            _fc_age = (
                _age_ob["faixa"].value_counts()
                .reindex(_OB_FAIXA_ORDER)
                .fillna(0).reset_index()
            )
            _fc_age.columns = ["faixa", "n"]
            _fig_age = px.bar(
                _fc_age, x="faixa", y="n", title="Por Faixa Etária",
                labels={"faixa": "Faixa Etária", "n": "Óbitos"},
                color_discrete_sequence=["#72B7B2"],
                category_orders={"faixa": _OB_FAIXA_ORDER},
            )
            _fig_age.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=320)
            st.plotly_chart(_fig_age, use_container_width=True)

        with _r1c:
            _rc = _ob["RACA_LABEL"].value_counts().reset_index()
            _rc.columns = ["raca", "n"]
            _fig_rc = px.bar(
                _rc, x="n", y="raca", orientation="h", title="Por Raça/Cor",
                labels={"raca": "", "n": "Óbitos"},
                color_discrete_sequence=["#B279A2"],
            )
            _fig_rc.update_layout(
                yaxis=dict(autorange="reversed"),
                margin=dict(l=10, r=10, t=50, b=10), height=320,
            )
            st.plotly_chart(_fig_rc, use_container_width=True)

        with _r1d:
            _bc = _ob["NM_BAIRRO"].value_counts().head(10).reset_index()
            _bc.columns = ["bairro", "n"]
            _fig_bairro = px.bar(
                _bc, x="n", y="bairro", orientation="h", title="Por Bairro (top 10)",
                labels={"bairro": "", "n": "Óbitos"},
                color_discrete_sequence=["#F58518"],
            )
            _fig_bairro.update_layout(
                yaxis=dict(autorange="reversed"),
                margin=dict(l=10, r=10, t=50, b=10), height=320,
            )
            st.plotly_chart(_fig_bairro, use_container_width=True)

        st.markdown("---")

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
                st.plotly_chart(_fig_h, use_container_width=True)

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
            st.plotly_chart(_fig_cl, use_container_width=True)

        st.markdown("---")

        # ---- Timeline: óbitos por semana epidemiológica --------------------
        st.markdown("#### Óbitos por Semana Epidemiológica (data do óbito)")
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
        st.plotly_chart(_fig_tl, use_container_width=True)

        st.markdown("---")

        # ---- Heatmap — residência dos óbitos ----------------------------------
        st.markdown("---")
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
            import streamlit.components.v1 as _components

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
                    max_val=_max_w,
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

                _map_html = _fmap._repr_html_()
                _components.html(_map_html, height=520, scrolling=False)

                st.caption(
                    f"{len(_ob_geo):,} de {len(_ob_map):,} óbitos geolocalizados "
                    f"({_pct_located:.0f}%) · "
                    f"Top bairro: **{_heat_data_df.nlargest(1,'weight').iloc[0]['official']}** "
                    f"({int(_heat_data_df['weight'].max())} óbitos)"
                )

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
        st.dataframe(_tbl_ob, use_container_width=True, hide_index=True)

