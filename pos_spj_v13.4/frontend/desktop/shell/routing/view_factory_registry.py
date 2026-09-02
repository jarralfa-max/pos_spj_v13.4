"""ViewFactoryRegistry — SHELL-9 §47.

Maps `view_factory_id` → a zero-argument callable that constructs the
route's view. Deliberately PyQt-free: a factory's `create()` returns a
`QWidget` in real usage (§47's example), but this registry only stores and
invokes callables generically — it never imports PyQt5 itself, so it stays
testable without a `QApplication` and reusable regardless of what UI
toolkit eventually backs a given route.
"""
from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable

from frontend.desktop.shell.routing.errors import (
    DuplicateViewFactoryRegistrationError,
    ViewFactoryNotFoundError,
)


@runtime_checkable
class ViewFactory(Protocol):
    def create(self) -> object: ...


class ViewFactoryRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], object]] = {}

    def register(self, view_factory_id: str, factory: Callable[[], object]) -> None:
        if view_factory_id in self._factories:
            raise DuplicateViewFactoryRegistrationError(
                f"'{view_factory_id}' ya está registrado — cada view factory se registra una sola vez."
            )
        self._factories[view_factory_id] = factory

    def is_registered(self, view_factory_id: str) -> bool:
        return view_factory_id in self._factories

    def get(self, view_factory_id: str) -> Callable[[], object] | None:
        return self._factories.get(view_factory_id)

    def require(self, view_factory_id: str) -> Callable[[], object]:
        factory = self.get(view_factory_id)
        if factory is None:
            raise ViewFactoryNotFoundError(f"Ninguna view factory registrada con id '{view_factory_id}'.")
        return factory

    def create_view(self, view_factory_id: str) -> object:
        return self.require(view_factory_id)()

    def all_ids(self) -> tuple[str, ...]:
        return tuple(self._factories.keys())
