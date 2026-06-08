"""ApplicationService for canonical inventory mutations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.infrastructure.db.repositories.inventory_repository import (
    InventoryMovementRecord,
    InventoryRepository,
)
from backend.shared.events.event_bus import EventBus, InMemoryEventBus
from backend.shared.events.event_contracts import DomainEvent, create_domain_event
from backend.shared.events.event_names import EventName


@dataclass(frozen=True)
class InventoryMutationResult:
    success: bool
    operation_id: str
    stock_before: float = 0.0
    stock_after: float = 0.0
    movement_type: str = ""
    message: str = ""
    movements: tuple[InventoryMovementRecord, ...] = field(default_factory=tuple)
    events: tuple[DomainEvent, ...] = field(default_factory=tuple)


class InventoryApplicationService:
    """Canonical mutation route for inventory_stock and inventory_movements."""

    def __init__(self, *, repository: InventoryRepository, event_bus: EventBus | None = None) -> None:
        self._repository = repository
        self._event_bus = event_bus or InMemoryEventBus()

    def increase_stock(
        self,
        product_id: int,
        branch_id: int,
        quantity: float,
        unit: str,
        reason: str,
        operation_id: str,
        source_module: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
        user_name: str = "",
    ) -> InventoryMutationResult:
        return self._change_stock(
            product_id=product_id,
            branch_id=branch_id,
            quantity=quantity,
            unit=unit,
            reason=reason,
            operation_id=operation_id,
            source_module=source_module,
            reference_type=reference_type,
            reference_id=reference_id,
            user_name=user_name,
            movement_type="INCREASE",
            signed_delta=float(quantity),
        )

    def decrease_stock(
        self,
        product_id: int,
        branch_id: int,
        quantity: float,
        unit: str,
        reason: str,
        operation_id: str,
        source_module: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
        user_name: str = "",
    ) -> InventoryMutationResult:
        return self._change_stock(
            product_id=product_id,
            branch_id=branch_id,
            quantity=quantity,
            unit=unit,
            reason=reason,
            operation_id=operation_id,
            source_module=source_module,
            reference_type=reference_type,
            reference_id=reference_id,
            user_name=user_name,
            movement_type="DECREASE",
            signed_delta=-float(quantity),
        )

    def adjust_stock(
        self,
        product_id: int,
        branch_id: int,
        new_quantity: float,
        unit: str,
        reason: str,
        operation_id: str,
        source_module: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
        user_name: str = "",
    ) -> InventoryMutationResult:
        self._validate_context(product_id, branch_id, operation_id, source_module, user_name)
        target_quantity = float(new_quantity)
        if target_quantity < 0:
            return InventoryMutationResult(False, operation_id, message="INVENTORY_NEGATIVE_STOCK_NOT_ALLOWED")
        current = self._repository.get_stock(product_id=int(product_id), branch_id=int(branch_id))
        delta = target_quantity - current.quantity
        movement_type = "ADJUST_INCREASE" if delta >= 0 else "ADJUST_DECREASE"
        movement = InventoryMovementRecord(
            operation_id=operation_id,
            product_id=int(product_id),
            branch_id=int(branch_id),
            movement_type=movement_type,
            quantity=abs(delta),
            stock_before=current.quantity,
            stock_after=target_quantity,
            unit=unit or current.unit,
            source_module=source_module,
            reference_type=reference_type,
            reference_id=reference_id,
            reason=reason,
            user_name=user_name,
        )
        return self._record_and_publish(movement)

    def transfer_stock(
        self,
        product_id: int,
        from_branch_id: int,
        to_branch_id: int,
        quantity: float,
        unit: str,
        reason: str,
        operation_id: str,
        source_module: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
        user_name: str = "",
    ) -> InventoryMutationResult:
        self._validate_context(product_id, from_branch_id, operation_id, source_module, user_name)
        self._validate_context(product_id, to_branch_id, operation_id, source_module, user_name)
        if int(from_branch_id) == int(to_branch_id):
            return InventoryMutationResult(False, operation_id, message="INVENTORY_TRANSFER_BRANCHES_MUST_DIFFER")
        qty = self._positive_quantity(quantity)
        origin = self._repository.get_stock(product_id=int(product_id), branch_id=int(from_branch_id))
        destination = self._repository.get_stock(product_id=int(product_id), branch_id=int(to_branch_id))
        origin_after = origin.quantity - qty
        if origin_after < 0:
            return InventoryMutationResult(False, operation_id, stock_before=origin.quantity, message="INVENTORY_NEGATIVE_STOCK_NOT_ALLOWED")
        outgoing = InventoryMovementRecord(
            operation_id=operation_id,
            product_id=int(product_id),
            branch_id=int(from_branch_id),
            movement_type="TRANSFER_OUT",
            quantity=qty,
            stock_before=origin.quantity,
            stock_after=origin_after,
            unit=unit or origin.unit,
            source_module=source_module,
            reference_type=reference_type,
            reference_id=reference_id,
            reason=reason,
            user_name=user_name,
        )
        incoming = InventoryMovementRecord(
            operation_id=operation_id,
            product_id=int(product_id),
            branch_id=int(to_branch_id),
            movement_type="TRANSFER_IN",
            quantity=qty,
            stock_before=destination.quantity,
            stock_after=destination.quantity + qty,
            unit=unit or destination.unit,
            source_module=source_module,
            reference_type=reference_type,
            reference_id=reference_id,
            reason=reason,
            user_name=user_name,
        )
        existing_out = self._repository.get_movement(
            operation_id=outgoing.operation_id,
            product_id=outgoing.product_id,
            branch_id=outgoing.branch_id,
            movement_type=outgoing.movement_type,
        )
        existing_in = self._repository.get_movement(
            operation_id=incoming.operation_id,
            product_id=incoming.product_id,
            branch_id=incoming.branch_id,
            movement_type=incoming.movement_type,
        )
        if existing_out is not None and existing_in is not None:
            return InventoryMutationResult(
                True,
                operation_id,
                stock_before=existing_out.stock_before,
                stock_after=existing_out.stock_after,
                movement_type="TRANSFER",
                movements=(existing_out, existing_in),
                events=(),
            )
        try:
            persisted_out = self._repository.record_movement(outgoing)
            persisted_in = self._repository.record_movement(incoming)
            self._repository.commit()
        except Exception as exc:
            self._repository.rollback()
            return InventoryMutationResult(False, operation_id, message=str(exc))
        events = self._publish_events(persisted_out) + self._publish_events(persisted_in)
        return InventoryMutationResult(
            True,
            operation_id,
            stock_before=origin.quantity,
            stock_after=origin_after,
            movement_type="TRANSFER",
            movements=(persisted_out, persisted_in),
            events=events,
        )

    def _change_stock(
        self,
        *,
        product_id: int,
        branch_id: int,
        quantity: float,
        unit: str,
        reason: str,
        operation_id: str,
        source_module: str,
        reference_type: str | None,
        reference_id: str | None,
        user_name: str,
        movement_type: str,
        signed_delta: float,
    ) -> InventoryMutationResult:
        self._validate_context(product_id, branch_id, operation_id, source_module, user_name)
        qty = self._positive_quantity(quantity)
        current = self._repository.get_stock(product_id=int(product_id), branch_id=int(branch_id))
        stock_after = current.quantity + signed_delta
        if stock_after < 0:
            return InventoryMutationResult(False, operation_id, stock_before=current.quantity, message="INVENTORY_NEGATIVE_STOCK_NOT_ALLOWED")
        movement = InventoryMovementRecord(
            operation_id=operation_id,
            product_id=int(product_id),
            branch_id=int(branch_id),
            movement_type=movement_type,
            quantity=qty,
            stock_before=current.quantity,
            stock_after=stock_after,
            unit=unit or current.unit,
            source_module=source_module,
            reference_type=reference_type,
            reference_id=reference_id,
            reason=reason,
            user_name=user_name,
        )
        return self._record_and_publish(movement)

    def _record_and_publish(self, movement: InventoryMovementRecord) -> InventoryMutationResult:
        existing = self._repository.get_movement(
            operation_id=movement.operation_id,
            product_id=movement.product_id,
            branch_id=movement.branch_id,
            movement_type=movement.movement_type,
        )
        if existing is not None:
            return InventoryMutationResult(
                True,
                existing.operation_id,
                stock_before=existing.stock_before,
                stock_after=existing.stock_after,
                movement_type=existing.movement_type,
                movements=(existing,),
                events=(),
            )
        try:
            persisted = self._repository.record_movement(movement)
            self._repository.commit()
        except Exception as exc:
            self._repository.rollback()
            return InventoryMutationResult(False, movement.operation_id, message=str(exc))
        events = self._publish_events(persisted)
        return InventoryMutationResult(
            True,
            persisted.operation_id,
            stock_before=persisted.stock_before,
            stock_after=persisted.stock_after,
            movement_type=persisted.movement_type,
            movements=(persisted,),
            events=events,
        )

    def _publish_events(self, movement: InventoryMovementRecord) -> tuple[DomainEvent, ...]:
        payload = self._movement_event_payload(movement)
        events = tuple(
            create_domain_event(
                event_name=event_name,
                operation_id=movement.operation_id,
                entity_id=str(movement.product_id),
                branch_id=str(movement.branch_id),
                user_name=movement.user_name or "system",
                source_module=movement.source_module,
                payload=dict(payload),
            )
            for event_name in (
                EventName.INVENTORY_MOVEMENT_RECORDED,
                EventName.INVENTORY_STOCK_UPDATED,
            )
        )
        for event in events:
            self._event_bus.publish(event)
        return events

    @staticmethod
    def _movement_event_payload(movement: InventoryMovementRecord) -> dict[str, Any]:
        return {
            "operation_id": movement.operation_id,
            "product_id": movement.product_id,
            "branch_id": movement.branch_id,
            "movement_type": movement.movement_type,
            "quantity": movement.quantity,
            "stock_before": movement.stock_before,
            "stock_after": movement.stock_after,
            "unit": movement.unit,
            "source_module": movement.source_module,
            "reference_type": movement.reference_type,
            "reference_id": movement.reference_id,
            "reason": movement.reason,
            "user_name": movement.user_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _validate_context(product_id: int, branch_id: int, operation_id: str, source_module: str, user_name: str) -> None:
        if int(product_id or 0) <= 0:
            raise ValueError("product_id is required")
        if int(branch_id or 0) <= 0:
            raise ValueError("branch_id is required")
        if not operation_id:
            raise ValueError("operation_id is required")
        if not source_module:
            raise ValueError("source_module is required")
        if not user_name:
            raise ValueError("user_name is required")

    @staticmethod
    def _positive_quantity(quantity: float) -> float:
        qty = float(quantity or 0.0)
        if qty <= 0:
            raise ValueError("quantity must be greater than zero")
        return qty
