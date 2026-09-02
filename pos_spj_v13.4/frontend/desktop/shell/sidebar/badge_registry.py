"""BadgeRegistry — SHELL-12.

Sidebar items can declare a `badge_key` (`NavigationItemDefinition`) but
there's no shell-wide badge/count service to source real numbers from yet
— same "declare the shape, wire the backend later" deferral SHELL-11's
`NotificationDrawer` and SHELL-8's empty `view_factories` use. A
`BadgeSource` is any zero-argument callable returning the current count;
real ones (e.g. "unread low-stock alerts") get registered once such a
service exists.

Unlike `NavigationItemRegistry`/`RouteRegistry`, re-registering a
`badge_key` is allowed (last write wins) rather than raising — a badge
source is a live counter that may legitimately be swapped (a stub replaced
by the real service later at runtime), not a catalog entry declared once.

An unregistered `badge_key` resolves to `None` — no badge shown — not
`0`, which would misleadingly claim a real, checked count of zero.
"""
from __future__ import annotations

from typing import Callable

BadgeSource = Callable[[], int]


class BadgeRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, BadgeSource] = {}

    def register(self, badge_key: str, source: BadgeSource) -> None:
        self._sources[badge_key] = source

    def is_registered(self, badge_key: str) -> bool:
        return badge_key in self._sources

    def count_for(self, badge_key: str) -> int | None:
        if not badge_key:
            return None
        source = self._sources.get(badge_key)
        if source is None:
            return None
        return source()
