"""Inspección de outputs de producción — contexto CALIDAD.

Procesamiento solicita la inspección y registra lo que Calidad decidió; nunca
aprueba, libera, bloquea ni condena por su cuenta.

Flujo:
    ProcessOutput (retenido en cuarentena)
    → RequestOutputInspectionUseCase      (lo pide Procesamiento)
    → DecideOutputInspectionUseCase       (lo decide un inspector)
        · segregación: quien produjo NO decide
        · Inventario mueve el lote a su estado: liberado → disponible;
          bloqueado / reproceso / condenado → bloqueado por calidad
        · se publica QUALITY_OUTPUT_RELEASED | _BLOCKED | _REWORK_REQUIRED |
          _CONDEMNED
    → Procesamiento registra la decisión en su output (manejador del evento).

Así output, lote y saldo cambian juntos: nunca queda un output «liberado» con
su lote retenido, ni un saldo disponible de un lote sin inspeccionar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from backend.application.quality.permissions import ALL_QUALITY_PERMISSIONS, QualityPermissions
from backend.application.security.system_integration_authorization import (
    DelegatedIntegrationPermissionChecker,
    IntegrationGrant,
)
from backend.infrastructure.db.repositories.quality.inspection_repository import (
    InspectionRepository,
    QualityOutboxRepository,
)
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.quality.output_inspection")

SUBJECT_PROCESS_OUTPUT = "PROCESS_OUTPUT"


class QualityDecision(str, Enum):
    RELEASED = "RELEASED"
    BLOCKED = "BLOCKED"
    REWORK_REQUIRED = "REWORK_REQUIRED"
    CONDEMNED = "CONDEMNED"


QUALITY_OUTPUT_RELEASED = "QUALITY_OUTPUT_RELEASED"
QUALITY_OUTPUT_BLOCKED = "QUALITY_OUTPUT_BLOCKED"
QUALITY_REWORK_REQUIRED = "QUALITY_REWORK_REQUIRED"
QUALITY_OUTPUT_CONDEMNED = "QUALITY_OUTPUT_CONDEMNED"

DECISION_EVENTS = {
    QualityDecision.RELEASED: QUALITY_OUTPUT_RELEASED,
    QualityDecision.BLOCKED: QUALITY_OUTPUT_BLOCKED,
    QualityDecision.REWORK_REQUIRED: QUALITY_REWORK_REQUIRED,
    QualityDecision.CONDEMNED: QUALITY_OUTPUT_CONDEMNED,
}
QUALITY_DECISION_EVENTS = frozenset(DECISION_EVENTS.values())

#: Procesamiento puede pedir inspecciones; nada más.
MEAT_PROCESSING_QUALITY_GRANT = IntegrationGrant(
    owner_context="quality", source_module="meat_processing",
    permissions=frozenset({QualityPermissions.INSPECTION_REQUEST}))
_GRANTS = {MEAT_PROCESSING_QUALITY_GRANT.source_module: MEAT_PROCESSING_QUALITY_GRANT}


class QualityPermissionDeniedError(PermissionError):
    pass


class QualityAuthorizationPolicy:
    def __init__(self, checker) -> None:
        if checker is None:
            raise ValueError("QualityAuthorizationPolicy requiere un verificador de permisos")
        self._checker = checker

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in ALL_QUALITY_PERMISSIONS:
            raise QualityPermissionDeniedError(f"Permiso desconocido: {permission_code}")
        if not user_id or not self._checker.has_permission(user_id, permission_code):
            raise QualityPermissionDeniedError(
                f"El usuario {user_id} no tiene el permiso {permission_code}")


def quality_policy_for(source_module: str, actor_user_id: str) -> QualityAuthorizationPolicy:
    grant = _GRANTS.get(source_module)
    if grant is None:
        raise QualityPermissionDeniedError(f"Calidad no concede nada al módulo «{source_module}»")
    return QualityAuthorizationPolicy(
        DelegatedIntegrationPermissionChecker(grant=grant, actor_user_id=actor_user_id))


@dataclass(frozen=True)
class QualityResult:
    success: bool
    inspection_id: str | None = None
    message: str = ""
    error_code: str | None = None
    already_processed: bool = False


class RequestOutputInspectionUseCase:
    def __init__(self, authorization: QualityAuthorizationPolicy) -> None:
        if authorization is None:
            raise ValueError("RequestOutputInspectionUseCase requiere autorización")
        self._auth = authorization

    def execute(self, connection, *, operation_id: str, actor_user_id: str,
                source_module: str, source_document_id: str, subject_id: str,
                product_id: str, lot_id: str | None, branch_id: str, warehouse_id: str,
                produced_by_user_id: str) -> QualityResult:
        try:
            self._auth.require(actor_user_id, QualityPermissions.INSPECTION_REQUEST)
        except QualityPermissionDeniedError as exc:
            return QualityResult(False, message=str(exc), error_code="PERMISSION_DENIED")
        repo = InspectionRepository(connection)
        previa = repo.find_by_subject(SUBJECT_PROCESS_OUTPUT, subject_id)
        if previa is not None:
            return QualityResult(True, previa.id, "Inspección ya solicitada (idempotente)",
                                 already_processed=True)
        inspection_id = repo.add(
            operation_id=operation_id, source_module=source_module,
            source_document_id=source_document_id, subject_type=SUBJECT_PROCESS_OUTPUT,
            subject_id=subject_id, product_id=product_id, lot_id=lot_id, branch_id=branch_id,
            warehouse_id=warehouse_id, produced_by_user_id=produced_by_user_id)
        connection.commit()
        return QualityResult(True, inspection_id, "Inspección solicitada")


_LOT_STATUS = {
    QualityDecision.RELEASED: "RELEASED",
    QualityDecision.BLOCKED: "BLOCKED",
    QualityDecision.REWORK_REQUIRED: "BLOCKED",
    QualityDecision.CONDEMNED: "REJECTED",
}


class DecideOutputInspectionUseCase:
    def __init__(self, authorization: QualityAuthorizationPolicy, *,
                 inventory_policy_factory=None) -> None:
        if authorization is None:
            raise ValueError("DecideOutputInspectionUseCase requiere autorización")
        self._auth = authorization
        if inventory_policy_factory is None:
            from backend.application.inventory.integration_grants import inventory_policy_for

            def inventory_policy_factory(actor):
                return inventory_policy_for("quality", actor)[0]
        self._inventory_policy = inventory_policy_factory

    def execute(self, connection, *, inspection_id: str, decision: QualityDecision,
                reason: str, operation_id: str, actor_user_id: str,
                dispatch=None) -> QualityResult:
        from backend.application.inventory.use_cases.lot_use_cases import (
            SetLotQualityStatusUseCase,
        )
        from backend.domain.inventory.enums import LotQualityStatus

        try:
            self._auth.require(actor_user_id, QualityPermissions.INSPECTION_DECIDE)
        except QualityPermissionDeniedError as exc:
            return QualityResult(False, message=str(exc), error_code="PERMISSION_DENIED")
        decision = QualityDecision(decision)
        repo = InspectionRepository(connection)
        inspeccion = repo.get(inspection_id)
        if inspeccion is None:
            return QualityResult(False, message="Inspección no encontrada",
                                 error_code="INSPECTION_NOT_FOUND")
        if inspeccion.status != "PENDING":
            if inspeccion.decision_operation_id == operation_id:
                return QualityResult(True, inspection_id, "Decisión ya registrada (idempotente)",
                                     already_processed=True)
            return QualityResult(False, inspection_id,
                                 f"La inspección ya se decidió ({inspeccion.status})",
                                 "ALREADY_DECIDED")
        if actor_user_id == inspeccion.produced_by_user_id:
            return QualityResult(False, inspection_id,
                                 "Quien produjo no puede decidir la calidad de lo que produjo.",
                                 "SEGREGATION_OF_DUTIES")
        if decision is not QualityDecision.RELEASED and not (reason or "").strip():
            return QualityResult(False, inspection_id, "Bloquear, mandar a reproceso o condenar "
                                 "exige un motivo.", "REASON_REQUIRED")
        if inspeccion.lot_id:
            r = SetLotQualityStatusUseCase(self._inventory_policy(actor_user_id)).execute(
                connection, lot_id=inspeccion.lot_id,
                new_status=LotQualityStatus(_LOT_STATUS[decision]), operation_id=operation_id,
                actor_user_id=actor_user_id, reason=reason or "Liberado por Calidad")
            if not r.success:
                return QualityResult(False, inspection_id,
                                     f"Inventario no aplicó la decisión: {r.message}",
                                     "INVENTORY_REJECTED")
        repo.decide(inspection_id, status=decision.value, decided_by_user_id=actor_user_id,
                    decision_operation_id=operation_id, reason=reason or "")
        evento_id = new_uuid()
        QualityOutboxRepository(connection).enqueue(
            event_id=evento_id, event_name=DECISION_EVENTS[decision], operation_id=operation_id,
            payload={"event_id": evento_id, "operation_id": operation_id,
                     "occurred_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "inspection_id": inspection_id, "decision": decision.value,
                     "decided_by_user_id": actor_user_id, "reason": reason or "",
                     "subject_type": inspeccion.subject_type,
                     "process_output_id": inspeccion.subject_id,
                     "source_module": inspeccion.source_module,
                     "source_document_id": inspeccion.source_document_id,
                     "product_id": inspeccion.product_id, "lot_id": inspeccion.lot_id,
                     "branch_id": inspeccion.branch_id,
                     "warehouse_id": inspeccion.warehouse_id})
        connection.commit()
        if dispatch is not None:
            dispatch(connection)
        return QualityResult(True, inspection_id, "Decisión de calidad registrada")
