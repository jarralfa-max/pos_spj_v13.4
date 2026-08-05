"""LOSS-6 orchestration over Inventory's canonical ledger use cases."""
from dataclasses import dataclass
from typing import Protocol

from backend.application.inventory.execution_context import InventoryExecutionContext
from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.permissions import LossPermissions
from backend.domain.inventory.entities.inventory_movement import InventoryMovement, InventoryMovementLine
from backend.domain.inventory.enums import InventoryStatus, MovementType
from backend.domain.losses.enums import LossClassificationCode, LossStatus
from backend.domain.losses.events import LossEvents, build_loss_event
from backend.domain.losses.exceptions import LossInvariantError


@dataclass(frozen=True)
class RequestLossInventoryCommand:
    operation_id: str
    loss_case_id: str
    context: LossExecutionContext


@dataclass(frozen=True)
class PostLossInventoryCommand(RequestLossInventoryCommand):
    pass


@dataclass(frozen=True)
class ReverseLossInventoryCommand(RequestLossInventoryCommand):
    reason: str


@dataclass(frozen=True)
class LossInventoryResult:
    case_id: str
    status: LossStatus
    inventory_movement_id: str | None = None
    replayed: bool = False


class LossInventoryRepositoryProtocol(Protocol):
    def transaction(self): ...
    def find_processed(self, operation_id: str): ...
    def get_case_for_inventory(self, case_id: str): ...
    def get_lines(self, case_id: str): ...
    def get_available_location(self, warehouse_id: str) -> str | None: ...
    def has_posting_request(self, case_id: str) -> bool: ...
    def record_request(self, case_id: str, operation_id: str, event: dict): ...
    def record_posted(self, case_id: str, operation_id: str, movement_id: str, event: dict): ...
    def record_reversed(self, case_id: str, operation_id: str, reversal_id: str, event: dict): ...


class LossInventoryGatewayProtocol(Protocol):
    def post(self, movement: InventoryMovement, **kwargs): ...
    def reverse(self, **kwargs): ...


_MOVEMENT_TYPE = {
    LossClassificationCode.EXPIRY: MovementType.EXPIRY_DISPOSAL,
    LossClassificationCode.SHRINKAGE: MovementType.SHRINKAGE,
}


class LossInventoryIntegrationService:
    def __init__(self, repository: LossInventoryRepositoryProtocol,
                 inventory: LossInventoryGatewayProtocol, authorization) -> None:
        self._repository = repository
        self._inventory = inventory
        self._authorization = authorization

    def request(self, command: RequestLossInventoryCommand) -> LossInventoryResult:
        replay = self._replay(command.operation_id)
        if replay:
            return replay
        self._authorization.require(command.context.actor_user_id, LossPermissions.POST_INVENTORY)
        case = self._case(command, expected=LossStatus.APPROVED)
        if not case["requires_inventory_posting"]:
            raise LossInvariantError("La clasificación no requiere movimiento físico")
        event = self._event(LossEvents.LOSS_INVENTORY_POSTING_REQUESTED, command, case)
        with self._repository.transaction():
            self._repository.record_request(case["id"], command.operation_id, event)
        return LossInventoryResult(case["id"], LossStatus.APPROVED)

    def post(self, command: PostLossInventoryCommand) -> LossInventoryResult:
        replay = self._replay(command.operation_id)
        if replay:
            return replay
        self._authorization.require(command.context.actor_user_id, LossPermissions.POST_INVENTORY)
        case = self._case(command, expected=LossStatus.APPROVED)
        if not self._repository.has_posting_request(case["id"]):
            raise LossInvariantError("El posteo requiere una solicitud previa")
        classification = LossClassificationCode(case["classification"])
        available_location = self._repository.get_available_location(case["warehouse_id"])
        if not available_location:
            raise LossInvariantError(
                "El almacén no tiene una ubicación técnica AVAILABLE configurada")
        movement = InventoryMovement.create(
            movement_type=_MOVEMENT_TYPE.get(classification, MovementType.WASTE),
            branch_id=case["branch_id"], warehouse_id=case["warehouse_id"],
            source_module="losses", source_document_type="LOSS_CASE",
            source_document_id=case["id"], operation_id=command.operation_id,
            created_by_user_id=command.context.actor_user_id,
            lines=[InventoryMovementLine.create(
                product_id=row["product_id"], lot_id=row["lot_id"],
                quantity=row["quantity"], weight=row["weight"], unit=row["unit"],
                from_location_id=row.get("location_id") or available_location,
                from_status=InventoryStatus.AVAILABLE,
                reason_code=classification.value,
            ) for row in self._repository.get_lines(case["id"])])
        with self._repository.transaction():
            result = self._inventory.post(
                movement, actor_user_id=command.context.actor_user_id,
                owns_transaction=False, context=self._inventory_context(command.context))
            self._require_inventory_success(result)
            event = self._event(
                LossEvents.LOSS_INVENTORY_POSTED, command, case,
                inventory_movement_id=result.entity_id)
            self._repository.record_posted(
                case["id"], command.operation_id, result.entity_id, event)
        return LossInventoryResult(case["id"], LossStatus.INVENTORY_POSTED,
                                   result.entity_id)

    def reverse(self, command: ReverseLossInventoryCommand) -> LossInventoryResult:
        replay = self._replay(command.operation_id)
        if replay:
            return replay
        self._authorization.require(command.context.actor_user_id, LossPermissions.REVERSE_INVENTORY)
        if not command.reason.strip():
            raise LossInvariantError("El reverso requiere un motivo")
        case = self._case(command, expected=LossStatus.INVENTORY_POSTED)
        if not case["inventory_movement_id"]:
            raise LossInvariantError("El expediente no tiene movimiento para reversar")
        with self._repository.transaction():
            result = self._inventory.reverse(
                movement_id=case["inventory_movement_id"], operation_id=command.operation_id,
                actor_user_id=command.context.actor_user_id, reason=command.reason.strip(),
                owns_transaction=False, context=self._inventory_context(command.context))
            self._require_inventory_success(result)
            event = self._event(
                LossEvents.LOSS_INVENTORY_REVERSED, command, case,
                inventory_movement_id=case["inventory_movement_id"],
                reversal_movement_id=result.entity_id, reason=command.reason.strip())
            self._repository.record_reversed(
                case["id"], command.operation_id, result.entity_id, event)
        return LossInventoryResult(case["id"], LossStatus.REVERSED, result.entity_id)

    def _case(self, command, *, expected: LossStatus):
        case = self._repository.get_case_for_inventory(command.loss_case_id)
        if not case:
            raise LossInvariantError("Expediente de pérdida no encontrado")
        command.context.enforce_branch(case["branch_id"])
        command.context.enforce_warehouse(case["warehouse_id"])
        if case["status"] != expected.value:
            raise LossInvariantError(
                f"El expediente debe estar en {expected.value}; estado actual {case['status']}")
        return case

    def _replay(self, operation_id):
        found = self._repository.find_processed(operation_id)
        return (LossInventoryResult(found[0], LossStatus(found[1]),
                                    found[2] if len(found) > 2 else None, True)
                if found else None)

    @staticmethod
    def _require_inventory_success(result):
        if not result.success:
            raise LossInvariantError(f"Inventario rechazó la operación: {result.message}")

    @staticmethod
    def _inventory_context(context):
        return InventoryExecutionContext(
            context.actor_user_id, context.active_branch_id,
            context.assigned_branch_ids, context.allowed_warehouse_ids,
            context.permissions, context.device_id)

    @staticmethod
    def _event(name, command, case, **payload):
        return build_loss_event(
            name, operation_id=command.operation_id, entity_id=case["id"],
            branch_id=case["branch_id"], warehouse_id=case["warehouse_id"],
            user_id=command.context.actor_user_id, **payload)
