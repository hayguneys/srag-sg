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


# --- Epidemiological-week range selector ---------------------------------
# Bounds of the selectable SE range. The lower bound matches the historical
# 2022 start used across the dashboard; the upper bound is the last complete
# epidemiological week with consolidated data (2026 SE 16).
EPIWEEK_MIN = (2022, 1)
EPIWEEK_MAX = (2026, 16)

# Per-page lower bounds for the SE/Ano selector, matching how far back each
# data source goes: SG from 2013, SRAG from 2019, eSUS-Notifica from 2020.
SG_EPIWEEK_MIN = (2013, 1)
SRAG_EPIWEEK_MIN = (2019, 1)
ESUS_EPIWEEK_MIN = (2020, 1)


def epiweek_options(start: tuple[int, int] = EPIWEEK_MIN,
                    end: tuple[int, int] = EPIWEEK_MAX) -> list[tuple[int, int]]:
    """Ordered (epi_year, epi_week) tuples from start to end, inclusive.

    Built by walking week-start Sundays and labelling each with
    ``paho_year_week`` — the same PAHO/MMWR (Brazilian Ministério da Saúde)
    algorithm used everywhere else — so every SE matches the official MS
    epidemiological-week table by construction (incl. 53-week years like 2025).
    """
    y0, w0 = start
    y1, w1 = end
    first = pd.Timestamp(y0, 1, 1) - pd.Timedelta(days=10)
    last  = pd.Timestamp(y1, 12, 31) + pd.Timedelta(days=10)
    sundays = pd.date_range(first, last, freq="W-SUN")
    yr, wk = paho_year_week(pd.Series(sundays))
    lo_key, hi_key = y0 * 100 + w0, y1 * 100 + w1
    out: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for y, w in zip(yr.astype(int), wk.astype(int)):
        k = y * 100 + w
        if lo_key <= k <= hi_key and (y, w) not in seen:
            seen.add((y, w))
            out.append((y, w))
    return out


def epiweek_label(y: int, w: int) -> str:
    """Render an epiweek tuple as "SE WW/YYYY"."""
    return f"SE {int(w):02d}/{int(y)}"


def render_epiweek_slider(
    key: str,
    label: str = "Período (SE/Ano)",
    start: tuple[int, int] = EPIWEEK_MIN,
    end: tuple[int, int] = EPIWEEK_MAX,
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Render an SE/Ano range select_slider; return (se_lo, se_hi) tuples."""
    opts = epiweek_options(start, end)
    labels = [epiweek_label(y, w) for y, w in opts]
    lbl_lo, lbl_hi = st.select_slider(
        label, options=labels, value=(labels[0], labels[-1]), key=key,
    )
    return opts[labels.index(lbl_lo)], opts[labels.index(lbl_hi)]


def filter_epiweek(df: pd.DataFrame, date_col: str,
                   se_lo: tuple[int, int], se_hi: tuple[int, int]) -> pd.DataFrame:
    """Filter df to rows whose date_col falls within the [se_lo, se_hi] SE range.

    Rows with a missing date are dropped (they have no epidemiological week).
    """
    d = df[df[date_col].notna()]
    if d.empty:
        return d.copy()
    yr, wk = paho_year_week(d[date_col])
    key = yr * 100 + wk
    lo = se_lo[0] * 100 + se_lo[1]
    hi = se_hi[0] * 100 + se_hi[1]
    return d[(key >= lo) & (key <= hi)].copy()


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


@st.cache_data(show_spinner="Carregando SRAG…")
def load_srag_withna() -> pd.DataFrame:
    # SIVEP-GRIPE SRAG, município de residência = Recife, série histórica.
    # Analytic date is DT_SIN_PRI (data dos primeiros sintomas). See
    # data/build_srag_sintomas.py for how this parquet is produced.
    path = DATA_DIR / "srag_sintomas.parquet"
    if not path.exists():
        st.error(f"Arquivo não encontrado: {path}")
        st.stop()
    df = pd.read_parquet(path)
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


# --- TEST: line frames around KPI cards ----------------------------------
# Experimental visual test. Rollback: set TEST_FRAMES = False (or revert the
# commit that introduced inject_test_frames + its call sites).
TEST_FRAMES = True


def inject_test_frames() -> None:
    """Draw a light line frame around every KPI card.

    Mirrors the bordered look of the scrollable "Por Bairro" container. Call
    once near the top of a page. No-op when TEST_FRAMES is False.
    """
    if not TEST_FRAMES:
        return
    st.markdown(
        """
        <style>
        div[data-testid="stMetric"] {
            border: 1px solid rgba(49, 51, 63, 0.2);
            border-radius: 0.5rem;
            padding: 0.75rem;
            background: #ffffff;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# --- Moving average overlay for stacked bar charts -----------------------
def add_ma_overlay(
    fig,
    agg: "pd.DataFrame",
    window: int = 4,
    color: str = "#1f1f1f",
    label: str | None = None,
) -> None:
    """Add a total-cases moving average line to a stacked weekly bar chart.

    ``agg`` must have columns ``semana``, ``semana_sort``, and ``n``.
    The MA is computed over the column-wise sum of ``n`` (total per week)
    with a ``window``-week rolling mean (min_periods=1).
    """
    import plotly.graph_objects as go

    totals = (
        agg.groupby(["semana", "semana_sort"])["n"]
        .sum()
        .reset_index()
        .sort_values("semana_sort")
    )
    totals["ma"] = totals["n"].rolling(window, min_periods=1).mean()
    if label is None:
        label = f"Média móvel {window} SE"
    fig.add_trace(go.Scatter(
        x=totals["semana"],
        y=totals["ma"].round(1),
        name=label,
        mode="lines",
        line=dict(color=color, width=2, dash="dot"),
        hovertemplate="%{x}<br>" + label + ": %{y:.1f}<extra></extra>",
    ))


# --- KPI rendering -------------------------------------------------------
def period_compare_label(se_lo: tuple[int, int], se_hi: tuple[int, int]) -> str:
    """Label comparing the selected SE range to the same range one year earlier.

    e.g. a single-year range gives "2026 vs 2025"; a multi-year range gives
    "2022–2026 vs 2021–2025".
    """
    y_lo, y_hi = se_lo[0], se_hi[0]
    cur  = f"{y_lo}" if y_lo == y_hi else f"{y_lo}–{y_hi}"
    prev = f"{y_lo - 1}" if y_lo == y_hi else f"{y_lo - 1}–{y_hi - 1}"
    return f"{cur} vs {prev}"


def _se_span_label(se_lo: tuple[int, int], se_hi: tuple[int, int]) -> str:
    """Exact SE span, e.g. "SE 01/2026 – SE 16/2026" (or a single SE)."""
    lo, hi = epiweek_label(*se_lo), epiweek_label(*se_hi)
    return lo if se_lo == se_hi else f"{lo} – {hi}"


def period_compare_se_label(se_lo: tuple[int, int], se_hi: tuple[int, int]) -> str:
    """Exact SE ranges compared: the selected span vs. the same span one year back.

    e.g. "SE 01/2026 – SE 16/2026 vs SE 01/2025 – SE 16/2025".
    """
    cur  = _se_span_label(se_lo, se_hi)
    prev = _se_span_label((se_lo[0] - 1, se_lo[1]), (se_hi[0] - 1, se_hi[1]))
    return f"{cur} vs {prev}"


def format_kpi_delta(cur: float, prev: float, compare_label: str) -> str | None:
    """Signed percent change vs. the previous period, annotated with the years.

    Returns a string for ``st.metric``'s ``delta`` (which renders a coloured
    up/down arrow from the sign), or None when there is no baseline to compare.
    """
    if not prev:
        return None
    pct = (cur - prev) / prev * 100
    return f"{pct:+.0f}% ({compare_label})"


def render_kpis(kpis: list[tuple]) -> None:
    """Render a row of KPI cards.

    Each kpi is ``(label, value)``, ``(label, value, delta)``, or
    ``(label, value, delta, help)``. A delta string is passed to
    ``st.metric``'s native ``delta`` slot (coloured ↑/↓ arrow by sign); the
    optional help text renders the hover tooltip balloon (e.g. the exact SE
    range being compared).
    """
    cols = st.columns(len(kpis))
    for col, kpi in zip(cols, kpis):
        with col:
            delta = kpi[2] if len(kpi) >= 3 else None
            help_txt = kpi[3] if len(kpi) >= 4 else None
            if delta:
                st.metric(kpi[0], kpi[1], delta=delta, help=help_txt)
            else:
                st.metric(kpi[0], kpi[1])


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
    st.plotly_chart(fig, width='stretch')


# --- Seasonality line (média móvel histórica por SE) ---------------------
def render_seasonality_hist(
    df_all: pd.DataFrame,
    onset_col: str,
    titulo: str = "Sazonalidade — Média Histórica por Semana Epidemiológica",
    value_label: str = "Casos",
    highlight_year: int | None = None,
    window: int = 4,
) -> None:
    """Plot the historical seasonal profile as a moving-average line.

    For every epidemiological week (SE 1…53) the mean weekly count is computed
    over **all** years available in ``df_all`` (quiet weeks count as zero within
    each year's observed span), then smoothed with a centred ``window``-week
    moving average to give the typical seasonal curve. The most recent year (or
    ``highlight_year``) is overlaid as a dotted line so the current season can be
    compared against the historical norm.
    """
    import plotly.graph_objects as go

    d = df_all.copy()
    d[onset_col] = pd.to_datetime(d[onset_col], errors="coerce")
    d = d.dropna(subset=[onset_col])
    if d.empty:
        st.info("Sem dados para o gráfico de sazonalidade.")
        return

    epi_year, epi_week = paho_year_week(d[onset_col])
    counts = (
        pd.DataFrame({"year": epi_year.values, "week": epi_week.values})
        .groupby(["year", "week"]).size().reset_index(name="n")
    )

    y_min, y_max = int(epi_year.min()), int(epi_year.max())
    # Build the full year × week grid (zero-filled) so quiet weeks count as 0.
    weeks_by_year = (
        counts.groupby("year")["week"].max().reindex(range(y_min, y_max + 1)).fillna(52)
    )
    grid = []
    for yr in range(y_min, y_max + 1):
        wk_max = int(max(52, weeks_by_year.get(yr, 52)))
        for wk in range(1, wk_max + 1):
            grid.append((yr, wk))
    grid = pd.DataFrame(grid, columns=["year", "week"])
    full = grid.merge(counts, on=["year", "week"], how="left")
    full["n"] = full["n"].fillna(0)

    season = (
        full.groupby("week")["n"].mean().reset_index(name="media").sort_values("week")
    )
    # Moving average across the SE axis to smooth the historical seasonal curve.
    season["ma"] = (
        season["media"].rolling(window, min_periods=1, center=True).mean().round(1)
    )

    fig = go.Figure()

    # Historical moving-average line (all years).
    fig.add_trace(go.Scatter(
        x=season["week"], y=season["ma"],
        name=f"Média móvel histórica ({y_min}–{y_max})", mode="lines",
        line=dict(color="#4C78A8", width=2.5),
        hovertemplate=(
            "SE %{x}<br>Média móvel: %{y:.1f} " + value_label.lower() + "<extra></extra>"
        ),
    ))

    # Most recent (or requested) year overlaid as a dotted line.
    hl_year = highlight_year if highlight_year is not None else y_max
    cur = counts[counts["year"] == hl_year].sort_values("week")
    if not cur.empty:
        fig.add_trace(go.Scatter(
            x=cur["week"], y=cur["n"],
            name=f"{hl_year}", mode="lines",
            line=dict(color="#E45756", width=2, dash="dot"),
            hovertemplate=f"SE %{{x}}/{hl_year}<br>{value_label}: %{{y}}<extra></extra>",
        ))

    fig.update_layout(
        title=titulo,
        xaxis=dict(title="Semana Epidemiológica", dtick=2, tickmode="linear"),
        yaxis=dict(title=f"Nº {value_label}"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center"),
        margin=dict(l=20, r=20, t=90, b=60),
        height=460, plot_bgcolor="white",
    )
    st.plotly_chart(fig, width='stretch')


# --- Notification-unit filter (full list + presets) ----------------------
def unit_code_map(df: pd.DataFrame, name_col: str, code_col: str | None) -> dict:
    """Map each notification-unit name to its (most frequent) unit code.

    Used to label the Unidade de Notificação filter "por extenso" with the
    unit code appended. Returns ``{name: code}``; names with no usable code map
    to "".
    """
    if name_col not in df.columns:
        return {}
    if code_col is None or code_col not in df.columns:
        names = df[name_col].dropna().astype(str).str.strip()
        return {n: "" for n in names.unique() if n}
    pair = df[[name_col, code_col]].dropna(subset=[name_col]).copy()
    pair[name_col] = pair[name_col].astype(str).str.strip()
    pair = pair[pair[name_col] != ""]
    pair[code_col] = pair[code_col].astype(str).str.strip().replace(
        {"nan": "", "None": "", "<NA>": ""}
    )
    out: dict = {}
    for name, grp in pair.groupby(name_col):
        codes = grp[code_col][grp[code_col] != ""]
        out[name] = str(codes.mode().iloc[0]) if not codes.empty else ""
    return out


# --- Nowcasting / Forecasting table from htmlwidgets HTML ----------------
def load_nowcast_table(filename: str) -> "pd.DataFrame | None":
    """Extract the nowcast/forecast estimates (and 95% CI) from a saved
    htmlwidgets/plotly nowcasting HTML.

    The plot stores, for each of "Nowcasting" and "Forecasting", two traces with
    the same name:
      * a line trace (fill is null) holding the central estimate per week, and
      * a filled polygon trace (fill == "toself") holding the CI ribbon — the
        lower bound left→right followed by the upper bound right→left, with the
        end points duplicated to close the polygon.
    """
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

    try:
        data = json.loads(m.group(1))
    except (ValueError, TypeError):
        return None
    traces = data.get("x", {}).get("data", [])
    epoch = _date(1970, 1, 1)

    def _d(v):
        return epoch + timedelta(days=int(v))

    def _pick(name, *, filled):
        for t in traces:
            if t.get("name") != name:
                continue
            is_fill = str(t.get("fill") or "").lower() == "toself"
            if is_fill == filled:
                return t
        return None

    def _estimate(name):
        t = _pick(name, filled=False)
        if not t or not t.get("x"):
            return {}
        return {
            _d(x): round(float(y), 1)
            for x, y in zip(t["x"], t["y"]) if y is not None
        }

    def _ci(name):
        """Return {date: (lo, hi)} from the filled ribbon polygon.

        The ribbon visits every week twice (once on the lower bound, once on the
        upper) plus a couple of duplicated closing vertices. Grouping all y
        values by date and taking min/max recovers the CI robustly regardless of
        vertex ordering or duplicates.
        """
        t = _pick(name, filled=True)
        if not t or not t.get("x"):
            return {}
        by_date: dict = {}
        for x, y in zip(t["x"], t["y"]):
            if y is None:
                continue
            by_date.setdefault(_d(x), []).append(float(y))
        return {
            d: (round(min(vs), 1), round(max(vs), 1))
            for d, vs in by_date.items()
        }

    rows = []
    for label, tipo in (("Nowcasting", "Nowcasting"), ("Forecasting", "Forecast")):
        est = _estimate(label)
        ci = _ci(label)
        for d, val in sorted(est.items()):
            lo, hi = ci.get(d, ("", ""))
            rows.append({
                "Data": d, "Tipo": tipo, "Estimativa": val,
                "IC Inferior": lo, "IC Superior": hi,
            })

    if not rows:
        return None

    df = pd.DataFrame(rows)
    df["Data"] = pd.to_datetime(df["Data"])
    return df


def render_forecast_table(filename: str, caption: bool = True) -> None:
    """Render a compact table of the forecasted weeks from a nowcasting HTML.

    Shows, for each projected week, the epidemiological week, the date, the
    central estimate (median) and the 95% credible interval.
    """
    tbl = load_nowcast_table(filename)
    fc = tbl[tbl["Tipo"] == "Forecast"].copy() if tbl is not None else None
    if fc is None or fc.empty:
        st.info("Dados de forecast não disponíveis.")
        return

    yr, wk = paho_year_week(fc["Data"])
    fc["Semana Epidemiológica"] = [f"SE{int(w):02d}/{int(y)}" for y, w in zip(yr, wk)]
    fc["Data"] = fc["Data"].dt.strftime("%d/%m/%Y")
    fc["IC 95%"] = [
        f"{lo:.0f} – {hi:.0f}" if lo != "" and hi != "" else "—"
        for lo, hi in zip(fc["IC Inferior"], fc["IC Superior"])
    ]
    fc["Casos estimados"] = fc["Estimativa"].round(0).astype("Int64")
    show = fc[["Semana Epidemiológica", "Data", "Casos estimados", "IC 95%"]]
    if caption:
        st.caption(
            "Estimativa de casos (mediana) e intervalo de credibilidade de 95% "
            "para as semanas projetadas pelo modelo."
        )
    st.dataframe(show, width='stretch', hide_index=True)


# --- Choropleth map (distritos sanitários) — Leaflet / folium -----------

_DISTRITO_NAMES = {
    1: "DS I", 2: "DS II", 3: "DS III",
    4: "DS IV", 5: "DS V", 6: "DS VI",
    7: "DS VII", 8: "DS VIII",
}

# Harvard crimson 7-step scale (light → dark)
_CRIMSON_STEPS = ["#fdf2f1", "#f5c6c2", "#e8827b", "#d94f45", "#b52d24", "#8b1a14", "#6b0001"]


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
        location=[-8.1891, -34.8711],
        zoom_start=11,
        tiles="CartoDB positron",
        control_scale=True,
        min_zoom=10,
        max_zoom=14,
        max_bounds=True,
        min_lat=-8.25, max_lat=-7.85,
        min_lon=-35.15, max_lon=-34.70,
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

    def _poly_centroid(ring):
        """Signed-area centroid of a closed polygon ring [[lon, lat], ...]."""
        n = len(ring)
        A = cx = cy = 0.0
        for i in range(n - 1):
            x0, y0 = ring[i][0], ring[i][1]
            x1, y1 = ring[i + 1][0], ring[i + 1][1]
            cross = x0 * y1 - x1 * y0
            A  += cross
            cx += (x0 + x1) * cross
            cy += (y0 + y1) * cross
        A *= 0.5
        if abs(A) < 1e-12:
            lons = [c[0] for c in ring]
            lats = [c[1] for c in ring]
            return sum(lats) / len(lats), sum(lons) / len(lons)
        cx /= 6 * A
        cy /= 6 * A
        return cy, cx  # (lat, lon)

    # White district name labels at true polygon centroids
    for feat in geojson["features"]:
        _code = feat["properties"].get("cdistscodi", 0)
        _dname = _DISTRITO_NAMES.get(_code)
        if not _dname:
            continue
        _geom = feat["geometry"]
        if _geom["type"] == "Polygon":
            _ring = _geom["coordinates"][0]
        elif _geom["type"] == "MultiPolygon":
            # pick the polygon with the largest area (most coords as proxy)
            _ring = max(_geom["coordinates"], key=lambda p: len(p[0]))[0]
        else:
            continue
        _clat, _clon = _poly_centroid(_ring)
        folium.Marker(
            location=[_clat, _clon],
            icon=folium.DivIcon(
                html=(
                    f'<div style="font-size:12px;font-weight:bold;color:white;'
                    f'text-shadow:-1px -1px 0 rgba(0,0,0,.55),1px -1px 0 rgba(0,0,0,.55),'
                    f'-1px 1px 0 rgba(0,0,0,.55),1px 1px 0 rgba(0,0,0,.55);'
                    f'white-space:nowrap;text-align:center;">{_dname}</div>'
                ),
                icon_size=(55, 20),
                icon_anchor=(27, 10),
            ),
        ).add_to(m)

    return m._repr_html_()


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


# --- eSUS full loader (for the e-SUS / COVID page) -----------------------
# Candidate column names (lowercased) for the symptom-onset date in richer
# eSUS-Notifica exports. The trimmed extract currently shipped has none of
# these, so the page falls back to the notification date.
_ESUS_SINTOMA_CANDS = (
    "datainiciosintomas", "dataprimeirossintomas", "data_inicio_sintomas",
    "dtsintomas", "dt_sintomas", "datasprimeirossintomas", "dataprimeirosintomas",
)


@st.cache_data(show_spinner="Carregando e-SUS Notifica…")
def load_esus_page() -> pd.DataFrame:
    """Load the full eSUS-Notifica extract for the e-SUS page.

    Reads every column so the page lights up automatically when a richer source
    (with symptom-onset date, idade, sexo, …) is dropped in. The analytic date
    ``DT_SINTOMAS`` is the data dos primeiros sintomas, filled from the
    notification date where empty ("primeiros sintomas = notificação quando
    vazio"); if the source has no symptom column it equals the notification date.
    """
    path = DATA_DIR / "eSUS_all.parquet"
    if not path.exists():
        st.error(f"Arquivo não encontrado: {path}")
        st.stop()
    df = pd.read_parquet(path)

    lower = {c.lower(): c for c in df.columns}
    notif_col = lower.get("datanotificacao") or lower.get("data_notificacao")
    sin_col = next((lower[c] for c in _ESUS_SINTOMA_CANDS if c in lower), None)

    notif = (
        pd.to_datetime(df[notif_col], errors="coerce") if notif_col
        else pd.Series(pd.NaT, index=df.index)
    )
    df["DT_NOTIFIC"] = notif
    if sin_col is not None:
        df["DT_SINTOMAS"] = pd.to_datetime(df[sin_col], errors="coerce").fillna(notif)
        df.attrs["sintoma_source"] = "primeiros sintomas (vazio → notificação)"
    else:
        df["DT_SINTOMAS"] = notif
        df.attrs["sintoma_source"] = "data de notificação (sem coluna de sintomas)"

    if "tipoteste" in df.columns:
        df["tipoteste"] = df["tipoteste"].astype(str).str.replace("–", "-", regex=False)
    return df


# --- HTML plot embed -----------------------------------------------------
def _fix_nowcast_legend(html: str) -> str:
    """Repair the legend in a ggplotly nowcasting widget.

    ggplotly emits a horizontal legend whose items are not spaced out, so the
    four series labels render stacked on the same point. Rewrite the widget's
    `layout.legend` block to a cleanly spaced horizontal legend.
    """
    import json
    import re

    m = re.search(r'(<script type="application/json"[^>]*>)(.*?)(</script>)', html, re.DOTALL)
    if not m:
        return html
    try:
        data = json.loads(m.group(2))
    except (ValueError, TypeError):
        return html

    layout = data.get("x", {}).get("layout")
    if not isinstance(layout, dict):
        return html

    layout["showlegend"] = True
    layout["legend"] = {
        "orientation": "h",
        "x": 0.5, "xanchor": "center",
        "y": -0.18, "yanchor": "top",
        "font": {"size": 13},
        "bgcolor": "rgba(255,255,255,0)",
        "bordercolor": "transparent",
        "traceorder": "normal",
        "itemwidth": 30,
        "tracegroupgap": 10,
    }
    # Give the legend room below the plot so it is not clipped.
    margin = layout.setdefault("margin", {})
    if isinstance(margin, dict):
        margin["b"] = max(int(margin.get("b", 0) or 0), 90)

    new_json = json.dumps(data)
    return html[: m.start()] + m.group(1) + new_json + m.group(3) + html[m.end():]


def embed_html_plot(filename: str, height: int = 700, fix_legend: bool = False) -> None:
    """Load a saved plotly HTML, inline any external *_files/ assets, and embed.

    When ``fix_legend`` is True, repair the ggplotly horizontal legend so the
    series labels are spaced out instead of overlapping on a single point.
    """
    import re
    import streamlit.components.v1 as components

    path = PLOTS_DIR / filename
    if not path.exists():
        st.warning(f"Gráfico não encontrado: {path}")
        return

    html = path.read_text(encoding="utf-8")
    base_dir = path.parent

    if fix_legend:
        html = _fix_nowcast_legend(html)

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
