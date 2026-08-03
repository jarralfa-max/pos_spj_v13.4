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
WAREHOUSE_TYPE_ES = {
    "STORE": "Tienda", "CENTRAL": "Central", "DISTRIBUTION_CENTER": "Centro de distribución",
    "RAW_MATERIAL": "Materia prima", "FINISHED_GOODS": "Producto terminado",
    "COLD_STORAGE": "Refrigerado", "FROZEN_STORAGE": "Congelado", "QUARANTINE": "Cuarentena",
}
WAREHOUSE_STATUS_ES = {"ACTIVE": "Activo", "BLOCKED": "Bloqueado", "INACTIVE": "Inactivo"}
LOCATION_STATUS_ES = {"ACTIVE": "Activa", "BLOCKED": "Bloqueada", "INACTIVE": "Inactiva"}
SOURCE_ES = {"PURCHASE": "Compra", "TRANSFER": "Transferencia"}
LOT_ORIGIN_ES = {
    "PURCHASE": "Compra", "PRODUCTION": "Producción", "SLAUGHTER": "Faena",
    "TRANSFER": "Transferencia", "RETURN": "Devolución", "ADJUSTMENT": "Ajuste",
}
LOT_QUALITY_ES = {
    "RELEASED": "Liberado", "PENDING_INSPECTION": "Por inspección",
    "BLOCKED": "Bloqueado", "QUARANTINED": "En cuarentena", "REJECTED": "Rechazado",
}
LOT_QUALITY_VARIANT = {
    "RELEASED": "success", "PENDING_INSPECTION": "warning", "BLOCKED": "danger",
    "QUARANTINED": "warning", "REJECTED": "danger",
}
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


def lot_origin_es(code) -> str:
    return LOT_ORIGIN_ES.get(str(code or ""), str(code or "—"))


def lot_quality_es(code) -> str:
    return LOT_QUALITY_ES.get(str(code or ""), str(code or "—"))


def warehouse_type_es(code) -> str:
    return WAREHOUSE_TYPE_ES.get(str(code or ""), str(code or "—"))


def warehouse_status_es(code) -> str:
    return WAREHOUSE_STATUS_ES.get(str(code or ""), str(code or "—"))


def location_status_es(code) -> str:
    return LOCATION_STATUS_ES.get(str(code or ""), str(code or "—"))


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


# §9.3 — orden canónico del desglose de disponibilidad (concepto es-MX → clave del
# dict .explain()). "Disponible" es lo que Ventas puede prometer; el resto explica
# por qué el stock existente no está disponible.
AVAILABILITY_BREAKDOWN_ROWS = (
    ("Total en mano", "total_on_hand"),
    ("Disponible", "available"),
    ("Reservado", "reserved"),
    ("Asignado", "allocated"),
    ("En tránsito", "in_transit"),
    ("Por inspección", "pending_inspection"),
    ("En cuarentena", "quarantined"),
    ("Bloqueado calidad", "blocked"),
    ("Dañado", "damaged"),
    ("Caducado", "expired"),
    ("Devuelto", "returned"),
    ("Retenido producción", "production_hold"),
    ("Retiro (recall)", "recall_hold"),
)


def availability_breakdown_table(explain: dict) -> TableViewModel:
    """explain: dict de ``AvailabilityDTO.explain()`` → tabla (Concepto, Cantidad)
    en el orden canónico. Sin producto (dict vacío) devuelve una tabla vacía."""
    if not explain:
        return TableViewModel(rows=[], row_ids=[], total=0)
    out, ids = [], []
    for label, key in AVAILABILITY_BREAKDOWN_ROWS:
        ids.append(key)
        out.append([label, qty(explain.get(key, 0))])
    return TableViewModel(rows=out, row_ids=ids, total=len(out))


def warehouses_table(rows: list[dict]) -> TableViewModel:
    out, ids = [], []
    for r in rows:
        ids.append(str(r.get("id") or ""))
        out.append([
            str(r.get("code") or "—"),
            str(r.get("name") or "—"),
            warehouse_type_es(r.get("warehouse_type")),
            warehouse_status_es(r.get("status")),
        ])
    return TableViewModel(rows=out, row_ids=ids, total=len(out))


def lots_table(rows: list[dict]) -> TableViewModel:
    """rows: lot rows (list_for_product) → display table (código, origen, calidad,
    caducidad), ordenadas por caducidad (FEFO)."""
    out, ids = [], []
    for r in rows:
        ids.append(str(r.get("id") or ""))
        out.append([
            str(r.get("lot_code") or "—"),
            lot_origin_es(r.get("origin_type")),
            lot_quality_es(r.get("quality_status")),
            str(r.get("expiration_date") or "—"),
        ])
    return TableViewModel(rows=out, row_ids=ids, total=len(out))


def locations_table(nodes) -> TableViewModel:
    """Flatten a LocationNode forest into an indented table (hierarchy visible)."""
    out, ids = [], []

    def _walk(node, depth):
        ids.append(node.id)
        out.append([
            ("· " * depth) + node.code,
            node.name,
            str(node.level),
            location_status_es(node.status),
        ])
        for child in node.children:
            _walk(child, depth + 1)

    for root in nodes:
        _walk(root, 0)
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
