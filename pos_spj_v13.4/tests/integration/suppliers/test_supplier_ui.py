"""FASE SUP-4/SUP-5 — supplier UI smoke tests (headless, both themes).

Builds the view against a real in-memory supplier DB, exercises the presenter
mapping, the list page states, and the ficha's lazy tabs.
"""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.infrastructure.db.schema.supplier_schema import create_supplier_schema  # noqa: E402
from frontend.desktop.modules.finance.suppliers.supplier_routes import (  # noqa: E402
    build_supplier_presenter,
)
from frontend.desktop.modules.finance.suppliers.suppliers_view import SuppliersView  # noqa: E402
from frontend.desktop.themes.theme_manager import ThemeManager  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def presenter():
    conn = sqlite3.connect(":memory:")
    create_supplier_schema(conn)
    yield build_supplier_presenter(conn)
    conn.close()


def _create(presenter, legal="Distribuidora del Valle SA de CV", rfc="DVA010203XY1"):
    ok, msg, data = presenter.create_supplier(legal_name=legal, tax_identifier=rfc,
                                              trade_name=legal)
    assert ok, msg
    return data


class TestPresenterMapping:
    def test_kpis_and_search(self, app, presenter):
        _create(presenter)
        kpis = presenter.overview_kpis()
        assert any(k.title == "Proveedores activos" for k in kpis)
        table = presenter.suppliers()
        assert table.total == 1 and table.rows[0][0] == "PRV-000001"

    def test_search_filter(self, app, presenter):
        _create(presenter, legal="Alfa", rfc="AAA010203XY1")
        _create(presenter, legal="Beta", rfc="BBB010203XY1")
        assert presenter.suppliers(search="alfa").total == 1

    def test_detail_and_risk(self, app, presenter):
        data = _create(presenter)
        # locate the supplier id via search
        sid = presenter.suppliers().row_ids[0]
        header = presenter.supplier_header(sid)
        assert header["supplier_code"] == "PRV-000001"
        assert header["status_label"] == "Borrador"
        risk = presenter.risk(sid)
        assert "level" in risk and "causes" in risk


class TestListPage:
    def test_view_builds_and_loads(self, app, presenter):
        ThemeManager.instance().apply(app, "light")
        _create(presenter)
        view = SuppliersView(presenter)
        view.ensure_loaded()
        # the list page shows the table (non-empty)
        assert view._list._table.rowCount() == 1

    def test_empty_state_when_no_rows(self, app):
        conn = sqlite3.connect(":memory:")
        create_supplier_schema(conn)
        view = SuppliersView(build_supplier_presenter(conn))
        view.ensure_loaded()
        assert view._list._stack.currentWidget() is view._list._empty
        conn.close()

    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_builds_in_both_themes(self, app, presenter, theme):
        ThemeManager.instance().apply(app, theme)
        view = SuppliersView(presenter)
        view.ensure_loaded()
        assert view is not None


class TestDetailDialog:
    def test_ficha_lazy_tabs_load(self, app, presenter):
        from frontend.desktop.modules.finance.suppliers.pages.supplier_detail_dialog import (
            SupplierDetailDialog,
        )
        _create(presenter)
        sid = presenter.suppliers().row_ids[0]
        # add a contact + bank account through the presenter (as the dialogs would)
        presenter.add_contact(supplier_id=sid, name="Ana", contact_type="PURCHASING",
                              phone_e164="+525511112222", email="ana@delvalle.mx")
        presenter.add_bank_account(supplier_id=sid, bank_name="BBVA",
                                   account_holder="Del Valle", clabe="012345678901231234")
        dialog = SupplierDetailDialog(presenter, sid)
        # activate each tab → lazy loader runs without error
        for i in range(dialog._tabs.count()):
            dialog._tabs.setCurrentIndex(i)
        assert dialog._contacts_table.rowCount() == 1
        # bank CLABE is masked in the ficha
        clabe_cell = dialog._bank_table.item(0, 2).text()
        assert clabe_cell.endswith("1234") and "•" in clabe_cell


class TestFinanceIntegration:
    def test_suppliers_page_registered_in_finance_nav(self):
        from frontend.desktop.modules.finance.finance_view import _NAVIGATION
        labels = [label for _s, label, _p in _NAVIGATION]
        assert "Maestro de proveedores" in labels
