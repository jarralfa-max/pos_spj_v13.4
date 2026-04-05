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
WA_VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN", "spj_pos_webhook_2025")
WA_API_URL = f"https://graph.facebook.com/{WA_API_VERSION}/{WA_PHONE_NUMBER_ID}/messages"

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

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── Fuzzy matching ────────────────────────────────────────────────────────────
FUZZY_MATCH_THRESHOLD = int(os.getenv("FUZZY_MATCH_THRESHOLD", "2"))  # Max Levenshtein distance

# ── Ollama / DeepSeek local (Nivel 3 NLP) ────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:8b")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "15.0"))  # Segundos
