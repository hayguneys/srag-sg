"""SG / SRAG Surveillance Dashboard — entry point and navigation."""
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="Dash de monitoramento e previsão de SG / SRAG",
    page_icon="🦠",
    layout="wide",
)


def intro():
    st.title("🦠 SG / SRAG — Painel de Vigilância")
    st.markdown(
        """
        Dashboard interativo para vigilância de **Síndrome Gripal (SG)** e
        **Síndrome Respiratória Aguda Grave (SRAG)** com **nowcasting** e
        **forecasting** via modelo INLA (Integrated Nested Laplace Approximations)
        estruturado por idade, tempo e atraso de notificação.

        ### Páginas disponíveis
        Use o menu lateral para navegar:

        - **SG** — Síndrome Gripal
        - **SRAG** — Síndrome Respiratória Aguda Grave

        Cada página possui abas: **Descritivo**, **Taxas de Positividade** e
        **Nowcasting + Forecasting**.

        ---
        **Sobre o nowcasting.** O modelo estima quantos casos *realmente* ocorreram
        em semanas recentes, corrigindo o atraso entre o início dos sintomas e o
        registro do caso. O forecasting projeta a curva algumas semanas adiante.

        ---
        **Sobre o forecasting.** Utilizando a mesma modelagem do nowcasting, o forecasting projeta a curva de casos para as próximas semanas epidemiológicas,
        que estima o número de casos futuros com base nas tendências atuais e nos padrões históricos, fornecendo insights valiosos para planejamento e resposta
        à saúde pública.

        ---
        Ambos usam estas configurações do modelo: `nowcaster::nowcasting_inla` com `wdw = 230`(230 semanas epidemiológicas contadas da última data disponível) semanas e
        `bins_age = "10 years"`

        O K  é zero para o nowcasting e 4 para o forecasting, para capturar as tendências das próximas 4 semanas futuras.
        """
        
    )

    st.markdown("### Acesso rápido — Nowcasting + Forecasting")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🤧 Nowcasting + Forecasting — SG", use_container_width=True):
            st.session_state["sg_goto_nowcasting"] = True
            st.switch_page("pages/1_SG.py")
    with col2:
        if st.button("🫁 Nowcasting + Forecasting — SRAG", use_container_width=True):
            st.session_state["srag_goto_nowcasting"] = True
            st.switch_page("pages/2_SRAG.py")

    st.info("Selecione **SG** ou **SRAG** no menu à esquerda para começar.")


pg = st.navigation([
    st.Page(intro, title="Introdução", icon="🏠", default=True),
    st.Page("pages/1_SG.py", title="SG", icon="🤧"),
    st.Page("pages/2_SRAG.py", title="SRAG", icon="🫁"),
])
pg.run()

_img = Path(__file__).parent / "images" / "regua vert.png"
if _img.exists():
    st.sidebar.image(str(_img), use_container_width=True)
