"""Reparto de un costo conjunto entre las salidas de una transformación.

Dueño: COSTOS. Antes vivía en Procesamiento Cárnico, que costeaba sus propias
salidas; ahora Procesamiento sólo publica qué consumió y qué produjo, y Costos
decide cómo se reparte.

Métodos (configurables, ninguno fijo):

- WEIGHT_BASED: cada salida carga por su peso. El desperdicio también: su parte
  es la merma valorizada que Finanzas reconoce.
- RELATIVE_SALES_VALUE: por `peso × precio de venta`. El desperdicio no carga.
- NET_REALIZABLE_VALUE: por `peso × (precio − costo separable por unidad)`.
- STANDARD_COST: por `peso × costo estándar` de cada salida.
- CONFIGURED_FACTOR: por `peso × factor` configurado para cada salida.

Puro, sin I/O, sólo `Decimal`. Nunca inventa un dato: si el método necesita un
precio, un costo estándar o un factor que falta, es un error explícito. El total
repartido cuadra al centavo con el costo de entrada (el último absorbe el
redondeo).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

_CENT = Decimal("0.01")
_UNIT = Decimal("0.0001")
_NON_STOCK_TYPES = frozenset({"WASTE", "LOSS"})


class AllocationMethod(str, Enum):
    WEIGHT_BASED = "WEIGHT_BASED"
    RELATIVE_SALES_VALUE = "RELATIVE_SALES_VALUE"
    NET_REALIZABLE_VALUE = "NET_REALIZABLE_VALUE"
    STANDARD_COST = "STANDARD_COST"
    CONFIGURED_FACTOR = "CONFIGURED_FACTOR"


class CostAllocationError(ValueError):
    pass


def _dec(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, float):
        raise TypeError("Los importes de costeo usan Decimal, nunca float")
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class AllocationInput:
    product_id: str
    output_type: str
    weight: Decimal
    unit_price: Decimal | None = None
    standard_unit_cost: Decimal | None = None
    separable_unit_cost: Decimal = Decimal("0")
    factor: Decimal | None = None

    def __post_init__(self) -> None:
        for name in ("weight", "unit_price", "standard_unit_cost", "separable_unit_cost",
                     "factor"):
            object.__setattr__(self, name, _dec(getattr(self, name)))
        if self.weight is None or self.weight < 0:
            raise CostAllocationError("El peso de una salida no puede ser negativo")

    @property
    def goes_to_stock(self) -> bool:
        return str(self.output_type) not in _NON_STOCK_TYPES


@dataclass(frozen=True)
class AllocatedOutput:
    product_id: str
    output_type: str
    weight: Decimal
    unit_price: Decimal | None
    allocated_cost: Decimal
    unit_cost: Decimal
    basis_value: Decimal = Decimal("0")


class JointCostAllocator:
    def __init__(self, method: AllocationMethod = AllocationMethod.RELATIVE_SALES_VALUE) -> None:
        self.method = AllocationMethod(method)

    def _basis(self, o: AllocationInput) -> Decimal | None:
        """Base de reparto de una salida, o None si esa salida no carga costo."""
        if o.weight <= 0:
            return None
        if self.method is AllocationMethod.WEIGHT_BASED:
            return o.weight
        if not o.goes_to_stock:
            return None
        if self.method is AllocationMethod.RELATIVE_SALES_VALUE:
            if o.unit_price is None or o.unit_price <= 0:
                raise CostAllocationError(f"sin precio de venta: {o.product_id}")
            return o.weight * o.unit_price
        if self.method is AllocationMethod.NET_REALIZABLE_VALUE:
            if o.unit_price is None:
                raise CostAllocationError(f"sin precio de venta: {o.product_id}")
            neto = o.unit_price - o.separable_unit_cost
            if neto <= 0:
                raise CostAllocationError(f"valor neto realizable no positivo: {o.product_id}")
            return o.weight * neto
        if self.method is AllocationMethod.STANDARD_COST:
            if o.standard_unit_cost is None or o.standard_unit_cost <= 0:
                raise CostAllocationError(f"sin costo estándar: {o.product_id}")
            return o.weight * o.standard_unit_cost
        if o.factor is None or o.factor <= 0:
            raise CostAllocationError(f"sin factor de reparto configurado: {o.product_id}")
        return o.weight * o.factor

    def allocate(self, total_cost, outputs: list[AllocationInput]) -> list[AllocatedOutput]:
        total_cost = _dec(total_cost)
        if total_cost is None or total_cost < 0:
            raise CostAllocationError("El costo a repartir no puede ser negativo")
        bases: dict[int, Decimal] = {}
        faltan: list[str] = []
        cargables = [i for i, o in enumerate(outputs) if o.weight > 0 and o.goes_to_stock]
        if self.method is not AllocationMethod.WEIGHT_BASED and len(cargables) == 1:
            # Un solo producto puede cargar costo: se lleva el 100 % con
            # CUALQUIER método, así que su base (precio, estándar, factor) no
            # cambia nada y no se exige.
            bases[cargables[0]] = outputs[cargables[0]].weight
        else:
            for i, o in enumerate(outputs):
                try:
                    base = self._basis(o)
                except CostAllocationError as exc:
                    faltan.append(str(exc))
                    continue
                if base is not None and base > 0:
                    bases[i] = base
        if faltan:
            raise CostAllocationError(
                f"No se puede repartir por {self.method.value}: " + "; ".join(faltan))
        if not bases:
            raise CostAllocationError("No hay salidas entre las que repartir el costo")
        base_total = sum(bases.values(), Decimal("0"))
        ultimo = max(bases)
        resultado: list[AllocatedOutput] = []
        repartido = Decimal("0")
        for i, o in enumerate(outputs):
            if i not in bases:
                resultado.append(AllocatedOutput(o.product_id, str(o.output_type), o.weight,
                                                 o.unit_price, Decimal("0"), Decimal("0")))
                continue
            if i == ultimo:
                costo = (total_cost - repartido).quantize(_CENT, rounding=ROUND_HALF_UP)
            else:
                costo = (total_cost * bases[i] / base_total).quantize(
                    _CENT, rounding=ROUND_HALF_UP)
                repartido += costo
            resultado.append(AllocatedOutput(
                o.product_id, str(o.output_type), o.weight, o.unit_price, costo,
                (costo / o.weight).quantize(_UNIT, rounding=ROUND_HALF_UP), bases[i]))
        return resultado
