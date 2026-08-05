"""LOSS-15 canonical investigation workflow."""

from dataclasses import dataclass
from datetime import datetime

from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.permissions import LossPermissions
from backend.domain.losses.events import LossEvents, build_loss_event
from backend.domain.losses.exceptions import LossInvariantError
from backend.domain.losses.investigation import InvestigationPolicy
from backend.shared.ids import new_uuid, validate_uuidv7


@dataclass(frozen=True, slots=True)
class InvestigationEvidenceInput:
    evidence_type: str
    storage_uri: str
    checksum: str
    metadata_json: str = "{}"


@dataclass(frozen=True, slots=True)
class OpenInvestigationCommand:
    operation_id: str
    loss_case_id: str
    context: LossExecutionContext
    assigned_to_user_id: str
    due_at: datetime
    reason: str


@dataclass(frozen=True, slots=True)
class AddInvestigationEvidenceCommand:
    operation_id: str
    investigation_id: str
    context: LossExecutionContext
    evidence: tuple[InvestigationEvidenceInput, ...]


@dataclass(frozen=True, slots=True)
class AddInvestigationFindingCommand:
    operation_id: str
    investigation_id: str
    context: LossExecutionContext
    cause_code: str
    description: str
    is_primary: bool
    evidence: tuple[InvestigationEvidenceInput, ...]


@dataclass(frozen=True, slots=True)
class ConcludeInvestigationCommand:
    operation_id: str
    investigation_id: str
    context: LossExecutionContext
    conclusion: str
    evidence: tuple[InvestigationEvidenceInput, ...]


@dataclass(frozen=True, slots=True)
class InvestigationResult:
    entity_id: str
    status: str
    replayed: bool = False


class LossInvestigationService:
    def __init__(self, repository, authorization, policy=None):
        self._repository = repository
        self._authorization = authorization
        self._policy = policy or InvestigationPolicy()

    def open(self, command: OpenInvestigationCommand) -> InvestigationResult:
        validate_uuidv7(command.operation_id); validate_uuidv7(command.loss_case_id)
        validate_uuidv7(command.assigned_to_user_id)
        replay = self._replay(command.operation_id)
        if replay: return replay
        actor = command.context.actor_user_id
        self._authorization.require(actor, LossPermissions.OPEN_INVESTIGATION)
        case = self._case(command.loss_case_id, command.context)
        self._policy.validate_open(case_status=case["status"],
            assigned_to_user_id=command.assigned_to_user_id, due_at=command.due_at,
            reason=command.reason)
        investigation_id = new_uuid()
        event = self._event(LossEvents.LOSS_INVESTIGATION_OPENED, command.operation_id,
            investigation_id, case, actor, assigned_to_user_id=command.assigned_to_user_id)
        with self._repository.transaction():
            self._repository.save_open(investigation_id=investigation_id,
                operation_id=command.operation_id, case=case,
                assigned_to_user_id=command.assigned_to_user_id,
                due_at=command.due_at.isoformat(), reason=command.reason.strip(),
                actor_user_id=actor, event=event)
        return InvestigationResult(investigation_id, "OPEN")

    def add_evidence(self, command: AddInvestigationEvidenceCommand) -> InvestigationResult:
        validate_uuidv7(command.operation_id); validate_uuidv7(command.investigation_id)
        replay = self._replay(command.operation_id)
        if replay: return replay
        actor = command.context.actor_user_id
        self._authorization.require(actor, LossPermissions.INVESTIGATE)
        item = self._active(command.investigation_id, command.context)
        self._policy.validate_evidence(command.evidence)
        event = self._event(LossEvents.LOSS_INVESTIGATION_EVIDENCE_ADDED,
            command.operation_id, command.investigation_id, item, actor,
            evidence_count=len(command.evidence))
        with self._repository.transaction():
            self._repository.save_evidence(investigation_id=command.investigation_id,
                operation_id=command.operation_id, evidence=command.evidence,
                actor_user_id=actor, event=event, case=item)
        return InvestigationResult(command.investigation_id, "IN_PROGRESS")

    def add_finding(self, command: AddInvestigationFindingCommand) -> InvestigationResult:
        validate_uuidv7(command.operation_id); validate_uuidv7(command.investigation_id)
        replay = self._replay(command.operation_id)
        if replay: return replay
        actor = command.context.actor_user_id
        self._authorization.require(actor, LossPermissions.INVESTIGATE)
        item = self._active(command.investigation_id, command.context)
        self._policy.validate_finding(cause_code=command.cause_code,
            description=command.description, evidence=command.evidence)
        finding_id = new_uuid()
        event = self._event(LossEvents.LOSS_INVESTIGATION_FINDING_ADDED,
            command.operation_id, finding_id, item, actor,
            investigation_id=command.investigation_id,
            cause_code=command.cause_code.strip(), is_primary=command.is_primary)
        with self._repository.transaction():
            self._repository.save_finding(finding_id=finding_id,
                investigation_id=command.investigation_id, operation_id=command.operation_id,
                cause_code=command.cause_code.strip(), description=command.description.strip(),
                is_primary=command.is_primary, evidence=command.evidence,
                actor_user_id=actor, event=event, case=item)
        return InvestigationResult(finding_id, "RECORDED")

    def conclude(self, command: ConcludeInvestigationCommand) -> InvestigationResult:
        validate_uuidv7(command.operation_id); validate_uuidv7(command.investigation_id)
        replay = self._replay(command.operation_id)
        if replay: return replay
        actor = command.context.actor_user_id
        self._authorization.require(actor, LossPermissions.CONCLUDE_INVESTIGATION)
        item = self._active(command.investigation_id, command.context)
        if item["opened_by_user_id"] == actor:
            raise LossInvariantError("Quien abre no puede concluir la investigación")
        self._policy.validate_conclusion(finding_count=item["finding_count"],
            conclusion=command.conclusion, evidence=command.evidence)
        event = self._event(LossEvents.LOSS_INVESTIGATION_CONCLUDED,
            command.operation_id, command.investigation_id, item, actor,
            finding_count=item["finding_count"])
        with self._repository.transaction():
            self._repository.conclude(investigation_id=command.investigation_id,
                operation_id=command.operation_id, conclusion=command.conclusion.strip(),
                evidence=command.evidence, actor_user_id=actor, event=event, case=item)
        return InvestigationResult(command.investigation_id, "CONCLUDED")

    def _active(self, investigation_id, context):
        item = self._repository.get_investigation(investigation_id)
        if not item: raise LossInvariantError("Investigación no encontrada")
        context.enforce_branch(item["branch_id"]); context.enforce_warehouse(item["warehouse_id"])
        if item["status"] not in ("OPEN", "IN_PROGRESS"):
            raise LossInvariantError("La investigación no está activa")
        return item

    def _case(self, case_id, context):
        case = self._repository.get_case(case_id)
        if not case: raise LossInvariantError("Expediente de pérdida no encontrado")
        context.enforce_branch(case["branch_id"]); context.enforce_warehouse(case["warehouse_id"])
        return case

    def _replay(self, operation_id):
        row = self._repository.find_processed(operation_id)
        return InvestigationResult(row["entity_id"], row["status"], True) if row else None

    @staticmethod
    def _event(name, operation_id, entity_id, case, actor, **payload):
        return build_loss_event(name, operation_id=operation_id, entity_id=entity_id,
            branch_id=case["branch_id"], warehouse_id=case["warehouse_id"], user_id=actor,
            loss_case_id=case.get("loss_case_id", case.get("id")), **payload)
