"""DeviceTestResult — SET-9 (§21): the outcome of an on-demand diagnostic
test for any device (scale read test, scanner scan test, connectivity
check, ...). Append-only history, same shape as SET-8's
`printer_test_result.py::PrinterTestResult`.

Generalized on purpose: SET-8 built a printer-only `PrinterTestResult`
before a second use case existed to prove out the right shape; now that
scales *and* readers need the same thing, this is the shared, reusable
entity going forward (SET-10's cajones/terminales should use this too,
not add a third near-duplicate). `PrinterTestResult`/`printer_test_results`
stays as-is — it already shipped (migration 212) and splitting it out
was a reasonable call at the time, not a mistake worth a breaking
migration to unwind.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.device_management.exceptions import DeviceInvalidValueError
from backend.shared.ids import new_uuid, validate_uuidv7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().isoformat(timespec="seconds")


@dataclass(slots=True)
class DeviceTestResult:
    id: str
    device_id: str
    test_type: str
    success: bool
    message: str = ""
    tested_by_user_id: str | None = None
    tested_at: str = field(default_factory=_utcnow_iso)

    @classmethod
    def record(
        cls, *, device_id: str, test_type: str, success: bool, message: str = "",
        tested_by_user_id: str | None = None, at: datetime | None = None,
    ) -> "DeviceTestResult":
        if not test_type.strip():
            raise DeviceInvalidValueError("test_type es obligatorio (p. ej. 'READ_WEIGHT', 'SCAN', 'CONNECTIVITY')")
        return cls(
            id=new_uuid(), device_id=validate_uuidv7(device_id), test_type=test_type.strip().upper(),
            success=bool(success), message=message.strip(), tested_by_user_id=tested_by_user_id,
            tested_at=(at or _utcnow()).isoformat(timespec="seconds"),
        )
