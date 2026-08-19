"""Line-level policies: when a line can be added/modified, and whether a
quantity is valid (master prompt §11-12)."""

from __future__ import annotations

from decimal import Decimal

from backend.domain.sales.enums import SaleStatus
from backend.domain.sales.exceptions import InvalidQuantityError, SaleInvalidStateError
from backend.domain.sales.policies.lifecycle_policies import SaleLifecyclePolicy
from backend.domain.sales.value_objects.quantity import Quantity


class SaleLinePolicy:
    @staticmethod
    def ensure_can_add_line(status: SaleStatus) -> None:
        if not SaleLifecyclePolicy.is_line_mutable(status):
            raise SaleInvalidStateError(
                f"No se pueden agregar líneas a una venta en estado {status}")

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
