"""Real Qt widget instantiation under the offscreen platform (already
defaulted for the whole suite in `tests/conftest.py`)."""

import pytest
from PyQt5.QtWidgets import QApplication

from frontend.desktop.modules.business_intelligence.navigation.business_intelligence_sidebar import (
    BUSINESS_INTELLIGENCE_NAV,
)
from frontend.desktop.modules.business_intelligence.widgets import (
    BusinessIntelligenceSidebarWidget,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_sidebar_lists_only_permitted_entries(qapp):
    widget = BusinessIntelligenceSidebarWidget(has_permission=lambda perm: True)
    assert widget.count() == len(BUSINESS_INTELLIGENCE_NAV)


def test_sidebar_selecting_first_row_by_default(qapp):
    widget = BusinessIntelligenceSidebarWidget(has_permission=lambda perm: True)
    assert widget.currentRow() == 0


def test_sidebar_emits_route_requested_on_selection_change(qapp):
    widget = BusinessIntelligenceSidebarWidget(has_permission=lambda perm: True)
    emitted = []
    widget.route_requested.connect(emitted.append)
    widget.setCurrentRow(1)
    assert emitted == [BUSINESS_INTELLIGENCE_NAV[1].page_id]


def test_sidebar_collapse_shows_only_first_letter(qapp):
    widget = BusinessIntelligenceSidebarWidget(has_permission=lambda perm: True)
    widget.set_collapsed(True)
    assert widget.collapsed is True
    assert widget.item(0).text() == BUSINESS_INTELLIGENCE_NAV[0].title[:1]
    widget.set_collapsed(False)
    assert widget.item(0).text() == BUSINESS_INTELLIGENCE_NAV[0].title


def test_sidebar_respects_permission_filtering(qapp):
    only_executive = {BUSINESS_INTELLIGENCE_NAV[0].permission}
    widget = BusinessIntelligenceSidebarWidget(has_permission=lambda perm: perm in only_executive)
    assert widget.count() == 1
