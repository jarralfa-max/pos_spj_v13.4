import os
import sqlite3

import pytest

from frontend.desktop.modules.business_intelligence.presenters.reports_presenter import (
    REPORT_CATALOG,
    ReportsPresenter,
    ReportUnavailableError,
)


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    yield connection
    connection.close()


def test_report_catalog_has_exactly_one_real_entry():
    assert len(REPORT_CATALOG) == 1
    assert REPORT_CATALOG[0]["key"] == "executive_summary"


def test_list_reports_returns_the_catalog(conn):
    presenter = ReportsPresenter(conn)
    assert presenter.list_reports() == REPORT_CATALOG


def test_default_filename_uses_report_key_and_format(conn):
    presenter = ReportsPresenter(conn)
    name = presenter.default_filename("executive_summary", "csv")
    assert name.startswith("executive_summary_")
    assert name.endswith(".csv")


def test_generate_rejects_an_unknown_report_key(conn):
    presenter = ReportsPresenter(conn)
    with pytest.raises(ReportUnavailableError):
        presenter.generate(report_key="not_a_real_report", fmt="csv", filepath="x.csv")


def test_generate_rejects_an_unknown_format(conn):
    presenter = ReportsPresenter(conn)
    with pytest.raises(ReportUnavailableError):
        presenter.generate(report_key="executive_summary", fmt="docx", filepath="x.docx")


def test_generate_writes_a_real_csv_file_against_a_bare_connection(conn, tmp_path):
    """No schema at all — `BiDashboardService.build_dashboard()` degrades to
    zero metrics (same as BI-24's own bare-connection test), but the export
    still writes a real file to disk."""
    presenter = ReportsPresenter(conn, actor_user_id="u1")
    target = str(tmp_path / "reporte.csv")
    written = presenter.generate(report_key="executive_summary", fmt="csv", filepath=target)
    assert os.path.exists(written)
    with open(written, encoding="utf-8-sig") as fh:
        content = fh.read()
    assert "Reporte BI" in content
