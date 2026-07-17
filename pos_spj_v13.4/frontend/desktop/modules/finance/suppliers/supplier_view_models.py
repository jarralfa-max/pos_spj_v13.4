"""Display-ready view models and mappers for the suppliers UI (es-MX)."""

from __future__ import annotations

from dataclasses import dataclass, field

from frontend.desktop.formatters import format_money, format_status

STATUS_ES = {
    "DRAFT": "Borrador", "PENDING_APPROVAL": "Pendiente", "ACTIVE": "Activo",
    "SUSPENDED": "Suspendido", "BLOCKED": "Bloqueado", "INACTIVE": "Baja",
    "REJECTED": "Rechazado",
}
RISK_ES = {"LOW": "Bajo", "MEDIUM": "Medio", "HIGH": "Alto", "CRITICAL": "Crítico"}

#: status → StatusBadge variant
STATUS_VARIANT = {
    "ACTIVE": "success", "PENDING_APPROVAL": "warning", "BLOCKED": "danger",
    "SUSPENDED": "warning", "REJECTED": "danger", "INACTIVE": "neutral",
    "DRAFT": "neutral",
}
RISK_VARIANT = {"LOW": "success", "MEDIUM": "warning", "HIGH": "danger", "CRITICAL": "danger"}
CATEGORY_ES = {
    "GOODS": "Bienes", "SERVICES": "Servicios", "LOGISTICS": "Logística",
    "MAINTENANCE": "Mantenimiento", "UTILITIES": "Servicios básicos",
    "PROFESSIONAL_SERVICES": "Servicios profesionales", "ASSETS": "Activos",
    "TECHNOLOGY": "Tecnología", "OTHER": "Otro",
    "POULTRY": "Pollo", "EGGS": "Huevo", "GROCERIES": "Abarrotes",
    "PACKAGING": "Empaques", "DISPOSABLES": "Desechables", "DRIED_CHILES": "Chiles secos",
    "CEREALS": "Cereales", "BULK_PRODUCTS": "Productos a granel", "CLEANING": "Limpieza",
    "TRANSPORT": "Transporte", "EQUIPMENT": "Equipo",
}


def status_es(code: str | None) -> str:
    return STATUS_ES.get(str(code or ""), format_status(code))


def risk_es(code: str | None) -> str:
    return RISK_ES.get(str(code or ""), str(code or "—"))


def category_es(code: str | None) -> str:
    return CATEGORY_ES.get(str(code or ""), str(code or ""))


@dataclass(frozen=True)
class TableViewModel:
    rows: list[list[str]] = field(default_factory=list)
    row_ids: list[str] = field(default_factory=list)
    total: int = 0


@dataclass(frozen=True)
class KpiVM:
    title: str
    value: str
    variant: str = "primary"


def money(value) -> str:
    return format_money(value)
