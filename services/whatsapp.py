"""
WhatsApp notification helpers.

If Twilio credentials are configured (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN /
TWILIO_WA_FROM env vars), messages are sent automatically via the Twilio
WhatsApp API.  When credentials are absent (local dev) the functions return a
wa.me deep-link that the UI can render as a manual-send button — so the flow
never crashes.

High-level API
--------------
  notify_new_booking(booking)      → alert provider about a new pending request
  notify_booking_confirmed(booking) → tell client their booking is confirmed
  notify_booking_rejected(booking)  → tell client their booking was rejected

Each function returns a NotifyResult(sent, wa_link, error).
"""

import logging
import urllib.parse
from dataclasses import dataclass, field

from config import PROVIDER_PHONE, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WA_FROM

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class NotifyResult:
    sent: bool          # True  → Twilio accepted the message
    wa_link: str        # wa.me deep-link, always populated for fallback
    error: str = field(default="")   # non-empty when sent=False due to error


# ---------------------------------------------------------------------------
# Core send
# ---------------------------------------------------------------------------

def _wa_link(phone: str, body: str) -> str:
    """Build a wa.me URL that pre-fills the message body in WhatsApp."""
    clean = phone.strip().lstrip("+").replace(" ", "").replace("-", "")
    return f"https://wa.me/{clean}?text={urllib.parse.quote(body)}"


def send_whatsapp(to_phone: str, body: str) -> NotifyResult:
    """
    Attempt to send *body* to *to_phone* via Twilio WhatsApp.

    If Twilio credentials are not configured, or the send fails, the function
    logs a warning and returns NotifyResult(sent=False, ...) with the wa_link
    filled in so the caller can show a manual fallback.
    """
    to_phone = (to_phone or "").strip()
    link = _wa_link(to_phone, body) if to_phone else ""

    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and to_phone):
        return NotifyResult(sent=False, wa_link=link)

    try:
        from twilio.rest import Client  # lazy import — keeps startup fast

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            from_=TWILIO_WA_FROM,
            to=f"whatsapp:{to_phone}",
            body=body,
        )
        log.info("WhatsApp sent to %s", to_phone)
        return NotifyResult(sent=True, wa_link=link)
    except Exception as exc:
        log.warning("WhatsApp send failed to %s: %s", to_phone, exc)
        return NotifyResult(sent=False, wa_link=link, error=str(exc))


# ---------------------------------------------------------------------------
# High-level notification helpers
# ---------------------------------------------------------------------------

def notify_new_booking(booking: dict) -> NotifyResult:
    """
    Notify the *provider* that a new booking request has arrived.

    Expected booking keys: id, client_name, client_phone,
                           service_name, requested_datetime.
    """
    if not PROVIDER_PHONE:
        return NotifyResult(sent=False, wa_link="")

    body = (
        f"📋 Nueva solicitud de cita:\n"
        f"• Cliente: {booking['client_name']}\n"
        f"• Servicio: {booking['service_name']}\n"
        f"• Fecha/hora: {booking['requested_datetime']}\n"
        f"• WhatsApp cliente: {booking['client_phone']}\n"
        f"• Ref. #{booking['id']}\n\n"
        f"Abre el panel de admin para confirmar o rechazar."
    )
    return send_whatsapp(PROVIDER_PHONE, body)


def notify_booking_confirmed(booking: dict) -> NotifyResult:
    """
    Notify the *client* that their booking has been confirmed.

    Expected booking keys: client_phone, service_name,
                           requested_datetime, duration_minutes.
    """
    body = (
        f"✅ ¡Tu cita fue confirmada!\n"
        f"• Servicio: {booking['service_name']}\n"
        f"• Fecha y hora: {booking['requested_datetime']}\n"
        f"• Duración: {booking['duration_minutes']} min\n\n"
        f"Te esperamos. Si necesitas cancelar escríbenos."
    )
    return send_whatsapp(booking["client_phone"], body)


def notify_booking_rejected(booking: dict) -> NotifyResult:
    """
    Notify the *client* that their booking could not be accommodated.

    Expected booking keys: client_phone, service_name, requested_datetime.
    """
    body = (
        f"😔 Lo sentimos, no podemos confirmar tu cita para\n"
        f"{booking['requested_datetime']} ({booking['service_name']}).\n\n"
        f"Por favor elige otro horario. ¡Gracias por tu comprensión!"
    )
    return send_whatsapp(booking["client_phone"], body)
