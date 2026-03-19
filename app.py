"""
Main Streamlit entry point.

Routes:
  ?page=admin  → provider admin panel  (Phase 3)
  (default)    → client booking view   (Phase 2)
"""

import streamlit as st

st.set_page_config(
    page_title="Reservas | Nails",
    page_icon="💅",
    layout="centered",
)

page = st.query_params.get("page", "client")

if page == "admin":
    # Phase 3 will provide this view
    try:
        from views.admin import render
    except ImportError:
        st.error("Panel de administración aún no disponible.")
        st.stop()
else:
    from views.client import render

render()
