import pytest

from frontend.desktop.shell.router.desktop_router import DesktopRouter
from frontend.desktop.shell.router.errors import NoNavigationHistoryError
from tests.unit.shell.router.conftest import make_context


def _router(routes, view_factories) -> DesktopRouter:
    context = make_context(permissions=frozenset({"*"}))
    return DesktopRouter(route_registry=routes, view_factory_registry=view_factories, initial_context=context)


def test_go_back_without_history_raises(routes, view_factories):
    router = _router(routes, view_factories)
    with pytest.raises(NoNavigationHistoryError):
        router.go_back()


def test_go_forward_without_history_raises(routes, view_factories):
    router = _router(routes, view_factories)
    with pytest.raises(NoNavigationHistoryError):
        router.go_forward()


def test_go_back_returns_to_previous_route(routes, view_factories):
    router = _router(routes, view_factories)
    router.navigate("sales.pos")
    router.navigate("inventory.overview")
    result = router.go_back()
    assert result.route.route_id == "sales.pos"
    assert router.current_route_id == "sales.pos"


def test_go_forward_after_go_back_returns_to_where_it_was(routes, view_factories):
    router = _router(routes, view_factories)
    router.navigate("sales.pos")
    router.navigate("inventory.overview")
    router.go_back()
    result = router.go_forward()
    assert result.route.route_id == "inventory.overview"


def test_can_go_back_and_forward_reflect_state(routes, view_factories):
    router = _router(routes, view_factories)
    assert router.can_go_back() is False
    router.navigate("sales.pos")
    router.navigate("inventory.overview")
    assert router.can_go_back() is True
    assert router.can_go_forward() is False
    router.go_back()
    assert router.can_go_forward() is True


def test_navigating_to_a_new_route_after_back_clears_forward(routes, view_factories):
    router = _router(routes, view_factories)
    router.navigate("sales.pos")
    router.navigate("inventory.overview")
    router.go_back()
    router.navigate("sales.pos")
    assert router.can_go_forward() is False
