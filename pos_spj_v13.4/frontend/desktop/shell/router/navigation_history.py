"""NavigationHistory — SHELL-10.

Two-stack back/forward history, same shape as a browser: `push()` on every
*new* navigation (clears the forward stack — you can't redo past a branch
point), `peek_back()`/`peek_forward()` to inspect the target without
committing, `commit_back()`/`commit_forward()` to move the pointer once
`DesktopRouter` has confirmed the target route is still resolvable and
allowed under the current context. The peek/commit split exists so a denied
`go_back()` (permission revoked since the visit, route deleted, etc.)
leaves the history exactly where it was rather than landing on a route it
then refuses to show.
"""
from __future__ import annotations

from frontend.desktop.shell.router.errors import NoNavigationHistoryError


class NavigationHistory:
    def __init__(self) -> None:
        self._back_stack: list[str] = []
        self._forward_stack: list[str] = []
        self._current: str | None = None

    def current(self) -> str | None:
        return self._current

    def push(self, route_id: str) -> None:
        if self._current is not None and self._current != route_id:
            self._back_stack.append(self._current)
        self._current = route_id
        self._forward_stack.clear()

    def can_go_back(self) -> bool:
        return bool(self._back_stack)

    def can_go_forward(self) -> bool:
        return bool(self._forward_stack)

    def peek_back(self) -> str:
        if not self._back_stack:
            raise NoNavigationHistoryError("No hay historial hacia atrás.")
        return self._back_stack[-1]

    def peek_forward(self) -> str:
        if not self._forward_stack:
            raise NoNavigationHistoryError("No hay historial hacia adelante.")
        return self._forward_stack[-1]

    def commit_back(self) -> str:
        route_id = self.peek_back()
        self._back_stack.pop()
        if self._current is not None:
            self._forward_stack.append(self._current)
        self._current = route_id
        return route_id

    def commit_forward(self) -> str:
        route_id = self.peek_forward()
        self._forward_stack.pop()
        if self._current is not None:
            self._back_stack.append(self._current)
        self._current = route_id
        return route_id

    def clear(self) -> None:
        self._back_stack.clear()
        self._forward_stack.clear()
        self._current = None
