"""Sidebar search filtering — SHELL-12.

Implements CLAUDE.md rule #20 ("Donde se seleccione producto, cliente,
proveedor, ... debe usarse barra de búsqueda/autocomplete, no listas
largas") for the module list itself: a plain case-insensitive substring
match against each resolved item's `label` and `group` (so typing a
category name like "Ventas" surfaces everything filed under it). No fuzzy
matching or accent folding — a reasonable minimal reading, not a spec
requirement, easy to extend once real usage shows it's needed.
"""
from __future__ import annotations

from frontend.desktop.shell.sidebar.sidebar_item_view_model import SidebarItemViewModel


def filter_sidebar_items(
    items: tuple[SidebarItemViewModel, ...], query: str,
) -> tuple[SidebarItemViewModel, ...]:
    normalized = (query or "").strip().lower()
    if not normalized:
        return items
    return tuple(
        item for item in items
        if normalized in item.label.lower() or normalized in item.group.lower()
    )
