"""NotificationRoutingPolicy — SET-20 "Routing": which `NotificationRoute`
applies for an ERP event code. Mirrors
`backend.domain.customer_display.policies.display_layout_resolution_policy.
resolve_layout()`'s shape (SET-17) — a plain lookup, no branch/workstation
scoping, matching the "one route per event" simplicity of the legacy
`TEMPLATES` dict this generalizes.
"""

from __future__ import annotations

from backend.domain.notifications.entities.notification_route import NotificationRoute
from backend.domain.notifications.exceptions import NotificationRouteNotFoundError


def resolve_route(routes: list[NotificationRoute], event_code: str) -> NotificationRoute:
    matching = [route for route in routes if route.event_code == event_code and route.active]
    if not matching:
        raise NotificationRouteNotFoundError(f"No hay NotificationRoute activa para event_code={event_code!r}")
    return matching[0]
