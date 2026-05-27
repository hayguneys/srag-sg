# SG / SRAG Surveillance Dashboard

Interactive Streamlit dashboard for **Síndrome Gripal (SG)** and
**Síndrome Respiratória Aguda Grave (SRAG)** surveillance data, with
nowcasting and forecasting outputs from the `nowcaster` INLA model.

## Structure

```
.
├── app.py                  # landing page
├── pages/
│   ├── 1_SG.py             # SG page (2 tabs)
│   └── 2_SRAG.py           # SRAG page (2 tabs)
├── utils/
│   └── helpers.py          # data loading, filters, KPI helpers
├── data/
│   ├── sg_main.parquet     # SG cases (already trimmed to needed cols)
│   └── srag_main.parquet   # SRAG cases (already trimmed to needed cols)
├── plots/
│   ├── nowcasting_sg.html  # pre-rendered interactive plotly
│   └── nowcasting_srag.html
├── requirements.txt
└── .streamlit/config.toml
```

## Pages

### SG
- **Tab 1 — Descritivo**
  - KPIs: total de casos · período (DT_DIGITA) · vacinação COVID
    (VACINA_COV) · vacinação influenza (VACINA) · tratamento antiviral
    COVID (TRAT_COV)
  - Dois gráficos de barras empilhadas (CLASSI_FIN por semana
    epidemiológica): **faixa 0–9 anos** e **faixa 60+ anos**
- **Tab 2 — Nowcasting + Forecasting** — gráfico plotly interativo

### SRAG
- **Tab 1 — Descritivo**
  - KPIs: total de casos · período (DT_DIGITA) · total de óbitos
    (EVOLUCAO == 2)
  - Histograma etário
- **Tab 2 — Nowcasting + Forecasting** — gráfico plotly interativo

### Sidebar
- Date range filter (DT_DIGITA, padrão 2022–2026)
- Age range filter (IDADE em SG, NU_IDADE_N em SRAG)

## Running locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open <http://localhost:8501>.

## Deploying to Streamlit Cloud

1. Push the entire folder (including `data/` and `plots/`) to a GitHub
   repository.
2. Go to <https://share.streamlit.io>, click **New app**, select your
   repo and `app.py` as the entry point.
3. Streamlit Cloud installs `requirements.txt` automatically.

The `data/*.parquet` files are committed because they are small (≪ 1 MB
each — already trimmed to only the columns the dashboard needs). The
`plots/*.html` files are larger (~3.7 MB each) but well under GitHub's
100 MB limit.

## Updating the data

If you generate new R output, save the dataframes to parquet from R:

```r
arrow::write_parquet(
  sg_main[, c("DT_DIGITA","DT_PRISINT","IDADE","CLASSI_FIN",
              "VACINA","VACINA_COV","TRAT_COV")],
  "data/sg_main.parquet"
)
arrow::write_parquet(
  srag_main[, c("DT_DIGITA","DT_SIN_PRI","NU_IDADE_N","EVOLUCAO")],
  "data/srag_main.parquet"
)
```

Then re-export the plotly HTMLs as in your existing R scripts:
`saveWidget(p_sg_plotly, "plots/nowcasting_sg.html", selfcontained = TRUE)`.

## Notes

- **EVOLUCAO == 2** is the DataSUS code for "óbito por SRAG". Adjust in
  `pages/2_SRAG.py` if your codification differs.
- The CLASSI_FIN color palette is defined in `utils/helpers.py` for
  consistency across the app.
- Date filter defaults to 2022-01-01 as the lower bound per spec, even
  though SRAG data may extend back to 2019.
