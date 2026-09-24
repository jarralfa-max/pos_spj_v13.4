"""Reparto del costo de la entrada entre las salidas (Fase 10, §10/§13).

Decisión del usuario (2026-09-19): **valor de venta relativo**. Cada salida
buena absorbe costo en proporción a `kg × precio de venta`: la pechuga carga
más que el huacal, como corresponde a coproductos cárnicos. La merma
(WASTE/LOSS) no absorbe costo: su costo lo cargan las salidas buenas, que es
justamente lo que hace subir el $/kg cuando el rendimiento baja.

Puro: sin I/O. El costo total y los precios los resuelve quien llama; aquí
sólo se reparte, y nunca se inventa un precio (§18): una salida buena sin
precio es un error explícito, no un cero silencioso.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")
_UNIT = Decimal("0.0001")
_NO_COST_TYPES = frozenset({"WASTE", "LOSS"})


class CostAllocationError(ValueError):
    pass


@dataclass(frozen=True)
class AllocationInput:
    product_id: str
    output_type: str
    weight: Decimal
    unit_price: Decimal | None


@dataclass(frozen=True)
class AllocatedOutput:
    product_id: str
    output_type: str
    weight: Decimal
    unit_price: Decimal | None
    allocated_cost: Decimal
    unit_cost: Decimal


class RelativeSalesValueCostAllocation:
    def allocate(self, total_cost: Decimal, outputs: list[AllocationInput]) -> list[AllocatedOutput]:
        total_cost = Decimal(str(total_cost))
        if total_cost < 0:
            raise CostAllocationError("El costo a repartir no puede ser negativo")
        buenas = [o for o in outputs
                  if str(o.output_type) not in _NO_COST_TYPES and o.weight > 0]
        sin_precio = [o.product_id for o in buenas if o.unit_price is None or o.unit_price <= 0]
        if sin_precio:
            raise CostAllocationError(
                "Para repartir el costo por valor de venta, cada salida necesita precio "
                "de venta. Sin precio: " + ", ".join(sin_precio))
        if not buenas:
            raise CostAllocationError("No hay salidas productivas entre las que repartir el costo")
        valores = {o.product_id: o.weight * o.unit_price for o in buenas}
        valor_total = sum(valores.values(), Decimal("0"))

        resultado: list[AllocatedOutput] = []
        repartido = Decimal("0")
        ultimo = buenas[-1].product_id
        for o in outputs:
            if o not in buenas:
                resultado.append(AllocatedOutput(o.product_id, str(o.output_type), o.weight,
                                                 o.unit_price, Decimal("0"), Decimal("0")))
                continue
            if o.product_id == ultimo:
                # El último absorbe el redondeo: el total repartido cuadra EXACTO.
                costo = (total_cost - repartido).quantize(_CENT, rounding=ROUND_HALF_UP)
            else:
                costo = (total_cost * valores[o.product_id] / valor_total).quantize(
                    _CENT, rounding=ROUND_HALF_UP)
                repartido += costo
            resultado.append(AllocatedOutput(
                o.product_id, str(o.output_type), o.weight, o.unit_price, costo,
                (costo / o.weight).quantize(_UNIT, rounding=ROUND_HALF_UP)))
        return resultado
