"""View models for the finance module — display-ready strings only."""

from __future__ import annotations

from dataclasses import dataclass, field

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
    "SETTLED": "Liquidado",
    "WRITTEN_OFF": "Castigado",
    "SCHEDULED": "Programado",
    "PARTIALLY_PAID": "Pago parcial",
    "AUTHORIZED": "Autorizado",
    "EXECUTED": "Ejecutado",
    "RECONCILED": "Conciliado",
    "IN_PROGRESS": "En proceso",
    "COMPLETED": "Completada",
    "REVERTED": "Revertida",
    "SUBMITTED": "Enviado",
    "APPROVED": "Aprobado",
    "REJECTED": "Rechazado",
    "CAPITALIZED": "Capitalizado",
    "FULLY_DEPRECIATED": "Depreciado 100%",
    "DISPOSED": "Dado de baja",
    "PENDING_RECOGNITION": "Pendiente de reconocer",
    "PARTIALLY_REDEEMED": "Canje parcial",
    "REDEEMED": "Canjeado",
    "EXPIRED": "Expirado",
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


def status_es(value: str | None) -> str:
    return STATUS_ES.get(str(value or ""), str(value or ""))


def money_display(value) -> str:
    try:
        return f"${float(str(value)):,.2f}"
    except (TypeError, ValueError):
        return str(value or "")


@dataclass(frozen=True)
class TableViewModel:
    """One prepared table payload: display rows plus hidden row ids."""

    rows: list[list[str]] = field(default_factory=list)
    row_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class KpiViewModel:
    title: str
    value: str
    variant: str = "primary"
