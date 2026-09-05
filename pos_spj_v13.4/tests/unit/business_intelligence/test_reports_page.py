"""Data path (generate) is covered exhaustively by
`test_reports_presenter.py`; this file only covers page construction,
routing, and the export flow — with `QFileDialog.getSaveFileName`
monkeypatched so no real file dialog opens during tests.
"""

import sqlite3

import pytest
from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox

from frontend.desktop.modules.business_intelligence.business_intelligence_routes import build_page
from frontend.desktop.modules.business_intelligence.pages.reports_page import ReportsPage
from frontend.desktop.modules.business_intelligence.presenters.reports_presenter import (
    ReportsPresenter,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    yield connection
    connection.close()


def test_page_constructs_with_the_report_and_format_catalogs(qapp, conn):
    page = ReportsPage(ReportsPresenter(conn))
    assert page.report_selector.count() == 1
    assert page.report_selector.itemData(0) == "executive_summary"
    assert page.format_selector.count() == 3


def test_export_selected_cancelled_dialog_does_nothing(qapp, conn, monkeypatch):
    page = ReportsPage(ReportsPresenter(conn))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    calls = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: calls.append(a))
    page.export_selected()
    assert calls == []


def test_export_selected_writes_a_real_file(qapp, conn, monkeypatch, tmp_path):
    page = ReportsPage(ReportsPresenter(conn))
    target = str(tmp_path / "reporte.csv")
    page.format_selector.setCurrentIndex(2)  # csv
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (target, ""))
    calls = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: calls.append(a))
    page.export_selected()
    assert len(calls) == 1
    import os
    assert os.path.exists(target)


def test_build_page_with_connection_returns_real_reports_page(qapp, conn):
    page = build_page("bi_reports", conn)
    assert isinstance(page, ReportsPage)
