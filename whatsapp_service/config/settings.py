# config/settings.py — WhatsApp Service for SPJ POS
"""
Configuración central. Lee de variables de entorno o .env.

El módulo desktop de WhatsApp guarda credenciales globales en la tabla
`configuraciones` con prefijo `wa_`:

- wa_meta_phone_id
- wa_meta_token
- wa_verify_token
- wa_microservicio_url

El microservicio debe poder arrancar con `.env`, pero en ejecución debe preferir
la configuración capturada desde el módulo cuando exista.
"""
import os
import sqlite3
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # python-dotenv es dependencia del proyecto, pero no debe impedir el arranque
    # si no está disponible en un entorno mínimo.
    pass

# ── WhatsApp Cloud API ────────────────────────────────────────────────────────
WA_API_VERSION = os.getenv("WA_API_VERSION", "v21.0")
WA_PHONE_NUMBER_ID = os.getenv("WA_PHONE_NUMBER_ID")
WA_ACCESS_TOKEN = os.getenv("WA_ACCESS_TOKEN")
WA_VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN")
WA_APP_SECRET = os.getenv("WA_APP_SECRET", "")

# Internal API key for ERP → microservice calls (notify_router auth)
WA_INTERNAL_API_KEY = os.getenv("WA_INTERNAL_API_KEY", "")

# ── ERP Connection ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent

ERP_DB_PATH = os.getenv(
    "ERP_DB_PATH",
    str(BASE_DIR / "pos_spj_v13.4" / "spj_pos_database.db")
)


def _read_erp_config(key: str, default: str = "") -> str:
    """Lee una clave desde `configuraciones` del ERP.

    El módulo UI usa `WhatsAppConfigRepository.set_config()`, que guarda claves
    como `wa_<key>`. Esta función acepta tanto `verify_token` como
    `wa_verify_token` y devuelve el primer valor encontrado.
    """
    db_path = ERP_DB_PATH
    if not db_path:
        return default
    clave = key if key.startswith("wa_") else f"wa_{key}"
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT valor FROM configuraciones WHERE clave=? LIMIT 1",
            (clave,),
        ).fetchone()
        conn.close()
        if row and row[0]:
            return str(row[0])
    except Exception:
        return default
    return default


def get_meta_phone_number_id() -> str:
    """Phone Number ID: primero módulo ERP, luego .env."""
    return _read_erp_config("meta_phone_id", "") or (WA_PHONE_NUMBER_ID or "")


def get_meta_access_token() -> str:
    """Access Token: primero módulo ERP, luego .env."""
    return _read_erp_config("meta_token", "") or (WA_ACCESS_TOKEN or "")


def get_verify_token() -> str:
    """
    Verify Token: primero módulo ERP, luego .env.

    Esto permite capturar el token desde el panel Meta/Credenciales y que el
    webhook oficial lo use para la validación de Meta.
    """
    return _read_erp_config("verify_token", "") or (WA_VERIFY_TOKEN or "")


def get_wa_api_url(phone_number_id: str = None) -> str:
    """Build Graph API URL lazily to avoid None-interpolation at import time."""
    pid = phone_number_id or get_meta_phone_number_id()
    if not pid:
        raise ValueError(
            "WA_PHONE_NUMBER_ID not configured. "
            "Set it in the WhatsApp module or pass phone_number_id explicitly."
        )
    return f"https://graph.facebook.com/{WA_API_VERSION}/{pid}/messages"


# Legacy alias kept for imports that read WA_API_URL directly.
# Will be None if no Phone Number ID is configured. New code must use
# get_wa_api_url() so it can read the value saved from the module.
_legacy_phone_id = get_meta_phone_number_id()
WA_API_URL: str = (
    f"https://graph.facebook.com/{WA_API_VERSION}/{_legacy_phone_id}/messages"
    if _legacy_phone_id else None
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
