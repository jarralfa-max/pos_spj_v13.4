"""PrinterTestResult — SET-8 (§21/§23): the outcome of an on-demand test
print. Append-only history, not a mutable status — each attempt is its
own record, never overwritten. "No ejecutar pruebas invasivas sin
advertencia" (§21) is a UI/application concern (confirm before firing a
physical test print); this entity only records what already happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.shared.ids import new_uuid, validate_uuidv7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().isoformat(timespec="seconds")


@dataclass(slots=True)
class PrinterTestResult:
    id: str
    device_id: str
    success: bool
    message: str = ""
    tested_by_user_id: str | None = None
    tested_at: str = field(default_factory=_utcnow_iso)

    @classmethod
    def record(
        cls, *, device_id: str, success: bool, message: str = "",
        tested_by_user_id: str | None = None, at: datetime | None = None,
    ) -> "PrinterTestResult":
        return cls(
            id=new_uuid(), device_id=validate_uuidv7(device_id), success=bool(success),
            message=message.strip(), tested_by_user_id=tested_by_user_id,
            tested_at=(at or _utcnow()).isoformat(timespec="seconds"),
        )
