"""CanonicalProductionInventoryHandler — the production flip (INV-27).

Replaces the legacy ProductionInventoryHandler on the live
PRODUCTION_ITEMS_PROCESS event. The live payload carries a flat ``movements``
list of ``{product_id, delta, movement_type, operation_id?}`` where the sign of
``delta`` is the direction:

- ``delta < 0`` → raw-material **consumption** (DECREASE) → PRODUCTION_CONSUMPTION
- ``delta > 0`` → derived-product **output** (INCREASE) → PRODUCTION_OUTPUT

It posts (at most) two canonical movements — one consumption, one output —
instead of the legacy per-item ``InventoryEngine.process_movement``. Both join
the production transaction (the outer flow owns the commit, legacy
``conn``-in-payload contract), and are idempotent by derived operation_id.

Merma is implicit: consumed inputs and produced outputs are different products,
so the yield gap simply *is* the loss (Finance values it from the cost ledger).
Location convention = branch_id (matches the canonical backfill opening balances).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from backend.application.inventory.use_cases.post_inventory_movement import (
    PostInventoryMovementUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import InventoryStatus, MovementType

logger = logging.getLogger("spj.inventory.production_bridge")


def _num(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


class CanonicalProductionInventoryHandler:
    """Subscribes to PRODUCTION_ITEMS_PROCESS and posts canonical stock movements."""

    event_name = "PRODUCTION_ITEMS_PROCESS"

    def __init__(self, connection_provider,
                 use_case: PostInventoryMovementUseCase | None = None) -> None:
        self._conn = connection_provider
        self._uc = use_case or PostInventoryMovementUseCase()

    def handle(self, payload: dict) -> None:
        branch_id = str(payload.get("branch_id") or payload.get("sucursal_id") or "")
        base_op = str(payload.get("operation_id") or payload.get("reference_id") or "").strip()
        document_id = str(payload.get("reference_id") or "")
        user = str(payload.get("user") or payload.get("usuario") or "produccion")
        movements = payload.get("movements", [])
        if not branch_id or not base_op or not movements:
            logger.warning("production bridge: payload incompleto; se ignora")
            return

        # The production flow shares its live transaction via the payload conn
        # (legacy atomicity contract); fall back to the injected provider.
        conn = payload.get("conn") or self._conn()

        consume_lines: list[InventoryMovementLine] = []
        output_lines: list[InventoryMovementLine] = []
        for mov in movements:
            product_id = str(mov.get("product_id") or "")
            delta = _num(mov.get("delta", 0))
            if not product_id or delta == 0:
                continue
            if delta < 0:
                consume_lines.append(InventoryMovementLine.create(
                    product_id=product_id, quantity=-delta,
                    from_location_id=branch_id, from_status=InventoryStatus.AVAILABLE,
                    reason_code="PRODUCTION_CONSUMPTION"))
            else:
                output_lines.append(InventoryMovementLine.create(
                    product_id=product_id, quantity=delta,
                    to_location_id=branch_id, to_status=InventoryStatus.AVAILABLE,
                    reason_code="PRODUCTION_OUTPUT"))

        if consume_lines:
            self._post(conn, MovementType.PRODUCTION_CONSUMPTION, consume_lines,
                       operation_id=f"{base_op}:consume", branch_id=branch_id,
                       document_id=document_id, user=user)
        if output_lines:
            self._post(conn, MovementType.PRODUCTION_OUTPUT, output_lines,
                       operation_id=f"{base_op}:output", branch_id=branch_id,
                       document_id=document_id, user=user)

    def _post(self, conn, movement_type, lines, *, operation_id, branch_id,
              document_id, user) -> None:
        movement = InventoryMovement.create(
            movement_type=movement_type, branch_id=branch_id, warehouse_id=branch_id,
            source_module="production", source_document_type="PRODUCTION",
            source_document_id=document_id, operation_id=operation_id,
            created_by_user_id=user, lines=lines)
        # Joins the production transaction; the outer flow owns the commit.
        result = self._uc.execute(conn, movement, actor_user_id=user,
                                  owns_transaction=False)
        if not result.success:
            raise RuntimeError(result.message or "No se pudo aplicar el movimiento de producción.")
