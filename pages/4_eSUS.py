"""e-SUS Notifica (COVID-19) page.

Espelha a estrutura das páginas de SG e SRAG, mas sobre o banco eSUS-Notifica.

Eixo temporal = data dos primeiros sintomas, preenchida com a data de
notificação quando vazia ("primeiros sintomas = notificação quando vazio"),
resolvida no loader ``load_esus_page``. O extrato atualmente disponível só traz
data, tipo de teste, resultado, bairro e município; as visões de perfil
(sexo / faixa etária / raça) acendem automaticamente quando uma fonte mais rica
(com idade, sexo, etc.) for colocada em ``data/eSUS_all.parquet``.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.helpers import (
    load_esus_page, render_kpis, fmt_int, paho_year_week,
    period_compare_label, period_compare_se_label, format_kpi_delta,
    render_epiweek_slider, filter_epiweek, add_ma_overlay,
    render_ma_chart, render_seasonality_hist, embed_html_plot,
    render_forecast_table, PLOTS_DIR, ESUS_EPIWEEK_MIN,
)

st.set_page_config(page_title="Covid-19", page_icon="🧬", layout="wide")
st.title("🧬 Covid-19 — e-SUS Notifica")
st.caption(
    "*Notificações de Síndrome Gripal no eSUS-Notifica (COVID-19). Eixo temporal "
    "pela data dos primeiros sintomas, preenchida pela data de notificação quando "
    "ausente. Município de notificação = Recife.*"
)

_FONTE_ESUS = "SESAU/SEVS/GGAM/GEVEPI/DDT/ESUS-NOTIFICA"

# --- Load data — município de notificação = Recife --------------------------
df_raw = load_esus_page()
_sintoma_src = df_raw.attrs.get("sintoma_source", "data de notificação")
if "municipionotificacao" in df_raw.columns:
    df_all = df_raw[df_raw["municipionotificacao"] == "Recife"].copy()
else:
    df_all = df_raw.copy()

# --- Detect optional columns (present only in a richer source) --------------
_cols = {c.lower(): c for c in df_all.columns}


def _col(*cands):
    return next((_cols[c] for c in cands if c in _cols), None)


_SEXO_COL  = _col("sexo", "cs_sexo")
_IDADE_COL = _col("idade", "nu_idade_n", "idadecaso")
_RACA_COL  = _col("racacor", "raca", "cs_raca", "raca_cor")
_BAIRRO_COL = _col("bairro")
_TIPOTESTE_COL = _col("tipoteste")
_RESULT_COL = _col("resultadofinal", "resultado", "resultadoteste")

if st.session_state.pop("esus_goto_nowcasting", False):
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

# Resultado labels / colors for the weekly stacked bars.
_RES_COLORS = {
    "Positivo":   "#E45756",
    "Negativo":   "#4C78A8",
    "Inconclusivo": "#EECA3B",
    "Sem resultado": "#9C9C9C",
}
_RES_ORDER = ["Positivo", "Negativo", "Inconclusivo", "Sem resultado"]

_FAIXA_BINS = [
    ("0–4",   lambda a: (a >= 0)  & (a <= 4)),
    ("5–9",   lambda a: (a >= 5)  & (a <= 9)),
    ("10–19", lambda a: (a >= 10) & (a <= 19)),
    ("20–29", lambda a: (a >= 20) & (a <= 29)),
    ("30–39", lambda a: (a >= 30) & (a <= 39)),
    ("40–49", lambda a: (a >= 40) & (a <= 49)),
    ("50–59", lambda a: (a >= 50) & (a <= 59)),
    ("60+",   lambda a: a >= 60),
]


def _norm_result(s: pd.Series) -> pd.Series:
    """Normalise resultadofinal into the four display buckets."""
    r = s.astype(str).str.strip()
    r = r.replace({
        "Inconclusivo ou indeterminado": "Inconclusivo",
        "Null": "Sem resultado", "nan": "Sem resultado",
        "None": "Sem resultado", "": "Sem resultado", "<NA>": "Sem resultado",
    })
    return r.where(r.isin(_RES_ORDER), "Sem resultado")


def _add_pct_hover(fig, agg, color_col, unit="notificações"):
    totals = agg.groupby("semana")["n"].transform("sum")
    a = agg.copy()
    a["pct"] = (a["n"] / totals * 100).round(1)
    for trace in fig.data:
        rows = a[a[color_col] == trace.name].set_index("semana")
        pct_vals = [rows.loc[x, "pct"] if x in rows.index else float("nan") for x in trace.x]
        trace.customdata = [[p] for p in pct_vals]
        trace.hovertemplate = (
            "%{x}<br>" + f"{trace.name}: " + f"%{{y}} {unit} (%{{customdata[0]:.1f}}%)" + "<extra></extra>"
        )


def _bar_layout(fig):
    fig.update_layout(
        barmode="stack", xaxis_tickangle=-90,
        legend=dict(orientation="h", y=-0.28, x=0.5, xanchor="center"),
        margin=dict(l=20, r=20, t=50, b=110), height=580,
    )


tab1, tab2, tab3 = st.tabs(["📊 Descritivo", "🧪 Testes", "📈 Nowcasting + Forecasting"])

# ============================================================
# TAB 1 — Descritivo
# ============================================================
with tab1:
    _se_lo, _se_hi = render_epiweek_slider("esus_desc_se", start=ESUS_EPIWEEK_MIN)

    df_filt = filter_epiweek(df_all, "DT_SINTOMAS", _se_lo, _se_hi)

    # Previous period = same SE window shifted back one year
    _se_lo_prev = (_se_lo[0] - 1, _se_lo[1])
    _se_hi_prev = (_se_hi[0] - 1, _se_hi[1])
    df_prev = filter_epiweek(df_all, "DT_SINTOMAS", _se_lo_prev, _se_hi_prev)

    # ---- KPIs --------------------------------------------------------------
    total_notif = len(df_filt)
    if _RESULT_COL:
        _res = _norm_result(df_filt[_RESULT_COL])
        _res_prev = _norm_result(df_prev[_RESULT_COL])
        total_pos = int((_res == "Positivo").sum())
        total_pos_prev = int((_res_prev == "Positivo").sum())
        _tested = int(_res.isin(["Positivo", "Negativo", "Inconclusivo"]).sum())
        pct_pos = (total_pos / _tested * 100) if _tested else 0.0
    else:
        total_pos = total_pos_prev = _tested = 0
        pct_pos = 0.0

    _cmp = period_compare_label(_se_lo, _se_hi)
    _cmp_se = period_compare_se_label(_se_lo, _se_hi)
    delta_notif = format_kpi_delta(total_notif, len(df_prev), _cmp)
    delta_pos   = format_kpi_delta(total_pos, total_pos_prev, _cmp)

    render_kpis([
        ("Notificações", fmt_int(total_notif), delta_notif, _cmp_se),
        ("Testes positivos", fmt_int(total_pos), delta_pos, _cmp_se),
        ("Positividade", f"{pct_pos:.1f}%"),
    ])
    st.caption(f"Data analítica: {_sintoma_src}.")

    st.markdown("---")

    # ---- Perfil dos casos (sexo / faixa etária / bairro) -------------------
    st.markdown("#### Perfil dos Casos")
    _has_demo = bool(_SEXO_COL or _IDADE_COL)
    _pc1, _pc2, _pc3 = st.columns(3)

    with _pc1:
        if _SEXO_COL:
            _sx = df_filt[_SEXO_COL].astype(str).str.strip().str.upper()
            _sx = _sx.replace({"M": "Masculino", "F": "Feminino",
                               "MASCULINO": "Masculino", "FEMININO": "Feminino"})
            _sx = _sx[_sx.isin(["Masculino", "Feminino"])]
            _sxc = _sx.value_counts().reset_index()
            _sxc.columns = ["sexo", "n"]
            if _sxc.empty:
                st.info("Sem dados de sexo.")
            else:
                _fig = px.pie(_sxc, names="sexo", values="n", title="Por Sexo", hole=0.45,
                              color="sexo",
                              color_discrete_map={"Feminino": "#E45756", "Masculino": "#4C78A8"})
                _fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=320)
                st.plotly_chart(_fig, width='stretch')
        else:
            st.info("Sexo não disponível no extrato atual.")

    with _pc2:
        if _IDADE_COL:
            _ag = df_filt.copy()
            _ag[_IDADE_COL] = pd.to_numeric(_ag[_IDADE_COL], errors="coerce")
            _ag = _ag.dropna(subset=[_IDADE_COL])
            _ag["faixa"] = pd.NA  # ensure column exists (empty-frame safe)
            for _lbl, _msk in _FAIXA_BINS:
                _ag.loc[_msk(_ag[_IDADE_COL]), "faixa"] = _lbl
            _ag = _ag.dropna(subset=["faixa"])
            _order = [l for l, _ in _FAIXA_BINS]
            _agc = _ag["faixa"].value_counts().reindex(_order).fillna(0).reset_index()
            _agc.columns = ["faixa", "n"]
            if _agc["n"].sum() == 0:
                st.info("Sem dados de faixa etária.")
            else:
                _fig = px.bar(_agc, x="faixa", y="n", title="Por Faixa Etária",
                              labels={"faixa": "Faixa Etária", "n": "Notificações"},
                              color_discrete_sequence=["#72B7B2"],
                              category_orders={"faixa": _order})
                _fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=320)
                st.plotly_chart(_fig, width='stretch')
        else:
            st.info("Faixa etária não disponível no extrato atual.")

    with _pc3:
        if _BAIRRO_COL:
            _bc = df_filt[_BAIRRO_COL].astype(str).str.title().value_counts().head(15).reset_index()
            _bc.columns = ["bairro", "n"]
            _bc = _bc[~_bc["bairro"].str.upper().isin(["", "SN", "NAN", "NONE"])]
            if _bc.empty:
                st.info("Sem dados de bairro.")
            else:
                st.markdown("**Por Bairro (top 15)**")
                _fig = px.bar(_bc, x="n", y="bairro", orientation="h",
                              labels={"bairro": "", "n": "Notificações"},
                              color_discrete_sequence=["#F58518"])
                _fig.update_layout(yaxis=dict(autorange="reversed"),
                                   margin=dict(l=10, r=10, t=10, b=10),
                                   height=max(280, len(_bc) * 24))
                with st.container(height=320, border=False):
                    st.plotly_chart(_fig, width='stretch')
        else:
            st.info("Bairro não disponível.")

    if not _has_demo:
        st.caption(
            "ℹ️ Sexo e faixa etária não estão no extrato atual do eSUS. "
            "Coloque uma fonte com `idade`/`sexo` em `data/eSUS_all.parquet` "
            "para que estas visões sejam preenchidas automaticamente."
        )
    st.caption(f"Fonte: {_FONTE_ESUS}")

    # ---- Total de notificações por SE (empilhado por resultado) ------------
    st.markdown("---")
    st.markdown("#### Total de Notificações por Semana Epidemiológica")

    if _RESULT_COL:
        _w = df_filt.dropna(subset=["DT_SINTOMAS"]).copy()
        _w["resultado"] = _norm_result(_w[_RESULT_COL])
        _yr, _wk = paho_year_week(_w["DT_SINTOMAS"])
        _w["semana"]      = "SE " + _wk.astype(str).str.zfill(2) + "/" + _yr.astype(str)
        _w["semana_sort"] = _yr * 100 + _wk
        _agg = _w.groupby(["semana", "semana_sort", "resultado"]).size().reset_index(name="n")
        if _agg.empty:
            st.info("Sem dados para o período selecionado.")
        else:
            _ord = _agg[["semana", "semana_sort"]].drop_duplicates().sort_values("semana_sort")["semana"].tolist()
            _present = [r for r in _RES_ORDER if r in _agg["resultado"].unique()]
            _fig = px.bar(
                _agg, x="semana", y="n", color="resultado",
                color_discrete_map=_RES_COLORS,
                title="Notificações por Semana Epidemiológica (por resultado)",
                labels={"semana": "Semana Epidemiológica", "n": "Nº Notificações", "resultado": "Resultado"},
                category_orders={"semana": _ord, "resultado": _present},
            )
            _add_pct_hover(_fig, _agg, "resultado")
            _bar_layout(_fig)
            add_ma_overlay(_fig, _agg)
            st.plotly_chart(_fig, width='stretch')
    else:
        st.info("Coluna de resultado não encontrada.")
    st.caption(f"Fonte: {_FONTE_ESUS}")

# ============================================================
# TAB 2 — Testes
# ============================================================
with tab2:
    _t2_se_lo, _t2_se_hi = render_epiweek_slider("esus_test_se", start=ESUS_EPIWEEK_MIN)
    _df_t2 = filter_epiweek(df_all, "DT_SINTOMAS", _t2_se_lo, _t2_se_hi)

    st.markdown("### Total de Testes e Taxa de Positividade")
    st.caption("Testes com resultado conclusivo e taxa de positividade por semana epidemiológica.")

    if not _RESULT_COL:
        st.info("Coluna de resultado não encontrada.")
    else:
        _base = _df_t2.dropna(subset=["DT_SINTOMAS"]).copy()
        _base["resultado"] = _norm_result(_base[_RESULT_COL])
        _base = _base[_base["resultado"].isin(["Positivo", "Negativo", "Inconclusivo"])]
        if _base.empty:
            st.info("Sem testes conclusivos no período.")
        else:
            _yr, _wk = paho_year_week(_base["DT_SINTOMAS"])
            _base["semana"]      = "SE " + _wk.astype(str).str.zfill(2) + "/" + _yr.astype(str)
            _base["semana_sort"] = _yr * 100 + _wk
            _base["positivo"] = _base["resultado"] == "Positivo"
            _agg = (
                _base.groupby(["semana", "semana_sort"])
                .agg(total=("positivo", "count"), positivos=("positivo", "sum"))
                .reset_index().sort_values("semana_sort")
            )
            _agg["pct"] = (_agg["positivos"] / _agg["total"] * 100).round(1)
            _pct_axis_max = max(_agg["pct"].max() * 1.15, 1)

            _fig = go.Figure()
            _fig.add_trace(go.Bar(
                x=_agg["semana"], y=_agg["total"],
                name="Total Testado", marker_color="#72B7B2", yaxis="y1",
                hovertemplate="%{x}<br>Total testado: %{y}<extra></extra>",
            ))
            _fig.add_trace(go.Scatter(
                x=_agg["semana"], y=_agg["pct"],
                name="Positividade (%)", mode="lines+markers",
                line=dict(color="#E45756", width=2), marker=dict(size=5), yaxis="y2",
                customdata=list(zip(_agg["positivos"].astype(int), _agg["total"].astype(int))),
                hovertemplate=("%{x}<br>Positividade: %{y:.1f}%"
                               "<br>(%{customdata[0]} positivos de %{customdata[1]} testados)<extra></extra>"),
            ))
            _fig.update_layout(
                title="Total de Testes Realizados e Taxa de Positividade",
                xaxis=dict(title="Semana Epidemiológica", tickangle=-90,
                           categoryorder="array", categoryarray=_agg["semana"].tolist()),
                yaxis=dict(title="Total de Testes Realizados", rangemode="tozero"),
                yaxis2=dict(overlaying="y", side="right", range=[0, _pct_axis_max],
                            showticklabels=False, showgrid=False, zeroline=False, title=""),
                legend=dict(orientation="h", y=-0.28, x=0.5, xanchor="center"),
                margin=dict(l=20, r=60, t=50, b=110), height=580, plot_bgcolor="white",
            )
            st.plotly_chart(_fig, width='stretch')
    st.caption(f"Fonte: {_FONTE_ESUS}")

    # ---- Positividade por tipo de teste ------------------------------------
    st.markdown("---")
    st.markdown("### Positividade por Tipo de Teste")
    if not (_TIPOTESTE_COL and _RESULT_COL):
        st.info("Tipo de teste ou resultado não encontrado.")
    else:
        _tt = _df_t2.copy()
        _tt["tipo"] = _tt[_TIPOTESTE_COL].astype(str).str.strip()
        _tt = _tt[~_tt["tipo"].isin(["", "nan", "None", "<NA>"])]
        _tt["resultado"] = _norm_result(_tt[_RESULT_COL])
        _tt = _tt[_tt["resultado"].isin(["Positivo", "Negativo", "Inconclusivo"])]
        if _tt.empty:
            st.info("Sem testes conclusivos no período.")
        else:
            _g = (
                _tt.assign(positivo=_tt["resultado"] == "Positivo")
                .groupby("tipo")
                .agg(total=("positivo", "count"), positivos=("positivo", "sum"))
                .reset_index()
            )
            _g["pct"] = (_g["positivos"] / _g["total"] * 100).round(1)
            _g = _g.sort_values("total", ascending=True)
            _fig = go.Figure()
            _fig.add_trace(go.Bar(
                x=_g["total"], y=_g["tipo"], orientation="h",
                name="Total testado", marker_color="#72B7B2",
                customdata=list(zip(_g["positivos"].astype(int), _g["pct"])),
                hovertemplate="%{y}<br>Testados: %{x}<br>Positivos: %{customdata[0]} (%{customdata[1]:.1f}%)<extra></extra>",
            ))
            _fig.update_layout(
                title="Total de Testes por Tipo (hover mostra positividade)",
                xaxis=dict(title="Nº Testes"), yaxis=dict(title=""),
                margin=dict(l=10, r=20, t=50, b=40), height=max(360, len(_g) * 38),
                plot_bgcolor="white",
            )
            st.plotly_chart(_fig, width='stretch')
    st.caption(f"Fonte: {_FONTE_ESUS}")

# ============================================================
# TAB 3 — Nowcasting + Forecasting
# ============================================================
with tab3:
    st.markdown("### Nowcasting + Forecasting — e-SUS (COVID-19)")
    _nowcast_html = PLOTS_DIR / "nowcasting_esus.html"
    if _nowcast_html.exists():
        st.caption(
            "Modelo INLA binomial negativo usando as variáveis: idade, atraso de notificação, casos por semana. "
            "Previsão de forecasting para as próximas 4 semanas depois da última data disponível."
        )
        embed_html_plot("nowcasting_esus.html", height=750, fix_legend=True)
        st.caption(f"Fonte: {_FONTE_ESUS}")
        st.markdown("---")
        st.markdown("### Semanas previstas")
        render_forecast_table("nowcasting_esus.html")
        st.caption(f"Fonte: {_FONTE_ESUS}")
    else:
        st.info(
            "Gráfico de nowcasting do eSUS ainda não disponível "
            "(`plots/nowcasting_esus.html`). As demais visões abaixo já usam "
            "todos os dados disponíveis."
        )

    st.markdown("---")
    st.markdown("### Média Móvel — Semanas Epidemiológicas 2026")
    st.caption("Média móvel de 4 semanas sobre notificações semanais por data dos primeiros sintomas.")
    render_ma_chart(df_all, onset_col="DT_SINTOMAS", titulo="Média Móvel 4 sem. — eSUS (COVID-19)")
    st.caption(f"Fonte: {_FONTE_ESUS}")

    st.markdown("---")
    st.markdown("### Sazonalidade — Média Histórica por Semana Epidemiológica")
    render_seasonality_hist(df_all, onset_col="DT_SINTOMAS",
                            value_label="Notificações",
                            titulo="Sazonalidade — eSUS (média por SE, todos os anos)")
    st.caption(f"Fonte: {_FONTE_ESUS}")
