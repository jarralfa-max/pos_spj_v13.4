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
MOVEMENT_TYPE_ES = {
    "PURCHASE_RECEIPT": "Recepción de compra",
    "DIRECT_PURCHASE_RECEIPT": "Recepción directa",
    "SALE_ISSUE": "Salida por venta", "SALE_RETURN": "Devolución de venta",
    "TRANSFER_DISPATCH": "Despacho de traslado", "TRANSFER_RECEIPT": "Recepción de traslado",
    "PRODUCTION_CONSUMPTION": "Consumo de producción",
    "PRODUCTION_OUTPUT": "Salida de producción",
    "KIT_ASSEMBLY": "Ensamble de kit", "KIT_DISASSEMBLY": "Desensamble de kit",
    "QUALITY_BLOCK": "Bloqueo de calidad", "QUALITY_RELEASE": "Liberación de calidad",
    "QUARANTINE_ENTRY": "Ingreso a cuarentena", "QUARANTINE_RELEASE": "Salida de cuarentena",
    "EXPIRY_STATUS_TRANSFER": "Caducidad", "ADJUSTMENT_IN": "Ajuste (entrada)",
    "ADJUSTMENT_OUT": "Ajuste (salida)", "COUNT_VARIANCE": "Varianza de conteo",
    "WASTE": "Merma", "SHRINKAGE": "Mermas/shrinkage", "EXPIRY_DISPOSAL": "Disposición por caducidad",
    "SUPPLIER_RETURN": "Devolución a proveedor", "CUSTOMER_RETURN": "Devolución de cliente",
    "REVERSAL": "Reverso",
}
MOVEMENT_STATUS_ES = {"POSTED": "Posteado", "REVERSED": "Reversado", "DRAFT": "Borrador"}
EXPIRY_RISK_ES = {
    "OK": "En rango", "WARNING": "Próximo a vencer", "CRITICAL": "Crítico",
    "EXPIRED": "Vencido",
}
EXPIRY_RISK_VARIANT = {
    "OK": "success", "WARNING": "warning", "CRITICAL": "danger", "EXPIRED": "danger",
}
SEVERITY_ES = {"INFO": "Informativo", "WARNING": "Advertencia", "CRITICAL": "Crítico"}
DIRECTION_ES = {"UPSTREAM": "Origen (ascendente)", "DOWNSTREAM": "Destino (descendente)"}
MOVEMENT_DIRECTION_ES = {
    "INCREASE": "Entrada", "DECREASE": "Salida",
    "STATUS_TRANSFER": "Cambio de estado", "VARIANCE": "Varianza", "MIXED": "Mixto",
}


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


def movement_type_es(code) -> str:
    return MOVEMENT_TYPE_ES.get(str(code or ""), str(code or "—"))


def movement_status_es(code) -> str:
    return MOVEMENT_STATUS_ES.get(str(code or ""), str(code or "—"))


def expiry_risk_es(code) -> str:
    return EXPIRY_RISK_ES.get(str(code or ""), str(code or "—"))


def movement_direction_es(code) -> str:
    return MOVEMENT_DIRECTION_ES.get(str(code or ""), str(code or "—"))


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


def stock_table(rows: list[dict]) -> TableViewModel:
    """rows: on-hand balance rows (list_on_hand) → display table (producto,
    almacén, estado/bucket, cantidad, reservado)."""
    out, ids = [], []
    for i, r in enumerate(rows):
        ids.append(f"{r.get('product_id','')}:{r.get('warehouse_id','')}:"
                   f"{r.get('inventory_status','')}:{i}")
        out.append([
            str(r.get("product_id") or "—"),
            str(r.get("warehouse_id") or "—"),
            status_es(r.get("inventory_status")),
            qty(r.get("quantity")),
            qty(r.get("reserved_quantity")),
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


def expiry_table(rows: list[dict]) -> TableViewModel:
    """rows: at-risk lot rows (list_at_risk) → display table (producto, lote,
    cantidad, días, riesgo), próximos a vencer primero."""
    out, ids = [], []
    for r in rows:
        ids.append(str(r.get("lot_id") or ""))
        days = r.get("days_to_expiry")
        out.append([
            str(r.get("product_id") or "—"),
            str(r.get("lot_code") or "—"),
            qty(r.get("quantity")),
            "—" if days is None else str(days),
            expiry_risk_es(r.get("risk")),
        ])
    return TableViewModel(rows=out, row_ids=ids, total=len(out))


def traceability_table(events) -> TableViewModel:
    """events: TraceEvent tuple (trace_upstream/downstream) → display table
    (fecha, movimiento, dirección, módulo, documento)."""
    out, ids = [], []
    for e in events:
        ids.append(str(getattr(e, "movement_id", "") or ""))
        doc = f"{getattr(e, 'source_document_type', '')} " \
              f"{getattr(e, 'source_document_id', '')}".strip() or "—"
        out.append([
            str(getattr(e, "occurred_at", "") or "—")[:19],
            movement_type_es(getattr(e, "movement_type", "")),
            movement_direction_es(getattr(e, "direction", "")),
            str(getattr(e, "source_module", "") or "—"),
            doc,
        ])
    return TableViewModel(rows=out, row_ids=ids, total=len(out))


def movements_table(rows: list[dict]) -> TableViewModel:
    """rows: ledger movement rows (list_recent) → display table (fecha, tipo,
    módulo, documento, estado), más recientes primero."""
    out, ids = [], []
    for r in rows:
        ids.append(str(r.get("id") or ""))
        doc_type = str(r.get("source_document_type") or "")
        doc_id = str(r.get("source_document_id") or "")
        documento = f"{doc_type} {doc_id}".strip() or "—"
        out.append([
            str(r.get("occurred_at") or "—")[:19],
            movement_type_es(r.get("movement_type")),
            str(r.get("source_module") or "—"),
            documento,
            movement_status_es(r.get("status")),
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
