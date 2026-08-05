"""LOSS-14 canonical plan, authorize and complete disposition workflow."""

from dataclasses import dataclass
from decimal import Decimal

from backend.application.inventory.execution_context import InventoryExecutionContext
from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.permissions import LossPermissions
from backend.domain.losses.disposition import DispositionMethod, DispositionPolicy
from backend.domain.losses.events import LossEvents, build_loss_event
from backend.domain.losses.exceptions import LossInvariantError
from backend.shared.ids import new_uuid, validate_uuidv7


@dataclass(frozen=True, slots=True)
class DispositionEvidenceInput:
    evidence_type: str
    storage_uri: str
    checksum: str
    metadata_json: str = "{}"


@dataclass(frozen=True, slots=True)
class PlanDispositionCommand:
    operation_id: str
    loss_case_id: str
    context: LossExecutionContext
    method: DispositionMethod
    quantity: Decimal
    weight: Decimal
    reason: str
    evidence: tuple[DispositionEvidenceInput, ...]


@dataclass(frozen=True, slots=True)
class AuthorizeDispositionCommand:
    operation_id: str
    disposition_id: str
    context: LossExecutionContext
    reason: str


@dataclass(frozen=True, slots=True)
class CompleteDispositionCommand:
    operation_id: str
    disposition_id: str
    context: LossExecutionContext
    certificate_reference: str
    evidence: tuple[DispositionEvidenceInput, ...]


@dataclass(frozen=True, slots=True)
class DispositionResult:
    disposition_id: str
    status: str
    replayed: bool = False


class LossDispositionService:
    def __init__(self, repository, inventory, authorization, policy=None) -> None:
        self._repository = repository
        self._inventory = inventory
        self._authorization = authorization
        self._policy = policy or DispositionPolicy()

    def plan(self, command: PlanDispositionCommand) -> DispositionResult:
        validate_uuidv7(command.operation_id); validate_uuidv7(command.loss_case_id)
        replay = self._repository.find_processed(command.operation_id)
        if replay: return DispositionResult(replay["entity_id"], replay["status"], True)
        actor = command.context.actor_user_id
        self._authorization.require(actor, LossPermissions.PLAN_DISPOSAL)
        case = self._case(command.loss_case_id, command.context)
        plan = self._policy.plan(method=command.method, quantity=command.quantity,
            weight=command.weight, quarantine_quantity=case["quarantine_quantity"],
            quarantine_weight=case["quarantine_weight"], reason=command.reason,
            evidence=command.evidence)
        disposition_id = new_uuid()
        event = self._event(LossEvents.LOSS_DISPOSITION_PLANNED, command.operation_id,
            disposition_id, case, actor, method=plan.method.value)
        with self._repository.transaction():
            self._repository.save_plan(disposition_id=disposition_id,
                operation_id=command.operation_id, case=case, plan=plan,
                evidence=command.evidence, actor_user_id=actor, event=event)
        return DispositionResult(disposition_id, "PLANNED")

    def authorize(self, command: AuthorizeDispositionCommand) -> DispositionResult:
        validate_uuidv7(command.operation_id); validate_uuidv7(command.disposition_id)
        replay = self._repository.find_processed(command.operation_id)
        if replay: return DispositionResult(replay["entity_id"], replay["status"], True)
        actor = command.context.actor_user_id
        self._authorization.require(actor, LossPermissions.AUTHORIZE_DISPOSAL)
        item = self._repository.get_disposition(command.disposition_id)
        if not item or item["status"] != "PLANNED":
            raise LossInvariantError("La disposición no está planeada")
        case = self._case(item["loss_case_id"], command.context)
        if item["planned_by_user_id"] == actor:
            raise LossInvariantError("Quien planea no puede autorizar la disposición")
        if not command.reason.strip(): raise LossInvariantError("La autorización requiere motivo")
        event = self._event(LossEvents.LOSS_DISPOSITION_AUTHORIZED,
            command.operation_id, command.disposition_id, case, actor)
        with self._repository.transaction():
            self._repository.authorize(disposition_id=command.disposition_id,
                operation_id=command.operation_id, actor_user_id=actor,
                reason=command.reason.strip(), event=event)
        return DispositionResult(command.disposition_id, "AUTHORIZED")

    def complete(self, command: CompleteDispositionCommand) -> DispositionResult:
        validate_uuidv7(command.operation_id); validate_uuidv7(command.disposition_id)
        replay = self._repository.find_processed(command.operation_id)
        if replay: return DispositionResult(replay["entity_id"], replay["status"], True)
        actor = command.context.actor_user_id
        self._authorization.require(actor, LossPermissions.COMPLETE_DISPOSAL)
        item = self._repository.get_disposition(command.disposition_id)
        if not item or item["status"] != "AUTHORIZED":
            raise LossInvariantError("La disposición no está autorizada")
        case = self._case(item["loss_case_id"], command.context)
        if item["authorized_by_user_id"] == actor:
            raise LossInvariantError("Quien autoriza no puede ejecutar la disposición")
        self._policy.validate_completion(certificate_required=bool(item["certificate_required"]),
            certificate_reference=command.certificate_reference, evidence=command.evidence)
        event = self._event(LossEvents.LOSS_DISPOSITION_COMPLETED,
            command.operation_id, command.disposition_id, case, actor,
            certificate_reference=command.certificate_reference.strip() or None)
        with self._repository.transaction():
            result = self._inventory.dispose_quarantine(quarantine_id=case["quarantine_id"],
                operation_id=command.operation_id, actor_user_id=actor,
                reason=item["reason"], context=self._inventory_context(command.context),
                owns_transaction=False)
            if not result.success:
                raise LossInvariantError(f"Inventario rechazó la disposición: {result.message}")
            self._repository.complete(disposition_id=command.disposition_id,
                operation_id=command.operation_id, actor_user_id=actor,
                certificate_reference=command.certificate_reference.strip() or None,
                evidence=command.evidence, event=event, case=case)
        return DispositionResult(command.disposition_id, "COMPLETED")

    def _case(self, case_id, context):
        case = self._repository.get_case(case_id)
        if not case: raise LossInvariantError("Expediente de pérdida no encontrado")
        context.enforce_branch(case["branch_id"]); context.enforce_warehouse(case["warehouse_id"])
        if case["status"] != "TREATMENT_PENDING" or not case["quarantine_id"]:
            raise LossInvariantError("La disposición requiere una cuarentena activa")
        return case

    @staticmethod
    def _event(name, operation_id, entity_id, case, actor, **payload):
        return build_loss_event(name, operation_id=operation_id, entity_id=entity_id,
            branch_id=case["branch_id"], warehouse_id=case["warehouse_id"],
            user_id=actor, loss_case_id=case["id"], **payload)

    @staticmethod
    def _inventory_context(context):
        return InventoryExecutionContext(context.actor_user_id, context.active_branch_id,
            context.assigned_branch_ids, context.allowed_warehouse_ids,
            context.permissions, context.device_id)
