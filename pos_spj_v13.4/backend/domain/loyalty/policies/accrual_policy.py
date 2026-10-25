"""Cuántos puntos gana una compra, y cuándo caducan (decisión del usuario,
2026-10-02).

Hasta ahora ningún cliente acumulaba puntos al comprar: existía
`AccrueLoyaltyPointsUseCase`, pero ninguna regla decía cuántos puntos vale un
peso ni nadie la aplicaba al cobrar. Las reglas, todas configurables desde
Fidelidad (`configuraciones`):

* 1 punto por cada `pesos_per_point` pesos del TOTAL PAGADO (después de
  descuentos; lo canjeado con puntos ya no forma parte del total), redondeado
  hacia abajo. Valor inicial: $10.
* `credit_earns`: si lo pagado a crédito también acumula. Inicial: sí.
* `expiration_months`: meses de vigencia de cada acumulación; 0 = no caducan.
  Inicial: 12.

Devolver mercancía quita los puntos en proporción a lo devuelto, sin quitar
más de los que la compra dio (`points_to_remove`).

Puro: sin E/S; sólo Decimal.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal


@dataclass(frozen=True)
class AccrualSettings:
    pesos_per_point: Decimal = Decimal("10")
    credit_earns: bool = True
    expiration_months: int = 12

    def __post_init__(self) -> None:
        if Decimal(str(self.pesos_per_point)) <= 0:
            raise ValueError("Los pesos por punto deben ser mayores a cero")
        if int(self.expiration_months) < 0:
            raise ValueError("Los meses de vigencia no pueden ser negativos")


#: Medios que NUNCA acumulan: vales (de cualquier tipo, también el prepagado
#: al gastarse) y puntos. Auditoría 968e0bc FID-04, decisión del usuario.
NON_EARNING_TENDERS = frozenset({"VOUCHER", "STORE_CREDIT", "LOYALTY", "LOYALTY_POINTS",
                                 "POINTS"})
#: Medios que no acumulan AL VENDER: el crédito acumula cuando se cobra
#: (`credit_earns`) o nunca.
DEFERRED_TENDERS = frozenset({"CREDIT"})


def _tenders(payments) -> list[tuple[str, Decimal]]:
    salida = []
    for pago in payments or ():
        if isinstance(pago, dict):
            metodo, importe = pago.get("method"), pago.get("amount")
        else:
            metodo, importe = pago[0], pago[1]
        salida.append((str(metodo or "").upper(), Decimal(str(importe or "0"))))
    return salida


class LoyaltyAccrualPolicy:
    @staticmethod
    def eligible_amount(*, total: Decimal, credit_amount: Decimal = Decimal("0"),
                        settings: AccrualSettings, payments=()) -> Decimal:
        """La base que acumula AL VENDER (la ÚNICA, para la vista previa y para
        la venta confirmada — FID-04): lo pagado en dinero. Se restan los vales,
        los puntos y el crédito (éste acumula al cobrarse, no al vender).

        Sin desglose de pagos (llamadores antiguos) se resta `credit_amount`."""
        total = Decimal(str(total))
        pagos = _tenders(payments)
        if pagos:
            fuera = sum((importe for metodo, importe in pagos
                         if metodo in NON_EARNING_TENDERS or metodo in DEFERRED_TENDERS),
                        Decimal("0"))
        else:
            fuera = Decimal(str(credit_amount or "0"))
        return max(total - fuera, Decimal("0"))

    @staticmethod
    def deferred_credit_amount(*, total: Decimal, payments=(),
                               credit_amount: Decimal = Decimal("0")) -> Decimal:
        """La parte a crédito de la base: acumulará cuando se cobre."""
        pagos = _tenders(payments)
        credito = (sum((i for m, i in pagos if m in DEFERRED_TENDERS), Decimal("0"))
                   if pagos else Decimal(str(credit_amount or "0")))
        vales = sum((i for m, i in pagos if m in NON_EARNING_TENDERS), Decimal("0"))
        tope = max(Decimal(str(total)) - vales, Decimal("0"))
        return max(min(credito, tope), Decimal("0"))

    @staticmethod
    def points_for(amount: Decimal, settings: AccrualSettings) -> int:
        if Decimal(str(amount)) <= 0:
            return 0
        return int((Decimal(str(amount)) / Decimal(str(settings.pesos_per_point)))
                   .to_integral_value(rounding=ROUND_DOWN))

    @staticmethod
    def expires_at(earned_at: datetime, settings: AccrualSettings) -> str | None:
        """Fecha de caducidad (ISO) de una acumulación, o None si no caduca.
        Se suman meses de calendario (31-ene + 1 mes = 28/29-feb)."""
        meses = int(settings.expiration_months)
        if meses <= 0:
            return None
        mes = earned_at.month - 1 + meses
        anio, mes = earned_at.year + mes // 12, mes % 12 + 1
        dia = min(earned_at.day, calendar.monthrange(anio, mes)[1])
        return earned_at.replace(year=anio, month=mes, day=dia).isoformat(timespec="seconds")

    @staticmethod
    def points_to_remove(*, earned: int, sale_total: Decimal, refunded_total: Decimal,
                         already_removed: int) -> int:
        """Puntos a quitar por una devolución: proporción de lo devuelto (acumulado)
        sobre el total, menos lo ya quitado. Nunca más de lo que la compra dio."""
        sale_total = Decimal(str(sale_total))
        if earned <= 0 or sale_total <= 0:
            return 0
        proporcion = min(Decimal(str(refunded_total)) / sale_total, Decimal("1"))
        objetivo = int((Decimal(earned) * proporcion).to_integral_value(rounding=ROUND_DOWN))
        if proporcion >= 1:
            objetivo = earned
        return max(objetivo - int(already_removed), 0)
