"""Composición de los adaptadores que usa Procesamiento para UNA orden.

Un solo lugar arma lo que preparar y ejecutar necesitan hacia Inventario,
Calidad, Mermas y Costos, siempre con la sucursal y el almacén de la orden y el
operador autenticado. La raíz de composición del módulo
(`meat_processing_factory.py`) y las pruebas de integración usan esto mismo.
"""

from __future__ import annotations

from backend.application.inventory.queries.stock_location_resolver import StockLocationResolver
from backend.application.meat_processing.ports import ExecutionPorts
from backend.infrastructure.integrations.meat_processing_ports import (
    CanonicalProductionConsumptionAdapter,
    CanonicalProductionReceiptAdapter,
    CostingAllocationAdapter,
    InventoryMaterialReservationAdapter,
    LossesYieldVarianceAdapter,
    QualityInspectionRequestAdapter,
)


def reservation_port_factory(connection, *, strategy=None):
    """(orden, operador) → reserva real en Inventario."""
    def factory(order, actor_user_id):
        return InventoryMaterialReservationAdapter(
            connection, branch_id=order.branch_id, warehouse_id=order.warehouse_id,
            actor_user_id=actor_user_id, document_id=order.id, strategy=strategy)
    return factory


def execution_ports_factory(*, dispatch_costing=None):
    """(conexión, orden, operador, motivo de variación) → `ExecutionPorts`."""
    def factory(connection, order, actor_user_id, variance_reason=None) -> ExecutionPorts:
        comunes = {"branch_id": order.branch_id, "warehouse_id": order.warehouse_id,
                   "actor_user_id": actor_user_id, "document_id": order.id}
        resolver = StockLocationResolver(connection)
        return ExecutionPorts(
            consumption=CanonicalProductionConsumptionAdapter(connection, **comunes),
            receipt=CanonicalProductionReceiptAdapter(connection, **comunes),
            reservation=InventoryMaterialReservationAdapter(connection, **comunes),
            quality=QualityInspectionRequestAdapter(
                connection, **comunes, produced_by_user_id=actor_user_id),
            losses=LossesYieldVarianceAdapter(
                connection, branch_id=order.branch_id, warehouse_id=order.warehouse_id,
                actor_user_id=actor_user_id, notes=variance_reason or ""),
            costing=CostingAllocationAdapter(
                connection, actor_user_id=actor_user_id, branch_id=order.branch_id,
                dispatch=dispatch_costing),
            output_location=lambda product_id: resolver.available_location(
                product_id=product_id, branch_id=order.branch_id,
                warehouse_id=order.warehouse_id))
    return factory
