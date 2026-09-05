"""AssetInspection — executed inspection against an asset (ASSET-7, §37).

Recording a checklist answer never validates business meaning of the value
(that belongs to a later application-layer / UI concern) — the domain only
guards the inspection's own lifecycle: answers before a result, one result
recorded once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.assets.enums import InspectionResultStatus, InspectionType
from backend.domain.assets.exceptions import AssetDomainError, InspectionStateInvalidError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class InspectionAnswer:
    checklist_item_id: str
    value: str


@dataclass(slots=True)
class AssetInspection:
    id: str
    asset_id: str
    inspection_type: InspectionType
    inspector_user_id: str
    operation_id: str
    checklist_template_id: str | None = None
    scheduled_at: str | None = None
    executed_at: str | None = None
    result: InspectionResultStatus | None = None
    notes: str = ""
    answers: list[InspectionAnswer] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, asset_id: str, inspection_type: InspectionType, inspector_user_id: str,
               operation_id: str, *, checklist_template_id: str | None = None,
               scheduled_at: str | None = None) -> "AssetInspection":
        if not asset_id:
            raise AssetDomainError("AssetInspection.asset_id is required")
        if not inspector_user_id:
            raise AssetDomainError("AssetInspection.inspector_user_id is required")
        return cls(
            id=new_uuid(), asset_id=asset_id, inspection_type=inspection_type,
            inspector_user_id=inspector_user_id, operation_id=operation_id,
            checklist_template_id=checklist_template_id, scheduled_at=scheduled_at,
        )

    def is_recorded(self) -> bool:
        return self.result is not None

    def answer(self, checklist_item_id: str, value: str) -> None:
        if self.is_recorded():
            raise InspectionStateInvalidError(
                "No se pueden agregar respuestas a una inspección ya registrada")
        self.answers.append(InspectionAnswer(checklist_item_id, value))

    def record_result(self, result: InspectionResultStatus, notes: str = "") -> None:
        if self.is_recorded():
            raise InspectionStateInvalidError("Esta inspección ya tiene un resultado registrado")
        self.result = result
        self.notes = notes
        self.executed_at = _utcnow()

    def fail(self, notes: str = "") -> None:
        self.record_result(InspectionResultStatus.FAIL, notes)

    def passed(self) -> bool:
        return self.result in (InspectionResultStatus.PASS_,
                               InspectionResultStatus.PASS_WITH_OBSERVATIONS)
