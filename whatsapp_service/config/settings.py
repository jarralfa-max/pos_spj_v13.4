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

IMPORTANTE:
La BD canónica del ERP está en:
<repo>/pos_spj_v13.4/data/spj_pos_database.db

No debe usarse ni crearse otra BD en la raíz del módulo.
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
ERP_CANONICAL_DB_PATH = BASE_DIR / "pos_spj_v13.4" / "data" / "spj_pos_database.db"

ERP_DB_PATH = os.getenv(
    "ERP_DB_PATH",
    str(ERP_CANONICAL_DB_PATH)
)


def _read_erp_config(key: str, default: str = "") -> str:
    """Lee una clave desde `configuraciones` del ERP.

    El módulo UI usa `WhatsAppConfigRepository.set_config()`, que guarda claves
    como `wa_<key>`. Esta función acepta tanto `verify_token` como
    `wa_verify_token` y devuelve el primer valor encontrado.

    Conservada tal cual (sin cache) para no romper otros llamadores directos;
    las funciones `get_*` de abajo usan en su lugar `SecretStore`, que aplica
    el mismo patrón de lectura pero con cache TTL en proceso (WA-1, Hallazgo 1
    de whatsapp_security_audit.md).
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


# ── SecretStore (WA-1) ────────────────────────────────────────────────────────
# Centraliza la lectura de `configuraciones` con cache TTL en proceso, para no
# reabrir SQLite en cada llamada a send_message/webhook (Hallazgo 1 del audit).
# El path de la BD se resuelve vía lambda (no valor capturado) para que un
# cambio de ERP_DB_PATH en tiempo de ejecución (p. ej. en tests) se refleje.
#
# `infrastructure` es un nombre de paquete top-level que TAMBIÉN existe en
# `pos_spj_v13.4/infrastructure/` (arquitectura objetivo del ERP). Si algún
# import previo en el mismo proceso ya resolvió `infrastructure` contra ESE
# paquete (p. ej. la suite de tests del ERP y la de este microservicio
# comparten proceso pytest), un `from infrastructure.secrets... import X`
# normal reusaría el `infrastructure` YA CACHEADO en sys.modules — insertar
# rutas en sys.path no ayuda una vez que el nombre del paquete padre ya está
# cacheado (mismo tipo de colisión de nombre top-level que ya documenta el
# propio main.py para el paquete `application`). Se carga por RUTA DE
# ARCHIVO explícita, bajo una clave de sys.modules que nunca colisiona, para
# evitar el problema por completo en vez de depender del orden de sys.path.
def _load_secret_store_class():
    import importlib.util
    import sys as _sys

    cache_key = "_wa_infra_secret_store"
    cached = _sys.modules.get(cache_key)
    if cached is not None:
        return cached.SecretStore

    module_path = Path(__file__).resolve().parent.parent / "infrastructure" / "secrets" / "secret_store.py"
    spec = importlib.util.spec_from_file_location(cache_key, str(module_path))
    module = importlib.util.module_from_spec(spec)
    _sys.modules[cache_key] = module
    spec.loader.exec_module(module)
    return module.SecretStore


SecretStore = _load_secret_store_class()

_secret_store = SecretStore(lambda: ERP_DB_PATH)


def get_secret_store():
    """Devuelve el `SecretStore` singleton del proceso (WA-1).

    Accesor público para que `bootstrap/composition_root.py` (WA-4) y
    cualquier otro consumidor reutilicen la MISMA instancia (y su cache
    TTL) en vez de construir una segunda — un solo `SecretStore` por
    proceso, mismo criterio de fuente única que el resto del canal.
    """
    return _secret_store


def get_meta_phone_number_id() -> str:
    """Phone Number ID: primero módulo ERP, luego .env."""
    return _secret_store.get("meta_phone_id", WA_PHONE_NUMBER_ID or "")


def get_meta_access_token() -> str:
    """Access Token: primero módulo ERP, luego .env."""
    return _secret_store.get("meta_token", WA_ACCESS_TOKEN or "")


def get_verify_token() -> str:
    """
    Verify Token: primero módulo ERP, luego .env.

    Esto permite capturar el token desde el panel Meta/Credenciales y que el
    webhook oficial lo use para la validación de Meta.
    """
    return _secret_store.get("verify_token", WA_VERIFY_TOKEN or "")

def get_internal_api_key() -> str:
    """Clave interna ERP ↔ microservicio: primero módulo ERP, luego .env."""
    fallback = (WA_INTERNAL_API_KEY or "") or (os.getenv("INTERNAL_API_KEY", "") or "")
    return _secret_store.get("internal_api_key", fallback)


def get_app_secret() -> str:
    """Secreto de firma HMAC de Meta (`X-Hub-Signature-256`): primero módulo
    ERP (`wa_app_secret`), luego `.env` (`WA_APP_SECRET`).

    Antes de WA-1 este valor solo se leía de `.env` (Hallazgo 2 del audit),
    lo que dejaba el webhook fail-open si se configuraba todo desde la UI
    pero no se tocaba el `.env`.
    """
    return _secret_store.get("app_secret", WA_APP_SECRET or "")


def get_mp_webhook_secret() -> str:
    """Secreto de firma de MercadoPago (`X-Signature`): primero módulo ERP
    (`wa_mp_webhook_secret`), luego `.env` (`MP_WEBHOOK_SECRET`).

    Misma corrección que `get_app_secret()` — antes solo se leía de `.env`.
    """
    return _secret_store.get("mp_webhook_secret", MP_WEBHOOK_SECRET or "")

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


# ── Environment helpers (FASE 2) ─────────────────────────────────────────────
def get_app_env() -> str:
    """
    Entorno de ejecución normalizado.
    Prioridad: APP_ENV -> ENVIRONMENT -> development.
    """
    raw = (os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "development").strip().lower()
    if raw in {"prod", "production"}:
        return "production"
    if raw in {"test", "testing"}:
        return "test"
    return "development"


def is_production() -> bool:
    return get_app_env() == "production"


def is_test() -> bool:
    return get_app_env() == "test"
