"""Data path (evaluate_all/apply_transition) is covered exhaustively by
`test_alert_explorer_presenter.py`; this file only covers page construction,
routing, table rendering, and the selection/lifecycle button callbacks —
all against a bare (schemaless) in-memory connection, safe to fully
`refresh()` since this page has no `HtmlChartView`.
"""

import sqlite3

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from frontend.desktop.modules.business_intelligence.business_intelligence_routes import build_page
from frontend.desktop.modules.business_intelligence.pages.alert_explorer_page import (
    AlertExplorerPage,
)
from frontend.desktop.modules.business_intelligence.presenters.alert_explorer_presenter import (
    AlertExplorerPresenter,
)
from backend.shared.ids import new_uuid


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    yield connection
    connection.close()


def test_page_constructs_with_an_empty_table(qapp, conn):
    page = AlertExplorerPage(AlertExplorerPresenter(conn))
    assert page._alerts_by_id == {}
    assert page.table.rowCount() == 0


def test_refresh_lists_the_real_margin_drop_breach_against_a_bare_connection(qapp, conn):
    page = AlertExplorerPage(AlertExplorerPresenter(conn))
    page.refresh()
    assert page.table.rowCount() == 1
    assert len(page._alerts_by_id) == 1


def test_apply_transition_without_a_selected_row_shows_a_message_not_a_crash(qapp, conn, monkeypatch):
    page = AlertExplorerPage(AlertExplorerPresenter(conn))
    page.refresh()
    calls = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: calls.append(a))
    page._apply_transition("acknowledge")
    assert len(calls) == 1


def test_apply_transition_updates_the_table_after_a_real_lifecycle_action(qapp, conn):
    page = AlertExplorerPage(AlertExplorerPresenter(conn, actor_user_id=new_uuid()))
    page.refresh()
    alert_id = next(iter(page._alerts_by_id))
    page.table.selectRow(0)
    page._apply_transition("acknowledge")
    assert page._alerts_by_id[alert_id].status.value == "ACKNOWLEDGED"


def test_build_page_with_connection_returns_real_alert_explorer(qapp, conn):
    page = build_page("bi_alerts", conn)
    assert isinstance(page, AlertExplorerPage)
