"""Política de contabilización de compras — una sola para crédito y contado.

Auditoría d9f2bca F26: los dos puentes de Compras (CxP a crédito y pago de
contado) repetían el mapa naturaleza→cuenta, la fecha del documento y la suma
de subtotales + IVA. Aquí vive una vez; cada puente conserva su propia política
de PAGO (el de crédito acredita CxP, el de contado la cuenta de tesorería).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.shared.business_dates import local_business_date

#: purchase_nature -> rol de cuenta del perfil PURCHASE. SERVICE no tiene rol
#: propio en el catálogo: un servicio comprado es gasto operativo.
NATURE_ACCOUNT_ROLE = {
    "INVENTORY": "inventory_account_id",
    "EXPENSE": "expense_account_id",
    "ASSET": "asset_account_id",
    "SERVICE": "expense_account_id",
    # Mismas naturalezas que Compras manda a existencias (STOCK_NATURES): si
    # entran al almacén, se reconocen como inventario, no como gasto.
    "CONSUMABLE": "inventory_account_id",
    "PACKAGING": "inventory_account_id",
    "MAINTENANCE": "expense_account_id",
}


def purchase_issue_date(payload: dict) -> date:
    """Día LOCAL del negocio, no el de UTC (el último día del mes el asiento
    caía en el periodo siguiente)."""
    return local_business_date(payload.get("timestamp"))


def purchase_debit_lines(profile, payload: dict, *, currency_code: str, label: str,
                         total: Money) -> list[LineSpec]:
    """Cargos por naturaleza + IVA acreditable. Vacía si el evento no trae el
    desglose (nunca se adivina una cuenta). Si trae desglose, debe sumar el
    total del documento."""
    nature_subtotals: dict = payload.get("nature_subtotals") or {}
    if not nature_subtotals:
        return []
    lines: list[LineSpec] = []
    debited = Decimal("0")
    for nature, subtotal in nature_subtotals.items():
        money = Money.from_string(str(subtotal), currency_code)
        if not money.is_positive():
            continue
        role = NATURE_ACCOUNT_ROLE.get(nature, "expense_account_id")
        lines.append(LineSpec(profile.account_for(role), debit=money,
                              description=f"{label} ({nature})"))
        debited += money.amount
    tax_total = Money.from_string(str(payload.get("tax_total") or "0"), currency_code)
    if tax_total.is_positive():
        lines.append(LineSpec(profile.account_for("tax_account_id"), debit=tax_total,
                              description=f"IVA acreditable {label}"))
        debited += tax_total.amount
    if lines and debited != total.amount:
        raise FinanceDomainError(
            f"{label}: subtotales por naturaleza + impuesto ({debited}) "
            f"!= total del documento ({total.amount})")
    return lines
