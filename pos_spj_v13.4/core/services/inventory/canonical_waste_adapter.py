"""CanonicalWasteInventoryService — canonical stock decrease for the waste flow.

Implements the ``decrease_stock(...)`` contract that ``WasteApplicationService``
expects (``InventoryApplicationServiceProtocol``), but instead of mutating the
legacy ``inventory_stock`` table it posts ONE canonical ``WASTE`` movement
(DECREASE from AVAILABLE) to the ledger via ``PostInventoryMovementUseCase``.

It never commits: it joins the waste repository's transaction (the repository's
``save_changes()`` owns the boundary, so the waste row and the stock movement
commit atomically; a failure rolls both back). Idempotent by ``operation_id``.
Location convention = branch_id (matches the canonical backfill / other flips).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from types import SimpleNamespace

from backend.application.inventory.use_cases.post_inventory_movement import (
    PostInventoryMovementUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import InventoryStatus, MovementType

logger = logging.getLogger("spj.inventory.waste_adapter")


class CanonicalWasteInventoryService:
    """Canonical replacement for the legacy inventory service in the merma flow."""

    def __init__(self, connection_provider, use_case: PostInventoryMovementUseCase | None = None) -> None:
        self._conn = connection_provider
        self._uc = use_case or PostInventoryMovementUseCase()

    def decrease_stock(self, *, product_id, branch_id, quantity, unit, reason,
                       operation_id, source_module, reference_type=None,
                       reference_id=None, user_name="", auto_commit=None):
        branch = str(branch_id or "")
        qty = Decimal(str(quantity or 0))
        user = user_name or "system"
        if qty <= 0 or not product_id or not branch:
            return SimpleNamespace(success=False, message="WASTE_INVALID_MOVEMENT",
                                   events=(), stock_before=None, stock_after=None)
        line = InventoryMovementLine.create(
            product_id=str(product_id), quantity=qty, unit=unit or "unit",
            from_location_id=branch, from_status=InventoryStatus.AVAILABLE,
            reason_code=(reason or "WASTE")[:64])
        movement = InventoryMovement.create(
            movement_type=MovementType.WASTE, branch_id=branch, warehouse_id=branch,
            source_module=source_module or "waste",
            source_document_type=reference_type or "WASTE",
            source_document_id=str(reference_id or ""), operation_id=str(operation_id),
            created_by_user_id=user, lines=[line])
        # owns_transaction=False → the waste repository's save_changes() commits both.
        result = self._uc.execute(self._conn(), movement, actor_user_id=user,
                                  owns_transaction=False)
        return SimpleNamespace(
            success=result.success, message=result.message, events=(),
            stock_before=None, stock_after=None)
