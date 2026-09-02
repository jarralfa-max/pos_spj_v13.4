import pytest

from frontend.desktop.shell.router.desktop_router import DesktopRouter
from frontend.desktop.shell.router.errors import (
    NavigationFeatureDisabledError,
    NavigationPermissionDeniedError,
)
from frontend.desktop.shell.routing.errors import RouteNotFoundError
from tests.unit.shell.router.conftest import make_context


def _router(routes, view_factories, context) -> DesktopRouter:
    return DesktopRouter(route_registry=routes, view_factory_registry=view_factories, initial_context=context)


def test_navigate_to_allowed_route_returns_view(routes, view_factories, context):
    router = _router(routes, view_factories, context)
    result = router.navigate("sales.pos")
    assert result.route.route_id == "sales.pos"
    assert result.view == {"widget": "pos"}
    assert result.context is context
    assert result.degraded_offline is False


def test_navigate_updates_current_route_id(routes, view_factories, context):
    router = _router(routes, view_factories, context)
    router.navigate("sales.pos")
    assert router.current_route_id == "sales.pos"


def test_navigate_unknown_route_raises(routes, view_factories, context):
    router = _router(routes, view_factories, context)
    with pytest.raises(RouteNotFoundError):
        router.navigate("does.not_exist")


def test_navigate_without_required_permission_is_denied(routes, view_factories):
    context = make_context(permissions=frozenset())
    router = _router(routes, view_factories, context)
    with pytest.raises(NavigationPermissionDeniedError):
        router.navigate("sales.pos")


def test_navigate_without_required_permission_does_not_advance_history(routes, view_factories):
    context = make_context(permissions=frozenset())
    router = _router(routes, view_factories, context)
    with pytest.raises(NavigationPermissionDeniedError):
        router.navigate("sales.pos")
    assert router.current_route_id is None


def test_admin_bypasses_permission_check(routes, view_factories):
    context = make_context(permissions=frozenset(), roles=("admin",))
    router = _router(routes, view_factories, context)
    result = router.navigate("sales.pos")
    assert result.route.route_id == "sales.pos"


def test_navigate_with_module_wildcard_permission_is_allowed(routes, view_factories):
    context = make_context(permissions=frozenset({"SALES.*"}))
    router = _router(routes, view_factories, context)
    result = router.navigate("sales.pos")
    assert result.route.route_id == "sales.pos"


def test_navigate_to_disabled_feature_flag_is_denied(routes, view_factories, context):
    router = _router(routes, view_factories, context)
    with pytest.raises(NavigationFeatureDisabledError):
        router.navigate("whatsapp.status")


def test_navigate_to_enabled_feature_flag_succeeds(routes, view_factories):
    from backend.bootstrap.application_context import FeatureContext

    context = make_context(feature_context=FeatureContext(enabled_features=frozenset({"whatsapp_module"})))
    router = _router(routes, view_factories, context)
    result = router.navigate("whatsapp.status")
    assert result.route.route_id == "whatsapp.status"


def test_route_without_required_permission_or_flag_is_always_reachable(routes, view_factories):
    context = make_context(permissions=frozenset())
    router = DesktopRouter(
        route_registry=routes, view_factory_registry=view_factories,
        initial_context=context,
    )
    from backend.bootstrap.application_context import FeatureContext
    router.update_context(make_context(
        permissions=frozenset(), feature_context=FeatureContext(enabled_features=frozenset({"whatsapp_module"})),
    ))
    result = router.navigate("whatsapp.status")
    assert result.route.route_id == "whatsapp.status"


def test_each_navigate_call_creates_a_fresh_view(routes, view_factories, context):
    router = _router(routes, view_factories, context)
    first = router.navigate("sales.pos")
    second = router.navigate("sales.pos")
    assert first.view is not second.view
