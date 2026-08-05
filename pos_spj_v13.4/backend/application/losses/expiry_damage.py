"""LOSS-10 orchestration: assess, quarantine, recover, and dispose lots."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from backend.application.inventory.execution_context import InventoryExecutionContext
from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.permissions import LossPermissions
from backend.domain.inventory.enums import QuarantineReason
from backend.domain.losses.expiry_damage import DamageSeverity, ExpiryDamageRiskPolicy, LotRiskLevel
from backend.domain.losses.exceptions import LossInvariantError


@dataclass(frozen=True, slots=True)
class AssessLotRiskCommand:
    operation_id: str
    loss_case_id: str
    lot_id: str
    context: LossExecutionContext
    as_of: date
    warning_days: int
    critical_days: int
    damage_severity: DamageSeverity


@dataclass(frozen=True, slots=True)
class BlockAtRiskLotCommand(AssessLotRiskCommand):
    reason_note: str


@dataclass(frozen=True, slots=True)
class ExpiryDamageResult:
    entity_id: str
    status: str
    risk_level: LotRiskLevel | None = None
    quarantine_id: str | None = None
    disposition_id: str | None = None
    replayed: bool = False


class ExpiryDamageRepositoryProtocol(Protocol):
    def transaction(self): ...
    def find_processed(self, operation_id): ...
    def get_lot_case(self, case_id, lot_id): ...


class ExpiryDamageWorkflowService:
    def __init__(self, repository: ExpiryDamageRepositoryProtocol, inventory,
                 authorization, risk_policy=None) -> None:
        self._repository = repository
        self._inventory = inventory
        self._authorization = authorization
        self._risk = risk_policy or ExpiryDamageRiskPolicy()

    def assess(self, command: AssessLotRiskCommand) -> ExpiryDamageResult:
        replay = self._replay(command.operation_id)
        if replay: return replay
        self._authorization.require(command.context.actor_user_id, LossPermissions.EXPIRY_DAMAGE_VIEW)
        case = self._case(command.loss_case_id, command.lot_id, command.context)
        assessment = self._assessment(command, case)
        with self._repository.transaction():
            self._repository.record_assessment(operation_id=command.operation_id,
                assessment=assessment, case=case, actor_user_id=command.context.actor_user_id)
        return ExpiryDamageResult(case["id"], "ASSESSED", assessment.risk_level)

    def block(self, command: BlockAtRiskLotCommand) -> ExpiryDamageResult:
        replay = self._replay(command.operation_id)
        if replay: return replay
        self._authorization.require(command.context.actor_user_id, LossPermissions.REVIEW)
        if not command.reason_note.strip():
            raise LossInvariantError("El bloqueo requiere un motivo")
        case = self._case(command.loss_case_id, command.lot_id, command.context)
        if case["status"] not in ("SUBMITTED", "UNDER_REVIEW", "TREATMENT_PENDING"):
            raise LossInvariantError("El expediente no admite bloqueo")
        assessment = self._assessment(command, case)
        if assessment.risk_level is LotRiskLevel.NORMAL:
            raise LossInvariantError("Un lote sin riesgo no puede bloquearse")
        reason = QuarantineReason.QUALITY_FAILURE
        with self._repository.transaction():
            result = self._inventory.quarantine(product_id=case["product_id"],
                branch_id=case["branch_id"], warehouse_id=case["warehouse_id"],
                reason=reason, quantity=case["quantity"], weight=case["weight"],
                lot_id=case["lot_id"], reason_note=command.reason_note.strip(),
                operation_id=command.operation_id, actor_user_id=command.context.actor_user_id,
                context=self._inventory_context(command.context), owns_transaction=False)
            self._require_success(result)
            self._repository.record_block(operation_id=command.operation_id, case=case,
                quarantine_id=result.entity_id, assessment=assessment,
                actor_user_id=command.context.actor_user_id)
        return ExpiryDamageResult(case["id"], "TREATMENT_PENDING", assessment.risk_level,
                                  result.entity_id)

    def _case(self, case_id, lot_id, context):
        case = self._repository.get_lot_case(case_id, lot_id)
        if not case: raise LossInvariantError("Lote del expediente no encontrado")
        context.enforce_branch(case["branch_id"]); context.enforce_warehouse(case["warehouse_id"])
        return case

    def _assessment(self, command, case):
        return self._risk.assess(expiration_date=case["expiration_date"], as_of=command.as_of,
            warning_days=command.warning_days, critical_days=command.critical_days,
            damage_severity=command.damage_severity, quantity=case["quantity"], weight=case["weight"])

    @staticmethod
    def _require_treatment(case):
        if case["status"] != "TREATMENT_PENDING" or not case["quarantine_id"]:
            raise LossInvariantError("El lote no tiene un bloqueo activo")

    def _replay(self, operation_id):
        row = self._repository.find_processed(operation_id)
        if not row: return None
        risk = LotRiskLevel(row["risk_level"]) if row.get("risk_level") else None
        return ExpiryDamageResult(row["entity_id"], row["kind"], risk,
            row.get("quarantine_id"), row.get("disposition_id") or
            (row["entity_id"] if row["kind"].startswith("DISPOSITION") else None), True)

    @staticmethod
    def _require_success(result):
        if not result.success:
            raise LossInvariantError(f"Inventario rechazó la operación: {result.message}")

    @staticmethod
    def _inventory_context(context):
        return InventoryExecutionContext(context.actor_user_id, context.active_branch_id,
            context.assigned_branch_ids, context.allowed_warehouse_ids,
            context.permissions, context.device_id)
