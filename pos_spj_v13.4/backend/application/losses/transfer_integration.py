"""LOSS-12 integration for transfer discrepancies, responsibility and claims."""

from dataclasses import dataclass
from decimal import Decimal

from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.permissions import LossPermissions
from backend.domain.losses.entities import LossCase, LossLine
from backend.domain.losses.enums import LossOrigin
from backend.domain.losses.events import LossEvents, build_loss_event
from backend.domain.losses.exceptions import LossInvariantError
from backend.domain.losses.transfer_integration import ClaimPartyType, TransferLossPolicy, decimal_value
from backend.shared.ids import new_uuid, validate_uuidv7


@dataclass(frozen=True, slots=True)
class TransferLossResult:
    case_id: str
    status: str
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class RegisterTransferClaimCommand:
    operation_id: str
    loss_case_id: str
    context: LossExecutionContext
    party_type: ClaimPartyType
    responsible_party_id: str | None
    claimed_value: Decimal
    reason: str
    evidence_references: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TransferClaimResult:
    claim_id: str
    status: str
    replayed: bool = False


class TransferLossIntegrationService:
    """Implements Transfers' ``TransferLossCaseGateway`` protocol."""

    def __init__(self, repository, authorization, policy=None, context_provider=None) -> None:
        self._repository = repository
        self._authorization = authorization
        self._policy = policy or TransferLossPolicy()
        self._context_provider = context_provider

    def request_loss_case(self, payload, *, context: LossExecutionContext | None = None) -> TransferLossResult:
        context = context or (self._context_provider() if self._context_provider else None)
        if context is None:
            raise LossInvariantError("La integración de transferencias requiere contexto autenticado")
        if payload.get("event_name") != "LOSS_CASE_REQUESTED":
            raise LossInvariantError("Evento de transferencia no soportado")
        operation_id = validate_uuidv7(str(payload.get("operation_id", "")))
        replay = self._repository.find_processed(operation_id)
        if replay: return TransferLossResult(replay["entity_id"], replay["status"], True)
        actor = validate_uuidv7(str(payload.get("requested_by_user_id", "")))
        if actor != context.actor_user_id:
            raise LossInvariantError("El actor del evento no coincide con el contexto autenticado")
        self._authorization.require(actor, LossPermissions.TRANSFER_LINK)
        transfer_id = validate_uuidv7(str(payload.get("transfer_id", "")))
        difference_id = validate_uuidv7(str(payload.get("difference_id", "")))
        resolution_id = validate_uuidv7(str(payload.get("resolution_id", "")))
        fact = self._repository.get_resolved_difference(transfer_id=transfer_id,
            difference_id=difference_id, resolution_id=resolution_id)
        if not fact or fact["resolution_type"] != "CREATE_LOSS_CASE":
            raise LossInvariantError("La diferencia no solicita un expediente de pérdida")
        context.enforce_branch(fact["branch_id"]); context.enforce_warehouse(fact["warehouse_id"])
        if not fact["inventory_receipt_posted"]:
            raise LossInvariantError("La recepción debe estar posteada en Inventario antes de registrar la pérdida")
        assessment = self._policy.assess(difference_type=fact["difference_type"],
            expected_quantity=fact["expected_quantity"], actual_quantity=fact["actual_quantity"],
            expected_weight=fact["expected_weight"], actual_weight=fact["actual_weight"],
            responsible_stage=fact["responsible_stage"])
        reason_id = self._repository.resolve_reason_id(assessment.classification.value)
        if not reason_id: raise LossInvariantError("La clasificación de transferencia no tiene causa activa")
        case = LossCase(id=new_uuid(), operation_id=operation_id,
            branch_id=fact["branch_id"], warehouse_id=fact["warehouse_id"],
            reported_by_user_id=actor, classification=assessment.classification,
            origin=LossOrigin.TRANSFER, reason_id=reason_id,
            source_document_id=difference_id,
            notes=f"Diferencia confirmada en transferencia {transfer_id}")
        case.add_line(LossLine(id=new_uuid(), product_id=fact["product_id"],
            lot_id=fact.get("lot_id"), quantity=assessment.loss_quantity,
            weight=assessment.loss_weight, unit="unit"))
        case.submit(actor_user_id=actor)
        event = build_loss_event(LossEvents.LOSS_TRANSFER_DIFFERENCE_REGISTERED,
            operation_id=operation_id, entity_id=case.id, branch_id=case.branch_id,
            warehouse_id=case.warehouse_id, user_id=actor, transfer_id=transfer_id,
            difference_id=difference_id, resolution_id=resolution_id,
            responsible_stage=assessment.responsible_stage,
            inventory_effect="POSTED_BY_TRANSFER_RECEIPT",
            inventory_receipt_operation_id=fact["receipt_operation_id"])
        with self._repository.transaction():
            self._repository.save_transfer_loss(operation_id=operation_id, case=case, fact=fact,
                assessment=assessment, event=event,
                inventory_effect="POSTED_BY_TRANSFER_RECEIPT")
        return TransferLossResult(case.id, case.status.value)

    def register_claim(self, command: RegisterTransferClaimCommand) -> TransferClaimResult:
        validate_uuidv7(command.operation_id); validate_uuidv7(command.loss_case_id)
        replay = self._repository.find_processed(command.operation_id)
        if replay: return TransferClaimResult(replay["entity_id"], replay["status"], True)
        self._authorization.require(command.context.actor_user_id, LossPermissions.MANAGE_CLAIMS)
        link = self._repository.get_transfer_loss(command.loss_case_id)
        if not link: raise LossInvariantError("Expediente de transferencia no encontrado")
        command.context.enforce_branch(link["branch_id"])
        command.context.enforce_warehouse(link["warehouse_id"])
        value = decimal_value(command.claimed_value, "claimed_value")
        if value <= 0: raise LossInvariantError("La reclamación requiere un valor positivo")
        party_type = ClaimPartyType(command.party_type)
        party_id = command.responsible_party_id
        if party_type is not ClaimPartyType.OTHER:
            if not party_id: raise LossInvariantError("La reclamación requiere parte responsable")
            validate_uuidv7(party_id)
        if not command.reason.strip(): raise LossInvariantError("La reclamación requiere motivo")
        if any(not item.strip() for item in command.evidence_references):
            raise LossInvariantError("Las referencias de evidencia no pueden estar vacías")
        claim_id = new_uuid()
        event = build_loss_event(LossEvents.LOSS_TRANSFER_CLAIM_OPENED,
            operation_id=command.operation_id, entity_id=claim_id,
            branch_id=link["branch_id"], warehouse_id=link["warehouse_id"],
            user_id=command.context.actor_user_id, loss_case_id=command.loss_case_id,
            transfer_id=link["transfer_id"], party_type=party_type.value,
            claimed_value=value)
        with self._repository.transaction():
            self._repository.save_claim(claim_id=claim_id, operation_id=command.operation_id,
                loss_case_id=command.loss_case_id, transfer_id=link["transfer_id"],
                party_type=party_type.value, responsible_party_id=party_id,
                claimed_value=value, reason=command.reason.strip(),
                evidence=command.evidence_references,
                actor_user_id=command.context.actor_user_id, event=event)
        return TransferClaimResult(claim_id, "OPEN")
