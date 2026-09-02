"""SET-20 — "Routing": NotificationRoute + notification_routing_policy.
resolve_route. Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.notifications.entities.notification_route import NotificationRoute
from backend.domain.notifications.enums import NotificationChannel
from backend.domain.notifications.exceptions import (
    NotificationRouteNotFoundError,
    NotificationsInvalidValueError,
)
from backend.domain.notifications.policies.notification_routing_policy import resolve_route
from backend.shared.ids import is_uuidv7, new_uuid


def _route(**overrides) -> NotificationRoute:
    kwargs = dict(
        event_code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, template_id=new_uuid(),
        account_id=new_uuid(),
    )
    kwargs.update(overrides)
    return NotificationRoute.create(**kwargs)


class TestNotificationRouteCreate:
    def test_mints_uuidv7(self):
        route = _route()
        assert is_uuidv7(route.id)
        assert route.active is True

    def test_requires_event_code(self):
        with pytest.raises(NotificationsInvalidValueError):
            _route(event_code="   ")

    def test_validates_template_id_and_account_id_as_uuid(self):
        with pytest.raises(ValueError):
            _route(template_id="not-a-uuid")
        with pytest.raises(ValueError):
            _route(account_id="not-a-uuid")

    def test_activate_deactivate(self):
        route = _route()
        route.deactivate()
        assert route.active is False
        route.activate()
        assert route.active is True


class TestResolveRoute:
    def test_finds_the_active_route_for_the_event(self):
        confirmado = _route(event_code="pedido_confirmado")
        listo = _route(event_code="pedido_listo")
        resolved = resolve_route([confirmado, listo], "pedido_confirmado")
        assert resolved is confirmado

    def test_raises_when_no_route_matches_the_event(self):
        listo = _route(event_code="pedido_listo")
        with pytest.raises(NotificationRouteNotFoundError):
            resolve_route([listo], "pedido_confirmado")

    def test_inactive_routes_are_ignored(self):
        route = _route()
        route.deactivate()
        with pytest.raises(NotificationRouteNotFoundError):
            resolve_route([route], "pedido_confirmado")

    def test_raises_on_empty_candidate_list(self):
        with pytest.raises(NotificationRouteNotFoundError):
            resolve_route([], "pedido_confirmado")
