"""NavigationItemRegistry — SHELL-12.

Same discipline as `RouteRegistry`/`ModuleRegistry`: duplicate `item_id`
fails eagerly at `register()`. Cross-registry consistency (does `route_id`
resolve in `RouteRegistry`? does `module_id` resolve in `ModuleRegistry`?)
is `SidebarResolver`'s job at resolve time, not this registry's — an item
can be registered before its route or module exists, the same ordering
independence `RouteRegistry` already has from `ModuleRegistry`.

`all()` returns items pre-sorted by `(group, order, label)` — the order
`GlobalSidebar` renders them in, and the order groups end up contiguous so
`GlobalSidebar._render()` only has to notice when the group changes.
"""
from __future__ import annotations

from frontend.desktop.shell.sidebar.errors import (
    DuplicateNavigationItemRegistrationError,
    NavigationItemNotFoundError,
)
from frontend.desktop.shell.sidebar.navigation_item_definition import NavigationItemDefinition


class NavigationItemRegistry:
    def __init__(self) -> None:
        self._items: dict[str, NavigationItemDefinition] = {}

    def register(self, item: NavigationItemDefinition) -> None:
        if item.item_id in self._items:
            raise DuplicateNavigationItemRegistrationError(
                f"'{item.item_id}' ya está registrado — cada ítem de navegación se registra una sola vez."
            )
        self._items[item.item_id] = item

    def is_registered(self, item_id: str) -> bool:
        return item_id in self._items

    def get(self, item_id: str) -> NavigationItemDefinition | None:
        return self._items.get(item_id)

    def require(self, item_id: str) -> NavigationItemDefinition:
        item = self.get(item_id)
        if item is None:
            raise NavigationItemNotFoundError(f"Ningún ítem de navegación registrado con id '{item_id}'.")
        return item

    def all(self) -> tuple[NavigationItemDefinition, ...]:
        return tuple(sorted(self._items.values(), key=lambda i: (i.group, i.order, i.label)))

    def by_module_id(self, module_id: str) -> tuple[NavigationItemDefinition, ...]:
        return tuple(i for i in self.all() if i.module_id == module_id)

    def by_group(self, group: str) -> tuple[NavigationItemDefinition, ...]:
        return tuple(i for i in self.all() if i.group == group)

    def item_for_route(self, route_id: str) -> NavigationItemDefinition | None:
        for item in self._items.values():
            if item.route_id == route_id:
                return item
        return None
