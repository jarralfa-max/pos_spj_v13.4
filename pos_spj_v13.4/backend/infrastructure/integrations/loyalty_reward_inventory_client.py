"""Fidelidad → Inventario: la recompensa de PRODUCTO sale del almacén (2026-10-03).

Decisión del usuario: "al confirmar la entrega se da salida al producto en la
sucursal que entrega (a su costo promedio)". Una salida de inventario con su
costo, en el almacén de venta de la sucursal (la misma elección que la venta) y
de los lotes que la misma estrategia elija. Sin existencia no se entrega: un
regalo no autoriza inventario negativo.

Se une a la transacción del caso de uso de Fidelidad (`owns_transaction=False`):
la entrega y la salida caen o se confirman juntas.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from backend.domain.loyalty.exceptions import LoyaltyDomainError

_CENT = Decimal("0.01")


class RewardStockError(LoyaltyDomainError):
    """No hay existencia (o almacén claro) para entregar la recompensa."""


class LoyaltyRewardInventoryClient:
    def __init__(self, connection, *, branch_id: str, actor_user_id: str) -> None:
        self._conn = connection
        self._branch_id = branch_id
        self._actor = actor_user_id

    def _warehouse(self) -> str:
        from backend.application.logistics.warehouse_directory import (
            WarehouseDirectoryQueryService,
        )

        almacenes = WarehouseDirectoryQueryService(self._conn).sales_warehouses_for_branch(
            self._branch_id)
        if len(almacenes) > 1:
            raise RewardStockError("La sucursal tiene varios almacenes de venta; deja uno solo.")
        return almacenes[0] if almacenes else self._branch_id

    def _unit_cost(self, product_id: str) -> Decimal | None:
        try:
            from backend.infrastructure.integrations.sales_pricing_client import (
                SalesPricingClient,
            )
            costo = SalesPricingClient(self._conn).unit_cost(product_id, branch_id=self._branch_id)
        except Exception:   # noqa: BLE001 - sin costo no se inventa
            return None
        return None if costo is None else Decimal(str(costo))

    def issue(self, *, redemption_id: str, product_id: str,
              quantity: Decimal) -> tuple[Decimal | None, Decimal, str]:
        """Da salida y devuelve (costo unitario, costo total, operación)."""
        from backend.application.inventory.use_cases.post_inventory_movement import (
            PostInventoryMovementUseCase,
        )
        from backend.application.inventory.use_cases.sale_reservation_use_cases import (
            plan_sale_issue,
        )
        from backend.domain.inventory.entities.inventory_movement import (
            InventoryMovement,
            InventoryMovementLine,
        )
        from backend.domain.inventory.enums import InventoryStatus, MovementType

        almacen = self._warehouse()
        rebanadas, faltante = plan_sale_issue(
            self._conn, product_id=product_id, branch_id=self._branch_id,
            warehouse_id=almacen, quantity=quantity)
        if faltante > 0:
            raise RewardStockError(
                f"No hay existencia suficiente para entregar la recompensa (faltan {faltante}).")
        costo = self._unit_cost(product_id)
        operacion = f"{redemption_id}:reward-issue"
        movimiento = InventoryMovement.create(
            movement_type=MovementType.ADJUSTMENT_OUT, branch_id=self._branch_id,
            warehouse_id=almacen, source_module="loyalty",
            source_document_type="LOYALTY_REWARD", source_document_id=redemption_id,
            operation_id=operacion, created_by_user_id=str(self._actor),
            lines=[InventoryMovementLine.create(
                product_id=product_id, quantity=r.quantity, from_location_id=r.location_id,
                lot_id=r.lot_id, from_status=InventoryStatus.AVAILABLE,
                reason_code="LOYALTY_REWARD", unit_cost=costo) for r in rebanadas])
        resultado = PostInventoryMovementUseCase().execute(
            self._conn, movimiento, actor_user_id=str(self._actor), owns_transaction=False)
        if not resultado.success:
            raise RewardStockError(resultado.message or "No se pudo dar salida a la recompensa.")
        total = ((costo or Decimal("0")) * Decimal(quantity)).quantize(_CENT, ROUND_HALF_UP)
        return costo, total, operacion


__all__ = ["LoyaltyRewardInventoryClient", "RewardStockError"]
