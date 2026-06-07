"""Application service for inventory mutations.

This service is the canonical entrypoint for desktop UI and future APIs. It
keeps the current business behavior by delegating to the protected legacy use
case, while dependencies are injected explicitly instead of passing a full
application composition object through the UI layer.
"""

from __future__ import annotations

from backend.application.commands.inventory_commands import (
    AdjustInventoryCommand,
    RegisterInventoryEntryCommand,
)
from core.use_cases.inventario import GestionarInventarioUC, ResultadoInventario


class InventoryApplicationService:
    """Inventory mutation facade with explicit dependencies."""

    def __init__(self, *, db, inventory_service, event_bus=None) -> None:
        self._use_case = GestionarInventarioUC(
            db=db,
            inventory_service=inventory_service,
            event_bus=event_bus,
        )

    def register_entry(self, command: RegisterInventoryEntryCommand) -> ResultadoInventario:
        command.validate_context()
        return self._use_case.registrar_entrada(
            producto_id=command.product_id,
            cantidad=command.quantity,
            sucursal_id=command.branch_id,
            usuario=command.user_name,
            costo_unit=command.unit_cost,
            proveedor_id=command.supplier_id,
            referencia=command.reference,
            notas=command.notes,
        )

    def adjust_stock(self, command: AdjustInventoryCommand) -> ResultadoInventario:
        command.validate_context()
        return self._use_case.registrar_ajuste(
            producto_id=command.product_id,
            cantidad_nueva=command.new_quantity,
            sucursal_id=command.branch_id,
            usuario=command.user_name,
            motivo=command.reason,
        )
