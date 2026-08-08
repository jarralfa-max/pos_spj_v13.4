"""FASE 6 (UI/UX enterprise) — RRHH reused SideNav and the shared WorklistPage
scaffold instead of a hand-rolled QListWidget/QMessageBox pattern. No UI test
existed for this module before; this is the regression net for that migration
(every page must load — even on an empty database — without crashing)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)

from PyQt5.QtWidgets import QApplication  # noqa: E402

from frontend.desktop.components.side_nav import SideNav  # noqa: E402
from frontend.desktop.modules.hr.hr_routes import build_hr_presenter  # noqa: E402
from frontend.desktop.modules.hr.hr_view import HRView  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_hr_view_uses_side_nav_not_raw_list_widget(app, hr_conn):
    presenter = build_hr_presenter(hr_conn)
    view = HRView(presenter)
    assert isinstance(view._nav, SideNav)


def test_every_hr_page_loads_without_crashing_on_empty_db(app, hr_conn):
    presenter = build_hr_presenter(hr_conn)
    view = HRView(presenter)
    assert view._nav.count() > 0
    for row in range(view._nav.count()):
        item = view._nav.item(row)
        if item is None or row not in view._row_to_page_index:
            continue  # non-selectable group heading
        view._nav.setCurrentRow(row)
        page = view._pages[view._row_to_page_index[row]]
        loaded = getattr(page, "_loaded", None)
        if loaded is None:
            continue
        notice = getattr(page, "_notice", None)
        assert loaded, (f"page at row {row} ({item.text()}) never finished loading: "
                        f"{notice.text() if notice else '(no notice widget)'}")
