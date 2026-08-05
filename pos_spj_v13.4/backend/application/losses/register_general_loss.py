"""Canonical LOSS-5 command: record a draft or submit it for review."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from hashlib import sha256
from typing import Protocol

from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.permissions import LossPermissions
from backend.domain.losses.entities import LossCase, LossLine
from backend.domain.losses.enums import LossClassificationCode, LossOrigin, LossStatus
from backend.domain.losses.events import LossEvents, build_loss_event
from backend.domain.losses.exceptions import LossInvariantError
from backend.domain.losses.policies import LossRegistrationPolicy
from backend.shared.ids import new_uuid


@dataclass(frozen=True)
class GeneralLossLineInput:
    product_id: str
    quantity: Decimal = Decimal("0")
    weight: Decimal = Decimal("0")
    unit: str = "unit"
    lot_id: str | None = None
    unit_cost: Decimal = Decimal("0")


@dataclass(frozen=True)
class EvidenceInput:
    path: str
    evidence_type: str = "FILE"


@dataclass(frozen=True)
class RegisterGeneralLossCommand:
    operation_id: str
    context: LossExecutionContext
    warehouse_id: str
    classification_id: str
    reason_id: str
    origin: LossOrigin
    lines: tuple[GeneralLossLineInput, ...]
    evidence: tuple[EvidenceInput, ...] = ()
    notes: str = ""
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    submit: bool = True


@dataclass(frozen=True)
class LossRegistrationResult:
    case_id: str
    status: LossStatus
    replayed: bool = False


class GeneralLossRepository(Protocol):
    def find_processed(self, operation_id: str): ...
    def resolve_reason(self, classification_id: str, reason_id: str): ...
    def save(self, case: LossCase, evidence: tuple[dict, ...], event: dict): ...


class RegisterGeneralLossUseCase:
    def __init__(self, repository: GeneralLossRepository, authorization,
                 policy: LossRegistrationPolicy | None = None) -> None:
        self._repository = repository
        self._authorization = authorization
        self._policy = policy or LossRegistrationPolicy()

    def execute(self, command: RegisterGeneralLossCommand) -> LossRegistrationResult:
        replay = self._repository.find_processed(command.operation_id)
        if replay:
            return LossRegistrationResult(replay[0], LossStatus(replay[1]), True)

        actor = command.context.actor_user_id
        self._authorization.require(actor, LossPermissions.REPORT)
        if command.submit:
            self._authorization.require(actor, LossPermissions.SUBMIT)
        command.context.enforce_branch(command.context.active_branch_id)
        command.context.enforce_warehouse(command.warehouse_id)

        resolved = self._repository.resolve_reason(
            command.classification_id, command.reason_id)
        if not resolved:
            raise LossInvariantError("La clasificación o causa no está activa")
        classification = LossClassificationCode(resolved[0])
        requires_evidence = bool(resolved[1])
        if requires_evidence and not command.evidence:
            raise LossInvariantError("La causa seleccionada requiere evidencia")
        self._policy.validate_origin(
            classification=classification, origin=command.origin,
            source_document_id=None)

        case = LossCase(
            id=new_uuid(), operation_id=command.operation_id,
            branch_id=command.context.active_branch_id,
            warehouse_id=command.warehouse_id, reported_by_user_id=actor,
            classification=classification, origin=command.origin,
            reason_id=command.reason_id, notes=command.notes.strip(),
            created_at=command.occurred_at,
        )
        for item in command.lines:
            case.add_line(LossLine(
                id=new_uuid(), product_id=item.product_id, lot_id=item.lot_id,
                quantity=item.quantity, weight=item.weight, unit=item.unit,
                unit_cost=item.unit_cost,
            ))
        if not case.lines:
            raise LossInvariantError("El registro requiere al menos un producto")
        if command.submit:
            case.submit(actor_user_id=actor)

        evidence = tuple(self._describe_evidence(item, case.id, actor)
                         for item in command.evidence)
        event_name = (LossEvents.LOSS_CASE_SUBMITTED if command.submit
                      else LossEvents.LOSS_CASE_CREATED)
        event = build_loss_event(
            event_name, operation_id=command.operation_id, entity_id=case.id,
            branch_id=case.branch_id, warehouse_id=case.warehouse_id,
            user_id=actor, status=case.status.value,
        )
        self._repository.save(case, evidence, event)
        return LossRegistrationResult(case.id, case.status)

    @staticmethod
    def _describe_evidence(item: EvidenceInput, case_id: str, actor: str) -> dict:
        path = Path(item.path).expanduser().resolve(strict=True)
        if not path.is_file():
            raise LossInvariantError("La evidencia debe ser un archivo")
        digest = sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return {
            "id": new_uuid(), "loss_case_id": case_id,
            "evidence_type": item.evidence_type,
            "storage_uri": path.as_uri(), "checksum": digest.hexdigest(),
            "captured_by_user_id": actor,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "metadata_json": "{}",
        }
