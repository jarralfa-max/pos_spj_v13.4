"""CustomerBirthday — día, mes y (opcional) año de nacimiento (2026-10-03)."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from backend.domain.customers.exceptions import CustomerDomainError


@dataclass(frozen=True)
class CustomerBirthday:
    month: int
    day: int
    year: int | None = None

    def __post_init__(self) -> None:
        if not 1 <= int(self.month) <= 12:
            raise CustomerDomainError("Mes de cumpleaños inválido")
        anio = int(self.year) if self.year else 2000   # bisiesto: admite 29 de febrero
        if not 1 <= int(self.day) <= calendar.monthrange(anio, int(self.month))[1]:
            raise CustomerDomainError("Día de cumpleaños inválido para ese mes")
        if self.year is not None and not 1900 <= int(self.year) <= date.today().year:
            raise CustomerDomainError("Año de nacimiento inválido")

    def days_from(self, on: date) -> int:
        """Distancia en días (con signo, el más cercano) entre `on` y el
        cumpleaños de ese año; un 29 de febrero se celebra el 28 en año no bisiesto."""
        mejores = []
        for anio in (on.year - 1, on.year, on.year + 1):
            dia = min(self.day, calendar.monthrange(anio, self.month)[1])
            mejores.append((date(anio, self.month, dia) - on).days)
        return min(mejores, key=abs)


__all__ = ["CustomerBirthday"]
