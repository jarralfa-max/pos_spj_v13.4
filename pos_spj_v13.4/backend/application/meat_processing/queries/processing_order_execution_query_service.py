"""Plan de captura de una orden: lo que la pantalla necesita para ejecutarla.

Entradas reservadas en Inventario (con su lote) y salidas esperadas, TODO desde
la definición congelada de la orden. Los nombres de producto son una lectura de
presentación, no de definición productiva.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.meat_processing.services.processing_execution_strategy import (
    strategy_for,
)


def _names(connection, ids) -> dict[str, str]:
    nombres = {}
    for pid in ids:
        try:
            fila = connection.execute("SELECT name FROM products WHERE id=?", (pid,)).fetchone()
        except Exception:  # noqa: BLE001 — base sin catálogo: se muestra el id
            fila = None
        nombres[pid] = str(fila[0]) if fila and fila[0] else pid
    return nombres


class ProcessingOrderExecutionQueryService:
    """Entradas reservadas (con lote) y salidas esperadas de una orden."""

    def __init__(self, connection) -> None:
        self._conn = connection

    def plan(self, order_id: str) -> dict | None:
        from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
            MeatProcessingUnitOfWork,
        )
        uow = MeatProcessingUnitOfWork(self._conn)
        order = uow.orders.get(order_id)
        if order is None:
            return None
        snapshot = uow.recipe_snapshots.get_by_order(order.id)
        asignaciones = uow.requirement_allocations.list_by_order(order.id)
        reservado: dict[str, Decimal] = {}
        lotes: dict[str, list] = {}
        for a in asignaciones:
            if a.status == "RELEASED":
                continue
            reservado[a.product_id] = reservado.get(a.product_id, Decimal("0")) + a.quantity
            lotes.setdefault(a.product_id, []).append(
                {"lot_id": a.allocated_lot_id, "quantity": a.quantity})
        if snapshot is None:
            return {"order_id": order.id, "status": order.status.value,
                    "has_definition": False, "inputs": [], "outputs": []}
        estrategia = strategy_for(snapshot)
        total = sum(reservado.values(), Decimal("0"))
        nombres = _names(self._conn, [i.product_id for i in snapshot.inputs]
                         + [o.product_id for o in snapshot.outputs])
        return {
            "order_id": order.id, "status": order.status.value, "has_definition": True,
            "process_family": snapshot.family.value if snapshot.family else None,
            "effective_version": snapshot.effective_version,
            "warehouse_id": order.warehouse_id,
            "inputs": [{"product_id": i.product_id, "product_name": nombres[i.product_id],
                        "reserved_weight": reservado.get(i.product_id, Decimal("0")),
                        "lot_controlled": i.lot_controlled,
                        "lots": lotes.get(i.product_id, [])} for i in snapshot.inputs],
            "outputs": [{"product_id": e.product_id, "product_name": nombres[e.product_id],
                         "output_type": e.output_type, "expected_weight": e.expected_weight,
                         "expected_yield_pct": e.expected_yield_pct,
                         "quality_gate": e.quality_gate, "goes_to_stock": e.goes_to_stock}
                        for e in (estrategia.expected_outputs(snapshot, total)
                                  if estrategia else [])],
            "reserved_total": total,
        }
