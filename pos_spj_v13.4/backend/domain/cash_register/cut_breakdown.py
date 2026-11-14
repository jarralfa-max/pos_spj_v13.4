"""Desglose de cobros por medio de pago para el Corte X/Z (SDLC-PAY-005).

El corte contaba sólo el libro de efectivo. Las asignaciones de cada cobro
(`payment_allocations`) dicen cuánto entró por cada medio; aquí se agrupan para
que el cajero cuadre la terminal y el reporte del procesador contra el corte.

El bruto es lo cobrado, sin restar ninguna comisión. El efectivo es lo que quedó
en el cajón (neto del cambio), igual que el libro de efectivo.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Mapping

#: Tipo canónico de la asignación → medio del corte.
_CATEGORY_BY_TYPE = {
    "CASH": "CASH",
    "BANK_CARD": "CARD",
    "PAYMENT_PROCESSOR": "MERCADO_PAGO",
    "BANK_TRANSFER": "TRANSFER",
    "REFUND_VOUCHER": "VOUCHER",
    "PROMOTIONAL_VOUCHER": "VOUCHER",
    "STORE_CREDIT": "VOUCHER",
    "GIFT_CARD": "VOUCHER",
    "CUSTOMER_CREDIT": "CREDIT",
}

#: Orden y etiqueta de cada medio en el documento.
CUT_PAYMENT_CATEGORIES = (
    ("CASH", "Efectivo"), ("CARD", "Tarjeta"), ("MERCADO_PAGO", "Mercado Pago"),
    ("TRANSFER", "Transferencia"), ("VOUCHER", "Vales y saldo a favor"),
    ("CREDIT", "Crédito"), ("OTHER", "Otros"),
)


def payment_breakdown(allocations: Iterable[Mapping], refunds: Iterable[Mapping]) -> dict[str, str]:
    """Claves `payment.<MEDIO>.count|gross`, `payment.sales`, `payment.mixed_sales`
    y `refund.electronic.count|amount`. Vacío si el turno no cobró nada."""
    gross: dict[str, Decimal] = {}
    count: dict[str, int] = {}
    by_record: dict[str, set[str]] = {}
    for row in allocations:
        category = _CATEGORY_BY_TYPE.get(str(row["method_type"]), "OTHER")
        gross[category] = gross.get(category, Decimal("0")) + Decimal(str(row["amount"]))
        count[category] = count.get(category, 0) + 1
        by_record.setdefault(str(row["payment_record_id"]), set()).add(category)
    result: dict[str, str] = {}
    for category, _label in CUT_PAYMENT_CATEGORIES:
        if category in gross:
            result[f"payment.{category}.count"] = str(count[category])
            result[f"payment.{category}.gross"] = str(gross[category])
    if by_record:
        result["payment.sales"] = str(len(by_record))
        result["payment.mixed_sales"] = str(sum(1 for c in by_record.values() if len(c) > 1))
    electronic = [Decimal(str(r["amount"])) for r in refunds
                  if str(r["method"]) != "CASH"]
    if electronic:
        result["refund.electronic.count"] = str(len(electronic))
        result["refund.electronic.amount"] = str(sum(electronic, Decimal("0")))
    return result


def cut_payment_lines(snapshot: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    """Los renglones del documento impreso, en el idioma del cajero."""
    lines: list[tuple[str, str]] = []
    for category, label in CUT_PAYMENT_CATEGORIES:
        if f"payment.{category}.gross" in snapshot:
            lines.append((f"{label} ({snapshot[f'payment.{category}.count']})",
                          snapshot[f"payment.{category}.gross"]))
    if snapshot.get("payment.sales"):
        lines.append(("Ventas con pago mixto",
                      f"{snapshot.get('payment.mixed_sales', '0')} de {snapshot['payment.sales']}"))
    if "refund.electronic.amount" in snapshot:
        lines.append((f"Reembolsos a medio electrónico ({snapshot['refund.electronic.count']})",
                      snapshot["refund.electronic.amount"]))
    return tuple(lines)
