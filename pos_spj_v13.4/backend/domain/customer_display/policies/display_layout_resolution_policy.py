"""DisplayLayoutResolutionPolicy — SET-17 "Modes"/"Layouts": which
`DisplayLayout` applies for a given `CustomerDisplayMode`. Simpler than
`device_management.policies.print_routing_policy.resolve_route()`
(SET-8) — no branch/workstation/module/channel scoping here, since the
legacy screen-mode mapping this generalizes
(`customer_display_query_service.py::_SCREEN_BY_STATUS`) was always one
single global mapping, not scoped per branch.
"""

from __future__ import annotations

from backend.domain.customer_display.entities.display_layout import DisplayLayout
from backend.domain.customer_display.enums import CustomerDisplayMode
from backend.domain.customer_display.exceptions import DisplayLayoutNotFoundError


def resolve_layout(layouts: list[DisplayLayout], mode: CustomerDisplayMode) -> DisplayLayout:
    matching = [layout for layout in layouts if layout.mode is mode and layout.active]
    if not matching:
        raise DisplayLayoutNotFoundError(f"No hay DisplayLayout activo para mode={mode.value!r}")
    return matching[0]
