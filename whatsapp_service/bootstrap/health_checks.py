# bootstrap/health_checks.py — WA-4 (§58 del prompt maestro)
"""
Agregador de health checks del canal WhatsApp. Cada check individual
retorna un `HealthCheckResult` (name, status, detail) — `detail` nunca
lleva un secreto, ruta local completa, ni ningún dato sensible (§58:
"El endpoint no debe devolver secretos, rutas locales ni detalles
sensibles").

Cubre hoy solo lo que existe: base de datos, esquema del canal (WA-3) y
disponibilidad de secretos críticos (WA-1). Los subsistemas que otras
fases todavía no construyen (Provider Gateway, inbox/outbox worker, API
ERP) se reportan explícitamente como UNKNOWN — nunca se fingen HEALTHY
solo para que la lista quede completa.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


# Orden de severidad para calcular el estado global — el peor check gana,
# pero UNKNOWN no debe enmascarar un UNHEALTHY real ni viceversa.
_SEVERITY_ORDER = {
    HealthStatus.HEALTHY: 0,
    HealthStatus.UNKNOWN: 1,
    HealthStatus.DEGRADED: 2,
    HealthStatus.UNHEALTHY: 3,
}


@dataclass(frozen=True)
class HealthCheckResult:
    name: str
    status: HealthStatus
    detail: str = ""


def check_database(root) -> HealthCheckResult:
    try:
        conn = root.registry.get("whatsapp_db_connection")
        conn.execute("SELECT 1").fetchone()
        return HealthCheckResult("database", HealthStatus.HEALTHY)
    except Exception:
        return HealthCheckResult("database", HealthStatus.UNHEALTHY, "conexión no responde")


def check_schema(root) -> HealthCheckResult:
    """Verifica que las 12 tablas canónicas del canal (migración 243)
    existan en la base conectada."""
    try:
        from backend.infrastructure.db.schema.whatsapp_schema import WHATSAPP_TABLES

        conn = root.registry.get("whatsapp_db_connection")
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = [t for t in WHATSAPP_TABLES if t not in existing]
        if not missing:
            return HealthCheckResult("schema", HealthStatus.HEALTHY)
        return HealthCheckResult(
            "schema",
            HealthStatus.UNHEALTHY,
            f"faltan {len(missing)} tabla(s) — ¿corrió la migración 243?",
        )
    except Exception:
        return HealthCheckResult("schema", HealthStatus.UNKNOWN, "no se pudo verificar")


def check_secrets(root) -> HealthCheckResult:
    """Espeja el gate de arranque de producción (WA-1,
    `main.py::_assert_production_secrets_configured`) como un check de
    salud continuo, no solo un chequeo en el instante de arranque."""
    from config.settings import (
        get_app_secret,
        get_internal_api_key,
        get_meta_access_token,
        get_meta_phone_number_id,
        get_verify_token,
        is_production,
    )

    required = {
        "meta_access_token": get_meta_access_token(),
        "meta_phone_number_id": get_meta_phone_number_id(),
        "verify_token": get_verify_token(),
        "app_secret": get_app_secret(),
        "internal_api_key": get_internal_api_key(),
    }
    missing = [name for name, value in required.items() if not value]
    if not missing:
        return HealthCheckResult("secrets", HealthStatus.HEALTHY)
    if is_production():
        return HealthCheckResult(
            "secrets", HealthStatus.UNHEALTHY, f"faltan {len(missing)} secreto(s) en producción"
        )
    return HealthCheckResult(
        "secrets", HealthStatus.DEGRADED, f"faltan {len(missing)} secreto(s) (modo desarrollo)"
    )


def check_provider_gateway(root) -> HealthCheckResult:
    """WA-5: `root.provider_gateway.health_check()` es un ping real y
    síncrono contra la Graph API (`GET /{phone_number_id}`) — no un stub.

    Si los secretos de Meta no están configurados, `check_secrets` ya lo
    reporta (DEGRADED fuera de producción, UNHEALTHY en producción) — este
    check NO repite esa misma señal con severidad distinta; reporta
    UNKNOWN con una nota. Solo pasa a UNHEALTHY cuando los secretos SÍ
    están configurados pero el ping real a la Graph API igual falla (token
    revocado, phone_number_id incorrecto, sin red) — una señal
    genuinamente nueva que ningún otro check detecta.
    """
    from config.settings import get_meta_access_token, get_meta_phone_number_id

    if not (get_meta_access_token() and get_meta_phone_number_id()):
        return HealthCheckResult(
            "provider_gateway", HealthStatus.UNKNOWN, "sin configurar — ver check 'secrets'"
        )

    try:
        gateway = root.provider_gateway
        healthy = gateway.health_check()
    except Exception:
        return HealthCheckResult("provider_gateway", HealthStatus.UNHEALTHY, "excepción durante el ping")

    if healthy:
        return HealthCheckResult("provider_gateway", HealthStatus.HEALTHY)
    return HealthCheckResult("provider_gateway", HealthStatus.UNHEALTHY, "ping a la Graph API falló")


# Umbrales de backlog — no calibrados contra tráfico real todavía (no hay
# ninguno en producción vía esta ruta nueva aún); punto de partida
# conservador, documentado para ajustarse cuando exista tráfico real.
_INBOX_DEGRADED_PENDING = 50
_INBOX_UNHEALTHY_PENDING = 500
_INBOX_DEGRADED_AGE_SECONDS = 5 * 60
_INBOX_UNHEALTHY_AGE_SECONDS = 60 * 60


def check_inbox_queue(root) -> HealthCheckResult:
    """WA-6: profundidad y antigüedad real de `whatsapp_inbox` — **no**
    confirma que un worker esté corriendo en un loop/hilo activo (eso es
    una decisión de despliegue fuera de alcance de esta fase, ver
    `infrastructure/webhooks/inbox_worker.py`); solo confirma que la cola
    es consultable y no está acumulando un backlog anormal."""
    try:
        conn = root.registry.get("whatsapp_db_connection")
        row = conn.execute(
            "SELECT COUNT(*), MIN(created_at) FROM whatsapp_inbox "
            "WHERE status IN ('PENDING','RETRY')"
        ).fetchone()
    except Exception:
        return HealthCheckResult("inbox_worker", HealthStatus.UNKNOWN, "no se pudo consultar la cola")

    pending_count = row[0] or 0
    oldest_created_at = row[1]

    age_seconds = 0.0
    if oldest_created_at:
        from datetime import datetime, timezone

        oldest = datetime.fromisoformat(oldest_created_at)
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - oldest).total_seconds()

    if pending_count >= _INBOX_UNHEALTHY_PENDING or age_seconds >= _INBOX_UNHEALTHY_AGE_SECONDS:
        return HealthCheckResult(
            "inbox_worker", HealthStatus.UNHEALTHY, f"{pending_count} pendientes, el más viejo con {int(age_seconds)}s"
        )
    if pending_count >= _INBOX_DEGRADED_PENDING or age_seconds >= _INBOX_DEGRADED_AGE_SECONDS:
        return HealthCheckResult(
            "inbox_worker", HealthStatus.DEGRADED, f"{pending_count} pendientes, el más viejo con {int(age_seconds)}s"
        )
    return HealthCheckResult("inbox_worker", HealthStatus.HEALTHY, f"{pending_count} pendientes")


_OUTBOX_DEGRADED_PENDING = 50
_OUTBOX_UNHEALTHY_PENDING = 500
_OUTBOX_DEGRADED_AGE_SECONDS = 5 * 60
_OUTBOX_UNHEALTHY_AGE_SECONDS = 60 * 60


def check_outbox_queue(root) -> HealthCheckResult:
    """WA-17 — mismo criterio que `check_inbox_queue` (WA-6), en sentido
    saliente: profundidad/antigüedad de `whatsapp_outbox`, no confirma un
    dispatcher corriendo en loop."""
    try:
        conn = root.registry.get("whatsapp_db_connection")
        row = conn.execute(
            "SELECT COUNT(*), MIN(created_at) FROM whatsapp_outbox WHERE status='PENDING'"
        ).fetchone()
    except Exception:
        return HealthCheckResult("outbox_worker", HealthStatus.UNKNOWN, "no se pudo consultar la cola")

    pending_count = row[0] or 0
    oldest_created_at = row[1]

    age_seconds = 0.0
    if oldest_created_at:
        from datetime import datetime, timezone

        oldest = datetime.fromisoformat(oldest_created_at)
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - oldest).total_seconds()

    if pending_count >= _OUTBOX_UNHEALTHY_PENDING or age_seconds >= _OUTBOX_UNHEALTHY_AGE_SECONDS:
        return HealthCheckResult(
            "outbox_worker", HealthStatus.UNHEALTHY,
            f"{pending_count} pendientes, el más viejo con {int(age_seconds)}s",
        )
    if pending_count >= _OUTBOX_DEGRADED_PENDING or age_seconds >= _OUTBOX_DEGRADED_AGE_SECONDS:
        return HealthCheckResult(
            "outbox_worker", HealthStatus.DEGRADED,
            f"{pending_count} pendientes, el más viejo con {int(age_seconds)}s",
        )
    return HealthCheckResult("outbox_worker", HealthStatus.HEALTHY, f"{pending_count} pendientes")


def check_erp_api(root) -> HealthCheckResult:
    """WA-9 dejó este check pendiente (§8) — nunca se actualizó cuando
    WA-9 construyó los clientes ERP reales. Corregido aquí, encontrado al
    hacer el smoke test de WA-17/WA-18: reporta si `CompositionRoot`
    resolvió un `ERPBridge` real (WA-9) o degradó a `UnavailableErpClient`
    (típico sin el esquema legacy — ver `_try_build_erp_bridge`)."""
    from infrastructure.erp_clients.unavailable_client import UnavailableErpClient

    try:
        client = root.customers
    except Exception:
        return HealthCheckResult("erp_api", HealthStatus.UNKNOWN, "no se pudo resolver el cliente ERP")

    if isinstance(client, UnavailableErpClient):
        return HealthCheckResult(
            "erp_api", HealthStatus.DEGRADED, "sin ERPBridge real (esquema legacy no disponible)"
        )
    return HealthCheckResult("erp_api", HealthStatus.HEALTHY)


def run_all_checks(root) -> List[HealthCheckResult]:
    return [
        check_database(root),
        check_schema(root),
        check_secrets(root),
        check_provider_gateway(root),
        check_inbox_queue(root),
        check_outbox_queue(root),
        check_erp_api(root),
    ]


def overall_status(results: List[HealthCheckResult]) -> HealthStatus:
    if not results:
        return HealthStatus.UNKNOWN
    return max(results, key=lambda r: _SEVERITY_ORDER[r.status]).status


def build_health_response(root) -> dict:
    """Cuerpo de respuesta de `/health` — usado tanto por la integración
    mínima en el `main.py` en vivo como por la app nueva de
    `application_factory.py`. Extraído como función standalone,
    testeable sin levantar FastAPI (mismo criterio que
    `main.py::_assert_production_secrets_configured`, WA-1)."""
    results = run_all_checks(root)
    return {
        "status": overall_status(results).value,
        "checks": [
            {"name": r.name, "status": r.status.value, "detail": r.detail} for r in results
        ],
    }
