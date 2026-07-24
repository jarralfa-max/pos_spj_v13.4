"""Display view models / mappers for the enterprise pricing UI (es-MX).

Pure: no Qt, no I/O, no SQL. Turns backend read rows into display-ready strings and
small frozen view models the pages render. Spanish labels + money/percent
formatting live here so the pages stay presentation-only. Decimal/str only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from frontend.desktop.formatters.money_formatter import format_money
from frontend.desktop.formatters.percentage_formatter import format_percentage

LIST_STATUS_ES = {
    "DRAFT": "Borrador", "UNDER_REVIEW": "En revisión", "APPROVED": "Aprobada",
    "ACTIVE": "Activa", "INACTIVE": "Inactiva",
}
LIST_STATUS_VARIANT = {
    "DRAFT": "neutral", "UNDER_REVIEW": "warning", "APPROVED": "info",
    "ACTIVE": "success", "INACTIVE": "neutral",
}
LIST_KIND_ES = {
    "BASE": "Base", "CHANNEL": "Canal", "CUSTOMER": "Cliente",
    "PROMOTIONAL": "Promoción",
}
COST_METHOD_ES = {"AVERAGE": "Promedio", "LAST": "Último", "STANDARD": "Estándar"}
PRICE_SOURCE_ES = {
    "VOLUME": "Volumen", "CUSTOMER_LIST": "Lista cliente", "LIST": "Lista",
    "BASE": "Base", "NONE": "Sin precio",
}
CHANGE_FIELD_ES = {"sale_price": "Precio de venta", "min_price": "Precio mínimo",
                   "cost": "Costo"}


def list_status_es(code) -> str:
    return LIST_STATUS_ES.get(str(code or ""), str(code or "—"))


def list_status_variant(code) -> str:
    return LIST_STATUS_VARIANT.get(str(code or ""), "neutral")


def list_kind_es(code) -> str:
    return LIST_KIND_ES.get(str(code or ""), str(code or "—"))


def cost_method_es(code) -> str:
    return COST_METHOD_ES.get(str(code or ""), str(code or "—"))


def price_source_es(code) -> str:
    return PRICE_SOURCE_ES.get(str(code or ""), str(code or "—"))


def change_field_es(code) -> str:
    return CHANGE_FIELD_ES.get(str(code or ""), str(code or "—"))


def _branch_es(branch_id) -> str:
    return "Todas" if not branch_id else str(branch_id)


def _product_label(row) -> str:
    name = row.get("product_name")
    code = row.get("product_code")
    if name and code:
        return f"{code} · {name}"
    return name or code or str(row.get("product_id") or "—")


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


def price_lists_table(rows: list[dict]) -> TableViewModel:
    out, ids = [], []
    for r in rows:
        ids.append(str(r.get("id") or ""))
        out.append([
            str(r.get("code") or "—"),
            str(r.get("name") or "—"),
            list_kind_es(r.get("kind")),
            list_status_es(r.get("status")),
            format_percentage(r.get("discount_pct"), decimals=1),
        ])
    return TableViewModel(rows=out, row_ids=ids, total=len(out))


def product_prices_table(rows: list[dict]) -> TableViewModel:
    out, ids = [], []
    for r in rows:
        ids.append(str(r.get("id") or ""))
        cur = r.get("currency") or "MXN"
        out.append([
            _product_label(r),
            str(r.get("list_name") or "—"),
            _branch_es(r.get("branch_id")),
            format_money(r.get("sale_price"), cur),
            format_money(r.get("min_price"), cur),
        ])
    return TableViewModel(rows=out, row_ids=ids, total=len(out))


def costs_table(rows: list[dict]) -> TableViewModel:
    out, ids = [], []
    for r in rows:
        ids.append(str(r.get("product_id") or ""))
        cur = r.get("currency") or "MXN"
        out.append([
            _product_label(r),
            format_money(r.get("average_cost"), cur),
            format_money(r.get("last_cost"), cur),
            format_money(r.get("standard_cost"), cur),
            cost_method_es(r.get("cost_method")),
        ])
    return TableViewModel(rows=out, row_ids=ids, total=len(out))


def history_table(rows: list[dict]) -> TableViewModel:
    out, ids = [], []
    for r in rows:
        ids.append(str(r.get("product_id") or ""))
        cur = r.get("currency") or "MXN"
        out.append([
            str(r.get("created_at") or "—"),
            _product_label(r) if r.get("product_name") else str(r.get("product_id") or "—"),
            change_field_es(r.get("field")),
            format_money(r.get("old_value"), cur),
            format_money(r.get("new_value"), cur),
            str(r.get("authorized_by") or r.get("user_id") or "—"),
        ])
    return TableViewModel(rows=out, row_ids=ids, total=len(out))
