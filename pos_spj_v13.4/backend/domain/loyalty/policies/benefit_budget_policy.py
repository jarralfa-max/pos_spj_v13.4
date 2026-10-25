"""Presupuesto de beneficios de una venta (auditoría Fidelidad 968e0bc FID-03).

Los topes de canje eran sólo porcentuales: vender en $100 algo que cuesta $95 y
dar $10 en puntos pasaba aunque se perdiera dinero. Ahora todos los beneficios
de una venta —descuento manual, promociones, cupones y puntos— comparten UN
presupuesto:

    por línea:  precio × cantidad − costo − margen mínimo × precio × cantidad
    venta:      Σ líneas − beneficios ya comprometidos   (nunca negativo)

Una línea SIN costo confiable no aporta presupuesto (decisión del usuario:
«sin costo, sin beneficio»); se informa para que el cajero sepa por qué y,
si procede, pida autorización.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

_ZERO = Decimal("0")
_CENT = Decimal("0.01")


@dataclass(frozen=True)
class BudgetLine:
    product_id: str
    name: str
    revenue: Decimal              # precio × cantidad, antes de beneficios
    cost: Decimal | None          # costo total de la línea; None = sin costo confiable
    min_margin: Decimal           # fracción (0.10 = 10 %)


@dataclass(frozen=True)
class BenefitBudget:
    room: Decimal                 # lo que el margen permite dar en total
    committed: Decimal            # lo que ya se dio en esta venta
    available: Decimal            # lo que todavía se puede dar
    lines_without_cost: tuple[str, ...] = ()

    def explain(self) -> str:
        if self.lines_without_cost:
            nombres = ", ".join(self.lines_without_cost[:3])
            return (f"Sin costo registrado para {nombres}: esas líneas no admiten "
                    "beneficios sin autorización.")
        if self.available <= 0:
            return ("La venta ya no tiene margen para más beneficios "
                    f"(margen disponible ${self.room:,.2f}, ya usado ${self.committed:,.2f}).")
        return f"Margen disponible para beneficios: ${self.available:,.2f}"


class BenefitBudgetPolicy:
    @staticmethod
    def compute(lines, *, committed: Decimal = _ZERO) -> BenefitBudget:
        room = _ZERO
        sin_costo: list[str] = []
        for line in lines:
            if line.cost is None:
                sin_costo.append(line.name or line.product_id)
                continue
            protegido = (Decimal(str(line.revenue)) * Decimal(str(line.min_margin)))
            room += max(Decimal(str(line.revenue)) - Decimal(str(line.cost)) - protegido, _ZERO)
        room = room.quantize(_CENT)
        usado = Decimal(str(committed)).quantize(_CENT)
        return BenefitBudget(room=room, committed=usado,
                             available=max(room - usado, _ZERO),
                             lines_without_cost=tuple(sin_costo))

    @staticmethod
    def allows(budget: BenefitBudget, extra: Decimal) -> bool:
        """¿Cabe un beneficio más de `extra` sin autorización?"""
        return not budget.lines_without_cost and Decimal(str(extra)) <= budget.available
