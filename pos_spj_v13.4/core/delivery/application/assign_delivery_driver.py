"""Assign a driver to a delivery order and transition it to preparation."""
from __future__ import annotations

import logging
from typing import Any

from core.delivery.domain.events import DeliveryEvents
from core.delivery.domain.state_machine import DeliveryStateMachine

from .ports import EventPublisher, NoopPublisher

logger = logging.getLogger("spj.delivery.application.assign_driver")


class AssignDeliveryDriverUseCase:
    """Assign driver + transition to 'preparing' atomically.

    Replaces the UI's direct SQL UPDATE that previously split driver
    assignment from the status change into two separate database writes.
    """

    def __init__(
        self,
        *,
        db,
        repository,
        publisher: EventPublisher = NoopPublisher,
        outbox_repository=None,
    ) -> None:
        self.db = db
        self.repository = repository
        self.publisher = publisher
        self.outbox_repository = outbox_repository

    def execute(
        self,
        order_id: int,
        driver_id: int,
        tiempo_estimado: str = "",
        notas: str = "",
        usuario: str = "sistema",
    ) -> dict[str, Any]:
        """Assign driver and move order to 'preparing'.

        Args:
            order_id: Delivery order primary key.
            driver_id: Driver primary key from the ``drivers`` table.
            tiempo_estimado: Estimated delivery time (free text, e.g. "30 min").
            notas: Optional operator notes appended to the order.
            usuario: User performing the action.

        Returns:
            Dict with order_id and driver_id.

        Raises:
            ValueError: If order not found, driver_id is missing, or the
                        current order state does not allow assignment.
        """
        if not driver_id:
            raise ValueError("driver_id es requerido para asignar repartidor")

        order = self.repository.get_order(order_id)
        if order is None:
            raise ValueError(f"Pedido {order_id} no encontrado")

        # Validate the state machine permits transitioning to preparing
        state_machine = DeliveryStateMachine()
        state_machine.assert_can_transition(order, "preparing")

        # Write driver fields + transition atomically
        self.db.execute(
            "UPDATE delivery_orders SET driver_id=? WHERE id=?",
            (driver_id, order_id),
        )
        if tiempo_estimado:
            try:
                self.db.execute(
                    "UPDATE delivery_orders SET tiempo_estimado=?, fecha_asignacion=datetime('now') WHERE id=?",
                    (tiempo_estimado, order_id),
                )
            except Exception:
                pass  # column may not exist in older schema versions
        if notas:
            self.db.execute(
                "UPDATE delivery_orders SET notas = ? WHERE id = ?",
                (notas, order_id),
            )

        self.repository.update_status(
            order_id,
            "preparing",
            usuario=usuario,
            observacion=f"Repartidor asignado: {driver_id}",
            reason="driver_assigned",
            metadata={"driver_id": driver_id, "source": "AssignDeliveryDriverUseCase"},
            commit=False,
        )

        operation_id = f"delivery:{order_id}:driver_assigned"
        payload: dict[str, Any] = {
            "order_id": order_id,
            "driver_id": driver_id,
            "tiempo_estimado": tiempo_estimado,
            "usuario": usuario,
        }

        if self.outbox_repository is not None:
            self.outbox_repository.enqueue(
                event_type=DeliveryEvents.DRIVER_ASSIGNED.value,
                aggregate_id=order_id,
                payload=payload,
                operation_id=operation_id,
                commit=False,
            )
            self.db.commit()
        else:
            self.db.commit()

        self.publisher(DeliveryEvents.DRIVER_ASSIGNED.value, payload)
        return {"order_id": order_id, "driver_id": driver_id}
