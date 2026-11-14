"""SDLC-FIN-003 — baja, venta y suspensión de activos fijos.

Decisiones del responsable (2026-11-05): si a la baja le faltan meses, se deprecian
antes de darla; y los meses omitidos se recuperan en el siguiente periodo corrido
(antes sólo el último mes de vida liquidaba lo pendiente).
"""

from datetime import date
from decimal import Decimal

import pytest

from backend.application.use_cases.finance.capitalize_asset_use_case import CapitalizeAssetUseCase
from backend.application.use_cases.finance.dispose_asset_use_case import (
    ChangeAssetStatusUseCase,
    DisposeAssetUseCase,
)
from backend.application.use_cases.finance.run_depreciation_use_case import RunDepreciationUseCase
from backend.domain.finance.enums import FixedAssetStatus, PostingPurpose, TreasuryAccountType
from backend.domain.finance.exceptions import AssetNotActiveError, FinanceDomainError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import new_uuid
from tests.integration.finance.conftest import fund, treasury


def _bank(conn):
    return treasury(conn, TreasuryAccountType.BANK).id


def _asset(conn, *, cost="1200.00", life=12, on=date(2026, 1, 10), residual="0.00"):
    fund(conn, _bank(conn), "9000.00", on=date(2026, 1, 1))
    return CapitalizeAssetUseCase().execute(
        conn, name="Vitrina", acquisition_cost=cost, residual_value=residual,
        useful_life_months=life, capitalization_date=on, operation_id=new_uuid(),
        paid_from_treasury_account_id=_bank(conn))


def _run(conn, month, year=2026):
    return RunDepreciationUseCase().execute(conn, year=year, month=month,
                                            operation_id=new_uuid(), created_by="c")


def _stored(conn, asset):
    with FinanceUnitOfWork(conn) as uow:
        return uow.fixed_assets.get(asset.id)


def _dispose(conn, asset, *, on=date(2026, 5, 15), operation_id=None, **kwargs):
    return DisposeAssetUseCase().execute(conn, asset_id=asset.id, disposal_date=on,
                                         operation_id=operation_id or new_uuid(),
                                         disposed_by="c", **kwargs)


def _balance(conn, code):
    rows = conn.execute(
        "SELECT jl.debit_amount, jl.credit_amount FROM journal_lines jl"
        " JOIN journal_entries je ON je.id = jl.journal_entry_id"
        " JOIN accounts a ON a.id = jl.account_id"
        " WHERE a.code = ? AND je.status IN ('POSTED','REVERSED')", (code,)).fetchall()
    return sum((Decimal(d) - Decimal(c) for d, c in rows), Decimal("0"))


def _assert_square(conn):
    rows = conn.execute("SELECT debit_amount, credit_amount FROM journal_lines").fetchall()
    assert sum(Decimal(d) for d, _ in rows) == sum(Decimal(c) for _, c in rows)


class TestMesesOmitidos:
    def test_next_run_recovers_the_skipped_months(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        _run(bootstrapped_conn, 1)
        entries = _run(bootstrapped_conn, 4)   # febrero y marzo omitidos
        assert len(entries) == 1
        stored = _stored(bootstrapped_conn, asset)
        assert stored.accumulated_depreciation.to_string() == "400.00"
        assert stored.last_depreciated_period == "2026-04"

    def test_first_run_recovers_from_the_capitalization_month(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        _run(bootstrapped_conn, 3)
        assert _stored(bootstrapped_conn, asset).accumulated_depreciation.to_string() == "300.00"

    def test_regular_months_stay_at_one_quota(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn, cost="100.00", life=3)
        for month in (1, 2):
            _run(bootstrapped_conn, month)
        assert _stored(bootstrapped_conn, asset).accumulated_depreciation.to_string() == "66.66"
        _run(bootstrapped_conn, 3)
        assert _stored(bootstrapped_conn, asset).accumulated_depreciation.to_string() == "100.00"

    def test_recovery_never_exceeds_the_base(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn, cost="1200.00", residual="200.00", life=10)
        _run(bootstrapped_conn, 12)            # más allá de la vida útil
        stored = _stored(bootstrapped_conn, asset)
        assert stored.accumulated_depreciation.to_string() == "1000.00"
        assert stored.is_fully_depreciated


class TestSuspension:
    def _suspend(self, conn, asset, on):
        ChangeAssetStatusUseCase().suspend(conn, asset_id=asset.id, reason="En reparación",
                                           operation_id=new_uuid(), actor="c", on_date=on)

    def _resume(self, conn, asset, on):
        ChangeAssetStatusUseCase().resume(conn, asset_id=asset.id, operation_id=new_uuid(),
                                          actor="c", on_date=on)

    def test_suspended_asset_does_not_depreciate(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        self._suspend(bootstrapped_conn, asset, date(2026, 2, 10))
        assert _run(bootstrapped_conn, 2) == []
        stored = _stored(bootstrapped_conn, asset)
        assert stored.status is FixedAssetStatus.SUSPENDED
        assert stored.status_reason == "En reparación"

    def test_suspended_months_are_not_recovered(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        _run(bootstrapped_conn, 1)
        self._suspend(bootstrapped_conn, asset, date(2026, 2, 10))
        self._resume(bootstrapped_conn, asset, date(2026, 4, 5))    # febrero y marzo fuera
        _run(bootstrapped_conn, 4)
        stored = _stored(bootstrapped_conn, asset)
        assert stored.status is FixedAssetStatus.ACTIVE
        assert stored.suspended_months == 2
        assert stored.accumulated_depreciation.to_string() == "200.00"

    def test_suspension_extends_the_end_of_life(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn, cost="300.00", life=3)
        _run(bootstrapped_conn, 1)
        self._suspend(bootstrapped_conn, asset, date(2026, 2, 10))
        self._resume(bootstrapped_conn, asset, date(2026, 3, 5))
        _run(bootstrapped_conn, 3)
        # Calendario: mes 3 de vida; en servicio: sólo 2. No liquida todavía.
        assert _stored(bootstrapped_conn, asset).accumulated_depreciation.to_string() == "200.00"

    def test_month_already_depreciated_when_suspended_does_not_stop_the_next(
            self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        _run(bootstrapped_conn, 1)
        self._suspend(bootstrapped_conn, asset, date(2026, 1, 20))
        self._resume(bootstrapped_conn, asset, date(2026, 2, 3))
        _run(bootstrapped_conn, 2)
        assert _stored(bootstrapped_conn, asset).accumulated_depreciation.to_string() == "200.00"

    def test_retired_asset_cannot_be_suspended_or_resumed(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        _dispose(bootstrapped_conn, asset, reason="Rota")
        with pytest.raises(AssetNotActiveError):
            self._suspend(bootstrapped_conn, asset, date(2026, 6, 1))
        with pytest.raises(FinanceDomainError):
            self._resume(bootstrapped_conn, asset, date(2026, 6, 1))

    def test_suspension_is_audited_and_needs_a_reason(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        with pytest.raises(FinanceDomainError):
            ChangeAssetStatusUseCase().suspend(
                bootstrapped_conn, asset_id=asset.id, reason=" ", operation_id=new_uuid(),
                actor="c", on_date=date(2026, 2, 1))
        before = self._audited(bootstrapped_conn, asset)
        self._suspend(bootstrapped_conn, asset, date(2026, 2, 1))
        assert self._audited(bootstrapped_conn, asset) == before + 1

    @staticmethod
    def _audited(conn, asset):
        return conn.execute("SELECT COUNT(*) FROM finance_audit_log WHERE entity_id=?",
                            (asset.id,)).fetchone()[0]

    def test_unknown_asset_is_rejected(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        asset.id = new_uuid()
        with pytest.raises(FinanceDomainError):
            self._resume(bootstrapped_conn, asset, date(2026, 2, 1))


class TestBajaConDepreciacionAlDia:
    def test_scrap_depreciates_the_missing_months_first(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        _run(bootstrapped_conn, 1)
        _dispose(bootstrapped_conn, asset, reason="Rota")
        stored = _stored(bootstrapped_conn, asset)
        assert stored.status is FixedAssetStatus.DISPOSED
        assert stored.accumulated_depreciation.to_string() == "400.00"     # hasta abril
        assert stored.last_depreciated_period == "2026-04"
        assert _balance(bootstrapped_conn, "6120") == Decimal("400.00")
        assert _balance(bootstrapped_conn, "7540") == Decimal("800.00")    # pérdida real
        assert _balance(bootstrapped_conn, "1201") == Decimal("0.00")
        assert _balance(bootstrapped_conn, "1202") == Decimal("0.00")
        _assert_square(bootstrapped_conn)

    def test_catch_up_is_a_registered_run(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        _dispose(bootstrapped_conn, asset, reason="Rota")
        runs = bootstrapped_conn.execute(
            "SELECT period_code, asset_count, total_amount FROM depreciation_runs").fetchall()
        assert runs == [("2026-04", 1, "400.00")]

    def test_sale_with_gain(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        bank_before = _balance(bootstrapped_conn, "1110")
        _dispose(bootstrapped_conn, asset, outcome=FixedAssetStatus.SOLD, proceeds="1000.00",
                 treasury_account_id=_bank(bootstrapped_conn), reason="Venta")
        assert _stored(bootstrapped_conn, asset).status is FixedAssetStatus.SOLD
        assert _balance(bootstrapped_conn, "1110") - bank_before == Decimal("1000.00")
        assert _balance(bootstrapped_conn, "7140") == Decimal("-200.00")   # libros 800
        assert _balance(bootstrapped_conn, "7540") == Decimal("0.00")
        _assert_square(bootstrapped_conn)

    def test_sale_with_loss(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        _dispose(bootstrapped_conn, asset, outcome=FixedAssetStatus.SOLD, proceeds="500.00",
                 treasury_account_id=_bank(bootstrapped_conn), reason="Venta")
        assert _balance(bootstrapped_conn, "7540") == Decimal("300.00")
        assert _balance(bootstrapped_conn, "7140") == Decimal("0.00")
        _assert_square(bootstrapped_conn)

    def test_write_off(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        _dispose(bootstrapped_conn, asset, outcome=FixedAssetStatus.WRITTEN_OFF, reason="Robo")
        assert _stored(bootstrapped_conn, asset).status is FixedAssetStatus.WRITTEN_OFF
        _assert_square(bootstrapped_conn)

    def test_asset_up_to_date_gets_no_extra_depreciation(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        _run(bootstrapped_conn, 4)
        runs = bootstrapped_conn.execute("SELECT COUNT(*) FROM depreciation_runs").fetchone()[0]
        _dispose(bootstrapped_conn, asset, reason="Rota")
        assert bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM depreciation_runs").fetchone()[0] == runs
        assert _stored(bootstrapped_conn, asset).accumulated_depreciation.to_string() == "400.00"

    def test_disposal_month_itself_is_not_depreciated(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn, on=date(2026, 5, 2))
        _dispose(bootstrapped_conn, asset, reason="Rota")
        stored = _stored(bootstrapped_conn, asset)
        assert stored.accumulated_depreciation.is_zero()
        assert _balance(bootstrapped_conn, "7540") == Decimal("1200.00")

    def test_suspended_asset_recovers_only_months_before_the_suspension(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        ChangeAssetStatusUseCase().suspend(
            bootstrapped_conn, asset_id=asset.id, reason="Reparación", operation_id=new_uuid(),
            actor="c", on_date=date(2026, 3, 10))
        _dispose(bootstrapped_conn, asset, reason="Irreparable")
        stored = _stored(bootstrapped_conn, asset)
        assert stored.status is FixedAssetStatus.DISPOSED
        assert stored.accumulated_depreciation.to_string() == "200.00"     # enero y febrero
        _assert_square(bootstrapped_conn)

    def test_fully_depreciated_asset_has_no_loss(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn, cost="300.00", life=3)
        _dispose(bootstrapped_conn, asset, reason="Vida útil cumplida")
        assert _stored(bootstrapped_conn, asset).is_fully_depreciated
        assert _balance(bootstrapped_conn, "7540") == Decimal("0.00")
        _assert_square(bootstrapped_conn)

    def test_failed_disposal_leaves_no_catch_up(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        with pytest.raises(FinanceDomainError):
            _dispose(bootstrapped_conn, asset, outcome=FixedAssetStatus.SOLD, proceeds="10.00",
                     treasury_account_id=new_uuid(), reason="Venta")
        assert _stored(bootstrapped_conn, asset).accumulated_depreciation.is_zero()
        assert bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM depreciation_runs").fetchone()[0] == 0


class TestIdempotencia:
    def test_second_disposal_returns_the_original_entry(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        first = _dispose(bootstrapped_conn, asset, reason="Rota")
        entries = bootstrapped_conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
        second = _dispose(bootstrapped_conn, asset, reason="Rota otra vez",
                          on=date(2026, 6, 1))
        assert second == first == _stored(bootstrapped_conn, asset).disposal_journal_entry_id
        assert bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM journal_entries").fetchone()[0] == entries

    def test_disposal_entry_is_marked_with_its_purpose(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        entry_id = _dispose(bootstrapped_conn, asset, reason="Rota")
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            entry = uow.journal_entries.find_by_posting_reference(
                "finance", asset.id, PostingPurpose.ASSET_DISPOSAL)
        assert entry.id == entry_id


class TestValidaciones:
    def test_active_status_is_not_a_disposal(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        with pytest.raises(FinanceDomainError):
            _dispose(bootstrapped_conn, asset, outcome=FixedAssetStatus.ACTIVE)

    def test_sale_needs_proceeds_and_account(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        with pytest.raises(FinanceDomainError):
            _dispose(bootstrapped_conn, asset, outcome=FixedAssetStatus.SOLD, proceeds="10.00")

    def test_only_a_sale_has_proceeds(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        with pytest.raises(FinanceDomainError):
            _dispose(bootstrapped_conn, asset, proceeds="10.00")


class TestMigracion381:
    def _run(self, conn):
        import importlib
        importlib.import_module(
            "migrations.standalone.381_fixed_assets_suspension_months").run(conn)

    def test_adds_the_columns_and_is_idempotent(self):
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE fixed_assets (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO fixed_assets VALUES ('a')")
        self._run(conn)
        self._run(conn)
        assert conn.execute("SELECT suspended_on, suspended_months FROM fixed_assets").fetchall() \
            == [(None, 0)]

    def test_is_registered_in_the_engine(self):
        from migrations.engine import MIGRATIONS
        assert "381" in {m.version for m in MIGRATIONS}
