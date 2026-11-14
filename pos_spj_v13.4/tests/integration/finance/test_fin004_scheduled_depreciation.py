"""SDLC-FIN-004 — la depreciación corre sola el día 1 (decisión del responsable).

El legacy depreciaba cada mes con un job; al borrarlo quedó sólo el botón de
Finanzas → Depreciación, y si nadie lo oprimía el cierre se trababa. El ciclo de
fondo de Finanzas corre ahora el mes anterior, una sola vez por periodo. Si la app
estuvo apagada el día 1, corre en el primer ciclo después.
"""

from datetime import date

import pytest

from backend.application.finance.wiring import finance_periodic_tick
from backend.application.use_cases.finance.capitalize_asset_use_case import CapitalizeAssetUseCase
from backend.application.use_cases.finance.run_depreciation_use_case import RunDepreciationUseCase
from backend.domain.finance.enums import FiscalPeriodStatus, TreasuryAccountType
from backend.domain.finance.exceptions import ClosedFiscalPeriodError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.application_bus import ApplicationEventBus
from backend.shared.ids import new_uuid
from tests.integration.finance.conftest import fund, treasury


@pytest.fixture(autouse=True)
def _loss_outbox(bootstrapped_conn):
    """El ciclo también entrega la merma; su tabla viene de otro contexto."""
    bootstrapped_conn.execute(
        "CREATE TABLE loss_outbox (id TEXT PRIMARY KEY, event_name TEXT NOT NULL,"
        " payload_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING',"
        " attempt_count INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)")


def _asset(conn, *, on=date(2026, 7, 1)):
    bank = treasury(conn, TreasuryAccountType.BANK).id
    fund(conn, bank, "9000.00", on=date(2026, 7, 1))
    return CapitalizeAssetUseCase().execute(
        conn, name="Vitrina", acquisition_cost="1200.00", useful_life_months=12,
        capitalization_date=on, operation_id=new_uuid(), paid_from_treasury_account_id=bank)


def _tick(conn, today):
    return finance_periodic_tick(conn, ApplicationEventBus(), today=today)


def _runs(conn):
    return conn.execute("SELECT period_code, total_amount FROM depreciation_runs"
                        " ORDER BY period_code").fetchall()


def _accumulated(conn, asset):
    with FinanceUnitOfWork(conn) as uow:
        return uow.fixed_assets.get(asset.id).accumulated_depreciation.to_string()


class TestCorridaAutomatica:
    def test_day_one_depreciates_the_month_that_ended(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        result = _tick(bootstrapped_conn, date(2026, 8, 1))
        assert result["depreciation"]["period"] == "2026-07"
        assert len(result["depreciation"]["entries"]) == 1
        assert _runs(bootstrapped_conn) == [("2026-07", "100.00")]
        assert _accumulated(bootstrapped_conn, asset) == "100.00"

    def test_two_triggers_of_the_same_period_make_one_run(self, bootstrapped_conn):
        _asset(bootstrapped_conn)
        _tick(bootstrapped_conn, date(2026, 8, 1))
        second = _tick(bootstrapped_conn, date(2026, 8, 1))
        assert second["depreciation"]["entries"] == []
        assert len(_runs(bootstrapped_conn)) == 1

    def test_a_later_day_of_the_month_adds_nothing(self, bootstrapped_conn):
        _asset(bootstrapped_conn)
        _tick(bootstrapped_conn, date(2026, 8, 1))
        _tick(bootstrapped_conn, date(2026, 8, 20))
        assert len(_runs(bootstrapped_conn)) == 1

    def test_app_closed_on_day_one_runs_on_the_first_tick_after(self, bootstrapped_conn):
        _asset(bootstrapped_conn)
        _tick(bootstrapped_conn, date(2026, 8, 12))
        assert _runs(bootstrapped_conn) == [("2026-07", "100.00")]

    def test_each_month_gets_its_own_run(self, bootstrapped_conn):
        _asset(bootstrapped_conn)
        _tick(bootstrapped_conn, date(2026, 8, 1))
        _tick(bootstrapped_conn, date(2026, 9, 1))
        assert _runs(bootstrapped_conn) == [("2026-07", "100.00"), ("2026-08", "100.00")]

    def test_january_runs_december_of_the_previous_year(self, bootstrapped_conn):
        _asset(bootstrapped_conn)
        assert _tick(bootstrapped_conn, date(2027, 1, 1))["depreciation"]["period"] == "2026-12"
        assert _runs(bootstrapped_conn) == [("2026-12", "600.00")]   # julio a diciembre

    def test_a_manual_run_of_the_period_is_respected(self, bootstrapped_conn):
        _asset(bootstrapped_conn)
        RunDepreciationUseCase().execute(bootstrapped_conn, year=2026, month=7,
                                         operation_id=new_uuid(), created_by="contador")
        _tick(bootstrapped_conn, date(2026, 8, 1))
        assert len(_runs(bootstrapped_conn)) == 1

    def test_without_assets_there_is_no_run(self, bootstrapped_conn):
        result = _tick(bootstrapped_conn, date(2026, 8, 1))
        assert result["depreciation"]["entries"] == []
        assert _runs(bootstrapped_conn) == []


class TestPeriodoCerrado:
    def _close(self, conn, year, month):
        with FinanceUnitOfWork(conn) as uow:
            period = uow.fiscal_periods.find_by_code(year, month)
            period.status = FiscalPeriodStatus.CLOSED
            uow.fiscal_periods.update(period)

    def test_closed_period_is_skipped_quietly(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        self._close(bootstrapped_conn, 2026, 7)
        result = _tick(bootstrapped_conn, date(2026, 8, 1))
        assert result["depreciation"]["entries"] == []
        assert _runs(bootstrapped_conn) == []
        assert _accumulated(bootstrapped_conn, asset) == "0.00"

    def test_next_open_period_recovers_it(self, bootstrapped_conn):
        asset = _asset(bootstrapped_conn)
        self._close(bootstrapped_conn, 2026, 7)
        _tick(bootstrapped_conn, date(2026, 8, 1))
        _tick(bootstrapped_conn, date(2026, 9, 1))
        assert _accumulated(bootstrapped_conn, asset) == "200.00"

    def test_a_failure_does_not_stop_the_rest_of_the_cycle(self, bootstrapped_conn, monkeypatch):
        from backend.application.use_cases.finance import scheduled_depreciation_use_case as uc

        def explode(*_args, **_kwargs):
            raise ClosedFiscalPeriodError("periodo cerrado a media corrida")

        monkeypatch.setattr(uc.RunDepreciationUseCase, "execute", explode)
        _asset(bootstrapped_conn)
        result = _tick(bootstrapped_conn, date(2026, 8, 1))
        assert "error" in result["depreciation"]
        assert "overdue" in result and "finance" in result
