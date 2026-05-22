# config/settings.py — WhatsApp Service for SPJ POS
"""
Configuración central. Lee de variables de entorno o .env
"""
import os
from pathlib import Path

# ── WhatsApp Cloud API ────────────────────────────────────────────────────────
WA_API_VERSION = os.getenv("WA_API_VERSION", "v21.0")
WA_PHONE_NUMBER_ID = os.getenv("WA_PHONE_NUMBER_ID")
WA_ACCESS_TOKEN = os.getenv("WA_ACCESS_TOKEN")
WA_VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN")

# Internal API key for ERP → microservice calls (notify_router auth)
WA_INTERNAL_API_KEY = os.getenv("WA_INTERNAL_API_KEY", "")


def get_wa_api_url(phone_number_id: str = None) -> str:
    """Build Graph API URL lazily to avoid None-interpolation at import time."""
    pid = phone_number_id or WA_PHONE_NUMBER_ID
    if not pid:
        raise ValueError(
            "WA_PHONE_NUMBER_ID not configured. "
            "Set it in .env or pass phone_number_id explicitly."
        )
    return f"https://graph.facebook.com/{WA_API_VERSION}/{pid}/messages"


# Legacy alias kept for imports that read WA_API_URL directly.
# Will be None if WA_PHONE_NUMBER_ID is not set — callers must use get_wa_api_url().
WA_API_URL: str = (
    f"https://graph.facebook.com/{WA_API_VERSION}/{WA_PHONE_NUMBER_ID}/messages"
    if WA_PHONE_NUMBER_ID else None
)

# ── ERP Connection ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent

ERP_DB_PATH = os.getenv(
    "ERP_DB_PATH",
    str(BASE_DIR / "pos_spj_v13.4" / "spj_pos_database.db")
)

# ── MercadoPago ───────────────────────────────────────────────────────────────
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
MP_WEBHOOK_SECRET = os.getenv("MP_WEBHOOK_SECRET", "")

# ── Rate limiting ─────────────────────────────────────────────────────────────
MAX_MESSAGES_PER_MINUTE = int(os.getenv("MAX_MESSAGES_PER_MINUTE", "15"))
MAX_FAILED_INTENTS = int(os.getenv("MAX_FAILED_INTENTS", "3"))

# ── Conversation ──────────────────────────────────────────────────────────────
CONVERSATION_TIMEOUT_MINUTES = int(os.getenv("CONVERSATION_TIMEOUT_MINUTES", "30"))
CONTEXT_DB_PATH = os.getenv("CONTEXT_DB_PATH", str(Path(__file__).parent.parent / "data" / "conversations.db"))

# ── Internal API security ─────────────────────────────────────────────────────
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── Fuzzy matching ────────────────────────────────────────────────────────────
FUZZY_MATCH_THRESHOLD = int(os.getenv("FUZZY_MATCH_THRESHOLD", "2"))  # Max Levenshtein distance

# ── Ollama / DeepSeek local (Nivel 3 NLP) ────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:8b")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "15.0"))  # Segundos
