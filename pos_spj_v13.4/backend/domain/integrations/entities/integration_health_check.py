"""IntegrationHealthCheck — SET-19 "Health": one recorded diagnostic
result for an `IntegrationInstance`. Append-only, no lifecycle of its own
— mirrors `backend.domain.device_management.entities.device_test_result.
DeviceTestResult`'s exact shape (SET-9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.integrations.exceptions import IntegrationsInvalidValueError
from backend.shared.ids import new_uuid, validate_uuidv7


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class IntegrationHealthCheck:
    id: str
    instance_id: str
    success: bool
    message: str = ""
    checked_at: str = field(default_factory=_utcnow)

    @classmethod
    def record(cls, *, instance_id: str, success: bool, message: str = "") -> "IntegrationHealthCheck":
        if not isinstance(success, bool):
            raise IntegrationsInvalidValueError(f"success debe ser bool, recibido {success!r}")
        return cls(id=new_uuid(), instance_id=validate_uuidv7(instance_id), success=success, message=message.strip())
