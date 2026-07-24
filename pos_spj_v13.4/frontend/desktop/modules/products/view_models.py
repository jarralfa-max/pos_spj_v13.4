"""Display view models / mappers for the enterprise products UI (es-MX).

Pure: no Qt, no I/O, no SQL. Turns backend DTOs/rows into display-ready strings
and small frozen view models the pages render. Spanish labels live here so the
pages stay presentation-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PRODUCT_TYPE_ES = {
    "RESALE_PRODUCT": "Reventa", "RAW_MATERIAL": "Materia prima",
    "LIVE_ANIMAL": "Animal vivo", "CARCASS": "Canal", "HALF_CARCASS": "Media canal",
    "QUARTER": "Cuarto", "PRIMARY_CUT": "Corte primario",
    "SECONDARY_CUT": "Corte secundario", "TRIM": "Recorte", "GROUND_MEAT": "Molido",
    "OFFAL": "Vísceras", "BY_PRODUCT": "Subproducto", "CO_PRODUCT": "Coproducto",
    "WASTE": "Desperdicio", "SEMI_FINISHED_GOOD": "Semiterminado",
    "FINISHED_GOOD": "Terminado", "PRODUCTION_COMPONENT": "Componente",
    "PACKAGING_MATERIAL": "Empaque", "CONSUMABLE": "Consumible",
    "MRO_MATERIAL": "MRO", "SPARE_PART": "Refacción", "SERVICE": "Servicio",
    "VIRTUAL_BUNDLE": "Combo virtual", "STOCKED_KIT": "Kit armado",
    "RETURNABLE_CONTAINER": "Contenedor retornable",
}
LIFECYCLE_ES = {
    "DRAFT": "Borrador", "UNDER_REVIEW": "En revisión", "ACTIVE": "Activo",
    "INACTIVE": "Inactivo", "BLOCKED": "Bloqueado", "DISCONTINUED": "Discontinuado",
    "ARCHIVED": "Archivado",
}
LIFECYCLE_VARIANT = {
    "DRAFT": "neutral", "UNDER_REVIEW": "warning", "ACTIVE": "success",
    "INACTIVE": "neutral", "BLOCKED": "danger", "DISCONTINUED": "warning",
    "ARCHIVED": "neutral",
}
SEVERITY_ES = {"INFO": "Informativo", "WARNING": "Advertencia",
               "DANGER": "Peligro", "CRITICAL": "Crítico"}
SEVERITY_VARIANT = {"INFO": "info", "WARNING": "warning",
                    "DANGER": "danger", "CRITICAL": "danger"}


def product_type_es(code) -> str:
    return PRODUCT_TYPE_ES.get(str(code or ""), str(code or "—"))


def lifecycle_es(code) -> str:
    return LIFECYCLE_ES.get(str(code or ""), str(code or "—"))


def lifecycle_variant(code) -> str:
    return LIFECYCLE_VARIANT.get(str(code or ""), "neutral")


def severity_es(code) -> str:
    return SEVERITY_ES.get(str(code or ""), str(code or "—"))


def severity_variant(code) -> str:
    return SEVERITY_VARIANT.get(str(code or ""), "neutral")


def _yesno(v) -> str:
    return "Sí" if v else "No"


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


def catalog_table(rows: list[dict]) -> TableViewModel:
    """rows: [{id, code, name, product_type, lifecycle_status, is_meat}] → table."""
    out, ids = [], []
    for r in rows:
        ids.append(str(r.get("id") or ""))
        out.append([
            str(r.get("code") or "—"),
            str(r.get("name") or "—"),
            product_type_es(r.get("product_type")),
            lifecycle_es(r.get("lifecycle_status")),
            _yesno(r.get("is_meat")),
        ])
    return TableViewModel(rows=out, row_ids=ids, total=len(out))


def alerts_table(rows: list[dict]) -> TableViewModel:
    out, ids = [], []
    for r in rows:
        ids.append(str(r.get("entity_id") or ""))
        out.append([
            severity_es(r.get("severity")),
            str(r.get("alert_type") or "—"),
            str(r.get("message") or "—"),
        ])
    return TableViewModel(rows=out, row_ids=ids, total=len(out))
