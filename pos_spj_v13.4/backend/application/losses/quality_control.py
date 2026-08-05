"""LOSS-11 canonical application service for quality rejection and condemnation."""

from dataclasses import dataclass
from decimal import Decimal

from backend.application.inventory.execution_context import InventoryExecutionContext
from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.permissions import LossPermissions
from backend.domain.inventory.enums import QuarantineReason, TemperaturePoint
from backend.domain.losses.enums import LossClassificationCode
from backend.domain.losses.exceptions import LossInvariantError
from backend.domain.losses.quality_control import (
    ContaminationLevel, QualityDecision, QualityDecisionPolicy,
)


@dataclass(frozen=True, slots=True)
class QualityEvidenceInput:
    evidence_type: str
    storage_uri: str
    checksum: str
    metadata_json: str = "{}"


@dataclass(frozen=True, slots=True)
class QualityInspectionCommand:
    operation_id: str
    loss_case_id: str
    lot_id: str
    context: LossExecutionContext
    decision: QualityDecision
    contamination_level: ContaminationLevel
    evidence: tuple[QualityEvidenceInput, ...]
    notes: str
    sensor_id: str | None = None
    temperature: Decimal | None = None
    minimum_temperature: Decimal | None = None
    maximum_temperature: Decimal | None = None
    reading_point: TemperaturePoint = TemperaturePoint.STORAGE


@dataclass(frozen=True, slots=True)
class QualityInspectionResult:
    case_id: str
    status: str
    quarantine_id: str | None = None
    temperature_reading_id: str | None = None
    replayed: bool = False


_QUALITY_CLASSIFICATIONS = frozenset({
    LossClassificationCode.QUALITY_REJECTION.value,
    LossClassificationCode.CONDEMNATION.value,
    LossClassificationCode.CONTAMINATION.value,
    LossClassificationCode.TEMPERATURE_EXCURSION.value,
})


class QualityInspectionService:
    def __init__(self, repository, inventory, authorization, policy=None) -> None:
        self._repository = repository
        self._inventory = inventory
        self._authorization = authorization
        self._policy = policy or QualityDecisionPolicy()

    def inspect(self, command: QualityInspectionCommand) -> QualityInspectionResult:
        replay = self._repository.find_processed(command.operation_id)
        if replay:
            return QualityInspectionResult(replay["case_id"], replay["status"],
                replay.get("quarantine_id"), replay.get("temperature_reading_id"), True)
        permission = (LossPermissions.QUALITY_REJECT
                      if command.decision is QualityDecision.REJECT
                      else LossPermissions.QUALITY_CONDEMN)
        self._authorization.require(command.context.actor_user_id, permission)
        case = self._repository.get_quality_case(command.loss_case_id, command.lot_id)
        if not case: raise LossInvariantError("Lote del expediente de calidad no encontrado")
        command.context.enforce_branch(case["branch_id"])
        command.context.enforce_warehouse(case["warehouse_id"])
        if case["classification"] not in _QUALITY_CLASSIFICATIONS:
            raise LossInvariantError("El expediente no tiene una clasificación de calidad")
        evaluation = self._policy.evaluate(decision=command.decision,
            contamination_level=command.contamination_level, evidence=command.evidence,
            temperature=command.temperature, minimum_temperature=command.minimum_temperature,
            maximum_temperature=command.maximum_temperature)
        if not command.notes.strip(): raise LossInvariantError("La decisión requiere observaciones")
        return (self._reject(command, case, evaluation)
                if evaluation.decision is QualityDecision.REJECT
                else self._condemn(command, case, evaluation))

    def _reject(self, command, case, evaluation):
        if case["status"] not in ("SUBMITTED", "UNDER_REVIEW"):
            raise LossInvariantError("El expediente no admite rechazo")
        with self._repository.transaction():
            reading_id = self._record_temperature(command, case)
            result = self._inventory.quarantine(product_id=case["product_id"],
                branch_id=case["branch_id"], warehouse_id=case["warehouse_id"],
                reason=(QuarantineReason.TEMPERATURE_EXCURSION
                        if evaluation.temperature_out_of_range
                        else QuarantineReason.QUALITY_FAILURE),
                quantity=case["quantity"], weight=case["weight"], lot_id=case["lot_id"],
                reason_note=command.notes.strip(), operation_id=command.operation_id,
                actor_user_id=command.context.actor_user_id,
                context=self._inventory_context(command.context), owns_transaction=False)
            self._require_success(result)
            self._repository.record_rejection(operation_id=command.operation_id, case=case,
                evaluation=evaluation, evidence=command.evidence, notes=command.notes.strip(),
                quarantine_id=result.entity_id, temperature_reading_id=reading_id,
                actor_user_id=command.context.actor_user_id)
        return QualityInspectionResult(case["id"], "REJECTED", result.entity_id, reading_id)

    def _condemn(self, command, case, evaluation):
        if case["status"] != "TREATMENT_PENDING" or not case["quarantine_id"]:
            raise LossInvariantError("El decomiso requiere un lote previamente bloqueado")
        if case["blocked_by_user_id"] == command.context.actor_user_id:
            raise LossInvariantError("Quien bloquea no puede ejecutar el decomiso")
        with self._repository.transaction():
            reading_id = self._record_temperature(command, case)
            self._repository.record_condemnation(operation_id=command.operation_id, case=case,
                evaluation=evaluation, evidence=command.evidence, notes=command.notes.strip(),
                temperature_reading_id=reading_id,
                actor_user_id=command.context.actor_user_id)
        return QualityInspectionResult(case["id"], "CONDEMNED_PENDING_DISPOSITION",
                                       case["quarantine_id"], reading_id)

    def _record_temperature(self, command, case):
        if command.temperature is None: return None
        if not command.sensor_id or not command.sensor_id.strip():
            raise LossInvariantError("La temperatura requiere sensor")
        result = self._inventory.record_temperature(sensor_id=command.sensor_id.strip(),
            warehouse_id=case["warehouse_id"], temperature=command.temperature,
            reading_point=command.reading_point, min_temp=command.minimum_temperature,
            max_temp=command.maximum_temperature, operation_id=command.operation_id,
            actor_user_id=command.context.actor_user_id, lot_id=case["lot_id"], auto_block=False,
            context=self._inventory_context(command.context), owns_transaction=False)
        self._require_success(result)
        return result.entity_id

    @staticmethod
    def _inventory_context(context):
        return InventoryExecutionContext(context.actor_user_id, context.active_branch_id,
            context.assigned_branch_ids, context.allowed_warehouse_ids,
            context.permissions, context.device_id)

    @staticmethod
    def _require_success(result):
        if not result.success:
            raise LossInvariantError(f"Inventario rechazó la operación: {result.message}")
