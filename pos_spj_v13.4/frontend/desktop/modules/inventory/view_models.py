"""Display view models / mappers for the enterprise inventory UI (es-MX).

Pure: no Qt, no I/O, no SQL. Turns backend DTOs/rows into display-ready strings
and small frozen view models the pages render. Spanish labels live here so the
pages stay presentation-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from frontend.desktop.formatters import format_quantity

INVENTORY_STATUS_ES = {
    "AVAILABLE": "Disponible", "RESERVED": "Reservado", "ALLOCATED": "Asignado",
    "IN_TRANSIT": "En tránsito", "PENDING_INSPECTION": "Por inspección",
    "QUARANTINED": "En cuarentena", "QUALITY_BLOCKED": "Bloqueado calidad",
    "DAMAGED": "Dañado", "EXPIRED": "Caducado", "RETURNED": "Devuelto",
    "PRODUCTION_HOLD": "Retenido producción", "RECALL_HOLD": "Retiro (recall)",
    "DISPOSED": "Dispuesto",
}
URGENCY_ES = {
    "OK": "En nivel", "REORDER": "Reordenar", "CRITICAL": "Crítico",
    "STOCKOUT": "Sin existencia",
}
URGENCY_VARIANT = {
    "OK": "success", "REORDER": "warning", "CRITICAL": "danger", "STOCKOUT": "danger",
}
SOURCE_ES = {"PURCHASE": "Compra", "TRANSFER": "Transferencia"}
SEVERITY_ES = {"INFO": "Informativo", "WARNING": "Advertencia", "CRITICAL": "Crítico"}
DIRECTION_ES = {"UPSTREAM": "Origen (ascendente)", "DOWNSTREAM": "Destino (descendente)"}


def status_es(code) -> str:
    return INVENTORY_STATUS_ES.get(str(code or ""), str(code or "—"))


def urgency_es(code) -> str:
    return URGENCY_ES.get(str(code or ""), str(code or "—"))


def urgency_variant(code) -> str:
    return URGENCY_VARIANT.get(str(code or ""), "neutral")


def source_es(code) -> str:
    return SOURCE_ES.get(str(code or ""), str(code or "—"))


def qty(value, unit: str | None = None) -> str:
    return format_quantity(value, unit)


@dataclass(frozen=True)
class TableViewModel:
    rows: list[list[str]] = field(default_factory=list)
    row_ids: list[str] = field(default_factory=list)
    total: int = 0


@dataclass(frozen=True)
class KpiViewModel:
    key: str
    title: str
    value: str
    variant: str = "neutral"
    subtitle: str | None = None
    tooltip: str | None = None


def availability_table(rows: list[dict]) -> TableViewModel:
    """rows: [{product_id, on_hand, reserved, available, ...}] → display table."""
    out, ids = [], []
    for r in rows:
        ids.append(str(r.get("product_id") or ""))
        out.append([
            str(r.get("product_id") or "—"),
            qty(r.get("on_hand")),
            qty(r.get("reserved")),
            qty(r.get("available")),
        ])
    return TableViewModel(rows=out, row_ids=ids, total=len(out))


def replenishment_table(rows: list[dict]) -> TableViewModel:
    """rows: notification-log-like suggestion rows → display table."""
    out, ids = [], []
    for r in rows:
        ids.append(str(r.get("id") or ""))
        out.append([
            str(r.get("product_id") or "—"),
            qty(r.get("current_available")),
            qty(r.get("suggested_quantity")),
            source_es(r.get("source_type")),
            urgency_es(r.get("urgency")),
        ])
    return TableViewModel(rows=out, row_ids=ids, total=len(out))
