"""LOSS-13 two-step recovery workflow with canonical external references."""

from dataclasses import dataclass
from decimal import Decimal

from backend.application.inventory.execution_context import InventoryExecutionContext
from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.permissions import LossPermissions
from backend.domain.losses.events import LossEvents, build_loss_event
from backend.domain.losses.exceptions import LossInvariantError
from backend.domain.losses.recovery import LossRecoveryPolicy, RecoveryType
from backend.shared.ids import new_uuid, validate_uuidv7


@dataclass(frozen=True, slots=True)
class RecordRecoveryCommand:
    operation_id: str
    loss_case_id: str
    context: LossExecutionContext
    recovery_type: RecoveryType
    quantity: Decimal
    weight: Decimal
    recovered_value: Decimal
    reference_id: str | None
    target_product_id: str | None
    notes: str


@dataclass(frozen=True, slots=True)
class ApproveRecoveryCommand:
    operation_id: str
    recovery_id: str
    context: LossExecutionContext
    reason: str


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    recovery_id: str
    status: str
    replayed: bool = False


class LossRecoveryService:
    def __init__(self, repository, inventory, authorization, policy=None) -> None:
        self._repository = repository
        self._inventory = inventory
        self._authorization = authorization
        self._policy = policy or LossRecoveryPolicy()

    def record(self, command: RecordRecoveryCommand) -> RecoveryResult:
        validate_uuidv7(command.operation_id); validate_uuidv7(command.loss_case_id)
        replay = self._repository.find_processed(command.operation_id)
        if replay: return RecoveryResult(replay["entity_id"], replay["status"], True)
        actor = command.context.actor_user_id
        self._authorization.require(actor, LossPermissions.RECORD_RECOVERY)
        case = self._case(command.loss_case_id, command.context)
        plan = self._policy.plan(recovery_type=command.recovery_type,
            quantity=command.quantity, weight=command.weight,
            recovered_value=command.recovered_value, gross_value=case["gross_value"],
            already_recovered=case["recovered_value"], reference_id=command.reference_id,
            target_product_id=command.target_product_id,
            quarantine_id=case.get("quarantine_id"),
            quarantine_quantity=case.get("quarantine_quantity", 0),
            quarantine_weight=case.get("quarantine_weight", 0),
            loss_quantity=case.get("loss_quantity", 0),
            loss_weight=case.get("loss_weight", 0),
            recovered_quantity=case.get("recovered_quantity", 0),
            recovered_weight=case.get("recovered_weight", 0))
        if command.reference_id: validate_uuidv7(command.reference_id)
        if command.target_product_id: validate_uuidv7(command.target_product_id)
        if not command.notes.strip(): raise LossInvariantError("La recuperación requiere observaciones")
        recovery_id = new_uuid()
        event = build_loss_event(LossEvents.LOSS_RECOVERY_SUBMITTED,
            operation_id=command.operation_id, entity_id=recovery_id,
            branch_id=case["branch_id"], warehouse_id=case["warehouse_id"], user_id=actor,
            loss_case_id=case["id"], recovery_type=plan.recovery_type.value,
            recovered_value=plan.recovered_value)
        with self._repository.transaction():
            self._repository.save_pending(recovery_id=recovery_id,
                operation_id=command.operation_id, case=case, plan=plan,
                reference_id=command.reference_id, target_product_id=command.target_product_id,
                notes=command.notes.strip(), actor_user_id=actor, event=event)
        return RecoveryResult(recovery_id, "PENDING_APPROVAL")

    def approve(self, command: ApproveRecoveryCommand) -> RecoveryResult:
        validate_uuidv7(command.operation_id); validate_uuidv7(command.recovery_id)
        replay = self._repository.find_processed(command.operation_id)
        if replay: return RecoveryResult(replay["entity_id"], replay["status"], True)
        actor = command.context.actor_user_id
        self._authorization.require(actor, LossPermissions.APPROVE_RECOVERY)
        recovery = self._repository.get_recovery(command.recovery_id)
        if not recovery or recovery["status"] != "PENDING_APPROVAL":
            raise LossInvariantError("La recuperación no está pendiente de aprobación")
        if recovery["recorded_by_user_id"] == actor:
            raise LossInvariantError("Quien registra no puede aprobar la recuperación")
        case = self._case(recovery["loss_case_id"], command.context)
        if not command.reason.strip(): raise LossInvariantError("La aprobación requiere motivo")
        kind = RecoveryType(recovery["recovery_type"])
        if kind in {RecoveryType.RECLASSIFICATION, RecoveryType.BY_PRODUCT,
                    RecoveryType.CO_PRODUCT, RecoveryType.CLAIM}:
            if not self._repository.validate_reference(kind.value, recovery["reference_id"],
                                                       recovery["target_product_id"]):
                raise LossInvariantError("La referencia de recuperación no está posteada o pagada")
        with self._repository.transaction():
            if kind is RecoveryType.REWORK:
                result = self._inventory.release_quarantine(
                    quarantine_id=case["quarantine_id"], operation_id=command.operation_id,
                    actor_user_id=actor, context=self._inventory_context(command.context),
                    owns_transaction=False)
                if not result.success:
                    raise LossInvariantError(f"Inventario rechazó la recuperación: {result.message}")
            event = build_loss_event(LossEvents.LOSS_RECOVERY_APPROVED,
                operation_id=command.operation_id, entity_id=command.recovery_id,
                branch_id=case["branch_id"], warehouse_id=case["warehouse_id"], user_id=actor,
                loss_case_id=case["id"], recovery_type=kind.value,
                recovered_value=recovery["recovered_value"])
            self._repository.approve(recovery_id=command.recovery_id,
                operation_id=command.operation_id, case=case, approved_by_user_id=actor,
                approval_reason=command.reason.strip(), event=event)
        return RecoveryResult(command.recovery_id, "APPROVED")

    def _case(self, case_id, context):
        case = self._repository.get_case(case_id)
        if not case: raise LossInvariantError("Expediente de pérdida no encontrado")
        context.enforce_branch(case["branch_id"]); context.enforce_warehouse(case["warehouse_id"])
        if case["status"] not in ("APPROVED", "INVENTORY_POSTED", "TREATMENT_PENDING"):
            raise LossInvariantError("El expediente no admite recuperación")
        return case

    @staticmethod
    def _inventory_context(context):
        return InventoryExecutionContext(context.actor_user_id, context.active_branch_id,
            context.assigned_branch_ids, context.allowed_warehouse_ids,
            context.permissions, context.device_id)
