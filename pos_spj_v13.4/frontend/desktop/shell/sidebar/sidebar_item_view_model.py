"""SidebarItemViewModel — SHELL-12.

What `GlobalSidebar` actually renders — resolved, presentation-ready state
`SidebarResolver` builds from a `NavigationItemDefinition` plus the current
`ApplicationContext`/route/badge counts. Holds no live reference back to
the registry or context it was built from, same as SHELL-10's
`NavigationResult`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SidebarItemViewModel:
    item_id: str
    route_id: str
    label: str
    icon: str
    group: str
    order: int
    badge_count: int | None
    is_active: bool
