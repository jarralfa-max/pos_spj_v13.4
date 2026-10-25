"""FASE 18 — la UI de Finanzas opera de punta a punta sobre datos reales.

El presenter compuesto por ``finance_routes`` (permisos de la sesión viva,
comandos autorizados) recorre los flujos que la pantalla ofrece: asiento
manual con segregación, cobro aplicado a varias facturas, ciclo de pago y
permisos visuales. Y cada una de las páginas carga con actividad sembrada.
"""

import os
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)

from PyQt5.QtWidgets import QApplication, QPushButton  # noqa: E402

from backend.application.finance.permissions import FinancePermissions  # noqa: E402
from backend.application.use_cases.finance.register_sale_credit_charge_use_case import (  # noqa: E402
    RegisterSaleCreditChargeUseCase,
)
from backend.domain.finance.enums import TreasuryAccountType  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402
from frontend.desktop.modules.finance.finance_routes import build_finance_presenter  # noqa: E402
from frontend.desktop.modules.finance.finance_view import FinanceView  # noqa: E402
from frontend.desktop.modules.finance.finance_view_models import money_display  # noqa: E402
from frontend.desktop.modules.finance.pages.chart_of_accounts_page import (  # noqa: E402
    ChartOfAccountsPage,
)
from tests.integration.finance.conftest import (  # noqa: E402
    account_id,
    fund,
    register_customer,
    register_supplier,
    treasury,
)

TODAY = date.today()


class Session:
    """Sesión viva mutable: cambiar ``user_id`` simula a otra persona."""

    def __init__(self, user_id="ana", granted=None):
        self.user_id = user_id
        self.is_active = True
        self.active_branch_id = None
        self._granted = granted

    def tiene_permiso(self, code):
        return self._granted is None or code in self._granted


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def session():
    return Session()


@pytest.fixture
def presenter(bootstrapped_conn, session):
    return build_finance_presenter(bootstrapped_conn, session)


def _bank(conn):
    return treasury(conn, TreasuryAccountType.BANK)


class TestManualJournalEntry:
    def _draft(self, presenter, conn):
        ok, message = presenter.create_journal_entry(
            entry_date=TODAY, description="Reclasificación", journal_type="GENERAL",
            currency_code="MXN", exchange_rate=None, lines=[
                {"account_id": account_id(conn, "6130"), "debit": "250.00", "credit": ""},
                {"account_id": _bank(conn).ledger_account_id, "debit": "", "credit": "250.00"},
            ])
        assert ok, message
        return presenter.journal_entries(status="DRAFT").row_ids[0]

    def test_creator_cannot_post_but_a_reviewer_can(self, presenter, session,
                                                    bootstrapped_conn):
        entry_id = self._draft(presenter, bootstrapped_conn)
        ok, _ = presenter.validate_journal_entry(entry_id)
        assert ok
        ok, message = presenter.post_journal_entry(entry_id)
        assert not ok and "otra persona" in message
        session.user_id = "contralor"
        ok, message = presenter.post_journal_entry(entry_id)
        assert ok, message
        detail = presenter.journal_entry(entry_id)
        assert detail["status"] == "POSTED"
        assert [(row[3], row[4]) for row in detail["lines"].rows] == [("$250.00", ""),
                                                                      ("", "$250.00")]

    def test_unbalanced_draft_cannot_be_validated(self, presenter, bootstrapped_conn):
        # Un borrador es trabajo en curso; validar exige partida doble.
        ok, _ = presenter.create_journal_entry(
            entry_date=TODAY, description="Descuadre", journal_type="GENERAL",
            currency_code="MXN", exchange_rate=None, lines=[
                {"account_id": account_id(bootstrapped_conn, "6130"), "debit": "10.00"},
                {"account_id": _bank(bootstrapped_conn).ledger_account_id, "credit": "9.00"},
            ])
        assert ok
        entry_id = presenter.journal_entries(status="DRAFT").row_ids[0]
        ok, message = presenter.validate_journal_entry(entry_id)
        assert not ok and message
        assert presenter.journal_entry(entry_id)["status"] == "DRAFT"


class TestCollectionAppliedToSeveralInvoices:
    def test_one_collection_settles_one_invoice_and_part_of_another(self, presenter,
                                                                   bootstrapped_conn):
        customer = register_customer(bootstrapped_conn, "Abarrotes Luna")
        first, second = (RegisterSaleCreditChargeUseCase().execute(
            bootstrapped_conn, customer_id=customer, sale_id=new_uuid(), payment_id=new_uuid(),
            folio=folio, amount="100.00", issue_date=TODAY) for folio in ("V-1", "V-2"))
        ok, message = presenter.register_collection(
            customer_id=customer, amount="150.00", treasury_account_id=_bank(bootstrapped_conn).id,
            payment_method="BANK_TRANSFER", collection_date=TODAY, reference="REC-9",
            applications=[{"receivable_id": first.id, "amount": "100.00"},
                          {"receivable_id": second.id, "amount": "30.00"}])
        assert ok, message
        assert "20.00" in message  # queda saldo a favor
        open_rows = presenter.open_receivables(customer_id=customer).rows
        assert [(r[0], r[1], r[5]) for r in open_rows] == [("V-2", "Abarrotes Luna", "$70.00")]
        assert presenter.customer_credit_balances().rows[0][4] == "$20.00"


class TestSupplierPaymentCycle:
    def test_schedule_authorize_execute_are_three_people(self, presenter, session,
                                                         bootstrapped_conn):
        supplier = register_supplier(bootstrapped_conn)
        bank = _bank(bootstrapped_conn)
        fund(bootstrapped_conn, bank.id, "1000.00", on=TODAY)
        ok, message = presenter.create_payable(
            supplier_id=supplier, document_number="F-77", amount="300.00", issue_date=TODAY,
            due_date=TODAY, debit_nature="OPERATING_EXPENSE",
            counterpart_account_id=account_id(bootstrapped_conn, "6130"),
            retention_amount=None, priority="HIGH", payment_terms="")
        assert ok, message
        payable_id = presenter.open_payables().row_ids[0]
        ok, message = presenter.schedule_supplier_payment(
            payable_id=payable_id, amount="300.00", treasury_account_id=bank.id,
            scheduled_date=TODAY, reference="P-1")
        assert ok, message
        payment_id = presenter.supplier_payments().row_ids[0]
        assert not presenter.authorize_supplier_payment(payment_id)[0]  # quien programó
        session.user_id = "beto"
        assert presenter.authorize_supplier_payment(payment_id)[0]
        ok, message = presenter.execute_supplier_payment(payment_id, "SPEI-1")
        assert not ok and "doble control" in message
        session.user_id = "carla"
        ok, message = presenter.execute_supplier_payment(payment_id, "SPEI-1")
        assert ok, message
        assert presenter.open_payables().rows == []


class TestPermissionsAreVisible:
    def test_action_without_permission_is_disabled_and_says_why(self, app, bootstrapped_conn):
        presenter = build_finance_presenter(
            bootstrapped_conn, Session(granted={FinancePermissions.VIEW}))
        page = ChartOfAccountsPage(presenter)
        button = next(b for b in page.findChildren(QPushButton) if b.text() == "Nueva cuenta")
        assert not button.isEnabled()
        assert FinancePermissions.ACCOUNT_MANAGE in button.toolTip()

    def test_without_session_every_command_is_rejected(self, bootstrapped_conn):
        presenter = build_finance_presenter(bootstrapped_conn, None)
        ok, _ = presenter.open_period(2026, 8)
        assert not ok


class TestEveryPageLoadsWithActivity:
    def test_all_pages_render_seeded_data(self, app, presenter, bootstrapped_conn):
        fund(bootstrapped_conn, _bank(bootstrapped_conn).id, "500.00", on=TODAY)
        RegisterSaleCreditChargeUseCase().execute(
            bootstrapped_conn, customer_id=register_customer(bootstrapped_conn),
            sale_id=new_uuid(), payment_id=new_uuid(), folio="V-10", amount="80.00",
            issue_date=TODAY)
        view = FinanceView(presenter)
        failures = []
        for row, index in view._row_to_page_index.items():
            view._nav.setCurrentRow(row)
            page = view._pages[index]
            if not getattr(page, "_loaded", True):
                notice = getattr(page, "_notice", None)
                failures.append((view._nav.item(row).text(),
                                 notice.text() if notice is not None else ""))
        assert failures == []


def test_money_is_formatted_without_float():
    assert money_display("9007199254740993.01") == "$9,007,199,254,740,993.01"
    assert money_display("-5") == "-$5.00"
    assert money_display("") == ""


def test_pages_fit_1366_by_768(app, presenter):
    """§29: con la barra lateral, el área de contenido a 1366×768 ronda los
    1100 px; ninguna página propia de Finanzas exige más (el maestro de
    proveedores es un submódulo con su propio diseño)."""
    from frontend.desktop.modules.finance.pages.suppliers_page import SuppliersPage
    view = FinanceView(presenter)
    view.resize(1366, 768)
    too_wide = []
    for row, index in view._row_to_page_index.items():
        view._nav.setCurrentRow(row)
        page = view._pages[index]
        if isinstance(page, SuppliersPage):
            continue
        width = page.minimumSizeHint().width()
        if width > 1100:
            too_wide.append((view._nav.item(row).text(), width))
    assert too_wide == []
