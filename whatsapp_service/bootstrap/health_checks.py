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


def _not_yet_built(name: str, owning_phase: str) -> HealthCheckResult:
    return HealthCheckResult(name, HealthStatus.UNKNOWN, f"pendiente — {owning_phase}")


def run_all_checks(root) -> List[HealthCheckResult]:
    return [
        check_database(root),
        check_schema(root),
        check_secrets(root),
        _not_yet_built("provider_gateway", "WA-5"),
        _not_yet_built("inbox_worker", "WA-6"),
        _not_yet_built("outbox_worker", "WA-17"),
        _not_yet_built("erp_api", "WA-9"),
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
