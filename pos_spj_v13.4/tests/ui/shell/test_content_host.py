from PyQt5.QtWidgets import QApplication, QLabel, QWidget

from frontend.desktop.shell.application_shell.content_host import ContentHost
from frontend.desktop.shell.router.navigation_result import NavigationResult
from frontend.desktop.shell.routing.cache_policy import CachePolicy
from frontend.desktop.shell.routing.route_definition import RouteDefinition
from tests.ui.shell.conftest import make_context


def _route(route_id="sales.pos", **overrides) -> RouteDefinition:
    kwargs = dict(module_id="sales", title=route_id, view_factory_id=f"{route_id}_view")
    kwargs.update(overrides)
    return RouteDefinition(route_id=route_id, **kwargs)


def _result(route, view) -> NavigationResult:
    return NavigationResult(route=route, view=view, context=make_context())


def test_display_mounts_the_view_as_current_widget():
    host = ContentHost()
    view = QLabel("hello")
    host.display(_result(_route(), view))
    assert host._stack.currentWidget() is view
    assert host.current_route_id == "sales.pos"


def test_recreate_on_navigation_replaces_widget_and_discards_old_one():
    host = ContentHost()
    route = _route(cache_policy=CachePolicy.RECREATE_ON_NAVIGATION)
    first = QLabel("first")
    second = QLabel("second")
    host.display(_result(route, first))
    host.display(_result(route, second))
    assert host._stack.currentWidget() is second
    assert host._stack.indexOf(first) == -1


def test_keep_alive_reuses_first_widget_on_later_navigation():
    host = ContentHost()
    route = _route(cache_policy=CachePolicy.KEEP_ALIVE)
    first = QLabel("first")
    second = QLabel("second")
    host.display(_result(route, first))
    host.display(_result(_route(cache_policy=CachePolicy.KEEP_ALIVE, view_factory_id="other"), QLabel("x")))
    host.display(_result(route, second))
    assert host._stack.currentWidget() is first
    assert host._stack.indexOf(second) == -1


def test_singleton_reuses_first_widget_forever():
    host = ContentHost()
    route = _route(cache_policy=CachePolicy.SINGLETON)
    first = QLabel("first")
    host.display(_result(route, first))
    host.display(_result(route, QLabel("ignored")))
    host.on_context_changed()
    host.display(_result(route, QLabel("still ignored")))
    assert host._stack.currentWidget() is first


def test_recreate_on_context_change_survives_ordinary_navigation():
    host = ContentHost()
    route = _route(cache_policy=CachePolicy.RECREATE_ON_CONTEXT_CHANGE)
    other = _route(cache_policy=CachePolicy.KEEP_ALIVE, view_factory_id="other")
    first = QLabel("first")
    host.display(_result(route, first))
    host.display(_result(other, QLabel("other")))
    host.display(_result(route, QLabel("ignored")))
    assert host._stack.currentWidget() is first


def test_recreate_on_context_change_is_evicted_by_on_context_changed():
    host = ContentHost()
    route = _route(cache_policy=CachePolicy.RECREATE_ON_CONTEXT_CHANGE)
    first = QLabel("first")
    second = QLabel("second")
    host.display(_result(route, first))
    host.on_context_changed()
    host.display(_result(route, second))
    assert host._stack.currentWidget() is second
    assert host._stack.indexOf(first) == -1


def test_on_context_changed_does_not_touch_keep_alive_routes():
    host = ContentHost()
    route = _route(cache_policy=CachePolicy.KEEP_ALIVE)
    first = QLabel("first")
    host.display(_result(route, first))
    host.on_context_changed()
    host.display(_result(route, QLabel("ignored")))
    assert host._stack.currentWidget() is first


def test_clear_empties_cache_and_current_route():
    host = ContentHost()
    route = _route(cache_policy=CachePolicy.KEEP_ALIVE)
    host.display(_result(route, QLabel("first")))
    host.clear()
    assert host.current_route_id is None
    assert host._stack.count() == 0


def test_non_qwidget_view_does_not_raise_and_still_tracks_route_id():
    host = ContentHost()
    route = _route()
    host.display(_result(route, {"not": "a widget"}))
    assert host.current_route_id == "sales.pos"
    assert host._stack.count() == 0


def test_repeated_navigation_to_recreate_on_navigation_route_does_not_leak_stack_entries():
    host = ContentHost()
    route = _route(cache_policy=CachePolicy.RECREATE_ON_NAVIGATION)
    for i in range(5):
        host.display(_result(route, QLabel(f"view-{i}")))
    assert host._stack.count() == 1


def test_cached_oversized_page_does_not_force_overflow_on_the_next_page():
    host = ContentHost()
    host.resize(640, 480)
    large = QWidget()
    large.setMinimumSize(1600, 1200)
    host.display(_result(_route("large", cache_policy=CachePolicy.KEEP_ALIVE), large))
    host.show()
    for _ in range(4):
        QApplication.processEvents()
    assert host.page_viewport.horizontalScrollBar().maximum() > 0
    assert host.page_viewport.verticalScrollBar().maximum() > 0
    host.display(_result(_route("small"), QLabel("Vista pequeña")))
    for _ in range(4):
        QApplication.processEvents()
    assert host.page_viewport.horizontalScrollBar().maximum() == 0
    assert host.page_viewport.verticalScrollBar().maximum() == 0
    host.close()


def test_page_with_own_scroll_and_wrapped_header_does_not_add_outer_scroll():
    from frontend.desktop.components.pages import FormPage
    from frontend.desktop.components.text_inputs import StandardLineEdit

    page = FormPage(title="Formulario", subtitle="Datos de la operación")
    for _ in range(20):
        page.add_content(StandardLineEdit(keyboard_enabled=False))
    host = ContentHost()
    host.display(_result(_route("form"), page))
    host.resize(1000, 500)
    host.show()
    for _ in range(4):
        QApplication.processEvents()
    assert page.viewport.verticalScrollBar().maximum() > 0
    assert host.page_viewport.verticalScrollBar().maximum() == 0
    host.close()
