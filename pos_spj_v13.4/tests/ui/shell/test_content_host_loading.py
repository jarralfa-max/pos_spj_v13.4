"""ContentHost's SHELL-13 additions: `load_failed` handling and `preload()`.

Additive to SHELL-11's `test_content_host.py`, which must keep passing
unmodified — these tests only cover the new behavior.
"""
from PyQt5.QtWidgets import QLabel

from frontend.desktop.shell.application_shell.content_host import ContentHost
from frontend.desktop.shell.router.navigation_result import NavigationResult
from frontend.desktop.shell.routing.cache_policy import CachePolicy
from frontend.desktop.shell.routing.route_definition import RouteDefinition
from tests.ui.shell.conftest import make_context


def _route(route_id="sales.pos", **overrides) -> RouteDefinition:
    kwargs = dict(module_id="sales", title=route_id, view_factory_id=f"{route_id}_view")
    kwargs.update(overrides)
    return RouteDefinition(route_id=route_id, **kwargs)


def _result(route, view, *, load_failed=False) -> NavigationResult:
    return NavigationResult(route=route, view=view, context=make_context(), load_failed=load_failed)


def test_load_failed_view_is_shown():
    host = ContentHost()
    route = _route(cache_policy=CachePolicy.KEEP_ALIVE)
    error_view = QLabel("error")
    host.display(_result(route, error_view, load_failed=True))
    assert host._stack.currentWidget() is error_view
    assert host.current_route_id == "sales.pos"


def test_load_failed_view_is_not_cached():
    host = ContentHost()
    route = _route(cache_policy=CachePolicy.KEEP_ALIVE)
    host.display(_result(route, QLabel("error"), load_failed=True))
    assert route.route_id not in host._cache


def test_load_failed_does_not_evict_a_previously_cached_good_view():
    host = ContentHost()
    route = _route(cache_policy=CachePolicy.KEEP_ALIVE)
    good_view = QLabel("good")
    host.display(_result(route, good_view))
    host.display(_result(route, QLabel("error"), load_failed=True))
    assert host._cache[route.route_id] is good_view


def test_after_load_failed_a_successful_retry_caches_normally():
    host = ContentHost()
    route = _route(cache_policy=CachePolicy.KEEP_ALIVE)
    host.display(_result(route, QLabel("error"), load_failed=True))
    good_view = QLabel("good")
    host.display(_result(route, good_view))
    assert host._cache[route.route_id] is good_view
    assert host._stack.currentWidget() is good_view


def test_repeated_load_failures_do_not_leak_error_widgets():
    host = ContentHost()
    route = _route(cache_policy=CachePolicy.RECREATE_ON_NAVIGATION)
    for i in range(3):
        host.display(_result(route, QLabel(f"error-{i}"), load_failed=True))
    assert host._stack.count() == 1


def test_preload_caches_without_changing_current_route():
    host = ContentHost()
    route = _route(cache_policy=CachePolicy.KEEP_ALIVE)
    view = QLabel("preloaded")
    host.preload(_result(route, view))
    assert host.current_route_id is None
    assert host._stack.indexOf(view) != -1


def test_preloading_a_second_route_does_not_steal_focus_from_a_displayed_one():
    host = ContentHost()
    shown_route = _route("sales.pos", cache_policy=CachePolicy.KEEP_ALIVE)
    shown_view = QLabel("shown")
    host.display(_result(shown_route, shown_view))

    preload_route = _route("inventory.overview", cache_policy=CachePolicy.KEEP_ALIVE)
    host.preload(_result(preload_route, QLabel("preloaded")))

    assert host.current_route_id == "sales.pos"
    assert host._stack.currentWidget() is shown_view


def test_display_after_preload_reuses_the_preloaded_widget():
    host = ContentHost()
    route = _route(cache_policy=CachePolicy.KEEP_ALIVE)
    preloaded = QLabel("preloaded")
    host.preload(_result(route, preloaded))
    host.display(_result(route, QLabel("fresh-and-unused")))
    assert host._stack.currentWidget() is preloaded


def test_preload_of_non_sticky_policy_discards_the_view():
    host = ContentHost()
    route = _route(cache_policy=CachePolicy.RECREATE_ON_NAVIGATION)
    view = QLabel("throwaway")
    host.preload(_result(route, view))
    assert route.route_id not in host._cache
    assert host._stack.indexOf(view) == -1


def test_preloading_an_already_cached_route_is_a_no_op():
    host = ContentHost()
    route = _route(cache_policy=CachePolicy.KEEP_ALIVE)
    first = QLabel("first")
    host.preload(_result(route, first))
    host.preload(_result(route, QLabel("second")))
    assert host._cache[route.route_id] is first
