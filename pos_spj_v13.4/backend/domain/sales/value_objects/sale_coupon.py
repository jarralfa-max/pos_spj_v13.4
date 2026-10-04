"""SaleCoupon — un cupón aplicado a la venta (2026-10-03).

Fidelidad decide si el cupón aplica (vigencia, dueño, combinación con otros
beneficios §24) y lo aparta para esta venta; Ventas guarda la RESPUESTA:
qué cupón, de qué tipo (monto fijo o porcentaje) y por cuánto. El importe se
recalcula con el carrito —un 10 % sigue siendo 10 % si se agrega otra línea—,
nunca más que lo que queda por cobrar.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from backend.shared.ids import new_uuid

_CENT = Decimal("0.01")
FIXED_AMOUNT = "FIXED_AMOUNT"
PERCENTAGE = "PERCENTAGE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class SaleCoupon:
    id: str
    sale_id: str
    coupon_instance_id: str
    code: str
    benefit_type: str
    benefit_value: Decimal
    amount: Decimal = Decimal("0")
    applied_at: str = field(default_factory=_now)

    @classmethod
    def create(cls, *, sale_id: str, coupon_instance_id: str, code: str, benefit_type: str,
               benefit_value: Decimal) -> "SaleCoupon":
        if benefit_type not in (FIXED_AMOUNT, PERCENTAGE):
            raise ValueError(f"Beneficio de cupón no aplicable al ticket: {benefit_type}")
        valor = Decimal(str(benefit_value))
        if valor <= 0 or (benefit_type == PERCENTAGE and valor > 100):
            raise ValueError("Valor de cupón inválido")
        return cls(id=new_uuid(), sale_id=sale_id, coupon_instance_id=coupon_instance_id,
                   code=code, benefit_type=benefit_type, benefit_value=valor)

    def priced(self, *, base: Decimal, available: Decimal) -> "SaleCoupon":
        """El cupón valorado contra `base` (subtotal tras descuentos) sin pasar
        de `available` (lo que aún queda por cobrar)."""
        if self.benefit_type == PERCENTAGE:
            bruto = (Decimal(base) * self.benefit_value / Decimal("100")).quantize(
                _CENT, rounding=ROUND_HALF_UP)
        else:
            bruto = self.benefit_value
        return replace(self, amount=max(min(bruto, Decimal(available)), Decimal("0")))


__all__ = ["FIXED_AMOUNT", "PERCENTAGE", "SaleCoupon"]
