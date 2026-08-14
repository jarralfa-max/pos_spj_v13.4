"""CRM-16 — Directorios: CustomerCrmPresenter directory methods + the four
directory pages (clientes/leads/oportunidades/casos)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from frontend.desktop.modules.customers_crm.customers_crm_presenter import CustomerCrmPresenter
from frontend.desktop.modules.customers_crm.pages.customers_directory_page import (
    CustomersDirectoryPage,
)
from frontend.desktop.modules.customers_crm.pages.leads_directory_page import LeadsDirectoryPage
from frontend.desktop.modules.customers_crm.pages.opportunities_directory_page import (
    OpportunitiesDirectoryPage,
)
from frontend.desktop.modules.customers_crm.pages.service_cases_directory_page import (
    ServiceCasesDirectoryPage,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _entity(entity_id, status, **fields):
    return SimpleNamespace(id=entity_id, status=SimpleNamespace(value=status), **fields)


class _FakeSession:
    user_id = "u1"

    def tiene_permiso(self, _permission: str) -> bool:
        return True


class _FakeDirectoryQueryService:
    def __init__(self, entities: list) -> None:
        self._entities = entities
        self.calls: list = []

    def list_directory(self, context, *, limit=200):
        self.calls.append((context, limit))
        return self._entities


class TestCustomerCrmPresenterDirectories:
    def test_customers_directory_empty_when_unwired(self):
        presenter = CustomerCrmPresenter(session_context=_FakeSession())
        assert presenter.customers_directory() == []

    def test_customers_directory_delegates_and_filters_by_search(self):
        entities = [
            _entity("c1", "ACTIVE", display_name="Restaurante El Sol", legal_name="",
                   code="C-0001"),
            _entity("c2", "ACTIVE", display_name="Otro Negocio", legal_name="", code="C-0002"),
        ]
        service = _FakeDirectoryQueryService(entities)
        presenter = CustomerCrmPresenter(
            session_context=_FakeSession(), query_services={"customers_directory": service})
        result = presenter.customers_directory(search="Sol")
        assert [e.id for e in result] == ["c1"]

    def test_customers_directory_filters_by_status(self):
        entities = [
            _entity("c1", "ACTIVE", display_name="A", legal_name="", code="C-1"),
            _entity("c2", "SUSPENDED", display_name="B", legal_name="", code="C-2"),
        ]
        service = _FakeDirectoryQueryService(entities)
        presenter = CustomerCrmPresenter(
            session_context=_FakeSession(), query_services={"customers_directory": service})
        result = presenter.customers_directory(status="SUSPENDED")
        assert [e.id for e in result] == ["c2"]

    def test_leads_directory_empty_when_unwired(self):
        presenter = CustomerCrmPresenter(session_context=_FakeSession())
        assert presenter.leads_directory() == []

    def test_leads_directory_search_matches_company_name(self):
        entities = [_entity("l1", "NEW", display_name="Juan", company_name="Acme Corp")]
        service = _FakeDirectoryQueryService(entities)
        presenter = CustomerCrmPresenter(
            session_context=_FakeSession(), query_services={"leads_directory": service})
        assert len(presenter.leads_directory(search="acme")) == 1
        assert presenter.leads_directory(search="nope") == []

    def test_opportunities_directory_empty_when_unwired(self):
        presenter = CustomerCrmPresenter(session_context=_FakeSession())
        assert presenter.opportunities_directory() == []

    def test_opportunities_directory_delegates(self):
        entities = [_entity("o1", "OPEN", name="Oportunidad de prueba")]
        service = _FakeDirectoryQueryService(entities)
        presenter = CustomerCrmPresenter(
            session_context=_FakeSession(), query_services={"opportunities_directory": service})
        assert [e.id for e in presenter.opportunities_directory()] == ["o1"]

    def test_cases_directory_empty_when_unwired(self):
        presenter = CustomerCrmPresenter(session_context=_FakeSession())
        assert presenter.cases_directory() == []

    def test_cases_directory_search_matches_code(self):
        entities = [_entity("k1", "NEW", subject="Consulta", code="CASE-0001")]
        service = _FakeDirectoryQueryService(entities)
        presenter = CustomerCrmPresenter(
            session_context=_FakeSession(), query_services={"cases_directory": service})
        result = presenter.cases_directory(search="CASE-0001")
        assert [e.id for e in result] == ["k1"]

    def test_no_filters_returns_everything(self):
        entities = [_entity("c1", "ACTIVE", display_name="A", legal_name="", code="C-1"),
                   _entity("c2", "SUSPENDED", display_name="B", legal_name="", code="C-2")]
        service = _FakeDirectoryQueryService(entities)
        presenter = CustomerCrmPresenter(
            session_context=_FakeSession(), query_services={"customers_directory": service})
        assert len(presenter.customers_directory()) == 2


class _FakePresenter:
    def __init__(self, method_name: str, entities: list) -> None:
        self._method_name = method_name
        self._entities = entities
        self.calls: list = []
        setattr(self, method_name, self._call)

    def _call(self, *, search="", status=None):
        self.calls.append((search, status))
        return self._entities


class _RaisingPresenter:
    def __init__(self, method_name: str) -> None:
        setattr(self, method_name, self._raise)

    def _raise(self, *, search="", status=None):
        raise RuntimeError("boom")


class _FakeCode:
    def __init__(self, text: str) -> None:
        self._text = text

    def __str__(self) -> str:
        return self._text


def _customer(**overrides):
    defaults = dict(
        code=_FakeCode("C-0001"), display_name="Restaurante El Sol",
        customer_type=SimpleNamespace(value="BUSINESS"),
        status=SimpleNamespace(value="ACTIVE"), id="c1")
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _lead(**overrides):
    defaults = dict(
        display_name="Juan Perez", company_name="Acme", id="l1",
        status=SimpleNamespace(value="NEW"), priority=SimpleNamespace(value="NORMAL"), score=10)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _opportunity(**overrides):
    defaults = dict(
        name="Oportunidad", id="o1", status=SimpleNamespace(value="OPEN"),
        amount=None, probability=50, expected_close_date=None)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _case(**overrides):
    defaults = dict(
        code=_FakeCode("CASE-0001"), subject="Consulta", id="k1",
        case_type=SimpleNamespace(value="QUESTION"), status=SimpleNamespace(value="NEW"),
        priority=SimpleNamespace(value="NORMAL"))
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestCustomersDirectoryPage:
    def test_reload_populates_table(self, app):
        presenter = _FakePresenter("customers_directory", [_customer()])
        page = CustomersDirectoryPage(presenter)
        page.reload()
        assert page._loaded is True
        assert page._stack.currentWidget() is page._table

    def test_reload_shows_empty_state_when_no_rows(self, app):
        presenter = _FakePresenter("customers_directory", [])
        page = CustomersDirectoryPage(presenter)
        page.reload()
        assert page._stack.currentWidget() is page._empty

    def test_reload_shows_error_when_presenter_raises(self, app):
        page = CustomersDirectoryPage(_RaisingPresenter("customers_directory"))
        page.reload()
        assert page._loaded is False
        assert not page._status.isHidden()
        assert "boom" in page._status.text()

    def test_search_change_triggers_reload_with_search_text(self, app):
        presenter = _FakePresenter("customers_directory", [])
        page = CustomersDirectoryPage(presenter)
        page._search.setText("Sol")
        page.reload()
        assert presenter.calls[-1] == ("Sol", None)

    def test_row_formats_customer_fields(self, app):
        page = CustomersDirectoryPage(_FakePresenter("customers_directory", []))
        row = page._row(_customer())
        assert row == ["C-0001", "Restaurante El Sol", "BUSINESS", "Activo"]


class TestLeadsDirectoryPage:
    def test_reload_populates_table(self, app):
        presenter = _FakePresenter("leads_directory", [_lead()])
        page = LeadsDirectoryPage(presenter)
        page.reload()
        assert page._stack.currentWidget() is page._table

    def test_row_formats_lead_fields(self, app):
        page = LeadsDirectoryPage(_FakePresenter("leads_directory", []))
        row = page._row(_lead())
        assert row == ["Juan Perez", "Acme", "Nuevo", "NORMAL", "10"]


class TestOpportunitiesDirectoryPage:
    def test_reload_populates_table(self, app):
        presenter = _FakePresenter("opportunities_directory", [_opportunity()])
        page = OpportunitiesDirectoryPage(presenter)
        page.reload()
        assert page._stack.currentWidget() is page._table

    def test_row_formats_amount_and_close_date_placeholders(self, app):
        page = OpportunitiesDirectoryPage(_FakePresenter("opportunities_directory", []))
        row = page._row(_opportunity())
        assert row[0] == "Oportunidad"
        assert row[1] == "Abierta"
        assert row[2] == "—"  # no amount
        assert row[4] == "—"  # no close date


class TestServiceCasesDirectoryPage:
    def test_reload_populates_table(self, app):
        presenter = _FakePresenter("cases_directory", [_case()])
        page = ServiceCasesDirectoryPage(presenter)
        page.reload()
        assert page._stack.currentWidget() is page._table

    def test_row_formats_case_fields(self, app):
        page = ServiceCasesDirectoryPage(_FakePresenter("cases_directory", []))
        row = page._row(_case())
        assert row == ["CASE-0001", "Consulta", "QUESTION", "Nuevo", "NORMAL"]

    def test_status_filter_selection_is_forwarded_on_reload(self, app):
        presenter = _FakePresenter("cases_directory", [])
        page = ServiceCasesDirectoryPage(presenter)
        assert page._status_filter.set_current_id("ESCALATED") is True
        page.reload()
        assert presenter.calls[-1] == ("", "ESCALATED")
