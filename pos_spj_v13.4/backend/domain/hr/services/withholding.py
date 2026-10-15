"""Puerto de retenciones de nómina (ISR, cuota obrera IMSS) — 2026-10-14.

La nómina no inventa tasas: las retenciones fiscales dependen de tablas
oficiales por año (ISR art. 96, subsidio, cuotas IMSS) y de decisiones legales.
Este puerto deja el punto exacto donde un motor fiscal se conecta: recibe al
empleado, sus líneas del periodo y el periodo, y devuelve deducciones
(``TAX_WITHHOLDING``/``SOCIAL_SECURITY``) que la corrida agrega como cualquier
otra línea. El valor por omisión NO retiene nada (como hasta hoy) y lo dice.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from backend.domain.hr.entities import Employee, PayrollLine
from backend.domain.hr.enums import PayrollConcept
from backend.domain.hr.value_objects import Money


class PayrollWithholdingProvider(Protocol):
    def withholdings(self, employee: Employee, lines: list[PayrollLine], *,
                     period_start: date, period_end: date
                     ) -> list[tuple[PayrollConcept, Money, str]]: ...


class NoWithholdingProvider:
    """Sin motor fiscal configurado: no se retiene ISR ni IMSS."""

    name = "Sin retenciones (motor fiscal no configurado)"

    def withholdings(self, employee, lines, *, period_start, period_end):
        return []
