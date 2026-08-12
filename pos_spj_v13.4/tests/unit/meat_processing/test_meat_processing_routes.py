import pytest

from frontend.desktop.modules.meat_processing.meat_processing_routes import (
    MEAT_PROCESSING_ROUTES,
    build_page,
)
from frontend.desktop.modules.meat_processing.navigation.meat_processing_sidebar import (
    MEAT_PROCESSING_NAV,
)


def test_every_nav_entry_has_a_route():
    assert set(MEAT_PROCESSING_ROUTES) == {entry.page_id for entry in MEAT_PROCESSING_NAV}


def test_unknown_route_raises_key_error():
    with pytest.raises(KeyError):
        build_page("not_a_real_route")
