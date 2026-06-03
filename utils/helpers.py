"""Shared helpers for the SG/SRAG dashboard."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

# --- PAHO / Brazilian epi-week (Sunday-start) ----------------------------
def paho_year_week(dates: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Return (epi_year, epi_week) using the PAHO/MMWR Sunday-start system."""
    dates = pd.to_datetime(dates)
    dow   = dates.dt.weekday                              # Mon=0 … Sun=6
    sun   = (dates - pd.to_timedelta((dow + 1) % 7, unit="D")).dt.normalize()

    cal_years = set(sun.dt.year.unique())
    cal_years |= {y - 1 for y in cal_years} | {y + 1 for y in cal_years}
    w1 = {}
    for y in cal_years:
        j4 = pd.Timestamp(y, 1, 4)
        w1[y] = j4 - pd.Timedelta(days=(j4.weekday() + 1) % 7)

    epiyear = sun.dt.year.copy()
    for _ in range(2):      # ≤2 passes handle all year-boundary cases
        w1_curr = epiyear.map(w1)
        w1_next = (epiyear + 1).map(w1)
        epiyear = epiyear.where(sun >= w1_curr, epiyear - 1)
        epiyear = epiyear.where(sun < w1_next,  epiyear + 1)

    epiweek = ((sun - epiyear.map(w1)).dt.days // 7 + 1).astype(int)
    return epiyear.astype(int), epiweek


# --- Paths ---------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
PLOTS_DIR = ROOT / "plots"

# --- CLASSI_FIN labels & colors -----------------------------------------
CLASSI_FIN_LABELS = {
    1: "SG por influenza",
    2: "SG por outro vírus respiratório",
    3: "SG por outro agente etiológico",
    4: "SG não especificado",
    5: "SG por covid-19",
}

CLASSI_FIN_COLORS = {
    "SG por influenza":                "#E45756",
    "SG por outro vírus respiratório": "#F58518",
    "SG por outro agente etiológico":  "#54A24B",
    "SG não especificado":             "#9C9C9C",
    "SG por covid-19":                 "#4C78A8",
}


# --- Loaders -------------------------------------------------------------
@st.cache_data(show_spinner="Carregando SG…")
def load_sg() -> pd.DataFrame:
    path = DATA_DIR / "sg_main.parquet"
    if not path.exists():
        st.error(f"Arquivo não encontrado: {path}")
        st.stop()
    df = pd.read_parquet(path)
    for c in ("DT_DIGITA", "DT_PRISINT", "DT_NASC", "DT_VACINA", "DT_ANTIVIR",
              "DT_COLETA", "IFI_DATA", "PCR_DATA", "DT_ENCERRA"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


@st.cache_data(show_spinner="Carregando SRAG…")
def load_srag() -> pd.DataFrame:
    path = DATA_DIR / "srag_main.parquet"
    if not path.exists():
        st.error(f"Arquivo não encontrado: {path}")
        st.stop()
    df = pd.read_parquet(path)
    for c in ("DT_DIGITA", "DT_SIN_PRI"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


@st.cache_data(show_spinner="Carregando eSUS-Notifica…")
def load_esus() -> pd.DataFrame:
    path = DATA_DIR / "eSUS_all.parquet"
    if not path.exists():
        st.error(f"Arquivo não encontrado: {path}")
        st.stop()
    df = pd.read_parquet(path, columns=["datanotificacao", "tipoteste", "resultadofinal", "municipionotificacao"])
    df["datanotificacao"] = pd.to_datetime(df["datanotificacao"], errors="coerce")
    # Normalise em-dash vs hyphen in test type names
    df["tipoteste"] = df["tipoteste"].str.replace("–", "-", regex=False)
    return df


@st.cache_data(show_spinner="Carregando óbitos eSUS…")
def load_esus_obitos() -> pd.DataFrame:
    path = DATA_DIR / "eSUS_all.parquet"
    if not path.exists():
        st.error(f"Arquivo não encontrado: {path}")
        st.stop()
    cols = [
        "evolucaocaso", "datanotificacao", "datainiciosintomas",
        "sexo", "idade", "bairro", "racacor",
        "sintomas", "classificacaofinal",
        "tipoteste", "resultadofinal", "municipio",
    ]
    df = pd.read_parquet(path, columns=cols)
    df = df[df["evolucaocaso"] == "Óbito"].copy()
    df["datanotificacao"]   = pd.to_datetime(df["datanotificacao"],   errors="coerce")
    df["datainiciosintomas"] = pd.to_datetime(df["datainiciosintomas"], errors="coerce")
    df["idade"] = pd.to_numeric(df["idade"], errors="coerce")
    df["tipoteste"] = df["tipoteste"].str.replace("–", "-", regex=False)
    df["bairro"] = df["bairro"].str.title()
    return df.reset_index(drop=True)


@st.cache_data(show_spinner="Carregando SRAG (with NA)…")
def load_srag_withna() -> pd.DataFrame:
    path = DATA_DIR / "sragmain_withna.csv"
    if not path.exists():
        st.error(f"Arquivo não encontrado: {path}")
        st.stop()
    df = pd.read_csv(path, low_memory=False, encoding="latin-1")
    for c in ("DT_DIGITA", "DT_SIN_PRI"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


# --- Sidebar filters -----------------------------------------------------
def sidebar_filters(
    df: pd.DataFrame,
    *,
    date_col: str,
    age_col: str,
    key_prefix: str,
    year_lo: int = 2022,
    year_hi: int = 2026,
) -> pd.DataFrame:
    """Return df filtered to the given year range."""
    mask = (
        (df[date_col].dt.year >= year_lo)
        & (df[date_col].dt.year <= year_hi)
    )
    return df.loc[mask].copy()


# --- KPI rendering -------------------------------------------------------
def render_kpis(kpis: list[tuple[str, str]]) -> None:
    """Render a row of KPI cards. Each kpi is (label, value)."""
    cols = st.columns(len(kpis))
    for col, (label, value) in zip(cols, kpis):
        with col:
            st.metric(label, value)


def fmt_int(n) -> str:
    try:
        return f"{int(n):,}".replace(",", ".")
    except Exception:
        return "—"


def fmt_date_range(series: pd.Series) -> str:
    s = pd.to_datetime(series, errors="coerce").dropna()
    if s.empty:
        return "—"
    return f"{s.min().date()} → {s.max().date()}"


# --- Moving average (2026) -----------------------------------------------
def render_ma_chart(
    df_all: pd.DataFrame,
    onset_col: str,
    titulo: str = "Média Móvel — Semanas Epidemiológicas 2026",
    window: int = 4,
) -> None:
    import plotly.graph_objects as go

    d = df_all.copy()
    d[onset_col] = pd.to_datetime(d[onset_col], errors="coerce")
    d = d.dropna(subset=[onset_col])
    d["onset_week"] = (
        d[onset_col] - pd.to_timedelta((d[onset_col].dt.weekday + 1) % 7, unit="D")
    ).dt.normalize()

    obs = (
        d.groupby("onset_week").size()
         .reset_index(name="n")
         .sort_values("onset_week")
         .reset_index(drop=True)
    )
    # Compute MA and rolling std on full history so early-2026 weeks include late-2025
    obs["ma"]  = obs["n"].rolling(window, min_periods=1).mean()
    obs["std"] = obs["n"].rolling(window, min_periods=1).std().fillna(0)

    epi_yr_obs, epi_wk_obs = paho_year_week(obs["onset_week"])
    obs["epi_year"] = epi_yr_obs.values
    obs["epi_week"] = epi_wk_obs.values

    obs_2026 = obs[obs["epi_year"] == 2026].copy()
    if obs_2026.empty:
        st.info("Sem dados de 2026 para plotar.")
        return

    all_weeks = pd.date_range(obs_2026["onset_week"].min(), obs_2026["onset_week"].max(), freq="W-SUN")
    tick_vals = list(all_weeks)
    epi_yr_ticks, epi_wk_ticks = paho_year_week(pd.Series(tick_vals))
    tick_text = [f"SE {int(wk):02d}/{int(yr)}" for yr, wk in zip(epi_yr_ticks, epi_wk_ticks)]

    x   = obs_2026["onset_week"].tolist()
    ma  = obs_2026["ma"].tolist()
    hi  = (obs_2026["ma"] + obs_2026["std"]).clip(lower=0).tolist()
    lo  = (obs_2026["ma"] - obs_2026["std"]).clip(lower=0).tolist()

    # PAHO labels for hover (avoids ISO %V mismatch — e.g. SE53/2025 ≠ ISO week 52)
    _epi_yr_x, _epi_wk_x = paho_year_week(pd.Series(x))
    _hover_lbl = [f"SE {int(wk):02d}/{int(yr)}" for yr, wk in zip(_epi_yr_x, _epi_wk_x)]

    fig = go.Figure()

    # Grey std band
    fig.add_trace(go.Scatter(
        x=x + x[::-1], y=hi + lo[::-1],
        fill="toself",
        fillcolor="rgba(150,150,150,0.25)",
        line=dict(width=0),
        name=f"±1 DP ({window} sem.)",
        showlegend=True,
        hoverinfo="skip",
    ))

    # Observed line
    fig.add_trace(go.Scatter(
        x=x, y=obs_2026["n"].tolist(),
        name="Observado", mode="lines",
        line=dict(color="rgba(0,0,0,0.35)", width=1, dash="dot"),
        customdata=_hover_lbl,
        hovertemplate="%{customdata}<br>Casos: %{y}<extra></extra>",
    ))

    # Moving average line
    fig.add_trace(go.Scatter(
        x=x, y=[round(v, 1) for v in ma],
        name=f"Média móvel {window} sem.", mode="lines",
        line=dict(color="#E45756", width=2.5),
        customdata=_hover_lbl,
        hovertemplate=f"%{{customdata}}<br>MM{window}: %{{y:.1f}}<extra></extra>",
    ))

    fig.update_layout(
        title=titulo,
        xaxis=dict(
            title=dict(text="Semana Epidemiológica", standoff=70),
            tickmode="array", tickvals=tick_vals, ticktext=tick_text,
            tickangle=-90,
        ),
        yaxis=dict(title="Nº Casos"),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            x=0.5, xanchor="center",
            entrywidthmode="fraction", entrywidth=0.45,
        ),
        margin=dict(l=20, r=20, t=120, b=180),
        height=520,
        plot_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True)


# --- Nowcasting / Forecasting table from htmlwidgets HTML ----------------
def load_nowcast_table(filename: str) -> "pd.DataFrame | None":
    import re
    import json
    from datetime import date as _date, timedelta

    path = PLOTS_DIR / filename
    if not path.exists():
        return None

    html = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'<script type="application/json"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return None

    data = json.loads(m.group(1))
    traces = data.get("x", {}).get("data", [])
    epoch = _date(1970, 1, 1)

    def _d(v):
        return epoch + timedelta(days=int(v))

    def _trace(name):
        return next((t for t in traces if t.get("name") == name), None)

    def _line(name):
        t = _trace(name)
        if not t:
            return {}
        return {_d(x): round(float(y), 1) for x, y in zip(t["x"], t["y"]) if y is not None}

    def _ci(name):
        t = _trace(name)
        if not t:
            return {}, {}
        xs, ys = t["x"], t["y"]
        n = len(xs) // 2
        lo = {_d(xs[i]): round(float(ys[i]), 1) for i in range(n - 1)}
        hi = {_d(xs[i]): round(float(ys[i]), 1) for i in range(n, 2 * n - 1)}
        return lo, hi

    nc_est = _line("(Nowcasting,1)")
    fc_est = _line("(Forecasting,1)")
    nc_lo, nc_hi = _ci("Nowcasting")
    fc_lo, fc_hi = _ci("Forecasting")

    rows = []
    for d, est in sorted(nc_est.items()):
        rows.append({"Data": d, "Tipo": "Nowcasting", "Estimativa": est,
                     "IC Inferior": nc_lo.get(d, ""), "IC Superior": nc_hi.get(d, "")})
    for d, est in sorted(fc_est.items()):
        rows.append({"Data": d, "Tipo": "Forecast", "Estimativa": est,
                     "IC Inferior": fc_lo.get(d, ""), "IC Superior": fc_hi.get(d, "")})

    if not rows:
        return None

    df = pd.DataFrame(rows)
    df["Data"] = pd.to_datetime(df["Data"])
    return df


# --- Choropleth maps (bairros + distritos) — Leaflet / folium -----------

_DISTRITO_NAMES = {
    1: "DS I", 2: "DS II", 3: "DS III",
    4: "DS IV", 5: "DS V", 6: "DS VI",
    7: "DS VII", 8: "DS VIII",
}

# Harvard crimson 7-step scale (light → dark)
_CRIMSON_STEPS = ["#fdf2f1", "#f5c6c2", "#e8827b", "#d94f45", "#b52d24", "#8b1a14", "#6b0001"]


def _folium_choropleth_bairros(data: pd.DataFrame, color_col: str = "n") -> str:
    """Return folium HTML string: bairro-level choropleth on Leaflet/OSM."""
    import json
    import folium
    from folium import Choropleth

    path = DATA_DIR / "bairros_recife.geojson"
    if not path.exists():
        return "<p>GeoJSON de bairros não encontrado.</p>"

    geojson = json.loads(path.read_text(encoding="utf-8"))

    # Normalize and deduplicate (sum) by bairro
    df = data.copy()
    df["bairro"] = df["bairro"].str.upper().str.strip()
    df = df.groupby("bairro")[color_col].sum().reset_index()

    # Add missing bairros with zero so every polygon has a value
    bairros_geo = [f["properties"].get("bairro", "") for f in geojson["features"]]
    existing = set(df["bairro"])
    zeros = pd.DataFrame(
        [{"bairro": b, color_col: 0} for b in bairros_geo if b and b not in existing]
    )
    if not zeros.empty:
        df = pd.concat([df, zeros], ignore_index=True)

    m = folium.Map(
        location=[-8.052, -34.95],
        zoom_start=11,
        tiles="CartoDB positron",
        control_scale=True,
    )

    Choropleth(
        geo_data=geojson,
        data=df,
        columns=["bairro", color_col],
        key_on="feature.properties.bairro",
        fill_color="YlOrRd",
        fill_opacity=0.75,
        line_opacity=0.4,
        line_color="#ffffff",
        line_weight=0.8,
        legend_name=color_col,
        bins=7,
        nan_fill_color="#e8e8e8",
        nan_fill_opacity=0.4,
    ).add_to(m)

    # Tooltip with bairro name + value
    val_map = df.set_index("bairro")[color_col].to_dict()
    style_fn = lambda feat: {
        "fillColor": "transparent",
        "color": "transparent",
        "weight": 0,
    }
    tooltip_fn = folium.GeoJsonTooltip(
        fields=["bairro"],
        aliases=["Bairro:"],
        localize=True,
    )
    folium.GeoJson(
        geojson,
        style_function=style_fn,
        tooltip=tooltip_fn,
        popup=folium.GeoJsonPopup(fields=["bairro"], aliases=["Bairro:"]),
    ).add_to(m)

    return m._repr_html_()


def _folium_choropleth_distritos(data: pd.DataFrame, color_col: str = "n") -> str:
    """Return folium HTML string: district-level choropleth on Leaflet/OSM."""
    import json
    import folium
    from folium import Choropleth

    path = DATA_DIR / "distritos-sanitarios-do-recife.geojson"
    if not path.exists():
        return "<p>GeoJSON de distritos não encontrado.</p>"

    geojson = json.loads(path.read_text(encoding="utf-8"))

    df = data.copy()
    if "distrito" not in df.columns:
        return "<p>Coluna 'distrito' não encontrada nos dados.</p>"

    # Detect whether rate columns are present
    has_rates = "taxa" in df.columns

    # Fill missing districts with zero
    all_names = list(_DISTRITO_NAMES.values())
    existing = set(df["distrito"])
    zero_row = {c: 0 for c in df.columns if c != "distrito"}
    zeros = pd.DataFrame([{"distrito": d, **zero_row} for d in all_names if d not in existing])
    if not zeros.empty:
        df = pd.concat([df, zeros], ignore_index=True)

    # Build lookup and embed all data columns into each GeoJSON feature
    lookup = df.set_index("distrito").to_dict(orient="index")
    tooltip_fields = ["distrito"]
    tooltip_aliases = ["Distrito:"]

    for feat in geojson["features"]:
        code = feat["properties"].get("cdistscodi", 0)
        name = _DISTRITO_NAMES.get(code, f"DS {code}")
        feat["properties"]["distrito"] = name
        row = lookup.get(name, {})
        for col, val in row.items():
            feat["properties"][col] = val

    cols = set(df.columns)
    use_rates = has_rates and color_col in ("taxa", "taxa_sg", "taxa_srag")
    if use_rates:
        # Only show the SG/SRAG breakdown when those columns are present
        if {"taxa_sg", "taxa_srag"} <= cols:
            tooltip_fields += ["taxa_sg", "taxa_srag", "taxa"]
            tooltip_aliases += ["SG (por 100k):", "SRAG (por 100k):", "Total (por 100k):"]
        else:
            tooltip_fields.append("taxa")
            tooltip_aliases.append("Taxa (por 100k):")
        legend_label = "Taxa por 100.000 hab."
    elif {"sg", "srag"} <= cols:
        tooltip_fields += ["sg", "srag", "n"]
        tooltip_aliases += ["SG:", "SRAG:", "Total:"]
        legend_label = "Casos"
    else:
        tooltip_fields.append("n")
        tooltip_aliases.append("Total:")
        legend_label = "Casos"

    m = folium.Map(
        location=[-8.052, -34.95],
        zoom_start=11,
        tiles="CartoDB positron",
        control_scale=True,
    )

    Choropleth(
        geo_data=geojson,
        data=df,
        columns=["distrito", color_col],
        key_on="feature.properties.distrito",
        fill_color="YlOrRd",
        fill_opacity=0.75,
        line_opacity=0.9,
        line_color="#ffffff",
        line_weight=1.5,
        legend_name=legend_label,
        bins=7,
        nan_fill_color="#e8e8e8",
        nan_fill_opacity=0.4,
    ).add_to(m)

    folium.GeoJson(
        geojson,
        style_function=lambda feat: {"fillColor": "transparent", "color": "transparent", "weight": 0},
        tooltip=folium.GeoJsonTooltip(fields=tooltip_fields, aliases=tooltip_aliases, localize=True),
        popup=folium.GeoJsonPopup(fields=tooltip_fields, aliases=tooltip_aliases),
    ).add_to(m)

    return m._repr_html_()


def leaflet_choropleth(
    data_bairros: pd.DataFrame,
    data_distritos: pd.DataFrame,
    toggle_key: str,
    height: int = 540,
    color_col: str = "n",
) -> None:
    """Render a Leaflet choropleth with a Streamlit toggle for bairros vs distritos."""
    import streamlit.components.v1 as components

    view = st.radio(
        "Nível de detalhe",
        ["Bairros", "Distritos Sanitários"],
        horizontal=True,
        key=toggle_key,
        label_visibility="collapsed",
    )

    if view == "Bairros":
        html = _folium_choropleth_bairros(data_bairros, color_col)
    else:
        html = _folium_choropleth_distritos(data_distritos, color_col)

    components.html(html, height=height, scrolling=False)


# Keep old names as thin wrappers for backward compatibility
def choropleth_bairros(
    data: pd.DataFrame,
    title: str = "Casos por Bairro",
    color_col: str = "n",
):
    import streamlit.components.v1 as components
    html = _folium_choropleth_bairros(data, color_col)
    components.html(html, height=540, scrolling=False)


def choropleth_distritos(
    data: pd.DataFrame,
    title: str = "Casos por Distrito Sanitário",
    color_col: str = "n",
):
    import streamlit.components.v1 as components
    html = _folium_choropleth_distritos(data, color_col)
    components.html(html, height=540, scrolling=False)


# --- Bairro → Distrito Sanitário lookup ---------------------------------
@st.cache_data(show_spinner=False)
def load_bairro_distrito() -> pd.DataFrame:
    path = DATA_DIR / "bairro_distrito_recife.csv"
    if not path.exists():
        return pd.DataFrame(columns=["bairro", "distrito"])
    df = pd.read_csv(path, encoding="utf-8")
    df["bairro"] = df["bairro"].str.upper().str.strip()
    return df[["bairro", "distrito"]].drop_duplicates("bairro")


@st.cache_data(show_spinner="Carregando progressões SG→SRAG…")
def load_sg_srag_linked() -> pd.DataFrame:
    path = DATA_DIR / "sg_srag_linked.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    for c in ["sg_DT_DIGITA", "sg_DT_PRISINT", "srag_DT_DIGITA", "srag_DT_SIN_PRI"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


# --- eSUS extended loader (for Resumo Executivo KPI cards) ---------------
@st.cache_data(show_spinner="Carregando eSUS — KPIs…")
def load_esus_kpi() -> pd.DataFrame:
    """Load eSUS with state column for Brazil / PE / Recife KPI computation."""
    path = DATA_DIR / "eSUS_all.parquet"
    if not path.exists():
        st.error(f"Arquivo não encontrado: {path}")
        st.stop()
    want = ["datanotificacao", "resultadofinal", "municipionotificacao", "estadonotificacao"]
    try:
        df = pd.read_parquet(path, columns=want)
    except Exception:
        df = pd.read_parquet(path)
        df = df[[c for c in want if c in df.columns]]
    df["datanotificacao"] = pd.to_datetime(df["datanotificacao"], errors="coerce")
    return df


@st.cache_data(show_spinner="Carregando eSUS — incidência por bairro…")
def load_esus_incidencia() -> pd.DataFrame:
    """Load eSUS with bairro of residence for incidence heatmap."""
    path = DATA_DIR / "eSUS_all.parquet"
    if not path.exists():
        return pd.DataFrame()
    want = ["datanotificacao", "bairro", "municipio", "municipionotificacao",
            "estadonotificacao", "resultadofinal"]
    try:
        df = pd.read_parquet(path, columns=want)
    except Exception:
        df = pd.read_parquet(path)
        df = df[[c for c in want if c in df.columns]]
    df["datanotificacao"] = pd.to_datetime(df["datanotificacao"], errors="coerce")
    return df


# --- HTML plot embed -----------------------------------------------------
def embed_html_plot(filename: str, height: int = 700) -> None:
    """Load a saved plotly HTML, inline any external *_files/ assets, and embed."""
    import re
    import streamlit.components.v1 as components

    path = PLOTS_DIR / filename
    if not path.exists():
        st.warning(f"Gráfico não encontrado: {path}")
        return

    html = path.read_text(encoding="utf-8")
    base_dir = path.parent

    def _inline_css(m):
        css_path = base_dir / m.group(1)
        if css_path.exists():
            return f"<style>{css_path.read_text(encoding='utf-8', errors='replace')}</style>"
        return m.group(0)

    def _inline_js(m):
        js_path = base_dir / m.group(1)
        if js_path.exists():
            return f"<script>{js_path.read_text(encoding='utf-8', errors='replace')}</script>"
        return m.group(0)

    html = re.sub(r'<link[^>]+href="([^"]+\.css)"[^>]*/?>',  _inline_css, html)
    html = re.sub(r'<script\s+src="([^"]+)"[^>]*></script>', _inline_js,  html)

    components.html(html, height=height, scrolling=True)
