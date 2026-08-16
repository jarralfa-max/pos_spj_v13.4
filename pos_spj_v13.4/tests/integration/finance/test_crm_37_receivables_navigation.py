"""CRM-37 (Fase 3, NavigationIntent) — Customer 360's "Ver CxC" action
lands on Finanzas' CxC screen with the summary already shown, instead of
an admin typing the legacy customer id by hand via QInputDialog."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)

from PyQt5.QtWidgets import QApplication  # noqa: E402

from frontend.desktop.modules.finance.finance_routes import build_finance_presenter  # noqa: E402
from frontend.desktop.modules.finance.finance_view import FinanceView  # noqa: E402
from frontend.desktop.modules.finance.pages.accounts_receivable_page import (  # noqa: E402
    AccountsReceivablePage,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def cxc_conn(finance_conn):
    finance_conn.execute("""
        CREATE TABLE cuentas_por_cobrar (
            id TEXT NOT NULL PRIMARY KEY,
            cliente_id TEXT NOT NULL,
            venta_id TEXT,
            folio TEXT,
            monto_original REAL NOT NULL,
            saldo_pendiente REAL NOT NULL,
            estado TEXT DEFAULT 'pendiente',
            sucursal_id TEXT,
            fecha DATETIME DEFAULT (datetime('now')),
            fecha_pago DATETIME
        )
    """)
    finance_conn.commit()
    return finance_conn


def _seed_cxc(conn, cliente_id: str, *, monto: float = 500.0) -> None:
    from backend.shared.ids import new_uuid
    conn.execute(
        "INSERT INTO cuentas_por_cobrar (id, cliente_id, monto_original, saldo_pendiente,"
        " estado, fecha) VALUES (?, ?, ?, ?, 'pendiente', datetime('now'))",
        (new_uuid(), cliente_id, monto, monto))
    conn.commit()


class TestShowCrmSummaryFor:
    def test_shows_summary_for_customer_with_exposure(self, app, cxc_conn, monkeypatch):
        _seed_cxc(cxc_conn, "legacy-cust-1", monto=750.0)
        presenter = build_finance_presenter(cxc_conn)
        page = AccountsReceivablePage(presenter)

        shown = []
        page.notify = lambda ok, msg: shown.append((ok, msg))
        info_calls = []
        monkeypatch.setattr(
            "frontend.desktop.modules.finance.pages.accounts_receivable_page.QMessageBox.information",
            lambda *a, **k: info_calls.append(a))

        page.show_crm_summary_for("legacy-cust-1")

        assert not shown, f"no debió reportar 'no encontrado': {shown}"
        assert len(info_calls) == 1
        assert "750" in info_calls[0][2]

    def test_shows_zero_exposure_summary_for_customer_with_no_cxc_history(
            self, app, cxc_conn, monkeypatch):
        """`CustomerAccountsReceivableSummaryQuery.get_summary()` always
        returns a summary (zero exposure, status SIN_MOVIMIENTOS for an
        unknown/no-history customer) — it never returns None. The
        `notify(False, ...)` branch only fires if `crm_receivable_summary`
        itself raises, which a missing customer does not trigger."""
        presenter = build_finance_presenter(cxc_conn)
        page = AccountsReceivablePage(presenter)

        shown = []
        page.notify = lambda ok, msg: shown.append((ok, msg))
        info_calls = []
        monkeypatch.setattr(
            "frontend.desktop.modules.finance.pages.accounts_receivable_page.QMessageBox.information",
            lambda *a, **k: info_calls.append(a))

        page.show_crm_summary_for("no-existe")

        assert not shown
        assert len(info_calls) == 1
        assert "SIN_MOVIMIENTOS" in info_calls[0][2]


class TestFinanceViewAplicarContexto:
    def test_switches_to_cxc_page_and_shows_summary(self, app, cxc_conn):
        _seed_cxc(cxc_conn, "legacy-cust-2", monto=200.0)
        presenter = build_finance_presenter(cxc_conn)
        view = FinanceView(presenter)

        cxc_page = next(p for p in view._pages if isinstance(p, AccountsReceivablePage))
        calls = []
        cxc_page.show_crm_summary_for = lambda cid: calls.append(cid)

        view.aplicar_contexto({"legacy_customer_id": "legacy-cust-2"})

        assert calls == ["legacy-cust-2"]
        assert view._stack.currentWidget() is cxc_page

    def test_empty_context_is_a_noop(self, app, cxc_conn):
        presenter = build_finance_presenter(cxc_conn)
        view = FinanceView(presenter)
        cxc_page = next(p for p in view._pages if isinstance(p, AccountsReceivablePage))
        calls = []
        cxc_page.show_crm_summary_for = lambda cid: calls.append(cid)

        view.aplicar_contexto({})

        assert calls == []
