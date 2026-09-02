import pytest

from frontend.desktop.shell.router.desktop_router import DesktopRouter
from frontend.desktop.shell.router.errors import NavigationRequiresOnlineError
from frontend.desktop.shell.routing.offline_policy import OfflinePolicy
from frontend.desktop.shell.routing.route_definition import RouteDefinition
from frontend.desktop.shell.routing.route_registry import RouteRegistry
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry
from tests.unit.shell.router.conftest import make_context


def _routes_with_offline_policies() -> RouteRegistry:
    registry = RouteRegistry()
    registry.register(RouteDefinition(
        route_id="sales.pos", module_id="sales", title="POS", view_factory_id="v1",
        offline_policy=OfflinePolicy.AVAILABLE_OFFLINE,
    ))
    registry.register(RouteDefinition(
        route_id="reports.dashboard", module_id="reports", title="Dashboard", view_factory_id="v2",
        offline_policy=OfflinePolicy.DEGRADED_OFFLINE,
    ))
    registry.register(RouteDefinition(
        route_id="whatsapp.status", module_id="whatsapp", title="WhatsApp", view_factory_id="v3",
        offline_policy=OfflinePolicy.REQUIRES_ONLINE,
    ))
    return registry


def _offline_view_factories() -> ViewFactoryRegistry:
    registry = ViewFactoryRegistry()
    registry.register("v1", lambda: object())
    registry.register("v2", lambda: object())
    registry.register("v3", lambda: object())
    return registry


def _router(offline_status) -> DesktopRouter:
    context = make_context(offline_status=offline_status, permissions=frozenset({"*"}))
    return DesktopRouter(
        route_registry=_routes_with_offline_policies(),
        view_factory_registry=_offline_view_factories(), initial_context=context,
    )


def test_online_context_allows_every_offline_policy():
    router = _router("ONLINE")
    for route_id in ("sales.pos", "reports.dashboard", "whatsapp.status"):
        result = router.navigate(route_id)
        assert result.degraded_offline is False


def test_offline_available_offline_route_succeeds_not_degraded():
    router = _router("OFFLINE")
    result = router.navigate("sales.pos")
    assert result.degraded_offline is False


def test_offline_degraded_route_succeeds_but_is_marked_degraded():
    router = _router("OFFLINE")
    result = router.navigate("reports.dashboard")
    assert result.degraded_offline is True


def test_offline_requires_online_route_is_denied():
    router = _router("OFFLINE")
    with pytest.raises(NavigationRequiresOnlineError):
        router.navigate("whatsapp.status")
