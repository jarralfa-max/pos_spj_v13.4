"""CashDrawerOpenRequest — SET-10 (§60): a well-formed request to open a
cash drawer. Shape-only validation lives here (who, which device, and —
if there's no linked sale — that *some* reason string was given); whether
that reason is actually *sufficient* to authorize the open is
`policies/cash_drawer_security_policy.py::assert_can_open()`'s job, kept
separate the same way `ConfigurationValue` (well-formed) and
`ConfigurationApprovalPolicy` (may this specific actor approve it) are
split in `backend/domain/settings/`.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.device_management.exceptions import DeviceInvalidValueError
from backend.shared.ids import validate_uuidv7


@dataclass(frozen=True, slots=True)
class CashDrawerOpenRequest:
    device_id: str
    opened_by_user_id: str
    sale_reference: str | None = None
    reason: str | None = None

    @classmethod
    def create(
        cls, *, device_id: str, opened_by_user_id: str, sale_reference: str | None = None,
        reason: str | None = None,
    ) -> "CashDrawerOpenRequest":
        validated_device_id = validate_uuidv7(device_id)
        if not opened_by_user_id or not opened_by_user_id.strip():
            raise DeviceInvalidValueError("opened_by_user_id es obligatorio")
        return cls(
            device_id=validated_device_id, opened_by_user_id=opened_by_user_id.strip(),
            sale_reference=sale_reference.strip() if sale_reference else None,
            reason=reason.strip() if reason else None,
        )

    def is_linked_to_sale(self) -> bool:
        return self.sale_reference is not None
