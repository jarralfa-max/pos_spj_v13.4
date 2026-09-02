"""ContentHost — SHELL-11.

The consumer SHELL-10's `DesktopRouter` docstring names but explicitly
leaves unbuilt: the place that actually enforces `RouteDefinition.cache_policy`
(SHELL-9 §53). `DesktopRouter.navigate()` always hands back a freshly
constructed view — deciding whether to actually mount it or reuse a widget
already built for that route is this class's job.

Caching rules, by `CachePolicy`:
- `RECREATE_ON_NAVIGATION` (default): the fresh view is always shown; the
  previously shown (non-cached) widget for that route, if any, is removed
  and `deleteLater()`'d so repeat navigation to the same route doesn't leak
  widget instances into the stack.
- `KEEP_ALIVE`: the first view built for a route is cached and reused on
  every later navigation to it; later fresh views for that route are
  discarded instead of mounted.
- `RECREATE_ON_CONTEXT_CHANGE`: behaves like `KEEP_ALIVE` across ordinary
  navigation, but its cache entry is evicted by `on_context_changed()` —
  the next navigation to that route then caches (and shows) a fresh view.
- `SINGLETON`: like `KEEP_ALIVE`, but immune to `on_context_changed()` too
  — once built, never recreated for the life of this host.

A discarded widget is `deleteLater()`'d only if it's a real `QWidget` —
`ViewFactoryRegistry` (SHELL-9) deliberately stays PyQt-free, so a factory
can still hand back a plain object in tests; nothing here assumes
otherwise. If the "fresh" view handed to a sticky-cache hit happens to be
the exact same object already cached (a factory that returns a singleton
itself), it is never discarded — that would delete the widget currently on
screen.

SHELL-13 adds two things:
- `result.load_failed` (an error view built after `ModuleLoader.ensure_loaded()`
  failed) is always shown transiently, regardless of `cache_policy` — an
  error placeholder is never written into the sticky cache, so the next
  successful navigation to that route caches the real view as if the
  failed attempt never happened.
- `preload()`: builds a route's sticky cache entry ahead of time, without
  displaying it — for `EAGER`/`BACKGROUND_PRELOAD` modules, so their first
  real navigation is instant instead of paying for view construction then.
"""
from __future__ import annotations

from PyQt5.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from frontend.desktop.shell.router.navigation_result import NavigationResult
from frontend.desktop.shell.routing.cache_policy import CachePolicy

_STICKY_POLICIES = (CachePolicy.KEEP_ALIVE, CachePolicy.RECREATE_ON_CONTEXT_CHANGE, CachePolicy.SINGLETON)


class ContentHost(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("contentHost")
        self._stack = QStackedWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        self._cache: dict[str, object] = {}
        self._policy_by_route: dict[str, CachePolicy] = {}
        self._transient_widget: object | None = None
        self._current_route_id: str | None = None

    @property
    def current_route_id(self) -> str | None:
        return self._current_route_id

    def display(self, result: NavigationResult) -> None:
        route = result.route
        policy = route.cache_policy
        self._policy_by_route[route.route_id] = policy

        if result.load_failed:
            self._evict_transient()
            widget = result.view
            if isinstance(widget, QWidget):
                self._transient_widget = widget
            self._mount(widget)
            self._current_route_id = route.route_id
            return

        if policy in _STICKY_POLICIES:
            widget = self._cache.get(route.route_id)
            if widget is None:
                widget = result.view
                self._cache[route.route_id] = widget
            elif widget is not result.view:
                self._discard(result.view)
        else:
            self._evict_transient()
            widget = result.view
            if isinstance(widget, QWidget):
                self._transient_widget = widget

        self._mount(widget)
        self._current_route_id = route.route_id

    def preload(self, result: NavigationResult) -> None:
        route = result.route
        policy = route.cache_policy
        self._policy_by_route[route.route_id] = policy

        if policy not in _STICKY_POLICIES or route.route_id in self._cache:
            self._discard(result.view)
            return

        widget = result.view
        self._cache[route.route_id] = widget
        if isinstance(widget, QWidget) and self._stack.indexOf(widget) == -1:
            self._stack.addWidget(widget)

    def on_context_changed(self) -> None:
        stale_route_ids = [
            route_id for route_id, policy in self._policy_by_route.items()
            if policy is CachePolicy.RECREATE_ON_CONTEXT_CHANGE
        ]
        for route_id in stale_route_ids:
            self._evict_cached(route_id)

    def clear(self) -> None:
        for route_id in list(self._cache.keys()):
            self._evict_cached(route_id)
        self._evict_transient()
        self._policy_by_route.clear()
        self._current_route_id = None

    def _mount(self, widget: object) -> None:
        if not isinstance(widget, QWidget):
            return
        if self._stack.indexOf(widget) == -1:
            self._stack.addWidget(widget)
        self._stack.setCurrentWidget(widget)

    def _evict_cached(self, route_id: str) -> None:
        widget = self._cache.pop(route_id, None)
        if widget is None:
            return
        if isinstance(widget, QWidget):
            self._stack.removeWidget(widget)
        self._discard(widget)

    def _evict_transient(self) -> None:
        widget = self._transient_widget
        self._transient_widget = None
        if widget is None:
            return
        self._stack.removeWidget(widget)
        self._discard(widget)

    @staticmethod
    def _discard(widget: object) -> None:
        deleter = getattr(widget, "deleteLater", None)
        if callable(deleter):
            deleter()
