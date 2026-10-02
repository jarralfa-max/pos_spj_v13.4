"""Line-level policies: when a line can be added/modified, and whether a
quantity is valid (master prompt §11-12)."""

from __future__ import annotations

from decimal import Decimal

from backend.domain.sales.enums import SaleStatus
from backend.domain.sales.exceptions import (
    InvalidQuantityError,
    InvalidWeightError,
    PricingUnavailableError,
    SaleInvalidStateError,
)
from backend.domain.sales.policies.lifecycle_policies import SaleLifecyclePolicy
from backend.domain.sales.value_objects.quantity import Quantity


class SaleLinePolicy:
    @staticmethod
    def ensure_can_add_line(status: SaleStatus) -> None:
        if not SaleLifecyclePolicy.is_line_mutable(status):
            raise SaleInvalidStateError(
                f"No se pueden agregar líneas a una venta en estado {status}")

    @staticmethod
    def ensure_priced(unit_price: Decimal) -> None:
        """Una línea necesita precio (§64 `PricingUnavailableError`).

        Medido en la base real (re-auditoría POS, 2026-10-01): `product_price`
        no tenía NINGUNA fila, el catálogo mostraba $0.00 en todo y el carrito
        aceptaba vender a cero. Sin motor de promociones (ver SALES-11), una
        línea en cero sólo puede nacer de un precio sin capturar."""
        if unit_price is None or Decimal(str(unit_price)) <= 0:
            raise PricingUnavailableError(
                "El producto no tiene precio de venta. Captúralo en Precios antes de venderlo.")

    @staticmethod
    def ensure_can_modify_line(status: SaleStatus) -> None:
        if not SaleLifecyclePolicy.is_line_mutable(status):
            raise SaleInvalidStateError(
                f"No se pueden modificar líneas de una venta en estado {status}")


class QuantityPolicy:
    @staticmethod
    def ensure_valid(quantity: Quantity, *, max_sellable: Decimal | None = None) -> None:
        if quantity.value <= 0:
            raise InvalidQuantityError("La cantidad debe ser mayor a cero")
        if max_sellable is not None and quantity.value > max_sellable:
            raise InvalidQuantityError(
                f"Cantidad {quantity.value} excede el máximo vendible ({max_sellable})")


#: Lo que reporta una báscula: kilogramos con gramos (3 decimales). Coincide
#: con `WeightInput` del sistema de diseño.
WEIGHT_DECIMALS = 3


class WeightPolicy:
    """Peso de un producto que se vende por peso (§18-19)."""

    @staticmethod
    def ensure_valid(weight: Decimal) -> Decimal:
        if isinstance(weight, float):
            raise InvalidWeightError("El peso no se captura como float")
        try:
            value = Decimal(str(weight))
        except (ArithmeticError, ValueError) as exc:
            raise InvalidWeightError(f"Peso inválido: {weight!r}") from exc
        if value <= 0:
            raise InvalidWeightError("El peso debe ser mayor a cero")
        if -value.as_tuple().exponent > WEIGHT_DECIMALS:
            raise InvalidWeightError(
                f"El peso admite a lo más {WEIGHT_DECIMALS} decimales (gramos)")
        return value

