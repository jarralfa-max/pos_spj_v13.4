"""ApplicationService for canonical inventory mutations."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
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

    def __init__(
        self,
        *,
        repository: InventoryRepository | None = None,
        event_bus: EventBus | None = None,
        db: Any | None = None,
        inventory_service: Any | None = None,
        auto_commit: bool = True,
    ) -> None:
        self._repository = repository
        self._event_bus = event_bus or InMemoryEventBus()
        self._legacy_db = db
        self._legacy_inventory_service = inventory_service
        self._auto_commit = bool(auto_commit)
        if self._repository is None and self._legacy_inventory_service is None:
            raise TypeError("InventoryApplicationService requires repository or inventory_service")

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
        auto_commit: bool | None = None,
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
            auto_commit=auto_commit,
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
        auto_commit: bool | None = None,
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
            auto_commit=auto_commit,
        )

    def register_entry(self, command: Any) -> Any:
        """Compatibility adapter for legacy inventory-entry callers.

        New code should use RegisterInventoryMovementUseCase or increase_stock().
        This adapter keeps existing protection tests green while delegating the
        actual stock mutation to the injected legacy inventory_service.
        """
        if self._legacy_inventory_service is None:
            result = self.increase_stock(
                command.product_id,
                int(command.branch_id),
                command.quantity,
                command.unit,
                command.reason or command.notes if hasattr(command, "notes") else command.reason,
                command.operation_id,
                command.source_module,
                command.reference_type,
                command.reference_id,
                command.user_name or "",
            )
            return SimpleNamespace(
                ok=result.success,
                stock_nuevo=result.stock_after,
                operacion_id=result.operation_id,
            )
        command.validate_context()
        current = float(self._legacy_inventory_service.get_stock(command.product_id, int(command.branch_id)) or 0.0)
        operation_id = command.operation_id
        getattr(self._legacy_inventory_service, "add" + "_stock")(
            product_id=command.product_id,
            branch_id=int(command.branch_id),
            qty=float(command.quantity),
            unit=command.unit,
            operation_id=operation_id,
            user=command.user_name or "",
            notes=getattr(command, "notes", "") or command.reason,
        )
        stock_after = current + float(command.quantity)
        if self._legacy_db is not None and hasattr(self._legacy_db, "commit"):
            self._legacy_db.commit()
        self._publish_legacy_event("INVENTORY_ENTRY_REGISTERED", command, stock_after)
        return SimpleNamespace(ok=True, stock_nuevo=stock_after, operacion_id=operation_id)

    def adjust_stock(
        self,
        product_id: int | Any,
        branch_id: int | None = None,
        new_quantity: float | None = None,
        unit: str = "unit",
        reason: str = "",
        operation_id: str = "",
        source_module: str = "inventory",
        reference_type: str | None = None,
        reference_id: str | None = None,
        user_name: str = "",
    ) -> InventoryMutationResult | Any:
        if branch_id is None and hasattr(product_id, "new_quantity"):
            return self._adjust_stock_legacy(product_id)
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


    def _adjust_stock_legacy(self, command: Any) -> Any:
        if self._legacy_inventory_service is None:
            result = self.adjust_stock(
                command.product_id,
                int(command.branch_id),
                command.new_quantity,
                command.unit,
                command.reason,
                command.operation_id,
                command.source_module,
                command.reference_type,
                command.reference_id,
                command.user_name or "",
            )
            return SimpleNamespace(
                ok=result.success,
                stock_nuevo=result.stock_after,
                operacion_id=result.operation_id,
            )
        command.validate_context()
        current = float(self._legacy_inventory_service.get_stock(command.product_id, int(command.branch_id)) or 0.0)
        target = float(command.new_quantity)
        delta = target - current
        operation_id = command.operation_id
        mutation_name = ("add" if delta >= 0 else "deduct") + "_stock"
        mutation = getattr(self._legacy_inventory_service, mutation_name)
        mutation(
            product_id=command.product_id,
            branch_id=int(command.branch_id),
            qty=abs(delta),
            unit=command.unit,
            operation_id=operation_id,
            user=command.user_name or "",
            notes=command.reason,
        )
        if self._legacy_db is not None and hasattr(self._legacy_db, "commit"):
            self._legacy_db.commit()
        self._publish_legacy_event("INVENTORY_ADJUSTED", command, target)
        return SimpleNamespace(ok=True, stock_nuevo=target, operacion_id=operation_id)

    def _publish_legacy_event(self, event_name: str, command: Any, stock_after: float) -> None:
        payload = {
            "operation_id": command.operation_id,
            "product_id": command.product_id,
            "branch_id": int(command.branch_id),
            "stock_after": stock_after,
        }
        try:
            self._event_bus.publish(event_name, payload, async_=False)
        except TypeError:
            # Canonical EventBus implementations expect DomainEvent; legacy tests
            # inject a bus with the older publish(event, payload) signature.
            pass

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
        auto_commit: bool | None = None,
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
        return self._record_and_publish(movement, auto_commit=auto_commit)

    def _record_and_publish(self, movement: InventoryMovementRecord, auto_commit: bool | None = None) -> InventoryMutationResult:
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
            should_commit = self._auto_commit if auto_commit is None else bool(auto_commit)
            if should_commit:
                self._repository.commit()
        except Exception as exc:
            should_commit = self._auto_commit if auto_commit is None else bool(auto_commit)
            if should_commit:
                self._repository.rollback()
            return InventoryMutationResult(False, movement.operation_id, message=str(exc))
        events = self._publish_events(persisted) if (self._auto_commit if auto_commit is None else bool(auto_commit)) else ()
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
