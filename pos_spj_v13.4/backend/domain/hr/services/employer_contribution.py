"""Puerto de la cuota patronal IMSS (SDLC-HR-001).

La calcula el sistema (decisión del responsable, 2026-11-05), pero sus tablas no
están definidas: UMA vigente, prima de riesgo de la empresa e integración del
salario base. Igual que ``PayrollWithholdingProvider``, este puerto deja el punto
exacto donde se conecta el cálculo y la nómina no inventa una tasa.
"""

from __future__ import annotations

from typing import Protocol

from backend.domain.hr.entities import PayrollRun
from backend.domain.hr.value_objects import Money


class EmployerContributionProvider(Protocol):
    def employer_contribution(self, run: PayrollRun) -> Money: ...


class NoEmployerContributionProvider:
    """Sin tablas oficiales configuradas: no se provisiona cuota patronal."""

    name = "Sin cuota patronal (tablas oficiales no configuradas)"

    def employer_contribution(self, run: PayrollRun) -> Money:
        return Money.zero(run.net_amount().currency_code)
