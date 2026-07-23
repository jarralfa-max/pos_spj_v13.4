# core/services/inventory_service.py
"""InventoryService — shim de compatibilidad hacia el inventario canónico (corte
INV-27). Ya NO escribe inventory_stock legacy: delega en
InventoryApplicationService respaldado por el ledger canónico
(CanonicalInventoryRepository). Conserva la firma pública que usan
ventas_facade, cotizacion, reservation_service y el adaptador de delivery.

No commitea (owns_transaction del caller): el flujo que lo invoca es dueño de la
transacción, igual que el shim legacy anterior.
"""

import logging

logger = logging.getLogger(__name__)


class InventoryService:
    """Compat shim: firma legacy, persistencia canónica (ledger)."""

    def __init__(self, db_conn, inventory_repo=None):
        self.db = db_conn
        from backend.application.services.canonical_inventory_repository import (
            CanonicalInventoryRepository,
        )
        from backend.application.services.inventory_application_service import (
            InventoryApplicationService,
        )
        # auto_commit=False: el flujo llamador es dueño del commit (contrato legacy).
        self._app = InventoryApplicationService(
            repository=CanonicalInventoryRepository(db_conn), auto_commit=False)

    def get_stock(self, product_id, branch_id) -> float:
        from backend.application.inventory.queries import (
            InventoryAvailabilityQueryService,
        )
        return float(InventoryAvailabilityQueryService(self.db).get_availability(
            product_id=str(product_id), branch_id=str(branch_id)).available)

    def add_stock(self, product_id, branch_id, qty, unit_cost,
                  reference_type, reference_id, operation_id, user, notes=""):
        if float(qty) <= 0:
            raise ValueError("La cantidad a ingresar debe ser mayor a cero.")
        result = self._app.increase_stock(
            str(product_id), str(branch_id), float(qty), "unit",
            notes or reference_type or "", str(operation_id),
            reference_type or "inventory", reference_type, str(reference_id),
            user or "system")
        if not result.success:
            raise RuntimeError(result.message or "Fallo al ingresar inventario.")

    def deduct_stock(self, product_id, branch_id, qty,
                     reference_type, reference_id, operation_id, user, notes=""):
        if float(qty) <= 0:
            raise ValueError("La cantidad a descontar debe ser mayor a cero.")
        result = self._app.decrease_stock(
            str(product_id), str(branch_id), float(qty), "unit",
            notes or reference_type or "", str(operation_id),
            reference_type or "inventory", reference_type, str(reference_id),
            user or "system")
        if not result.success:
            # preserva el contrato: stock insuficiente → ValueError
            raise ValueError(result.message or "Stock insuficiente.")

    # ── aliases en español para EventBus wiring ───────────────────────────────
    def descontar_stock(self, producto_id, cantidad, branch_id=1,
                        referencia_id="EVT", usuario="sistema", **kwargs) -> None:
        self.deduct_stock(
            product_id=producto_id, branch_id=branch_id, qty=cantidad,
            reference_type="SALE_EVENT", reference_id=str(referencia_id),
            operation_id=kwargs.get("operation_id", str(referencia_id)),
            user=usuario, notes=kwargs.get("notes", ""))

    def incrementar_stock(self, producto_id, cantidad, unit_cost=0.0, branch_id=1,
                          referencia_id="EVT", usuario="sistema", **kwargs) -> None:
        self.add_stock(
            product_id=producto_id, branch_id=branch_id, qty=cantidad,
            unit_cost=unit_cost, reference_type="PURCHASE_EVENT",
            reference_id=str(referencia_id),
            operation_id=kwargs.get("operation_id", str(referencia_id)),
            user=usuario, notes=kwargs.get("notes", ""))

    def ajustar_merma(self, producto_id, cantidad, branch_id=1,
                      referencia_id="MERMA", usuario="sistema", **kwargs) -> None:
        self.deduct_stock(
            product_id=producto_id, branch_id=branch_id, qty=cantidad,
            reference_type="WASTE", reference_id=str(referencia_id),
            operation_id=kwargs.get("operation_id", str(referencia_id)),
            user=usuario, notes=kwargs.get("notes", "merma"))
