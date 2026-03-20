import os

PROVIDER_ID = 1
TIMEZONE = "America/Bogota"
DAYS_AHEAD = 30
SLOT_INTERVAL_MINUTES = 30

# ---------------------------------------------------------------------------
# WhatsApp / Twilio  (set these as environment variables or in
# .streamlit/secrets.toml for Streamlit Cloud deployments)
# ---------------------------------------------------------------------------

# Provider's WhatsApp number in E.164 format, e.g. "+573001234567".
# Used to notify the provider when a new booking arrives.
PROVIDER_PHONE: str = os.getenv("PROVIDER_PHONE", "")

# Twilio credentials — leave empty to disable auto-send (wa.me links are
# shown as manual fallback in the UI).
TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")

# Twilio WhatsApp sender.  Use the sandbox number while testing:
# whatsapp:+14155238886  (requires clients to opt-in via the sandbox).
# Switch to your approved WhatsApp Business number for production.
TWILIO_WA_FROM: str = os.getenv("TWILIO_WA_FROM", "whatsapp:+14155238886")
