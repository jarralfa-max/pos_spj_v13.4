"""GlobalSidebar errors — SHELL-12."""
from __future__ import annotations


class DuplicateNavigationItemRegistrationError(ValueError):
    """An `item_id` was registered twice — caught eagerly at `register()`,
    same discipline as `RouteRegistry`/`ModuleRegistry`."""


class NavigationItemNotFoundError(KeyError):
    """`NavigationItemRegistry.require()` referenced an unregistered
    `item_id`."""
