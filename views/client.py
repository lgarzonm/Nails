"""
Client-facing booking view.

Flow:
  1. Select service
  2. Pick a date (today + DAYS_AHEAD)
  3. Pick an available time slot
  4. Enter name & phone
  5. Submit → booking created with status='pending'
"""

import re
from datetime import date, timedelta

import streamlit as st

from config import DAYS_AHEAD, PROVIDER_ID
from db.database import create_booking, get_active_services, init_db
from services.availability import get_available_slots

PHONE_RE = re.compile(r"^\+?[\d\s\-]{7,15}$")


def _validate_phone(phone: str) -> bool:
    return bool(PHONE_RE.match(phone.strip()))


def render():
    init_db()

    st.title("Reserva tu cita 💅")
    st.markdown("Completa los pasos para solicitar tu cita. Te confirmaremos por WhatsApp.")

    # ------------------------------------------------------------------ #
    # Step 1 – Service selection
    # ------------------------------------------------------------------ #
    services = get_active_services(PROVIDER_ID)
    if not services:
        st.warning("No hay servicios disponibles por el momento.")
        return

    service_names = [s["name"] for s in services]
    selected_service_name = st.selectbox("¿Qué servicio deseas?", service_names)
    selected_service = next(s for s in services if s["name"] == selected_service_name)

    st.caption(f"Duración: {selected_service['duration_minutes']} minutos")

    # ------------------------------------------------------------------ #
    # Step 2 – Date picker
    # ------------------------------------------------------------------ #
    today = date.today()
    max_date = today + timedelta(days=DAYS_AHEAD)
    selected_date = st.date_input(
        "Selecciona una fecha",
        value=today + timedelta(days=1),
        min_value=today + timedelta(days=1),
        max_value=max_date,
    )

    # ------------------------------------------------------------------ #
    # Step 3 – Available slots
    # ------------------------------------------------------------------ #
    slots = get_available_slots(PROVIDER_ID, selected_date, selected_service["duration_minutes"])

    if not slots:
        st.info("No hay horarios disponibles para esa fecha. Por favor elige otro día.")
        return

    # Display time portion only for readability
    slot_labels = [s.split(" ")[1] for s in slots]
    slot_map = dict(zip(slot_labels, slots))

    selected_label = st.selectbox("Hora disponible", slot_labels)
    selected_slot = slot_map[selected_label]

    # ------------------------------------------------------------------ #
    # Step 4 – Client info
    # ------------------------------------------------------------------ #
    st.markdown("---")
    st.subheader("Tus datos")
    client_name = st.text_input("Nombre completo")
    client_phone = st.text_input("Número de WhatsApp (ej. +573001234567)")
    notes = st.text_area("¿Algo más que debamos saber? (opcional)", height=80)

    # ------------------------------------------------------------------ #
    # Step 5 – Submit
    # ------------------------------------------------------------------ #
    if st.button("Solicitar cita", type="primary", use_container_width=True):
        errors = []
        if not client_name.strip():
            errors.append("Por favor ingresa tu nombre.")
        if not client_phone.strip():
            errors.append("Por favor ingresa tu número de WhatsApp.")
        elif not _validate_phone(client_phone):
            errors.append("El número de teléfono no parece válido.")

        if errors:
            for e in errors:
                st.error(e)
            return

        booking_id = create_booking(
            provider_id=PROVIDER_ID,
            service_id=selected_service["id"],
            client_name=client_name.strip(),
            client_phone=client_phone.strip(),
            requested_datetime=selected_slot,
            duration_minutes=selected_service["duration_minutes"],
            notes=notes.strip(),
        )

        st.success(
            f"¡Solicitud enviada! 🎉  \n"
            f"**Servicio:** {selected_service_name}  \n"
            f"**Fecha y hora:** {selected_slot}  \n"
            f"Te confirmaremos por WhatsApp en breve. (Ref. #{booking_id})"
        )
        st.balloons()
