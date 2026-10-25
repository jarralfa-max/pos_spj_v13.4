"""Economía del programa de puntos en una sola cuenta (auditoría de Fidelidad
968e0bc, FID-09): «cuánto me cuesta cada punto y cuánto regalo como máximo».

Pura: recibe los parámetros que ya gobiernan la acumulación (`pesos_per_point`)
y el canje (`point_value`, `min_points`, `max_percent`) y devuelve los números
que el dueño necesita ver antes de guardar. No decide nada; las reglas de
bonificación (Reglas de acumulación) suben la tasa por encima de esta base.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

_HUNDRED = Decimal("100")


@dataclass(frozen=True)
class ProgramEconomy:
    pesos_per_point: Decimal
    point_value: Decimal
    min_points: int
    #: Fracción del ticket pagadera con puntos (0.5 = 50 %).
    max_percent: Decimal

    @property
    def return_rate_percent(self) -> Decimal | None:
        """Lo que regresa al cliente, en % de lo que pagó (base, sin bonos)."""
        if self.pesos_per_point <= 0:
            return None
        return (self.point_value / self.pesos_per_point * _HUNDRED).quantize(Decimal("0.01"))

    @property
    def purchase_to_first_redemption(self) -> Decimal:
        """Cuánto debe comprar un cliente nuevo para alcanzar el mínimo de canje."""
        return (Decimal(self.min_points) * self.pesos_per_point).quantize(Decimal("0.01"))

    @property
    def min_redemption_value(self) -> Decimal:
        """Descuento que obtiene al canjear el mínimo de puntos."""
        return (Decimal(self.min_points) * self.point_value).quantize(Decimal("0.01"))

    @property
    def max_ticket_percent(self) -> Decimal:
        return (self.max_percent * _HUNDRED).quantize(Decimal("0.01"))


__all__ = ["ProgramEconomy"]
