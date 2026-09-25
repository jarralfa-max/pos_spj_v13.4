"""QUALITY_OUTPUT_* → Procesamiento registra en su output lo que Calidad decidió.

El actor es el inspector que decidió (viene en el evento), autorizado con la
concesión explícita que Procesamiento da a `quality`. El `operation_id` es el de
la decisión de Calidad: la misma operación, vista desde este contexto, e
idempotente si el evento se entrega dos veces.
"""

from __future__ import annotations

from backend.application.meat_processing.integration_grants import meat_processing_policy_for
from backend.domain.meat_processing.enums import OutputQualityStatus

#: Decisión de Calidad → estado del output de producción.
DECISION_TO_OUTPUT_STATUS = {
    "RELEASED": OutputQualityStatus.RELEASED,
    "BLOCKED": OutputQualityStatus.REJECTED,
    "REWORK_REQUIRED": OutputQualityStatus.REWORK_REQUIRED,
    "CONDEMNED": OutputQualityStatus.CONDEMNED,
}


class QualityDecisionRecordedHandler:
    def __init__(self, connection) -> None:
        self._conn = connection

    def handle(self, payload: dict) -> None:
        from backend.application.meat_processing.use_cases.quality_use_cases import (
            RecordQualityDecisionUseCase,
        )
        if payload.get("source_module") != "meat_processing":
            return
        inspector = str(payload["decided_by_user_id"])
        from backend.infrastructure.integrations.meat_processing_ports import (
            QualityDecisionReadAdapter,
        )
        r = RecordQualityDecisionUseCase(
            meat_processing_policy_for("quality", inspector),
            quality_decisions=QualityDecisionReadAdapter(self._conn)).execute(
            self._conn, output_id=str(payload["process_output_id"]),
            operation_id=str(payload["operation_id"]),
            decision=DECISION_TO_OUTPUT_STATUS[str(payload["decision"])],
            actor_user_id=inspector, quality_inspection_id=str(payload["inspection_id"]))
        if not r.success:
            raise RuntimeError(f"Procesamiento no registró la decisión de Calidad: {r.message}")
