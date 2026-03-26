"""
Provider admin panel.

Sections (tabs):
  1. Solicitudes pendientes  – confirm / reject pending bookings
  2. Agenda confirmada       – read-only view of upcoming confirmed bookings
  3. Horarios de trabajo     – manage weekly availability rules
  4. Bloqueos                – manage one-off blocked windows
"""

from datetime import date, datetime, timedelta

import streamlit as st

from config import DAYS_AHEAD, PROVIDER_ID
from services.whatsapp import notify_booking_confirmed, notify_booking_rejected
from db.database import (
    add_blocked_window,
    delete_blocked_window,
    deactivate_availability_rule,
    get_all_blocked_windows,
    get_availability_rules,
    get_confirmed_bookings,
    get_pending_bookings,
    init_db,
    update_booking_status,
    upsert_availability_rule,
)

DAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

# Simple in-memory PIN guard (no session secret needed for MVP)
ADMIN_PIN = "1234"


def _check_auth() -> bool:
    if st.session_state.get("admin_authenticated"):
        return True
    st.title("Panel de administración 🔒")
    pin = st.text_input("PIN de acceso", type="password", max_chars=8)
    if st.button("Entrar"):
        if pin == ADMIN_PIN:
            st.session_state["admin_authenticated"] = True
            st.rerun()
        else:
            st.error("PIN incorrecto.")
    return False


# ---------------------------------------------------------------------------
# Tab 1 – Pending bookings
# ---------------------------------------------------------------------------

def _tab_pending():
    st.subheader("Solicitudes pendientes")
    pending = get_pending_bookings(PROVIDER_ID)

    if not pending:
        st.info("No hay solicitudes pendientes.")
        return

    for b in pending:
        with st.expander(
            f"#{b['id']} · {b['client_name']} · {b['requested_datetime']} · {b['service_name']}",
            expanded=True,
        ):
            col1, col2 = st.columns(2)
            col1.markdown(f"**Cliente:** {b['client_name']}")
            col1.markdown(f"**WhatsApp:** {b['client_phone']}")
            col2.markdown(f"**Servicio:** {b['service_name']}")
            col2.markdown(f"**Fecha/hora:** {b['requested_datetime']}")
            col2.markdown(f"**Duración:** {b['duration_minutes']} min")
            if b["notes"]:
                st.markdown(f"**Notas:** {b['notes']}")

            c1, c2 = st.columns(2)
            if c1.button("✅ Confirmar", key=f"confirm_{b['id']}", use_container_width=True):
                update_booking_status(b["id"], "confirmed")
                result = notify_booking_confirmed(b)
                if result.sent:
                    st.success("Cita confirmada · cliente notificado por WhatsApp ✅")
                else:
                    st.success("Cita confirmada.")
                    if result.wa_link:
                        st.markdown(
                            f"[📲 Notificar al cliente por WhatsApp]({result.wa_link})"
                        )
                st.rerun()
            if c2.button("❌ Rechazar", key=f"reject_{b['id']}", use_container_width=True):
                update_booking_status(b["id"], "rejected")
                result = notify_booking_rejected(b)
                if result.sent:
                    st.warning("Cita rechazada · cliente notificado por WhatsApp ✅")
                else:
                    st.warning("Cita rechazada.")
                    if result.wa_link:
                        st.markdown(
                            f"[📲 Notificar al cliente por WhatsApp]({result.wa_link})"
                        )
                st.rerun()


# ---------------------------------------------------------------------------
# Tab 2 – Confirmed agenda
# ---------------------------------------------------------------------------

def _tab_agenda():
    st.subheader("Agenda confirmada")
    bookings = get_confirmed_bookings(PROVIDER_ID)

    if not bookings:
        st.info("No hay citas confirmadas próximas.")
        return

    rows = []
    for b in bookings:
        rows.append({
            "Fecha/hora": b["requested_datetime"],
            "Servicio": b["service_name"],
            "Cliente": b["client_name"],
            "WhatsApp": b["client_phone"],
            "Duración": f"{b['duration_minutes']} min",
            "Notas": b["notes"] or "",
        })

    st.dataframe(rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Tab 3 – Availability rules
# ---------------------------------------------------------------------------

def _tab_availability():
    st.subheader("Horarios de trabajo")
    st.caption("Define los horarios habituales por día de la semana.")

    rules = get_availability_rules(PROVIDER_ID)
    rule_by_day = {r["day_of_week"]: r for r in rules if r["is_active"]}

    def _fmt(t: str) -> str:
        h, m = map(int, t.split(":"))
        period = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12}:{m:02d} {period}"

    st.markdown("#### Horarios actuales")
    if not rule_by_day:
        st.info("Aún no hay horarios configurados.")
    else:
        today = date.today()
        for dow, rule in sorted(rule_by_day.items()):
            days_ahead = (dow - today.weekday()) % 7
            next_date = today + timedelta(days=days_ahead)
            date_label = next_date.strftime("%-d %b")
            col1, col2, col3 = st.columns([3, 3, 1])
            col1.write(f"**{DAY_NAMES[dow]}** {date_label}  ·  {_fmt(rule['start_time'])} – {_fmt(rule['end_time'])}")
            if col3.button("Eliminar", key=f"del_rule_{rule['id']}"):
                deactivate_availability_rule(rule["id"])
                st.rerun()

    st.markdown("---")
    st.markdown("#### Agregar / actualizar horario")
    with st.form("add_rule_form", clear_on_submit=True):
        day = st.selectbox("Día", options=list(range(7)), format_func=lambda d: DAY_NAMES[d])
        c1, c2 = st.columns(2)
        start = c1.time_input("Hora de inicio", value=datetime.strptime("09:00", "%H:%M").time())
        end = c2.time_input("Hora de fin", value=datetime.strptime("17:00", "%H:%M").time())
        submitted = st.form_submit_button("Guardar horario", use_container_width=True)

    if submitted:
        if start >= end:
            st.error("La hora de inicio debe ser antes de la hora de fin.")
        else:
            upsert_availability_rule(
                PROVIDER_ID, day,
                start.strftime("%H:%M"),
                end.strftime("%H:%M"),
            )
            st.success(f"Horario guardado para {DAY_NAMES[day]}.")
            st.rerun()


# ---------------------------------------------------------------------------
# Tab 4 – Blocked windows
# ---------------------------------------------------------------------------

def _tab_blocked():
    st.subheader("Bloqueos de horario")
    st.caption("Bloquea fechas u horas específicas (vacaciones, descansos, etc.).")

    windows = get_all_blocked_windows(PROVIDER_ID)

    st.markdown("#### Bloqueos existentes")
    if not windows:
        st.info("No hay bloqueos configurados.")
    else:
        for w in windows:
            col1, col2 = st.columns([5, 1])
            label = f"**{w['date']}** · {_fmt(w['start_time'])} – {_fmt(w['end_time'])}"
            if w["reason"]:
                label += f" · _{w['reason']}_"
            col1.markdown(label)
            if col2.button("Eliminar", key=f"del_bw_{w['id']}"):
                delete_blocked_window(w["id"])
                st.rerun()

    st.markdown("---")
    st.markdown("#### Agregar bloqueo")
    today = date.today()
    with st.form("add_block_form", clear_on_submit=True):
        block_date = st.date_input(
            "Fecha",
            value=today,
            min_value=today,
            max_value=today + timedelta(days=DAYS_AHEAD * 2),
        )
        c1, c2 = st.columns(2)
        block_start = c1.time_input(
            "Desde", value=datetime.strptime("00:00", "%H:%M").time()
        )
        block_end = c2.time_input(
            "Hasta", value=datetime.strptime("23:59", "%H:%M").time()
        )
        reason = st.text_input("Motivo (opcional)")
        submitted = st.form_submit_button("Guardar bloqueo", use_container_width=True)

    if submitted:
        if block_start >= block_end:
            st.error("La hora de inicio debe ser antes de la hora de fin.")
        else:
            add_blocked_window(
                PROVIDER_ID,
                block_date.strftime("%Y-%m-%d"),
                block_start.strftime("%H:%M"),
                block_end.strftime("%H:%M"),
                reason.strip(),
            )
            st.success("Bloqueo guardado.")
            st.rerun()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def render():
    init_db()

    if not _check_auth():
        return

    st.title("Panel de administración 💅")

    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 Solicitudes",
        "📅 Agenda",
        "🕐 Horarios",
        "🚫 Bloqueos",
    ])

    with tab1:
        _tab_pending()
    with tab2:
        _tab_agenda()
    with tab3:
        _tab_availability()
    with tab4:
        _tab_blocked()
