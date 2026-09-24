"""Precio mínimo de venta (Fase 5, decisión del usuario 2026-09-18).

"Bajo el mínimo pide autorización": un descuento que deja el precio unitario
EFECTIVO de una línea por debajo de su precio mínimo exige la misma
autorización en caliente que un descuento grande (otro usuario con permiso,
más un motivo) y queda auditado.

Medido antes del cambio: con Pollo a 100 y mínimo 95, un descuento de línea del
10 % lo dejaba en 90 sin pedir nada. El umbral del 20 % de `SaleDiscountPolicy`
no lo detecta: es una regla sobre el PORCENTAJE, ésta es sobre el PRECIO.

El precio efectivo de una línea descuenta su propio descuento y la parte que le
toca del descuento de la venta, repartido en proporción al importe bruto de cada
línea (la misma base sobre la que `apply_sale_discount` valida el descuento).
Decisión pura: los mínimos los resuelve Precios y los entrega quien llama.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")


@dataclass(frozen=True)
class LineBelowMinimum:
    line_id: str
    product_id: str
    effective_unit_price: Decimal
    minimum_price: Decimal

    def as_payload(self) -> dict[str, str]:
        return {"line_id": self.line_id, "product_id": self.product_id,
                "effective_unit_price": str(self.effective_unit_price),
                "minimum_price": str(self.minimum_price)}


class MinimumPricePolicy:
    @staticmethod
    def lines_below_minimum(
        lines: Iterable, *, minimums: Mapping[str, Decimal | None],
        sale_level_discount: Decimal = Decimal("0"),
    ) -> list[LineBelowMinimum]:
        """Líneas cuyo precio unitario efectivo queda bajo su mínimo.

        `minimums` va por `line_id`; una línea sin mínimo (None) nunca cuenta.
        """
        lines = list(lines)
        bruto_total = sum((l.quantity.value * l.unit_price for l in lines), Decimal("0"))
        descuento_venta = Decimal(str(sale_level_discount or 0))
        debajo: list[LineBelowMinimum] = []
        for linea in lines:
            minimo = minimums.get(linea.id)
            cantidad = linea.quantity.value
            if minimo is None or cantidad <= 0:
                continue
            bruto = cantidad * linea.unit_price
            reparto = (descuento_venta * bruto / bruto_total) if bruto_total > 0 else Decimal("0")
            efectivo = ((bruto - linea.discount_total - reparto) / cantidad).quantize(
                _CENT, rounding=ROUND_HALF_UP)
            # Sólo cuenta si un DESCUENTO la bajó. Una línea sin descuento cuyo
            # precio aprobado (lista de cliente, volumen) ya está bajo el mínimo
            # base es decisión de Precios, no del cajero: no debe bloquear el
            # descuento de OTRA línea.
            if efectivo < Decimal(str(minimo)) and efectivo < linea.unit_price:
                debajo.append(LineBelowMinimum(
                    line_id=linea.id, product_id=linea.product_id,
                    effective_unit_price=efectivo,
                    minimum_price=Decimal(str(minimo)).quantize(_CENT, rounding=ROUND_HALF_UP)))
        return debajo
