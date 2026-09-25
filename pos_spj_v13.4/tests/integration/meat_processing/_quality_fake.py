"""Calidad que YA decidió, para pruebas de Procesamiento que no son de Calidad.

`RecordQualityDecisionUseCase` sólo registra una decisión que exista en Calidad
(esa inspección, de ese output, decidida así y por ese usuario). Las pruebas de
cierre, reproceso o del propio registro necesitan una decisión ya tomada; ésta
la representa con el mismo contrato de lectura que usa producción
(`QualityDecisionReadPort`). El flujo real de Calidad se prueba en
`test_quality_release_moves_output_to_available_inventory.py`.
"""
from __future__ import annotations

from backend.application.meat_processing.use_cases import RecordQualityDecisionUseCase
from backend.domain.meat_processing.enums import OutputQualityStatus
from backend.shared.ids import new_uuid

_STATUS = {OutputQualityStatus.RELEASED: "RELEASED", OutputQualityStatus.REJECTED: "BLOCKED",
           OutputQualityStatus.REWORK_REQUIRED: "REWORK_REQUIRED",
           OutputQualityStatus.CONDEMNED: "CONDEMNED"}


class QualityDecided:
    def __init__(self) -> None:
        self._decisiones: dict[str, dict] = {}

    def decided(self, *, output_id: str, decision, actor: str) -> str:
        inspection_id = new_uuid()
        self._decisiones[inspection_id] = {
            "subject_id": output_id, "source_module": "meat_processing",
            "status": _STATUS.get(OutputQualityStatus(decision), str(decision)),
            "decided_by_user_id": actor}
        return inspection_id

    def decision_of(self, inspection_id: str) -> dict | None:
        return self._decisiones.get(inspection_id)


def record_decided_by_quality(conn, *, authorization=None, **kwargs):
    """Registra en Procesamiento una decisión que Calidad ya tomó.
    ``quality_inspection_id=""`` prueba el caso sin inspección."""
    calidad = QualityDecided()
    if kwargs.get("quality_inspection_id") != "":
        kwargs["quality_inspection_id"] = calidad.decided(
            output_id=kwargs["output_id"], decision=kwargs["decision"],
            actor=kwargs["actor_user_id"])
    return RecordQualityDecisionUseCase(authorization, quality_decisions=calidad).execute(
        conn, **kwargs)
