"""SG (Síndrome Gripal) page."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.helpers import (
    load_sg, load_esus, load_sg_srag_linked, load_bairro_distrito,
    render_kpis, fmt_int,
    embed_html_plot, render_ma_chart, load_nowcast_table, paho_year_week,
)


st.set_page_config(page_title="SG", page_icon="🤧", layout="wide")
st.title("🤧 SG — Síndrome Gripal")

# --- Load data — filter to Recife notification municipality (COD_MUNIC) -----
df_all = load_sg()
df_all = df_all[df_all["COD_MUNIC"] == 261160].copy()

_UNIDADES_KW_SG = ["BARROS LIMA", "ARNALDO MARQUES", "AMAURY COUTINHO", "AGAMENON", "CRAVO GAMA"]

_FONTE_SG   = "BRASIL. Ministério da Saúde. SIVEP-GRIPE. Banco de Dados de Síndrome Gripal. Brasília, 2026."
_FONTE_ESUS = "BRASIL. Ministério da Saúde. eSUS-Notifica. Brasília, 2026."
_FONTE_PROG = "BRASIL. Ministério da Saúde. SIVEP-GRIPE. Banco de Dados de Síndrome Gripal e Síndromes Respiratórias Agudas Graves. Brasília, 2026."

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

    # ---- Year slider and unit filter ----------------------------------------
    _c_year, _c_unit = st.columns([2, 2])
    with _c_year:
        _year_lo, _year_hi = st.slider(
            "Período (ano)", 2022, 2026, (2022, 2026), step=1, key="sg_desc_year",
        )
    with _c_unit:
        _unit_filter = st.radio(
            "Unidade de saúde", ["Todas", "Unidades Municipais"],
            horizontal=True, key="sg_desc_unit",
        )

    df_filt = df_all[df_all["DT_DIGITA"].dt.year.between(_year_lo, _year_hi)].copy()
    if _unit_filter == "Unidades Municipais":
        _nm = df_filt["NOME_UNIDA"].str.upper().str.strip().fillna("")
        df_filt = df_filt[_nm.apply(lambda x: any(kw in x for kw in _UNIDADES_KW_SG))].copy()
    _yr_f, _wk_f = paho_year_week(df_filt["DT_DIGITA"])
    if _year_hi == 2026:
        df_filt = df_filt[~((_yr_f == 2026) & (_wk_f > 16))]

    # ---- KPIs --------------------------------------------------------------
    total_cases = len(df_filt)
    vac_cov  = int(df_filt["VACINA_COV"].notna().sum()) if "VACINA_COV" in df_filt.columns else 0
    vac_flu  = int((df_filt["VACINA"] == 1).sum())      if "VACINA"     in df_filt.columns else 0
    trat_cov = int((df_filt["TRAT_COV"] == 1).sum())   if "TRAT_COV"   in df_filt.columns else 0

    render_kpis([
        ("Total de casos",             fmt_int(total_cases)),
        ("Período",                    f"{_year_lo} – {_year_hi}"),
        ("Vacinação COVID",            fmt_int(vac_cov)),
        ("Vacinação Influenza",        fmt_int(vac_flu)),
        ("Tratamento antiviral COVID", fmt_int(trat_cov)),
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

    # shared colour maps
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
        "1–4": "#4C78A8", "5–9": "#F58518", "10–19": "#E45756",
        "20–29": "#72B7B2", "30–39": "#54A24B", "40–49": "#EECA3B",
        "50–59": "#B279A2", "60+": "#FF9DA6",
    }
    RACA_LABELS = {1: "Branca", 2: "Preta", 3: "Amarela", 4: "Parda", 5: "Indígena", 9: "Ignorado"}
    RACA_COLORS = {
        "Branca": "#4C78A8", "Parda": "#F58518", "Preta": "#E45756",
        "Amarela": "#EECA3B", "Indígena": "#54A24B", "Ignorado": "#9C9C9C",
    }
    DISTRITO_COLORS = {
        "DS I":   "#4C78A8", "DS II":  "#F58518",
        "DS III": "#E45756", "DS IV":  "#72B7B2",
        "DS V":   "#54A24B", "DS VI":  "#EECA3B",
        "DS VII": "#B279A2", "DS VIII":"#FF9DA6",
        "Não mapeado": "#CCCCCC",
    }
    DISTRITO_ORDER = [
        "DS I", "DS II", "DS III", "DS IV",
        "DS V", "DS VI", "DS VII", "DS VIII",
        "Não mapeado",
    ]

    def _wsb(df_in, col, color_map, title, col_order=None, fonte=None):
        """Weekly stacked bar helper."""
        _d = df_in.dropna(subset=["DT_DIGITA", col]).copy()
        if _d.empty:
            st.info(f"Sem dados para {title}.")
            return
        _yr, _wk = paho_year_week(_d["DT_DIGITA"])
        _d["semana"]      = "SE " + _wk.astype(str).str.zfill(2) + "/" + _yr.astype(str)
        _d["semana_sort"] = _yr * 100 + _wk
        _agg = _d.groupby(["semana", "semana_sort", col]).size().reset_index(name="n")
        _ord = _agg[["semana","semana_sort"]].drop_duplicates().sort_values("semana_sort")["semana"].tolist()
        _cat = {"semana": _ord}
        if col_order:
            _cat[col] = col_order
        _fig = px.bar(
            _agg, x="semana", y="n", color=col,
            color_discrete_map=color_map,
            title=title,
            labels={"semana": "Semana Epidemiológica", "n": "Nº Casos", col: col},
            category_orders=_cat,
        )
        _add_pct_hover(_fig, _agg)
        _bar_layout(_fig)
        st.plotly_chart(_fig, use_container_width=True)
        if fonte:
            st.caption(f"Fonte: {fonte}")

    # ---- 1. Casos por Faixa Etária ----------------------------------------
    st.markdown("#### Casos por Faixa Etária")
    _age = df_filt.copy()
    _age["IDADE"] = pd.to_numeric(_age["IDADE"], errors="coerce")
    _age = _age.dropna(subset=["DT_DIGITA", "IDADE"])
    for _lbl, _msk in FAIXA_BINS:
        _age.loc[_msk(_age["IDADE"]), "faixa"] = _lbl
    _age = _age.dropna(subset=["faixa"])
    _wsb(_age, "faixa", FAIXA_COLORS,
         "Casos por Faixa Etária por Semana Epidemiológica",
         col_order=[l for l, _ in FAIXA_BINS], fonte=_FONTE_SG)

    st.markdown("---")

    # ---- 2. Casos por Raça/Cor --------------------------------------------
    st.markdown("#### Casos por Raça/Cor")
    _raca = df_filt.copy()
    _raca["raca_lbl"] = pd.to_numeric(_raca["RACA"], errors="coerce").map(RACA_LABELS)
    _wsb(_raca, "raca_lbl", RACA_COLORS,
         "Casos por Raça/Cor por Semana Epidemiológica",
         col_order=list(RACA_COLORS.keys()), fonte=_FONTE_SG)

    st.markdown("---")

    # ---- 3. Casos por Sexo ------------------------------------------------
    st.markdown("#### Casos por Sexo")
    _sexo = df_filt.copy()
    _sexo["sexo_lbl"] = pd.to_numeric(_sexo["SEXO"], errors="coerce").map({1: "Masculino", 2: "Feminino"})
    _wsb(_sexo, "sexo_lbl", {"Masculino": "#4C78A8", "Feminino": "#E45756"},
         "Casos por Sexo por Semana Epidemiológica",
         col_order=["Masculino", "Feminino"], fonte=_FONTE_SG)

    st.markdown("---")

    # ---- 4. Casos por Distrito Sanitário ----------------------------------
    st.markdown("#### Casos por Distrito Sanitário")
    _bairro_ds = load_bairro_distrito()
    _dist = df_filt.copy()
    _dist["_bairro_up"] = _dist["NOM_BAIRRO"].str.upper().str.strip().fillna("")
    _dist = _dist.merge(_bairro_ds.rename(columns={"bairro": "_bairro_up"}),
                        on="_bairro_up", how="left")
    _dist["distrito"] = _dist["distrito"].fillna("Não mapeado")
    _dist = _dist[_dist["distrito"] != "Não mapeado"]
    _wsb(_dist, "distrito", DISTRITO_COLORS,
         "Casos por Distrito Sanitário por Semana Epidemiológica",
         col_order=[d for d in DISTRITO_ORDER if d != "Não mapeado"], fonte=_FONTE_SG)

    # ---- FIN_FLU — Influenza type ----------------------------------------------
    st.markdown("---")
    st.markdown("#### Tipo de Influenza ")

    FIN_FLU_LABELS = {1: "Influenza A", 2: "Influenza B"}
    FIN_FLU_COLORS = {"Influenza A": "#E45756", "Influenza B": "#4C78A8"}

    if "FIN_FLU" not in df_filt.columns:
        st.warning("Coluna FIN_FLU não encontrada.")
    else:
        _flu = df_filt.copy()
        _flu["FIN_FLU"] = pd.to_numeric(_flu["FIN_FLU"], errors="coerce")
        _flu = _flu.dropna(subset=["DT_DIGITA", "FIN_FLU"])
        _flu["FIN_FLU"] = _flu["FIN_FLU"].astype(int)
        _flu = _flu[_flu["FIN_FLU"].isin(FIN_FLU_LABELS)]
        _flu["FIN_FLU_LABEL"] = _flu["FIN_FLU"].map(FIN_FLU_LABELS)

        if _flu.empty:
            st.info("Sem dados de tipo de influenza para os filtros selecionados.")
        else:
            _yr_f, _wk_f = paho_year_week(_flu["DT_DIGITA"])
            _flu["semana"]      = "SE " + _wk_f.astype(str).str.zfill(2) + "/" + _yr_f.astype(str)
            _flu["semana_sort"] = _yr_f * 100 + _wk_f
            _agg_f = _flu.groupby(["semana", "semana_sort", "FIN_FLU_LABEL"]).size().reset_index(name="n")
            _ord_f = _agg_f[["semana","semana_sort"]].drop_duplicates().sort_values("semana_sort")["semana"].tolist()
            _fig_f = px.bar(
                _agg_f, x="semana", y="n", color="FIN_FLU_LABEL",
                color_discrete_map=FIN_FLU_COLORS,
                title="Tipo de Influenza por Semana Epidemiológica",
                labels={"semana": "Semana Epidemiológica", "n": "Nº Casos", "FIN_FLU_LABEL": "Tipo"},
                category_orders={"semana": _ord_f},
            )
            _add_pct_hover(_fig_f, _agg_f)
            _bar_layout(_fig_f)
            st.plotly_chart(_fig_f, use_container_width=True)
            st.caption("Fonte: BRASIL. Ministério da Saúde. SIVEP-GRIPE. Banco de Dados de Síndrome Gripal. Brasília, 2026.")

    # ---- FIN_SUBT — Influenza subtypes -----------------------------------------
    st.markdown("---")
    st.markdown("#### Subtipo de Influenza A")

    FIN_SUBT_LABELS = {
        1: "Influenza A (H1N1)pdm09",
        4: "Influenza A não subtipado",
        6: "Influenza A (H3N2)",
        7: "Influenza A não subtipável",
        8: "Inconclusivo",
    }
    FIN_SUBT_COLORS = {
        "Influenza A (H1N1)pdm09":   "#E45756",
        "Influenza A (H3N2)":         "#F58518",
        "Influenza A não subtipado":  "#9C9C9C",
        "Influenza A não subtipável": "#72B7B2",
        "Inconclusivo":               "#B279A2",
    }

    if "FIN_SUBT" not in df_filt.columns:
        st.warning("Coluna FIN_SUBT não encontrada.")
    else:
        _sub = df_filt.copy()
        _sub["FIN_SUBT"] = pd.to_numeric(_sub["FIN_SUBT"], errors="coerce")
        _sub = _sub.dropna(subset=["DT_DIGITA", "FIN_SUBT"])
        _sub["FIN_SUBT"] = _sub["FIN_SUBT"].astype(int)
        _sub = _sub[_sub["FIN_SUBT"].isin(FIN_SUBT_LABELS)]
        _sub["FIN_SUBT_LABEL"] = _sub["FIN_SUBT"].map(FIN_SUBT_LABELS)

        if _sub.empty:
            st.info("Sem dados de subtipo para os filtros selecionados.")
        else:
            _yr_s, _wk_s = paho_year_week(_sub["DT_DIGITA"])
            _sub["semana"]      = "SE " + _wk_s.astype(str).str.zfill(2) + "/" + _yr_s.astype(str)
            _sub["semana_sort"] = _yr_s * 100 + _wk_s
            _agg_s = _sub.groupby(["semana", "semana_sort", "FIN_SUBT_LABEL"]).size().reset_index(name="n")
            _ord_s = _agg_s[["semana","semana_sort"]].drop_duplicates().sort_values("semana_sort")["semana"].tolist()
            _fig_s = px.bar(
                _agg_s, x="semana", y="n", color="FIN_SUBT_LABEL",
                color_discrete_map=FIN_SUBT_COLORS,
                title="Subtipo de Influenza por Semana Epidemiológica",
                labels={"semana": "Semana Epidemiológica", "n": "Nº Casos", "FIN_SUBT_LABEL": "Subtipo"},
                category_orders={"semana": _ord_s},
            )
            _add_pct_hover(_fig_s, _agg_s)
            _bar_layout(_fig_s)
            st.plotly_chart(_fig_s, use_container_width=True)
            st.caption("Fonte: BRASIL. Ministério da Saúde. SIVEP-GRIPE. Banco de Dados de Síndrome Gripal. Brasília, 2026.")


# ============================================================
# TAB 2 — Taxas de Positividade
# ============================================================
with tab2:

    # ---- Year slider and unit filter ----------------------------------------
    _t2_cy, _t2_cu = st.columns([2, 2])
    with _t2_cy:
        _t2_year_lo, _t2_year_hi = st.slider(
            "Período (ano)", 2022, 2026, (2022, 2026), step=1, key="sg_test_year",
        )
    with _t2_cu:
        _t2_unit = st.radio(
            "Unidade de saúde", ["Todas", "Unidades Municipais"],
            horizontal=True, key="sg_test_unit",
        )

    _df_t2 = df_all[df_all["DT_DIGITA"].dt.year.between(_t2_year_lo, _t2_year_hi)].copy()
    if _t2_unit == "Unidades Municipais":
        _nm_t2 = _df_t2["NOME_UNIDA"].str.upper().str.strip().fillna("")
        _df_t2 = _df_t2[_nm_t2.apply(lambda x: any(kw in x for kw in _UNIDADES_KW_SG))].copy()
    if _t2_year_hi == 2026:
        _yr_t2b, _wk_t2b = paho_year_week(_df_t2["DT_DIGITA"])
        _df_t2 = _df_t2[~((_yr_t2b == 2026) & (_wk_t2b > 16))].copy()

    def positividade_chart(
        source: pd.DataFrame,
        total_col: str, total_val,
        pos_col: str,   pos_val,
        bar_name: str,  bar_color: str,
        titulo: str,
        group_weeks: int = 1,
    ):
        base = source.dropna(subset=["DT_DIGITA"]).copy()
        base[total_col] = pd.to_numeric(base[total_col], errors="coerce")
        base[pos_col]   = pd.to_numeric(base[pos_col],   errors="coerce")
        base = base[base[total_col] == total_val]

        if base.empty:
            st.info(f"Sem dados para {titulo}.")
            return

        base = base.copy()
        _epi_yr, _epi_wk = paho_year_week(base["DT_DIGITA"])

        if group_weeks == 1:
            base["semana"]      = "SE " + _epi_wk.astype(str).str.zfill(2) + "/" + _epi_yr.astype(str)
            base["semana_sort"] = _epi_yr * 100 + _epi_wk
        else:
            period  = (_epi_wk - 1) // group_weeks
            start_w = period * group_weeks + 1
            end_w   = (period + 1) * group_weeks
            base["semana"]      = ("SE " + start_w.astype(str).str.zfill(2)
                                   + "-" + end_w.astype(str).str.zfill(2)
                                   + "/" + _epi_yr.astype(str))
            base["semana_sort"] = _epi_yr * 100 + period

        base["positivo"] = base[pos_col] == pos_val

        agg = (
            base.groupby(["semana", "semana_sort"])
                .agg(total=("positivo", "count"), positivos=("positivo", "sum"))
                .reset_index()
                .sort_values("semana_sort")
        )
        agg["pct"] = (agg["positivos"] / agg["total"] * 100).round(1)
        semana_order = agg["semana"].tolist()

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=agg["semana"], y=agg["total"],
            name=bar_name, marker_color=bar_color,
            hovertemplate="%{x}<br>Testes: %{y}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=agg["semana"], y=agg["pct"],
            name="% Positivos",
            mode="lines+markers",
            line=dict(color="#E45756", width=2),
            marker=dict(size=5),
            yaxis="y2",
            hovertemplate="%{x}<br>Positividade: %{y:.1f}%<extra></extra>",
        ))
        fig.update_layout(
            title=titulo,
            xaxis=dict(
                categoryorder="array", categoryarray=semana_order,
                tickangle=-90, title="Semana Epidemiológica",
            ),
            yaxis=dict(title="Nº Testes"),
            yaxis2=dict(
                overlaying="y",
                side="right",
                range=[0, 105],
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
        st.plotly_chart(fig, use_container_width=True)

    # ---- (SIVEP-GRIPE) Total (IFI + PCR) ----------------------------------------
    st.markdown("### (SIVEP-GRIPE) Total de Testes e Taxa de Positividade")
    st.caption("Soma de testes IFI e PCR Influenza realizados e taxa de positividade combinada.")

    _sg_base = _df_t2.dropna(subset=["DT_DIGITA"]).copy()

    _tot_rows, _pos_rows = [], []

    if "IFI" in _sg_base.columns and "IFI_RESUL" in _sg_base.columns:
        _ifi = _sg_base.copy()
        _ifi["IFI"]      = pd.to_numeric(_ifi["IFI"],      errors="coerce")
        _ifi["IFI_RESUL"]= pd.to_numeric(_ifi["IFI_RESUL"],errors="coerce")
        _ifi_t = _ifi[_ifi["IFI"] == 1][["DT_DIGITA"]].copy()
        _ifi_p = _ifi[(_ifi["IFI"] == 1) & (_ifi["IFI_RESUL"] == 1)][["DT_DIGITA"]].copy()
        _tot_rows.append(_ifi_t)
        _pos_rows.append(_ifi_p)

    if "PCR_RESUL" in _sg_base.columns and "POS_PCRFLU" in _sg_base.columns:
        _pcr = _sg_base.copy()
        _pcr["PCR_RESUL"] = pd.to_numeric(_pcr["PCR_RESUL"], errors="coerce")
        _pcr["POS_PCRFLU"]= pd.to_numeric(_pcr["POS_PCRFLU"],errors="coerce")
        _pcr_t = _pcr[_pcr["PCR_RESUL"] == 1][["DT_DIGITA"]].copy()
        _pcr_p = _pcr[(_pcr["PCR_RESUL"] == 1) & (_pcr["POS_PCRFLU"] == 1)][["DT_DIGITA"]].copy()
        _tot_rows.append(_pcr_t)
        _pos_rows.append(_pcr_p)

    if not _tot_rows:
        st.info("Sem dados de testes IFI/PCR para o período.")
    else:
        _tall_sg = pd.concat(_tot_rows, ignore_index=True).dropna(subset=["DT_DIGITA"])
        _pall_sg = pd.concat(_pos_rows, ignore_index=True).dropna(subset=["DT_DIGITA"])

        _yr_tt, _wk_tt = paho_year_week(_tall_sg["DT_DIGITA"])
        _tall_sg["semana"]      = "SE " + _wk_tt.astype(str).str.zfill(2) + "/" + _yr_tt.astype(str)
        _tall_sg["semana_sort"] = _yr_tt * 100 + _wk_tt
        _tested_wk_sg = _tall_sg.groupby(["semana", "semana_sort"]).size().reset_index(name="total_tested")

        _yr_tp, _wk_tp = paho_year_week(_pall_sg["DT_DIGITA"])
        _pall_sg["semana"]      = "SE " + _wk_tp.astype(str).str.zfill(2) + "/" + _yr_tp.astype(str)
        _pall_sg["semana_sort"] = _yr_tp * 100 + _wk_tp
        _pos_wk_sg = _pall_sg.groupby(["semana", "semana_sort"]).size().reset_index(name="total_pos")

        _tot_sg = _tested_wk_sg.merge(_pos_wk_sg, on=["semana", "semana_sort"], how="left").fillna(0)
        _tot_sg = _tot_sg.sort_values("semana_sort").reset_index(drop=True)
        _tot_sg["pct_pos"] = (_tot_sg["total_pos"] / _tot_sg["total_tested"] * 100).round(1)

        _pct_max_sg   = _tot_sg["pct_pos"].max()
        _pct_axis_max_sg = max(_pct_max_sg * 1.15, 1)

        _fig_tot_sg = go.Figure()
        _fig_tot_sg.add_trace(go.Bar(
            x=_tot_sg["semana"],
            y=_tot_sg["total_tested"],
            name="Total Testado (IFI + PCR)",
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
            title="(SIVEP-GRIPE) Total de Testes Realizados (IFI + PCR) e Taxa de Positividade",
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
        st.plotly_chart(_fig_tot_sg, use_container_width=True)
        st.caption(f"Fonte: {_FONTE_SG}")

    st.markdown("---")
    st.markdown("### (Sivep-GRIPE) Taxas de Positividade — IFI")
    positividade_chart(
        _df_t2,
        total_col="IFI",      total_val=1,
        pos_col="IFI_RESUL",  pos_val=1,
        bar_name="Testes IFI", bar_color="#4C78A8",
        titulo="(SIVEP-GRIPE) Testes IFI e Taxa de Positividade por Semana Epidemiológica",
    )
    st.caption(f"Fonte: {_FONTE_SG}")

    st.markdown("---")
    st.markdown("### (SIVEP-GRIPE) Taxas de Positividade — PCR Influenza")
    pcr_view = st.radio(
        "Agrupamento", ["Semanal", "4 Semanas"],
        horizontal=True, key="pcr_group",
    )
    positividade_chart(
        _df_t2,
        total_col="PCR_RESUL",  total_val=1,
        pos_col="POS_PCRFLU",   pos_val=1,
        bar_name="Testes PCR",  bar_color="#54A24B",
        titulo="(SIVEP-GRIPE) Testes PCR e Taxa de Positividade para Influenza por Semana Epidemiológica",
        group_weeks=4 if pcr_view == "4 Semanas" else 1,
    )
    st.caption(f"Fonte: {_FONTE_SG}")

    # ------------------------------------------------------------------ eSUS
    st.markdown("---")
    st.markdown("### eSUS-Notifica — Total de Testes e Taxa de Positividade")
    st.caption(
        "Testes por tipo (coluna `tipoteste`) agrupados por semana de notificação. "
        "Positividade = `resultadofinal == 'Positivo'` / (Positivo + Negativo)."
    )

    _esus = load_esus()

    # Filter to notifications made in Recife, apply year slider, cap at SE16/2026
    _esus = _esus[_esus["municipionotificacao"] == "Recife"].copy()
    _esus = _esus[_esus["datanotificacao"].dt.year.between(_t2_year_lo, _t2_year_hi)].copy()
    _yr_e, _wk_e = paho_year_week(_esus["datanotificacao"])
    if _t2_year_hi == 2026:
        _esus = _esus[~((_yr_e == 2026) & (_wk_e > 16))]
    _esus = _esus.dropna(subset=["datanotificacao", "tipoteste"])

    if _esus.empty:
        st.info("Sem dados eSUS para o período.")
    else:
        _yr_e2, _wk_e2 = paho_year_week(_esus["datanotificacao"])
        _esus["semana"]      = "SE " + _wk_e2.astype(str).str.zfill(2) + "/" + _yr_e2.astype(str)
        _esus["semana_sort"] = _yr_e2 * 100 + _wk_e2

        # Stacked bar: total tests by type per week
        _agg_e = (
            _esus.groupby(["semana", "semana_sort", "tipoteste"])
                 .size().reset_index(name="n")
        )
        _ord_e = (
            _agg_e[["semana", "semana_sort"]].drop_duplicates()
            .sort_values("semana_sort")["semana"].tolist()
        )
        _test_types = (
            _agg_e.groupby("tipoteste")["n"].sum()
            .sort_values(ascending=False).index.tolist()
        )

        # Palette — only assign colours for types actually present in the data
        _PALETTE = [
            "#4C78A8", "#E45756", "#F58518", "#72B7B2",
            "#54A24B", "#EECA3B", "#B279A2", "#FF9DA6", "#9C9C9C",
        ]
        ESUS_COLORS = {t: _PALETTE[i % len(_PALETTE)] for i, t in enumerate(_test_types)}

        _fig_e = px.bar(
            _agg_e, x="semana", y="n", color="tipoteste",
            color_discrete_map=ESUS_COLORS,
            title="eSUS-Notifica — Total de Testes por Tipo e Semana Epidemiológica",
            labels={"semana": "Semana Epidemiológica", "n": "Nº Testes", "tipoteste": "Tipo de Teste"},
            category_orders={"semana": _ord_e, "tipoteste": _test_types},
        )

        # Positivity line: Positivo / (Positivo + Negativo) per week
        _pos_wk_e = (
            _esus[_esus["resultadofinal"] == "Positivo"]
            .groupby(["semana", "semana_sort"]).size().reset_index(name="positivos")
        )
        _neg_wk_e = (
            _esus[_esus["resultadofinal"].isin(["Positivo", "Negativo"])]
            .groupby(["semana", "semana_sort"]).size().reset_index(name="com_resultado")
        )
        _rate_e = _neg_wk_e.merge(_pos_wk_e, on=["semana", "semana_sort"], how="left").fillna(0)
        _rate_e = _rate_e.sort_values("semana_sort")
        _rate_e["pct"] = (_rate_e["positivos"] / _rate_e["com_resultado"] * 100).round(1)

        _pct_max_e = _rate_e["pct"].max()
        _pct_axis_max_e = max(_pct_max_e * 1.15, 1)

        _fig_e.add_trace(go.Scatter(
            x=_rate_e["semana"],
            y=_rate_e["pct"],
            name="Positividade (%)",
            mode="lines+markers",
            line=dict(color="#E45756", width=2),
            marker=dict(size=5),
            yaxis="y2",
            customdata=list(zip(
                _rate_e["positivos"].astype(int),
                _rate_e["com_resultado"].astype(int),
            )),
            hovertemplate=(
                "%{x}<br>Positividade: %{y:.1f}%"
                "<br>(%{customdata[0]} positivos de %{customdata[1]} com resultado)"
                "<extra></extra>"
            ),
        ))

        _fig_e.update_layout(
            barmode="stack",
            xaxis=dict(
                title="Semana Epidemiológica",
                tickangle=-90,
                categoryorder="array",
                categoryarray=_ord_e,
            ),
            yaxis=dict(title="Nº Testes", rangemode="tozero"),
            yaxis2=dict(
                overlaying="y",
                side="right",
                range=[0, _pct_axis_max_e],
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
        st.plotly_chart(_fig_e, use_container_width=True)
        st.caption(f"Fonte: {_FONTE_ESUS}")

# ============================================================
# TAB 3 — Nowcasting + Forecasting
# ============================================================
with tab3:
    st.markdown("### Nowcasting + Forecasting — SG (R / INLA)")
    st.caption(
        "Modelo INLA estruturado por idade (`bins_age = '10 years'`), "
        "`wdw = 230` semanas, `K = 4` semanas de forecast."
    )
    embed_html_plot("nowcasting_sg.html", height=750)
    st.caption(f"Fonte: {_FONTE_SG}")

    st.markdown("---")
    st.markdown("### Média Móvel — Semanas Epidemiológicas 2026")
    st.caption("Média móvel de 4 semanas sobre casos semanais por semana de início dos sintomas (`DT_PRISINT`).")
    render_ma_chart(df_all, onset_col="DT_PRISINT", titulo="Média Móvel 4 sem. — SG (ILI)", fonte=_FONTE_SG)

    st.markdown("---")
    st.markdown("###Semanas previstas")
    _tbl = load_nowcast_table("nowcasting_sg.html")
    if _tbl is not None:
        _fc = _tbl[_tbl["Tipo"] == "Forecast"].copy()
        _fc["Data"] = _fc["Data"].dt.strftime("%d/%m/%Y")
        st.dataframe(_fc.drop(columns=["Tipo"]), use_container_width=True, hide_index=True)
    else:
        st.info("Dados de nowcasting não disponíveis.")

# ============================================================
# TAB 4 — Progressão SG → SRAG
# ============================================================
with tab4:
    st.markdown("### Progressão para SRAG — Recife")

    _prog = load_sg_srag_linked()

    if _prog.empty:
        st.info("Arquivo de progressão não encontrado (`data/sg_srag_linked.parquet`).")
    else:
        # ---- Derived fields ------------------------------------------------
        _prog = _prog.copy()
        _prog["_sexo"]  = pd.to_numeric(_prog["sg_SEXO"], errors="coerce").map({1: "Masculino", 2: "Feminino"})
        _prog["_idade"] = pd.to_numeric(_prog["sg_IDADE"], errors="coerce")

        # ---- KPIs ----------------------------------------------------------
        _n_fem   = (_prog["_sexo"] == "Feminino").sum()
        _n_masc  = (_prog["_sexo"] == "Masculino").sum()
        _avg_age = _prog["_idade"].mean()
        _n_obito = (_prog["srag_evolucao_label"] == "Obito").sum()

        render_kpis([
            ("Total de progressões", fmt_int(len(_prog))),
            ("Feminino",             fmt_int(_n_fem)),
            ("Masculino",            fmt_int(_n_masc)),
            ("Idade média (SG)",     f"{_avg_age:.1f} anos"),
            ("Óbitos (SRAG)",        fmt_int(_n_obito)),
        ])

        st.markdown("---")

        # ---- Charts row: Sexo | Faixa Etária | Bairro | Desfecho -----------
        _c1, _c2, _c3, _c4 = st.columns(4)

        with _c1:
            _sx = _prog["_sexo"].value_counts().reset_index()
            _sx.columns = ["sexo", "n"]
            _sx = _sx[_sx["sexo"].isin(["Masculino", "Feminino"])]
            _fig_sx = px.pie(
                _sx, names="sexo", values="n",
                title="Por Sexo",
                color="sexo",
                color_discrete_map={"Feminino": "#E45756", "Masculino": "#4C78A8"},
                hole=0.45,
            )
            _fig_sx.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=320)
            st.plotly_chart(_fig_sx, use_container_width=True)
            st.caption(f"Fonte: {_FONTE_PROG}")

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
            for _lbl, _msk in _PROG_FAIXA_BINS:
                _age_p.loc[_msk(_age_p["_idade"]), "faixa"] = _lbl
            _age_p = _age_p.dropna(subset=["faixa"])
            _age_cnt = (
                _age_p["faixa"].value_counts()
                .reindex(_PROG_FAIXA_ORDER).fillna(0).reset_index()
            )
            _age_cnt.columns = ["faixa", "n"]
            _fig_age_p = px.bar(
                _age_cnt, x="faixa", y="n",
                title="Por Faixa Etária (SG)",
                labels={"faixa": "Faixa Etária", "n": "Casos"},
                color_discrete_sequence=["#72B7B2"],
                category_orders={"faixa": _PROG_FAIXA_ORDER},
            )
            _fig_age_p.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=320)
            st.plotly_chart(_fig_age_p, use_container_width=True)
            st.caption(f"Fonte: {_FONTE_PROG}")

        with _c3:
            _bairro_p = (
                _prog["sg_NOM_BAIRRO"].str.title()
                .value_counts().head(10).reset_index()
            )
            _bairro_p.columns = ["bairro", "n"]
            _fig_bairro_p = px.bar(
                _bairro_p, x="n", y="bairro",
                orientation="h",
                title="Por Bairro (top 10)",
                labels={"bairro": "", "n": "Casos"},
                color_discrete_sequence=["#F58518"],
            )
            _fig_bairro_p.update_layout(
                yaxis=dict(autorange="reversed"),
                margin=dict(l=10, r=10, t=50, b=10),
                height=320,
            )
            st.plotly_chart(_fig_bairro_p, use_container_width=True)
            st.caption(f"Fonte: {_FONTE_PROG}")

        with _c4:
            _ev = _prog["srag_evolucao_label"].fillna("Sem registro").value_counts().reset_index()
            _ev.columns = ["evolucao", "n"]
            _fig_ev = px.pie(
                _ev, names="evolucao", values="n",
                title="Desfecho (SRAG)",
                hole=0.45,
                color_discrete_map={
                    "Cura": "#54A24B", "Obito": "#E45756",
                    "Obito por outras causas": "#F58518",
                    "Ignorado": "#9C9C9C", "Sem registro": "#CCCCCC",
                },
            )
            _fig_ev.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=320)
            st.plotly_chart(_fig_ev, use_container_width=True)
            st.caption(f"Fonte: {_FONTE_PROG}")

        st.markdown("---")

        # ---- Gap distribution bar chart ------------------------------------
        st.markdown("#### Intervalo entre notificação SG e SRAG")
        _gap_order = ["0-7d", "8-14d", "15-30d", "31-60d", "61-90d", "91-180d", "181-365d", ">365d"]
        _gap_cnt = (
            _prog["gap_faixa"].value_counts()
            .reindex(_gap_order).fillna(0).reset_index()
        )
        _gap_cnt.columns = ["intervalo", "n"]
        _fig_gap = px.bar(
            _gap_cnt, x="intervalo", y="n",
            title="Dias entre notificação SG e SRAG",
            labels={"intervalo": "Intervalo", "n": "Casos"},
            color_discrete_sequence=["#B279A2"],
            category_orders={"intervalo": _gap_order},
        )
        _fig_gap.update_layout(
            margin=dict(l=20, r=20, t=50, b=60),
            height=340,
            plot_bgcolor="white",
        )
        st.plotly_chart(_fig_gap, use_container_width=True)
        st.caption(f"Fonte: {_FONTE_PROG}")

        st.markdown("---")

        # ---- Onset and notification gap comparison --------------------------
        st.markdown("#### Intervalos de tempo — sintomas e notificação")
        st.caption(
            "**Sintomas SG → Sintomas SRAG**: dias entre o início dos sintomas do episódio SG e o início dos sintomas do episódio SRAG. "
            "**Notificação SG → Sintomas SRAG**: dias entre a notificação do caso SG e o início dos sintomas do SRAG. "
            "Apenas intervalos positivos são exibidos (agravamento de SG para SRAG)."
        )

        _g_onset  = pd.to_numeric(_prog["gap_sintomas_dias"], errors="coerce").dropna()
        _g_notif  = (
            pd.to_datetime(_prog["srag_DT_SIN_PRI"], errors="coerce") -
            pd.to_datetime(_prog["sg_DT_DIGITA"],    errors="coerce")
        ).dt.days.dropna()

        # Keep only positive gaps (SG precedes SRAG = severity increase)
        _g_onset = _g_onset[_g_onset >= 0]
        _g_notif = _g_notif[_g_notif >= 0]

        _sym_bins   = [0, 7, 14, 30, 60, 90, 180, 365, 9999]
        _sym_labels = ["0-7d", "8-14d", "15-30d", "31-60d", "61-90d", "91-180d", "181-365d", ">365d"]

        def _bin_series(s):
            return pd.cut(s, bins=_sym_bins, labels=_sym_labels, right=True, include_lowest=True)

        _df_gaps = pd.DataFrame({
            "Sintomas SG → Sintomas SRAG":   _bin_series(_g_onset).value_counts().reindex(_sym_labels).fillna(0),
            "Notificação SG → Sintomas SRAG": _bin_series(_g_notif).value_counts().reindex(_sym_labels).fillna(0),
        }).reset_index().rename(columns={"index": "intervalo"})
        _df_gaps_long = _df_gaps.melt(id_vars="intervalo", var_name="Série", value_name="n")

        _fig_gaps2 = px.bar(
            _df_gaps_long, x="intervalo", y="n", color="Série", barmode="group",
            title="Distribuição dos Intervalos Temporais",
            labels={"intervalo": "Intervalo (dias)", "n": "Casos", "Série": ""},
            color_discrete_map={
                "Sintomas SG → Sintomas SRAG":    "#4C78A8",
                "Notificação SG → Sintomas SRAG": "#F58518",
            },
            category_orders={"intervalo": _sym_labels},
        )
        _fig_gaps2.update_layout(
            barmode="group",
            xaxis_tickangle=-45,
            legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center"),
            margin=dict(l=20, r=20, t=80, b=120),
            height=440,
            plot_bgcolor="white",
        )
        st.plotly_chart(_fig_gaps2, use_container_width=True)
        st.caption(f"Fonte: {_FONTE_PROG}")

        # ---- Characteristics profile table ---------------------------------
        st.markdown("#### Perfil dos casos com progressão")

        _prog_faixa = _prog.copy()
        for _lbl, _msk in _PROG_FAIXA_BINS:
            _prog_faixa.loc[_msk(_prog_faixa["_idade"]), "_faixa"] = _lbl

        def _profile_block(series, label):
            vc = series.value_counts(dropna=False)
            pct = (vc / len(_prog) * 100).round(1)
            df = pd.DataFrame({"Categoria": label, "Valor": vc.index.astype(str),
                                "n": vc.values, "%": pct.values})
            return df

        _profile = pd.concat([
            _profile_block(_prog["_sexo"].fillna("Ignorado"),            "Sexo"),
            _profile_block(_prog_faixa["_faixa"].fillna("Sem dado"),     "Faixa etária"),
            _profile_block(_prog["srag_classi_label"].fillna("Sem dado"),"Classificação Final"),
        ], ignore_index=True)

        _profile = _profile.sort_values(["Categoria", "n"], ascending=[True, False]).reset_index(drop=True)
        st.dataframe(_profile, use_container_width=True, hide_index=True)

        st.markdown("---")

        # ---- Detailed table ------------------------------------------------
        st.markdown("#### Tabela de Casos")
        _tbl_p = _prog[[c for c in [
            "sg_DT_DIGITA", "srag_DT_DIGITA", "gap_dias",
            "_sexo", "_idade", "sg_NOM_BAIRRO",
            "sg_classi_label", "srag_classi_label",
            "srag_evolucao_label", "srag_NM_UN_INTE",
        ] if c in _prog.columns]].copy()
        _tbl_p = _tbl_p.rename(columns={
            "sg_DT_DIGITA":        "Data SG",
            "srag_DT_DIGITA":      "Data SRAG",
            "gap_dias":            "Intervalo (dias)",
            "_sexo":               "Sexo",
            "_idade":              "Idade (SG)",
            "sg_NOM_BAIRRO":       "Bairro",
            "sg_classi_label":     "Classificação SG",
            "srag_classi_label":   "Classificação SRAG",
            "srag_evolucao_label": "Desfecho SRAG",
            "srag_NM_UN_INTE":     "Hospital (SRAG)",
        })
        for _dc in ["Data SG", "Data SRAG"]:
            if _dc in _tbl_p.columns:
                _tbl_p[_dc] = pd.to_datetime(_tbl_p[_dc], errors="coerce").dt.strftime("%d/%m/%Y")
        if "Bairro" in _tbl_p.columns:
            _tbl_p["Bairro"] = _tbl_p["Bairro"].str.title()
        if "Hospital (SRAG)" in _tbl_p.columns:
            _tbl_p["Hospital (SRAG)"] = _tbl_p["Hospital (SRAG)"].str.title()
        st.dataframe(_tbl_p, use_container_width=True, hide_index=True)
