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


class LoyaltyAccrualPolicy:
    @staticmethod
    def eligible_amount(*, total: Decimal, credit_amount: Decimal,
                        settings: AccrualSettings) -> Decimal:
        """Lo que acumula: el total pagado, menos lo pagado a crédito si el
        programa no deja acumular a crédito."""
        total = Decimal(str(total))
        if not settings.credit_earns:
            total -= Decimal(str(credit_amount))
        return max(total, Decimal("0"))

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
