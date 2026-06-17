# SG / SRAG Surveillance Dashboard

Dashboard interativo feito pela equipe de dados do CIE para **Síndrome Gripal (SG)** e
**Síndrome Respiratória Aguda Grave (SRAG)**, com
nowcasting e forecasting usando o modelo `nowcaster` INLA .

## estrutura

```
.
├── app.py                  # landing page + navigation
├── pages/
│   ├── 1_SG.py             # SG page
│   ├── 2_SRAG.py           # SRAG page
│   ├── 4_eSUS.py           # e-SUS Notifica (COVID-19) page
│   └── 3_Resumo_Executivo.py
├── utils/
│   └── helpers.py          # data loading, filters, KPI/seasonality helpers
├── data/
│   ├── sg_main.parquet         # SG cases — série histórica desde 2013
│   ├── srag_sintomas.parquet   # SRAG cases — série histórica desde 2019
│   └── eSUS_all.parquet        # eSUS-Notifica (COVID-19)
├── plots/
│   ├── nowcasting_sg.html  # pre-rendered interactive plotly
│   └── nowcasting_srag.html
├── requirements.txt
└── .streamlit/config.toml
```

## Filtros e séries históricas

- **Período (SE/Ano):** o seletor de semana epidemiológica abre toda a série
  disponível — SG desde 2013, SRAG desde 2019, eSUS desde 2020.
- **Unidade de Notificação:** atalhos municipais + lista completa de todas as
  unidades de notificação por extenso com código (SG: `NOME_UNIDA`/`COD_UNID`;
  SRAG: `ID_UNIDADE`/`CO_UNI_NOT`).
- **Sazonalidade:** as abas de Nowcasting + Forecasting (SG, SRAG e e-SUS) trazem
  um histograma da média de casos por semana epidemiológica usando todos os anos.

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

### e-SUS (COVID-19)
- Espelha a estrutura de SG/SRAG sobre o banco eSUS-Notifica.
- Eixo temporal = data dos primeiros sintomas, preenchida pela data de
  notificação quando vazia (a página acende as visões de sexo/idade
  automaticamente quando uma fonte mais rica é colocada em `data/eSUS_all.parquet`).
- **Tabs:** Descritivo · Testes · Nowcasting + Forecasting (com sazonalidade)

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
