"""Single route registry for every internal Losses page."""

from frontend.desktop.modules.losses.navigation.losses_sidebar import LOSSES_NAV


LOSSES_ROUTES = {entry.page_id: entry for entry in LOSSES_NAV}


def build_page(page_id: str, _presenter=None):
    try:
        entry = LOSSES_ROUTES[page_id]
    except KeyError as exc:
        raise KeyError(f"Unknown Losses route: {page_id}") from exc
    from frontend.desktop.modules.losses.pages import LossesPlaceholderPage
    return LossesPlaceholderPage(title=entry.title, subtitle=entry.tooltip)
