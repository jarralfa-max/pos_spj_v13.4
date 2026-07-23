"""CanonicalSaleInventoryHandler — the sales flip (INV-27).

Replaces the legacy SaleInventoryHandler on the live SALE_ITEMS_PROCESS event.
The BOM/recipe explosion (composite product → component deductions) is preserved
verbatim via RecipeResolver — only the final mutation changes: instead of the
legacy inventory engine's decrease_stock, it posts ONE canonical SALE_ISSUE
movement to the ledger through PostInventoryMovementUseCase (atomic with the
sale's transaction, idempotent by operation_id).

Payload (legacy shape): branch_id/sucursal_id, operation_id|sale_id, user, folio,
items:[{product_id, qty|cantidad, unit|unidad, es_compuesto}].
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

logger = logging.getLogger("spj.inventory.sale_bridge")


def _num(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


class CanonicalSaleInventoryHandler:
    """Subscribes to SALE_ITEMS_PROCESS and deducts stock from the canonical ledger."""

    event_name = "SALE_ITEMS_PROCESS"

    def __init__(self, connection_provider,
                 use_case: PostInventoryMovementUseCase | None = None) -> None:
        self._conn = connection_provider
        self._uc = use_case or PostInventoryMovementUseCase()

    def handle(self, payload: dict) -> None:
        branch_id = str(payload.get("branch_id") or payload.get("sucursal_id") or "")
        operation_id = str(payload.get("operation_id") or payload.get("sale_id") or "").strip()
        sale_id = str(payload.get("sale_id") or payload.get("venta_id") or "")
        user = str(payload.get("user") or payload.get("usuario") or "system")
        items = payload.get("items", [])
        if not branch_id or not operation_id or not items:
            logger.warning("sale bridge: payload incompleto; se ignora")
            return

        deductions = self._resolve_deductions(items, branch_id)
        lines = [
            InventoryMovementLine.create(
                product_id=pid, quantity=qty, from_location_id=branch_id,
                from_status=InventoryStatus.AVAILABLE, reason_code="SALE")
            for pid, qty in deductions.items() if qty > 0
        ]
        if not lines:
            return

        movement = InventoryMovement.create(
            movement_type=MovementType.SALE_ISSUE, branch_id=branch_id,
            warehouse_id=branch_id, source_module="sales",
            source_document_type="SALE", source_document_id=sale_id,
            operation_id=operation_id, created_by_user_id=user, lines=lines)
        # The sale opens its own SAVEPOINT and dispatches SALE_ITEMS_PROCESS
        # synchronously on the shared connection; the outer sale owns the commit
        # (legacy contract: decrease_stock(auto_commit=False)). So we join that
        # transaction instead of committing here. A SALE_ISSUE is system-driven
        # (no manual permission gate — the default use case carries no checker);
        # any failure must abort the sale rather than silently skip the
        # deduction and leak stock, so we raise on every non-success.
        result = self._uc.execute(self._conn(), movement, actor_user_id=user,
                                  owns_transaction=False)
        if not result.success:
            raise RuntimeError(result.message or "No se pudo descontar inventario de la venta.")

    # ── resolution (business logic preserved) ────────────────────────────────
    def _resolve_deductions(self, items, branch_id: str) -> dict[str, Decimal]:
        totals: dict[str, Decimal] = {}
        for item in items:
            product_id = str(item.get("product_id") or "")
            qty = _num(item.get("qty", item.get("cantidad", 0)))
            if qty <= 0 or not product_id:
                continue
            if int(item.get("es_compuesto", 0) or 0) == 1:
                for cid, cqty in self._explode_bom(product_id, qty, branch_id).items():
                    totals[cid] = totals.get(cid, Decimal("0")) + cqty
            else:
                totals[product_id] = totals.get(product_id, Decimal("0")) + qty
        return totals

    def _explode_bom(self, product_id: str, sale_qty: Decimal, branch_id: str) -> dict[str, Decimal]:
        from core.services.recipes.recipe_resolver import RecipeResolver
        explosion = RecipeResolver(self._conn()).resolve_for_sale(
            product_id, float(sale_qty), branch_id)
        if getattr(explosion, "cycle_detected", False):
            raise ValueError(
                f"El producto ID={product_id} tiene una receta con referencia circular.")
        no_recipe = (not explosion.deductions or (
            len(explosion.deductions) == 1
            and str(explosion.deductions[0].product_id) == product_id
            and explosion.deductions[0].is_virtual))
        if no_recipe:
            raise ValueError(
                f"El producto compuesto ID={product_id} no tiene receta activa.")
        merged: dict[str, Decimal] = {}
        for line in explosion.deductions:
            merged[str(line.product_id)] = merged.get(
                str(line.product_id), Decimal("0")) + _num(line.quantity)
        return {pid: q for pid, q in merged.items() if q > 0}
