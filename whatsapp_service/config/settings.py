from decimal import Decimal
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
La BD del ERP la resuelve `AppPaths` (`backend/shared/app_paths.py`), la MISMA
resolución que usa el escritorio: desde código fuente es
<repo>/pos_spj_v13.4/data/spj_pos_database.db; instalado, la carpeta de datos
elegida en el instalador. No debe usarse ni crearse otra BD en la raíz del
módulo.

Instalado como servicio local (opcional), las credenciales `.env` y las
conversaciones viven en `<datos>/whatsapp/`, fuera de los archivos que el
instalador reemplaza o desinstala.
"""
import logging
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from backend.shared.app_paths import AppPaths

logger = logging.getLogger("wa.settings")

_APP_PATHS = AppPaths.from_environment()
if _APP_PATHS.is_installed:
    load_dotenv(_APP_PATHS.whatsapp_data_dir / "whatsapp.env", override=False)
else:
    load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)

WA_API_VERSION = os.getenv("WA_API_VERSION", "v21.0")
WA_PHONE_NUMBER_ID = os.getenv("WA_PHONE_NUMBER_ID")
WA_ACCESS_TOKEN = os.getenv("WA_ACCESS_TOKEN")
WA_VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN")
WA_APP_SECRET = os.getenv("WA_APP_SECRET", "")

# Internal API key for ERP → microservice calls (notify_router auth)
WA_INTERNAL_API_KEY = os.getenv("WA_INTERNAL_API_KEY", "")

# ── ERP Connection ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ERP_CANONICAL_DB_PATH = _APP_PATHS.database_path

ERP_DB_PATH = os.getenv(
    "ERP_DB_PATH",
    str(ERP_CANONICAL_DB_PATH)
)


from whatsapp_service.infrastructure.secrets.secret_store import SecretStore


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


MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
MP_WEBHOOK_SECRET = os.getenv("MP_WEBHOOK_SECRET", "")

# ── Rate limiting ─────────────────────────────────────────────────────────────
MAX_MESSAGES_PER_MINUTE = int(os.getenv("MAX_MESSAGES_PER_MINUTE", "15"))
MAX_FAILED_INTENTS = int(os.getenv("MAX_FAILED_INTENTS", "3"))

# ── Conversation ──────────────────────────────────────────────────────────────
CONVERSATION_TIMEOUT_MINUTES = int(os.getenv("CONVERSATION_TIMEOUT_MINUTES", "30"))
CONTEXT_DB_PATH = os.getenv("CONTEXT_DB_PATH", str(
    _APP_PATHS.whatsapp_data_dir / "conversations.db" if _APP_PATHS.is_installed
    else Path(__file__).parent.parent / "data" / "conversations.db"))

# ── Internal API security ─────────────────────────────────────────────────────
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── Fuzzy matching ────────────────────────────────────────────────────────────
FUZZY_MATCH_THRESHOLD = int(os.getenv("FUZZY_MATCH_THRESHOLD", "2"))  # Max Levenshtein distance

# ── Ollama / DeepSeek local (Nivel 3 NLP) ────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:8b")
OLLAMA_TIMEOUT = int(Decimal(os.getenv("OLLAMA_TIMEOUT", "15") or "15"))  # Segundos


# ── Environment helpers (FASE 2) ─────────────────────────────────────────────
def _raw_app_env() -> str:
    return (os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "development").strip().lower()


def get_app_env() -> str:
    """
    Entorno de ejecución normalizado.
    Prioridad: APP_ENV -> ENVIRONMENT -> development.
    """
    raw = _raw_app_env()
    if raw in {"prod", "production"}:
        return "production"
    if raw in {"test", "testing"}:
        return "test"
    return "development"


def is_production() -> bool:
    return get_app_env() == "production"


def is_test() -> bool:
    return get_app_env() == "test"


# ── Firma de webhooks (SDLC-WA-002) ──────────────────────────────────────────
# Las estaciones instaladas nunca fijan APP_ENV y corren en `development`, así
# que el entorno no puede decidir si un webhook se acepta sin firma: eso exige
# un opt-in explícito, ignorado en producción y en estación instalada.
_UNSIGNED_OPT_IN_VAR = "WA_ALLOW_UNSIGNED_WEBHOOKS"
_UNSIGNED_OPT_IN_VALUES = frozenset({"1", "true", "yes"})
_KNOWN_APP_ENVS = frozenset({"production", "prod", "test", "testing", "development", "dev"})
_DEFAULT_MP_SIGNATURE_MAX_AGE_SECONDS = 300


def _unsigned_opt_in_requested() -> bool:
    return os.getenv(_UNSIGNED_OPT_IN_VAR, "").strip().lower() in _UNSIGNED_OPT_IN_VALUES


def _unsigned_opt_in_blocker() -> str | None:
    """Motivo por el que esta máquina no admite el opt-in; None si lo admite."""
    if is_production():
        return "producción"
    if _APP_PATHS.is_installed:
        return "estación instalada"
    return None


def allow_unsigned_webhooks() -> bool:
    """True sólo con opt-in explícito en una máquina de desarrollo."""
    return _unsigned_opt_in_requested() and _unsigned_opt_in_blocker() is None


def unsigned_webhook_rejection(secret_name: str) -> str:
    """Texto único del `error` de un 503 por falta de secreto. Sólo nombres."""
    text = (
        f"{secret_name} no configurado; webhook rechazado sin procesar. "
        "Configúralo desde el módulo WhatsApp o en el archivo de entorno del servicio."
    )
    blocker = _unsigned_opt_in_blocker()
    if _unsigned_opt_in_requested() and blocker:
        return f"{text} {_UNSIGNED_OPT_IN_VAR} se ignoró por {blocker}."
    return (
        f"{text} Sólo en una máquina de desarrollo se puede aceptar sin firma "
        f"con {_UNSIGNED_OPT_IN_VAR}=1."
    )


def describe_webhook_security() -> dict:
    """Estado de la firma de webhooks para el arranque; nunca lleva secretos."""
    raw_env = _raw_app_env()
    return {
        "env": get_app_env(),
        "installed": _APP_PATHS.is_installed,
        "unsigned_allowed": allow_unsigned_webhooks(),
        "unrecognized_env_value": raw_env if raw_env and raw_env not in _KNOWN_APP_ENVS else None,
        "opt_in_ignored_reason": _unsigned_opt_in_blocker() if _unsigned_opt_in_requested() else None,
    }


def get_mp_signature_max_age_seconds() -> int:
    """Ventana anti-replay de MercadoPago, leída en cada llamada."""
    raw = os.getenv("MP_SIGNATURE_MAX_AGE_SECONDS", "").strip()
    if not raw:
        return _DEFAULT_MP_SIGNATURE_MAX_AGE_SECONDS
    try:
        seconds = int(raw)
    except ValueError:
        seconds = 0
    if seconds <= 0:
        logger.warning(
            "MP_SIGNATURE_MAX_AGE_SECONDS inválido (%r); se usa %d.",
            raw, _DEFAULT_MP_SIGNATURE_MAX_AGE_SECONDS,
        )
        return _DEFAULT_MP_SIGNATURE_MAX_AGE_SECONDS
    return seconds


def _read_erp_config(key: str, default: str = "") -> str:
    return _secret_store.get(key, default)
