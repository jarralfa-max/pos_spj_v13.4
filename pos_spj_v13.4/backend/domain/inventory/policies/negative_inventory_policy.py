"""NegativeInventoryPolicy — negative on-hand is forbidden by default (§16).

An outgoing movement may not drive a balance below zero unless a configured
exception applies (product + branch allowed) AND a hot authorization was granted.
Negative stock is never hidden by silent auto-adjustments.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.inventory.exceptions import (
    InventoryAuthorizationRequiredError,
    InventoryDomainError,
)


def _dec(value: Decimal | int | str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InventoryDomainError("No se permite float en balances")
    return Decimal(str(value))


class NegativeInventoryPolicy:
    def enforce_can_decrease(
        self,
        *,
        current_on_hand: Decimal | int | str,
        decrease_by: Decimal | int | str,
        allowed: bool = False,
        authorized: bool = False,
    ) -> None:
        """Raise unless the decrease is legal.

        - stays >= 0 → always allowed;
        - goes negative + not allowed → hard block;
        - goes negative + allowed but not authorized → needs hot authorization.
        """
        current = _dec(current_on_hand)
        delta = _dec(decrease_by)
        if delta < 0:
            raise InventoryDomainError("La disminución debe ser no negativa")
        resulting = current - delta
        if resulting >= 0:
            return
        if not allowed:
            raise InventoryDomainError(
                "Inventario negativo no permitido para este producto/sucursal")
        if not authorized:
            raise InventoryAuthorizationRequiredError(
                "El inventario negativo requiere autorización explícita")
