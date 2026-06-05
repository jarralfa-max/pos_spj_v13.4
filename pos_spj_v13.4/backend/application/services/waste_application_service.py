"""Canonical application service for waste registration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from typing import Any, Protocol

from backend.application.commands.waste_commands import RegisterWasteCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.shared.events.event_bus import EventBus, InMemoryEventBus
from backend.shared.events.event_contracts import create_domain_event
from backend.shared.events.event_names import EventName


class WasteRepositoryProtocol(Protocol):
    def operation_exists(self, operation_id: str) -> bool: ...
    def get_product_for_waste(self, product_id: int | str) -> Any: ...
    def register_waste(self, entry: dict[str, Any]) -> str: ...
    def decrease_inventory_for_waste(self, product_id: int | str, quantity: float) -> None: ...


@dataclass(frozen=True)
class WasteFinanceHandler:
    """Records financial loss for waste when a finance service is available."""

    finance_service: Any | None = None

    def record_loss(self, *, amount: float, product_id: int | str, quantity: float, reason: str,
                    waste_id: str, branch_id: str, user_name: str | None, user_id: str | None,
                    operation_id: str) -> None:
        if amount <= 0 or self.finance_service is None:
            return
        if hasattr(self.finance_service, "registrar_asiento"):
            self.finance_service.registrar_asiento(
                debe="mermas_y_deterioro",
                haber="inventario_almacen",
                concepto=f"Merma: {reason} — producto {product_id}",
                monto=round(abs(amount), 2),
                modulo="waste",
                referencia_id=waste_id,
                usuario_id=user_id or user_name,
                sucursal_id=branch_id,
                evento="WASTE_REGISTERED",
                metadata={
                    "operation_id": operation_id,
                    "product_id": product_id,
                    "quantity": quantity,
                    "reason": reason,
                },
            )
        elif hasattr(self.finance_service, "registrar_egreso"):
            self.finance_service.registrar_egreso(
                "merma",
                f"Merma prod #{product_id}: {reason}",
                round(abs(amount), 2),
                branch_id,
                operation_id,
                user_name or user_id or "",
            )


class WasteApplicationService:
    """Coordinates the single canonical waste mutation route."""

    def __init__(
        self,
        *,
        repository: WasteRepositoryProtocol,
        event_bus: EventBus | None = None,
        finance_handler: WasteFinanceHandler | Any | None = None,
    ) -> None:
        self._repository = repository
        self._event_bus = event_bus or InMemoryEventBus()
        if finance_handler is None or hasattr(finance_handler, "record_loss"):
            self._finance_handler = finance_handler or WasteFinanceHandler()
        else:
            self._finance_handler = WasteFinanceHandler(finance_handler)

    def register(self, command: RegisterWasteCommand) -> UseCaseResult:
        command.validate_context()
        branch_id = str(command.branch_id)
        product_id = command.product_id
        quantity = float(command.quantity)
        if not product_id:
            return UseCaseResult(False, command.operation_id, message="WASTE_PRODUCT_REQUIRED")
        if quantity <= 0:
            return UseCaseResult(False, command.operation_id, message="WASTE_QUANTITY_MUST_BE_GREATER_THAN_ZERO")
        if not command.reason:
            return UseCaseResult(False, command.operation_id, message="WASTE_REASON_REQUIRED")

        if self._repository.operation_exists(command.operation_id):
            return UseCaseResult(False, command.operation_id, message="WASTE_OPERATION_ALREADY_REGISTERED")

        product = self._repository.get_product_for_waste(product_id)
        if product is None:
            return UseCaseResult(False, command.operation_id, message="WASTE_PRODUCT_NOT_FOUND")

        unit = command.unit or str(product.get("unit") or "kg")
        unit_cost = float(product.get("unit_cost") or 0.0)
        loss_value = round(quantity * unit_cost, 2)
        waste_date = command.date or date_type.today().isoformat()

        entry = {
            "product_id": product_id,
            "branch_id": branch_id,
            "quantity": quantity,
            "unit": unit,
            "reason": command.reason,
            "unit_cost": unit_cost,
            "loss_value": loss_value,
            "notes": command.notes,
            "user_name": command.user_name or "",
            "operation_id": command.operation_id,
            "date": waste_date,
        }
        waste_id = self._repository.register_waste(entry)
        self._repository.decrease_inventory_for_waste(product_id, quantity)
        if hasattr(self._repository, "save_changes"):
            self._repository.save_changes()

        self._finance_handler.record_loss(
            amount=loss_value,
            product_id=product_id,
            quantity=quantity,
            reason=command.reason,
            waste_id=waste_id,
            branch_id=branch_id,
            user_name=command.user_name,
            user_id=command.user_id,
            operation_id=command.operation_id,
        )

        event = create_domain_event(
            event_name=EventName.WASTE_REGISTERED,
            operation_id=command.operation_id,
            entity_id=str(waste_id),
            branch_id=branch_id,
            user_id=command.user_id,
            user_name=command.user_name,
            source_module="waste",
            payload={
                "waste_id": waste_id,
                "product_id": product_id,
                "product_name": product.get("name"),
                "quantity": quantity,
                "unit": unit,
                "reason": command.reason,
                "unit_cost": unit_cost,
                "loss_value": loss_value,
                "date": waste_date,
            },
        )
        self._event_bus.publish(event)

        return UseCaseResult(
            True,
            command.operation_id,
            entity_id=str(waste_id),
            message="WASTE_REGISTERED",
            data={
                "waste_id": waste_id,
                "product_id": product_id,
                "product_name": product.get("name"),
                "quantity": quantity,
                "unit": unit,
                "unit_cost": unit_cost,
                "loss_value": loss_value,
                "date": waste_date,
            },
            events=(event,),
        )
