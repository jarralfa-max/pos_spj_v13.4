"""CashDrawerSecurityPolicy — SET-10 (§60, §69 `PermissionDeniedError`
family): may this cash drawer actually be opened?

Traceable to the legacy `CASH_DRAWER_OPEN_WITHOUT_SALE` permission the
SET-0 audit found (`docs/refactor/settings_legacy_inventory.md` §7,
Cash Register's own permission catalog) — opening a drawer with no sale
behind it is exactly the "no-sale drawer pop" anti-theft control every
POS needs. This policy is the one place that rule lives for Device
Management's own drawer-open path; it does not decide *permission codes*
(that's `core/security/permission_catalog.py`'s job at the application
layer) — only whether the *request itself* carries the justification a
no-sale open requires.
"""

from __future__ import annotations

from backend.domain.device_management.exceptions import CashDrawerOpeningNotAuthorizedError
from backend.domain.device_management.value_objects.cash_drawer_open_request import CashDrawerOpenRequest


def assert_can_open(request: CashDrawerOpenRequest) -> None:
    has_reason = bool(request.reason and request.reason.strip())
    if not request.is_linked_to_sale() and not has_reason:
        raise CashDrawerOpeningNotAuthorizedError(
            f"Abrir el cajón {request.device_id} sin una venta asociada requiere un motivo "
            "explícito (§60 — apertura sin venta es una operación sensible)."
        )
