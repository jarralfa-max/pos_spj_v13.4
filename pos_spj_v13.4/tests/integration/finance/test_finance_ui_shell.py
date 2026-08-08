"""FASE 6 (UI/UX enterprise) — the finance module reused SideNav and the
shared WorklistPage scaffold instead of a hand-rolled QListWidget/QMessageBox
pattern. No UI test existed for this module before; this is the regression
net for that migration (every page must load — even on an empty database —
without crashing, exercising the ViewState EMPTY path they never had)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)

from PyQt5.QtWidgets import QApplication  # noqa: E402

from frontend.desktop.components.side_nav import SideNav  # noqa: E402
from frontend.desktop.modules.finance.finance_routes import (  # noqa: E402
    build_finance_presenter,
)
from frontend.desktop.modules.finance.finance_view import FinanceView  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_finance_view_uses_side_nav_not_raw_list_widget(app, finance_conn):
    presenter = build_finance_presenter(finance_conn)
    view = FinanceView(presenter)
    assert isinstance(view._nav, SideNav)


def test_every_finance_page_loads_without_crashing_on_empty_db(app, finance_conn):
    presenter = build_finance_presenter(finance_conn)
    view = FinanceView(presenter)
    assert view._nav.count() > 0
    for row in range(view._nav.count()):
        item = view._nav.item(row)
        if item is None or row not in view._row_to_page_index:
            continue  # non-selectable group heading
        view._nav.setCurrentRow(row)
        page = view._pages[view._row_to_page_index[row]]
        loaded = getattr(page, "_loaded", None)
        if loaded is None:
            continue  # e.g. SuppliersPage wraps its own sub-view, no _loaded of its own
        notice = getattr(page, "_notice", None)
        assert loaded, (f"page at row {row} ({item.text()}) never finished loading: "
                        f"{notice.text() if notice else '(no notice widget)'}")
