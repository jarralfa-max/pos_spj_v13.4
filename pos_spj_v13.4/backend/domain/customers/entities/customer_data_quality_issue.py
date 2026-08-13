"""CustomerDataQualityIssue — one detected data-quality problem on a
customer record (§46). Produced by CustomerDataQualityService (application
layer — evaluating rules needs to read customer+child records, so it isn't
pure domain logic); this entity only models the issue's own lifecycle.

Status transitions:

    OPEN ──acknowledge()──► ACKNOWLEDGED ──correct()──► CORRECTED
      │                          │
      └──────────dismiss(reason)─┴──► DISMISSED
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customers.enums import DataQualityIssueStatus, DataQualityRuleCode
from backend.domain.customers.exceptions import InvalidDataQualityIssueStateError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_ACKNOWLEDGEABLE = {DataQualityIssueStatus.OPEN}
_CORRECTABLE = {DataQualityIssueStatus.ACKNOWLEDGED}
_DISMISSIBLE = {DataQualityIssueStatus.OPEN, DataQualityIssueStatus.ACKNOWLEDGED}


@dataclass(slots=True)
class CustomerDataQualityIssue:
    id: str
    customer_id: str
    rule_code: DataQualityRuleCode
    description: str = ""
    status: DataQualityIssueStatus = DataQualityIssueStatus.OPEN
    acknowledged_by_user_id: str | None = None
    acknowledged_at: str | None = None
    corrected_at: str | None = None
    dismissed_by_user_id: str | None = None
    dismissed_at: str | None = None
    dismissal_reason: str = ""
    operation_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    @classmethod
    def detect(
        cls, customer_id: str, rule_code: DataQualityRuleCode, description: str = "", *,
        operation_id: str | None = None,
    ) -> "CustomerDataQualityIssue":
        if not customer_id:
            raise InvalidDataQualityIssueStateError("customer_id es obligatorio")
        return cls(id=new_uuid(), customer_id=customer_id, rule_code=rule_code,
                   description=description.strip(), operation_id=operation_id)

    def acknowledge(self, acknowledged_by_user_id: str) -> None:
        if self.status not in _ACKNOWLEDGEABLE:
            raise InvalidDataQualityIssueStateError(
                f"No se puede reconocer desde {self.status.value}")
        self.status = DataQualityIssueStatus.ACKNOWLEDGED
        self.acknowledged_by_user_id = acknowledged_by_user_id
        self.acknowledged_at = _utcnow()
        self._touch()

    def correct(self) -> None:
        if self.status not in _CORRECTABLE:
            raise InvalidDataQualityIssueStateError(
                f"No se puede corregir desde {self.status.value}")
        self.status = DataQualityIssueStatus.CORRECTED
        self.corrected_at = _utcnow()
        self._touch()

    def dismiss(self, dismissed_by_user_id: str, reason: str) -> None:
        if self.status not in _DISMISSIBLE:
            raise InvalidDataQualityIssueStateError(
                f"No se puede descartar desde {self.status.value}")
        if not reason.strip():
            raise InvalidDataQualityIssueStateError("Descartar requiere un motivo")
        self.status = DataQualityIssueStatus.DISMISSED
        self.dismissed_by_user_id = dismissed_by_user_id
        self.dismissed_at = _utcnow()
        self.dismissal_reason = reason.strip()
        self._touch()

    def is_resolved(self) -> bool:
        return self.status in (DataQualityIssueStatus.CORRECTED, DataQualityIssueStatus.DISMISSED)
