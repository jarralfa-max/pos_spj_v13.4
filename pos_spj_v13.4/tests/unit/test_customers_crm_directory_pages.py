"""CRM-43 — bandejas de Clientes y CRM sobre ``CrmWorkbenchPage``.

Reemplaza las pruebas de los cuatro directorios de sólo lectura de CRM-16
(borrados): ahora cada bandeja tiene acciones que se habilitan según el
estado del registro Y el permiso del usuario, etiquetas en español y filtros.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from backend.application.crm.permissions import CRMPermissions
from tests.unit._crm_fake_presenter import CrmFakePresenter, FakeResult


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _enum(value):
    return SimpleNamespace(value=value)


def _customer_row(customer_id, name, status="ACTIVE", ctype="INDIVIDUAL", credit="NOT_CONFIGURED"):
    customer = SimpleNamespace(
        id=customer_id, code=f"CLI-{customer_id}", display_name=name, legal_name="",
        customer_type=_enum(ctype), status=_enum(status), lifecycle_stage=_enum("CUSTOMER"),
        purchase_count=0, last_purchase_at=None)
    return SimpleNamespace(customer=customer, contact_name="", phone="", email="",
                           owner_user_id=None, segments=(), credit_status=credit,
                           last_activity_at=None)


def _buttons(page):
    return {b.text(): b for b in page.findChildren(QtWidgets.QPushButton)}


class TestCustomersDirectoryPage:
    def _page(self, rows, **kw):
        from frontend.desktop.modules.customers_crm.pages.customers_directory_page import (
            CustomersDirectoryPage,
        )
        presenter = CrmFakePresenter(readers={"customer_rows": lambda **_k: rows}, **kw)
        page = CustomersDirectoryPage(presenter)
        page.reload()
        return page

    def test_labels_are_spanish_not_domain_codes(self, app):
        page = self._page([_customer_row("1", "Mostrador", ctype="PUBLIC_CUSTOMER")])
        cells = [page._table.item(0, c).text() for c in range(page._table.columnCount())]
        assert "Público en general" in cells
        assert "PUBLIC_CUSTOMER" not in cells
        assert "Activo" in cells

    def test_suspended_and_blocked_stay_visible_by_default(self, app):
        """CRM-43: el directorio sólo listaba ACTIVOS y un suspendido no se
        podía volver a encontrar para reactivarlo."""
        page = self._page([_customer_row("1", "A"), _customer_row("2", "B", "SUSPENDED"),
                           _customer_row("3", "C", "BLOCKED"), _customer_row("4", "D", "MERGED")])
        assert page._table.rowCount() == 3  # fusionados/cerrados/anonimizados se ocultan

    def test_status_filter_all_includes_merged(self, app):
        page = self._page([_customer_row("1", "A"), _customer_row("4", "D", "MERGED")])
        page._filter_widgets["status"].set_current_id("ALL")
        assert page._table.rowCount() == 2

    def test_credit_filter(self, app):
        page = self._page([_customer_row("1", "A", credit="AUTHORIZED"), _customer_row("2", "B")])
        page._filter_widgets["credit"].set_current_id("WITH")
        assert page._table.rowCount() == 1

    def test_new_customer_button_hidden_without_permission(self, app):
        page = self._page([], permissions={"CLIENTES.ver"})
        assert "Nuevo cliente" not in _buttons(page)


def _lead(lead_id, status, *, next_action=None, assigned=None):
    return SimpleNamespace(
        id=lead_id, code=f"LEAD-{lead_id}", display_name=f"Prospecto {lead_id}",
        company_name="", contact_name="", phone_e164=None, email=None,
        source=_enum("REFERRAL"), assigned_user_id=assigned, score=0,
        priority=_enum("HIGH"), last_contact_at=None, next_action_at=next_action,
        status=_enum(status), estimated_value=None, created_at="2026-10-08T10:00:00+00:00")


class TestLeadPages:
    def _page(self, cls_name, leads, **kw):
        from frontend.desktop.modules.customers_crm.pages import leads_pages
        presenter = CrmFakePresenter(readers={"leads": lambda **_k: leads}, **kw)
        page = getattr(leads_pages, cls_name)(presenter)
        page.reload()
        return page, presenter

    def test_open_lead_without_next_action_says_so(self, app):
        page, _ = self._page("LeadsPage", [_lead("1", "ASSIGNED")])
        cells = [page._table.item(0, c).text() for c in range(page._table.columnCount())]
        assert "Sin seguimiento" in cells

    def test_actions_follow_the_lead_state(self, app):
        page, _ = self._page("LeadsPage", [_lead("1", "QUALIFIED")])
        page._table.selectRow(0)
        buttons = _buttons(page)
        assert buttons["Convertir"].isEnabled()
        assert not buttons["Calificar"].isEnabled()
        assert not buttons["Archivar"].isEnabled()

    def test_actions_hidden_without_permission(self, app):
        page, _ = self._page("LeadsPage", [_lead("1", "QUALIFIED")],
                             permissions={CRMPermissions.LEADS_VIEW})
        assert "Convertir" not in _buttons(page)
        assert "Nuevo prospecto" not in _buttons(page)

    def test_conversion_route_only_shows_qualified(self, app):
        page, _ = self._page("LeadConversionPage", [_lead("1", "QUALIFIED"), _lead("2", "NEW")])
        assert page._table.rowCount() == 1

    def test_contacted_action_runs_the_use_case_and_reloads(self, app):
        page, presenter = self._page("LeadsPage", [_lead("1", "ASSIGNED")])
        page._table.selectRow(0)
        _buttons(page)["Contactado"].click()
        assert presenter.commands == [("mark_lead_contacted", {"lead_id": "1"})]
        assert "Listo" in page._notice.text()

    def test_rejected_use_case_shows_its_message(self, app):
        from frontend.desktop.modules.customers_crm.pages.leads_pages import LeadsPage
        presenter = CrmFakePresenter(
            readers={"leads": lambda **_k: [_lead("1", "ASSIGNED")]},
            results={"mark_lead_contacted": FakeResult(False, "No se puede")})
        page = LeadsPage(presenter)
        page.reload()
        page._table.selectRow(0)
        _buttons(page)["Contactado"].click()
        assert page._notice.text() == "No se puede"


class TestServiceCasesPage:
    def test_sla_is_text_not_only_color(self, app):
        from backend.domain.customer_service.entities.sla_instance import SLAInstance
        from frontend.desktop.modules.customers_crm.pages.service_pages import CasesPage

        past = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat(timespec="seconds")
        sla = SLAInstance.create("c1", "p1", 60, 120, reference_time=past)
        case = SimpleNamespace(
            id="c1", code="CASE-1", is_sensitive=False, subject="Llegó caliente",
            customer_id="cust", case_type=_enum("COMPLAINT"), priority=_enum("HIGH"),
            status=_enum("ASSIGNED"), assigned_user_id="u1", channel=_enum("PHONE"),
            reopen_count=0, description="", updated_at=past)
        presenter = CrmFakePresenter(readers={"case_rows": lambda **_k: [
            SimpleNamespace(case=case, sla=sla)]})
        page = CasesPage(presenter)
        page.reload()
        cells = [page._table.item(0, c).text() for c in range(page._table.columnCount())]
        assert any(cell.startswith("Vencido") for cell in cells)
        assert "Queja" in cells


class TestCreditPages:
    def test_masked_amounts_are_not_formatted_as_money(self, app):
        from frontend.desktop.modules.customers_crm.pages.credit_pages import (
            CreditProfilesPage,
        )
        profile = SimpleNamespace(
            id="p1", customer_id="cust", status=_enum("AUTHORIZED"), risk_level=_enum("LOW"),
            payment_terms_days=15, requested_by_user_id="u1", authorized_by_user_id="u2",
            authorized_at=None, credit_limit=Decimal("5000"))
        summary = SimpleNamespace(credit_limit="••••", available_credit="••••",
                                  current_exposure="••••", overdue_amount="••••",
                                  next_due_date=None, receivable_status="SIN_MOVIMIENTOS")
        presenter = CrmFakePresenter(readers={"credit_rows": lambda **_k: [
            SimpleNamespace(profile=profile, summary=summary, alerts=())]})
        page = CreditProfilesPage(presenter)
        page.reload()
        cells = [page._table.item(0, c).text() for c in range(page._table.columnCount())]
        assert "••••" in cells
        assert "Autorizado" in cells
