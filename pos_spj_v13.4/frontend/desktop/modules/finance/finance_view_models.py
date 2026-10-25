"""View models del módulo de Finanzas — sólo cadenas listas para mostrar.

Los importes llegan del backend como texto decimal y se formatean con
``Decimal``: nunca pasan por ``float`` (§3, F20).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

STATUS_ES = {
    "DRAFT": "Borrador",
    "VALIDATED": "Validado",
    "POSTED": "Contabilizado",
    "REVERSED": "Reversado",
    "CANCELLED": "Cancelado",
    "OPEN": "Abierto",
    "SOFT_CLOSED": "Pre-cierre",
    "CLOSED": "Cerrado",
    "PARTIALLY_COLLECTED": "Cobro parcial",
    "COLLECTED": "Cobrado",
    "OVERDUE": "Vencido",
    "DISPUTED": "En disputa",
    "WRITTEN_OFF": "Castigado",
    "UNAPPLIED": "Sin aplicar",
    "PARTIALLY_APPLIED": "Aplicado parcial",
    "APPLIED": "Aplicado",
    "SCHEDULED": "Programado",
    "PARTIALLY_PAID": "Pago parcial",
    "PAID": "Pagado",
    "AUTHORIZED": "Autorizado",
    "EXECUTED": "Ejecutado",
    "IN_PROGRESS": "En proceso",
    "COMPLETED": "Completada",
    "REVERTED": "Revertida",
    "SUBMITTED": "Enviado",
    "REQUESTED": "Solicitado",
    "APPROVED": "Aprobado",
    "ACTIVE": "Activo",
    "REJECTED": "Rechazado",
    "ACCRUED": "Devengado",
    "SETTLED": "Liquidado",
    "SUSPENDED": "Suspendido",
    "DISPOSED": "Dado de baja",
    "SOLD": "Vendido",
    "PENDING_RECOGNITION": "Pendiente de reconocer",
    "PARTIALLY_REDEEMED": "Canje parcial",
    "REDEEMED": "Canjeado",
    "EXPIRED": "Expirado",
    "UNMATCHED": "Sin conciliar",
    "SUGGESTED": "Sugerida",
    "MATCHED": "Conciliada",
    "IGNORED": "Ignorada",
    "ADJUSTMENT_REQUIRED": "Requiere ajuste",
    "AVAILABLE": "Disponible",
    "WARNING": "Advertencia",
    "BLOCKING": "Bloqueado",
    "OK": "Correcto",
    "KEPT": "Cumplida",
    "BROKEN": "Incumplida",
}

ACCOUNT_TYPE_ES = {
    "ASSET": "Activo",
    "CONTRA_ASSET": "Complementaria de activo",
    "LIABILITY": "Pasivo",
    "EQUITY": "Capital",
    "REVENUE": "Ingreso",
    "CONTRA_REVENUE": "Contra-ingreso",
    "COST_OF_SALES": "Costo de ventas",
    "EXPENSE": "Gasto",
    "OTHER_INCOME": "Otros ingresos",
    "OTHER_EXPENSE": "Otros gastos",
}

TREASURY_TYPE_ES = {
    "GENERAL_CASH": "Caja general",
    "PETTY_CASH": "Caja chica",
    "CASH_REGISTER": "Caja registradora",
    "BANK": "Banco",
    "CREDIT_CARD": "Tarjeta de crédito",
    "DIGITAL_WALLET": "Monedero digital",
}

INSTRUMENT_ES = {
    "LOYALTY_POINTS": "Puntos de fidelidad",
    "PROMOTIONAL_COUPON": "Cupón promocional",
    "DISCOUNT_COUPON": "Cupón de descuento",
    "REFUND_VOUCHER": "Vale por devolución",
    "STORE_CREDIT": "Saldo a favor",
    "GIFT_CARD": "Tarjeta de regalo",
    "PREPAID_VOUCHER": "Vale prepago",
    "PROMOTIONAL_BALANCE": "Saldo promocional",
    "CUSTOMER_WALLET": "Monedero de cliente",
    "THIRD_PARTY_VOUCHER": "Vale de tercero",
}

AGING_ES = {
    "CURRENT": "Al corriente",
    "1-30": "1 a 30 días",
    "31-60": "31 a 60 días",
    "61-90": "61 a 90 días",
    "90+": "Más de 90 días",
    "NO_DUE_DATE": "Sin vencimiento",
}


def status_es(value: str | None) -> str:
    return STATUS_ES.get(str(value or ""), str(value or ""))


def account_type_es(value: str | None) -> str:
    return ACCOUNT_TYPE_ES.get(str(value or ""), str(value or ""))


def money_display(value) -> str:
    """``"1234.5"`` → ``"$1,234.50"`` con ``Decimal`` (un vacío se queda vacío)."""
    if value is None or str(value).strip() == "":
        return ""
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return str(value)
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def yes_no(value) -> str:
    return "Sí" if value else "No"


@dataclass(frozen=True)
class TableViewModel:
    """Una tabla preparada: renglones visibles y los ids ocultos de cada uno."""

    rows: list[list[str]] = field(default_factory=list)
    row_ids: list[str] = field(default_factory=list)
    #: Total de resultados del servidor cuando la tabla es una página (F24).
    total: int | None = None


@dataclass(frozen=True)
class KpiViewModel:
    title: str
    value: str
    variant: str = "primary"


@dataclass(frozen=True)
class AlertViewModel:
    label: str
    count: int
    severity: str
    route: str
