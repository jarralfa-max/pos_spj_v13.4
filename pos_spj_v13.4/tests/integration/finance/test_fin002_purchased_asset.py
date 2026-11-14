"""SDLC-FIN-002 — un activo comprado en Compras llega al auxiliar una sola vez.

Antes el puente cargaba la cuenta de activo y acreditaba CxP (o tesorería), pero
no creaba nada en ``fixed_assets``: no se depreciaba, y darlo de alta en Finanzas
duplicaba la CxP o el pago.

Decisión del responsable: alta automática, y se actualiza hasta completar. Por
eso nace en DRAFT, sin vida útil inventada, y al completarse se activa SIN
asiento: el costo ya se reconoció.
"""

from datetime import date
from decimal import Decimal

import pytest

from backend.application.event_handlers.finance.procurement_compensation_bridges import (
    ProcurementImmediatePaymentReversalHandler,
    ProcurementReturnCreditHandler,
)
from backend.application.event_handlers.finance.procurement_immediate_payment_bridge import (
    ProcurementImmediatePaymentBridgeHandler,
)
from backend.application.event_handlers.finance.procurement_payable_bridge import (
    ProcurementPayableBridgeHandler,
)
from backend.application.services.finance.period_close_checklist import PeriodCloseChecklist
from backend.application.use_cases.finance.capitalize_asset_use_case import CapitalizeAssetUseCase
from backend.application.use_cases.finance.purchased_asset_use_case import (
    CompletePurchasedAssetUseCase,
)
from backend.application.use_cases.finance.run_depreciation_use_case import RunDepreciationUseCase
from backend.domain.finance.enums import FixedAssetStatus, TreasuryAccountType
from backend.domain.finance.exceptions import FinanceDomainError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import new_uuid
from tests.integration.finance.conftest import account_id, fund, treasury

ISSUED = "2026-07-16T13:00:00"


def _credit_payload(document_id=None, *, document_number="F-100", supplier_id="prov-1",
                    natures=None, tax="192.00", amount="1392.00"):
    return {"source_module": "procurement", "supplier_id": supplier_id,
            "document_id": document_id or new_uuid(), "document_number": document_number,
            "amount": amount, "currency_code": "MXN", "operation_id": new_uuid(),
            "timestamp": ISSUED, "tax_total": tax, "user_id": "comprador",
            "nature_subtotals": natures or {"ASSET": "1000.00", "INVENTORY": "200.00"}}


def _cash_payload(document_id=None):
    payload = _credit_payload(document_id, document_number="CD-2026-000003")
    payload["payment_source"] = "BANK_TRANSFER"
    return payload


def _assets(conn):
    with FinanceUnitOfWork(conn) as uow:
        return uow.fixed_assets.list_all()


def _count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _trial_balance_is_square(conn):
    rows = conn.execute("SELECT debit_amount, credit_amount FROM journal_lines").fetchall()
    return sum(Decimal(d) for d, _ in rows) == sum(Decimal(c) for _, c in rows)


def _balance(conn, code):
    rows = conn.execute(
        "SELECT jl.debit_amount, jl.credit_amount FROM journal_lines jl"
        " JOIN journal_entries je ON je.id = jl.journal_entry_id"
        " JOIN accounts a ON a.id = jl.account_id"
        " WHERE a.code = ? AND je.status IN ('POSTED','REVERSED')", (code,)).fetchall()
    return sum((Decimal(d) - Decimal(c) for d, c in rows), Decimal("0"))


def _complete(conn, asset, **changes):
    values = {"useful_life_months": 10, "capitalization_date": date(2026, 7, 16),
              "name": "Refrigerador"}
    values.update(changes)
    return CompletePurchasedAssetUseCase().execute(
        conn, asset_id=asset.id, operation_id=new_uuid(), completed_by="contador", **values)


class TestAltaAutomatica:
    def test_credit_purchase_leaves_the_asset_in_the_subledger(self, bootstrapped_conn):
        payload = _credit_payload()
        ProcurementPayableBridgeHandler(bootstrapped_conn).handle(payload)
        assets = _assets(bootstrapped_conn)
        assert len(assets) == 1
        asset = assets[0]
        assert asset.status is FixedAssetStatus.DRAFT
        assert asset.acquisition_cost.to_string() == "1000.00"
        assert asset.source_document_id == payload["document_id"]
        assert asset.source_document_number == "F-100"
        assert asset.supplier_id == "prov-1"
        assert asset.acquisition_date == date(2026, 7, 16)
        assert asset.asset_account_id == account_id(bootstrapped_conn, "1201")

    def test_cash_purchase_leaves_the_asset_in_the_subledger(self, bootstrapped_conn):
        fund(bootstrapped_conn, treasury(bootstrapped_conn, TreasuryAccountType.BANK).id,
             "5000.00")
        ProcurementImmediatePaymentBridgeHandler(bootstrapped_conn).handle(_cash_payload())
        assets = _assets(bootstrapped_conn)
        assert [a.source_document_number for a in assets] == ["CD-2026-000003"]
        assert assets[0].acquisition_cost.to_string() == "1000.00"

    def test_purchase_without_asset_nature_creates_nothing(self, bootstrapped_conn):
        ProcurementPayableBridgeHandler(bootstrapped_conn).handle(
            _credit_payload(natures={"INVENTORY": "1200.00"}))
        assert _assets(bootstrapped_conn) == []

    def test_retrying_the_event_creates_one_asset_and_one_payable(self, bootstrapped_conn):
        payload = _credit_payload()
        handler = ProcurementPayableBridgeHandler(bootstrapped_conn)
        handler.handle(payload)
        handler.handle(payload)
        assert len(_assets(bootstrapped_conn)) == 1
        assert _count(bootstrapped_conn, "payables") == 1

    def test_failed_recognition_leaves_no_asset(self, bootstrapped_conn):
        payload = _credit_payload(natures={"ASSET": "10.00"})  # no cuadra con el total
        with pytest.raises(FinanceDomainError):
            ProcurementPayableBridgeHandler(bootstrapped_conn).handle(payload)
        assert _assets(bootstrapped_conn) == []


class TestCompletarDatos:
    def _purchased(self, conn):
        ProcurementPayableBridgeHandler(conn).handle(_credit_payload())
        return _assets(conn)[0]

    def test_update_until_complete(self, bootstrapped_conn):
        asset = self._purchased(bootstrapped_conn)
        partial = _complete(bootstrapped_conn, asset, useful_life_months=None,
                            capitalization_date=None)
        assert partial.status is FixedAssetStatus.DRAFT
        assert partial.name == "Refrigerador"
        done = _complete(bootstrapped_conn, asset, residual_value="100.00")
        assert done.status is FixedAssetStatus.ACTIVE
        stored = _assets(bootstrapped_conn)[0]
        assert stored.useful_life_months == 10
        assert stored.residual_value.to_string() == "100.00"
        assert stored.depreciation_expense_account_id == account_id(bootstrapped_conn, "6120")

    def test_completing_never_posts_a_second_recognition(self, bootstrapped_conn):
        asset = self._purchased(bootstrapped_conn)
        entries = _count(bootstrapped_conn, "journal_entries")
        _complete(bootstrapped_conn, asset)
        assert _count(bootstrapped_conn, "journal_entries") == entries
        assert _count(bootstrapped_conn, "payables") == 1

    def test_category_supplies_the_useful_life(self, bootstrapped_conn):
        asset = self._purchased(bootstrapped_conn)
        category_id = new_uuid()
        bootstrapped_conn.execute(
            "INSERT INTO fixed_asset_categories (id, code, name, asset_account_id,"
            " depreciation_expense_account_id, accumulated_depreciation_account_id,"
            " default_useful_life_months, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (category_id, "MAQ", "Maquinaria", account_id(bootstrapped_conn, "1150"),
             account_id(bootstrapped_conn, "6120"), account_id(bootstrapped_conn, "1202"),
             24, "2026-07-01"))
        done = _complete(bootstrapped_conn, asset, useful_life_months=None,
                         asset_category_id=category_id)
        assert done.status is FixedAssetStatus.ACTIVE
        assert done.useful_life_months == 24
        # El costo sigue en la cuenta que Compras cargó, aunque la categoría diga otra.
        assert done.asset_account_id == account_id(bootstrapped_conn, "1201")

    def test_completed_asset_cannot_be_completed_again(self, bootstrapped_conn):
        asset = self._purchased(bootstrapped_conn)
        _complete(bootstrapped_conn, asset)
        with pytest.raises(FinanceDomainError):
            _complete(bootstrapped_conn, asset, useful_life_months=20)


class TestRegresionDeCompraAActivo:
    def test_purchase_to_depreciation_keeps_one_payable_and_square_books(self, bootstrapped_conn):
        ProcurementPayableBridgeHandler(bootstrapped_conn).handle(_credit_payload())
        _complete(bootstrapped_conn, _assets(bootstrapped_conn)[0])
        entries = RunDepreciationUseCase().execute(
            bootstrapped_conn, year=2026, month=7, operation_id=new_uuid(), created_by="c")
        assert len(entries) == 1
        assert _assets(bootstrapped_conn)[0].accumulated_depreciation.to_string() == "100.00"
        assert _count(bootstrapped_conn, "payables") == 1
        assert _balance(bootstrapped_conn, "1201") == Decimal("1000.00")
        assert _balance(bootstrapped_conn, "2101") == Decimal("-1392.00")
        assert _balance(bootstrapped_conn, "6120") == Decimal("100.00")
        assert _balance(bootstrapped_conn, "1202") == Decimal("-100.00")
        assert _trial_balance_is_square(bootstrapped_conn)


class TestDobleCapitalizacion:
    def _capitalize(self, conn, *, document_number, supplier_id="prov-1", treasury_id=None):
        return CapitalizeAssetUseCase().execute(
            conn, name="Refrigerador", acquisition_cost="1000.00", useful_life_months=10,
            capitalization_date=date(2026, 7, 16), operation_id=new_uuid(),
            supplier_id=None if treasury_id else supplier_id,
            paid_from_treasury_account_id=treasury_id, document_number=document_number)

    def test_same_invoice_on_credit_is_rejected(self, bootstrapped_conn):
        ProcurementPayableBridgeHandler(bootstrapped_conn).handle(_credit_payload())
        with pytest.raises(FinanceDomainError, match="F-100"):
            self._capitalize(bootstrapped_conn, document_number="F-100")
        assert _count(bootstrapped_conn, "payables") == 1
        assert len(_assets(bootstrapped_conn)) == 1

    def test_same_folio_from_treasury_is_rejected(self, bootstrapped_conn):
        bank = treasury(bootstrapped_conn, TreasuryAccountType.BANK).id
        fund(bootstrapped_conn, bank, "5000.00")
        ProcurementImmediatePaymentBridgeHandler(bootstrapped_conn).handle(_cash_payload())
        with pytest.raises(FinanceDomainError, match="CD-2026-000003"):
            self._capitalize(bootstrapped_conn, document_number="cd-2026-000003",
                             treasury_id=bank)

    def test_receipt_folio_matches_either_part(self, bootstrapped_conn):
        ProcurementPayableBridgeHandler(bootstrapped_conn).handle(
            _credit_payload(document_number="CD-1 / REC-9"))
        with pytest.raises(FinanceDomainError):
            self._capitalize(bootstrapped_conn, document_number="CD-1")

    def test_same_number_from_another_supplier_is_a_different_document(self, bootstrapped_conn):
        ProcurementPayableBridgeHandler(bootstrapped_conn).handle(_credit_payload())
        asset = self._capitalize(bootstrapped_conn, document_number="F-100",
                                 supplier_id="prov-2")
        assert asset.status is FixedAssetStatus.ACTIVE

    def test_finance_capitalization_also_guards_itself(self, bootstrapped_conn):
        self._capitalize(bootstrapped_conn, document_number="F-200")
        with pytest.raises(FinanceDomainError):
            self._capitalize(bootstrapped_conn, document_number="F-200")
        assert _count(bootstrapped_conn, "payables") == 1


class _NoPendingSources:
    def status(self, *, period_start, period_end):
        from types import SimpleNamespace
        return SimpleNamespace(open_cash_shifts=0, pending_sales_events=0,
                               pending_purchase_events=0, pending_payroll_events=0,
                               pending_inventory_events=0)


class TestCierre:
    def _item(self, conn, month):
        items = PeriodCloseChecklist(_NoPendingSources()).evaluate(conn, year=2026, month=month)
        return next(i for i in items if i.key == "purchased_assets_completed")

    def test_incomplete_purchased_asset_blocks_the_close(self, bootstrapped_conn):
        ProcurementPayableBridgeHandler(bootstrapped_conn).handle(_credit_payload())
        item = self._item(bootstrapped_conn, 7)
        assert item.status == "BLOCKING" and "1" in item.detail

    def test_asset_acquired_after_the_period_does_not_block_it(self, bootstrapped_conn):
        ProcurementPayableBridgeHandler(bootstrapped_conn).handle(_credit_payload())
        assert self._item(bootstrapped_conn, 6).status == "OK"

    def test_completed_asset_no_longer_blocks(self, bootstrapped_conn):
        ProcurementPayableBridgeHandler(bootstrapped_conn).handle(_credit_payload())
        _complete(bootstrapped_conn, _assets(bootstrapped_conn)[0])
        assert self._item(bootstrapped_conn, 7).status == "OK"


class TestCompensaciones:
    def test_reversed_cash_purchase_cancels_the_pending_asset(self, bootstrapped_conn):
        fund(bootstrapped_conn, treasury(bootstrapped_conn, TreasuryAccountType.BANK).id,
             "5000.00")
        payload = _cash_payload()
        ProcurementImmediatePaymentBridgeHandler(bootstrapped_conn).handle(payload)
        ProcurementImmediatePaymentReversalHandler(bootstrapped_conn).handle(
            {"document_id": payload["document_id"], "operation_id": new_uuid(),
             "timestamp": ISSUED, "reason": "Compra duplicada"})
        asset = _assets(bootstrapped_conn)[0]
        assert asset.status is FixedAssetStatus.WRITTEN_OFF
        assert asset.disposal_journal_entry_id
        assert _balance(bootstrapped_conn, "1201") == Decimal("0.00")

    def test_partial_return_reduces_the_cost(self, bootstrapped_conn):
        payload = _credit_payload()
        ProcurementPayableBridgeHandler(bootstrapped_conn).handle(payload)
        ProcurementReturnCreditHandler(bootstrapped_conn).handle({
            "document_id": new_uuid(), "operation_id": new_uuid(), "return_value": "400.00",
            "return_tax": "0.00", "currency_code": "MXN", "timestamp": ISSUED,
            "invoice_ids": [payload["document_id"]], "document_number": "DEV-1",
            "nature_subtotals": {"ASSET": "400.00"}})
        asset = _assets(bootstrapped_conn)[0]
        assert asset.status is FixedAssetStatus.DRAFT
        assert asset.acquisition_cost.to_string() == "600.00"
        assert _balance(bootstrapped_conn, "1201") == Decimal("600.00")

    def test_full_return_cancels_the_asset(self, bootstrapped_conn):
        payload = _credit_payload()
        ProcurementPayableBridgeHandler(bootstrapped_conn).handle(payload)
        ProcurementReturnCreditHandler(bootstrapped_conn).handle({
            "document_id": new_uuid(), "operation_id": new_uuid(), "return_value": "1000.00",
            "return_tax": "0.00", "currency_code": "MXN", "timestamp": ISSUED,
            "invoice_ids": [payload["document_id"]], "document_number": "DEV-2",
            "nature_subtotals": {"ASSET": "1000.00"}})
        assert _assets(bootstrapped_conn)[0].status is FixedAssetStatus.WRITTEN_OFF


class TestMigracion380:
    def _run(self, conn):
        import importlib
        importlib.import_module(
            "migrations.standalone.380_fixed_assets_source_document_number").run(conn)

    def test_adds_the_column_to_an_older_table_and_is_idempotent(self):
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE fixed_assets (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO fixed_assets VALUES ('a')")
        self._run(conn)
        self._run(conn)
        assert conn.execute("SELECT id, source_document_number FROM fixed_assets").fetchall() \
            == [("a", None)]

    def test_database_without_finance_is_left_alone(self):
        import sqlite3
        self._run(sqlite3.connect(":memory:"))

    def test_is_registered_in_the_engine(self):
        from migrations.engine import MIGRATIONS
        assert "380" in {m.version for m in MIGRATIONS}


class TestPantalla:
    """Sin Qt: el formulario se declara y aquí se intercepta el diálogo."""

    def _presenter(self, conn):
        from types import SimpleNamespace

        from backend.application.finance.permissions import FinancePermissions
        from frontend.desktop.modules.finance.finance_routes import build_finance_presenter

        granted = {FinancePermissions.VIEW, FinancePermissions.ASSET_MANAGE}
        session = SimpleNamespace(user_id=new_uuid(), is_active=True, active_branch_id="b1",
                                  tiene_permiso=lambda code: code in granted)
        return build_finance_presenter(conn, session)

    def test_presenter_lists_and_completes_the_pending_asset(self, bootstrapped_conn):
        ProcurementPayableBridgeHandler(bootstrapped_conn).handle(_credit_payload())
        asset = _assets(bootstrapped_conn)[0]
        presenter = self._presenter(bootstrapped_conn)
        assert presenter.asset_status(asset.id) == "DRAFT"
        assert presenter.pending_asset(asset.id)["source_document_number"] == "F-100"
        ok, message = presenter.complete_purchased_asset(asset.id, name="Horno")
        assert ok and "falta la vida útil" in message
        ok, message = presenter.complete_purchased_asset(
            asset.id, useful_life_months=24, capitalization_date=date(2026, 7, 16))
        assert ok and "ya deprecia" in message
        assert presenter.asset_status(asset.id) == "ACTIVE"

    def test_manual_capitalization_reaches_the_use_case(self, bootstrapped_conn):
        """``name`` es un dato del activo: chocaba con el parámetro de ``_command``
        y «Capitalizar activo» reventaba con TypeError antes de llegar al caso de uso."""
        bank = treasury(bootstrapped_conn, TreasuryAccountType.BANK).id
        fund(bootstrapped_conn, bank, "5000.00")
        presenter = self._presenter(bootstrapped_conn)
        ok, message = presenter.capitalize_asset(
            name="Vitrina", acquisition_cost="1000.00", useful_life_months=10,
            capitalization_date=date(2026, 7, 16), paid_from_treasury_account_id=bank)
        assert ok, message

    def test_form_offers_what_the_purchase_left_pending(self, bootstrapped_conn, monkeypatch):
        from types import SimpleNamespace

        from frontend.desktop.modules.finance.pages import fixed_assets_page as page

        ProcurementPayableBridgeHandler(bootstrapped_conn).handle(_credit_payload())
        asset = _assets(bootstrapped_conn)[0]
        captured = {}

        def fake_ask(_parent, _title, fields, **_kwargs):
            captured.update({spec.key: spec for spec in fields})
            return {"name": "Horno", "asset_code": "", "asset_category_id": None,
                    "residual_value": "0.00", "useful_life_months": 24,
                    "capitalization_date": date(2026, 7, 20), "project_id": None}

        monkeypatch.setattr(page, "ask", fake_ask)
        results = []
        fake_page = SimpleNamespace(_presenter=self._presenter(bootstrapped_conn),
                                    selected_id=lambda: asset.id, run=results.append)
        page.FixedAssetsPage._complete(fake_page)
        assert captured["capitalization_date"].default == date(2026, 7, 16)
        assert captured["source_document_number"].default == "F-100"
        assert results[0][0] is True, results[0]
        stored = _assets(bootstrapped_conn)[0]
        assert stored.status is FixedAssetStatus.ACTIVE
        assert stored.capitalization_date == date(2026, 7, 20)


class TestComando:
    def test_completing_requires_the_asset_permission(self, bootstrapped_conn):
        from backend.application.finance.authorization import (
            DenyAllFinancePermissionCheckerForTests,
            FinanceAuthorizationPolicy,
        )
        from backend.application.finance.finance_commands import FinanceCommandService
        from backend.domain.finance.exceptions import PermissionDeniedError

        ProcurementPayableBridgeHandler(bootstrapped_conn).handle(_credit_payload())
        asset = _assets(bootstrapped_conn)[0]
        commands = FinanceCommandService(
            connection_provider=lambda: bootstrapped_conn,
            use_cases={"complete_purchased_asset": CompletePurchasedAssetUseCase()},
            authorization=FinanceAuthorizationPolicy(DenyAllFinancePermissionCheckerForTests()),
            actor_provider=lambda: "u1")
        with pytest.raises(PermissionDeniedError):
            commands.complete_purchased_asset(asset.id, useful_life_months=10)
        assert _assets(bootstrapped_conn)[0].status is FixedAssetStatus.DRAFT
