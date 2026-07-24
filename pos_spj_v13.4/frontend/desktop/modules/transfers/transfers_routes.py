"""Canonical route registry for the Transfers internal sidebar.

The registry is the single page factory used by the internal sidebar.
"""
from __future__ import annotations

from .navigation.transfers_sidebar import TRANSFERS_NAV


TRANSFERS_ROUTE_IDS = frozenset(entry.page_id for entry in TRANSFERS_NAV)


def build_page(page_id: str, presenter):
    """Build one canonical page; unknown or parallel route IDs are rejected."""
    if page_id not in TRANSFERS_ROUTE_IDS:
        raise KeyError(f"Unknown Transfers route: {page_id}")
    from .pages import OverviewPage, PAGE_CLASSES
    if page_id == "transfers_overview":
        page_class = OverviewPage
    elif page_id == "transfers_analytics":
        from .pages.analytics_page import AnalyticsPage
        page_class = AnalyticsPage
    else:
        page_class = PAGE_CLASSES[page_id]
    return page_class(presenter)
