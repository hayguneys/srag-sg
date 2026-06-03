# SG / SRAG Surveillance Dashboard

Dashboard interativo feito pela equipe de dados do CIE para **Síndrome Gripal (SG)** e
**Síndrome Respiratória Aguda Grave (SRAG)**, com
nowcasting e forecasting usando o modelo `nowcaster` INLA .

## estrutura

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

## Páginas

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

### painel lateral(sidebar)
- Date range filter (DT_DIGITA, padrão 2022–2026)
- Age range filter (IDADE em SG, NU_IDADE_N em SRAG)

## Rodar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open <http://localhost:8501>.

## Updating the data

Se for feito novo output em R, salvar df em parquet no R:

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

re-exportar HTMLs como estão nos scripts do R:
`saveWidget(p_sg_plotly, "plots/nowcasting_sg.html", selfcontained = TRUE)`.
