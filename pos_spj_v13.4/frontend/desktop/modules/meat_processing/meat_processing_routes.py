"""Single route registry for every internal Meat Processing page. Mirrors
frontend/desktop/modules/losses/losses_routes.py.
"""

from frontend.desktop.modules.meat_processing.navigation.meat_processing_sidebar import (
    MEAT_PROCESSING_NAV,
)


MEAT_PROCESSING_ROUTES = {entry.page_id: entry for entry in MEAT_PROCESSING_NAV}


def build_page(page_id: str, _presenter=None):
    try:
        entry = MEAT_PROCESSING_ROUTES[page_id]
    except KeyError as exc:
        raise KeyError(f"Unknown Meat Processing route: {page_id}") from exc
    from frontend.desktop.modules.meat_processing.pages import MeatProcessingPlaceholderPage
    return MeatProcessingPlaceholderPage(title=entry.title, subtitle=entry.tooltip)
