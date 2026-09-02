import pytest

from frontend.desktop.shell.router.desktop_router import DesktopRouter
from frontend.desktop.shell.router.errors import NavigationPermissionDeniedError
from frontend.desktop.shell.router.navigation_events import (
    NAVIGATION_BACK,
    NAVIGATION_DENIED,
    NAVIGATION_FORWARD,
    NAVIGATION_REQUESTED,
    NAVIGATION_SUCCEEDED,
)
from tests.unit.shell.router.conftest import make_context


def test_successful_navigate_publishes_requested_then_succeeded(routes, view_factories):
    events = []
    context = make_context(permissions=frozenset({"*"}))
    router = DesktopRouter(
        route_registry=routes, view_factory_registry=view_factories, initial_context=context,
        event_publisher=lambda name, payload: events.append((name, payload)),
    )
    router.navigate("sales.pos")
    names = [name for name, _ in events]
    assert names == [NAVIGATION_REQUESTED, NAVIGATION_SUCCEEDED]


def test_denied_navigate_publishes_requested_then_denied(routes, view_factories):
    events = []
    context = make_context(permissions=frozenset())
    router = DesktopRouter(
        route_registry=routes, view_factory_registry=view_factories, initial_context=context,
        event_publisher=lambda name, payload: events.append((name, payload)),
    )
    with pytest.raises(NavigationPermissionDeniedError):
        router.navigate("sales.pos")
    names = [name for name, _ in events]
    assert names == [NAVIGATION_REQUESTED, NAVIGATION_DENIED]


def test_go_back_publishes_navigation_back(routes, view_factories):
    events = []
    context = make_context(permissions=frozenset({"*"}))
    router = DesktopRouter(
        route_registry=routes, view_factory_registry=view_factories, initial_context=context,
        event_publisher=lambda name, payload: events.append((name, payload)),
    )
    router.navigate("sales.pos")
    router.navigate("inventory.overview")
    events.clear()
    router.go_back()
    assert events[-1][0] == NAVIGATION_BACK


def test_go_forward_publishes_navigation_forward(routes, view_factories):
    events = []
    context = make_context(permissions=frozenset({"*"}))
    router = DesktopRouter(
        route_registry=routes, view_factory_registry=view_factories, initial_context=context,
        event_publisher=lambda name, payload: events.append((name, payload)),
    )
    router.navigate("sales.pos")
    router.navigate("inventory.overview")
    router.go_back()
    events.clear()
    router.go_forward()
    assert events[-1][0] == NAVIGATION_FORWARD


def test_no_event_publisher_is_safe_default(routes, view_factories, context):
    router = DesktopRouter(route_registry=routes, view_factory_registry=view_factories, initial_context=context)
    router.navigate("sales.pos")  # must not raise
