"""FASES 17-18 — estados financieros y query services de solo lectura."""

from backend.application.event_handlers.finance.payroll_paid_handler import PayrollPaidHandler
from backend.application.event_handlers.finance.purchase_received_handler import (
    PurchaseReceivedHandler,
)
from backend.application.event_handlers.finance.sale_completed_handler import (
    SaleCompletedHandler,
)
from backend.application.queries.finance.finance_read_services import (
    CommercialObligationQueryService,
    FinanceDashboardQueryService,
    JournalQueryService,
    PayableQueryService,
    ReceivableQueryService,
    TreasuryQueryService,
)
from backend.application.queries.finance.financial_statement_query_service import (
    FinancialStatementQueryService,
)
from backend.application.use_cases.finance.generate_financial_statements_use_case import (
    GenerateFinancialStatementsUseCase,
)
from backend.shared.ids import new_uuid

OCCURRED = "2026-07-16T12:00:00Z"
FROM, TO = "2026-07-01", "2026-07-31"


def _seed_activity(conn):
    """One cash sale (470 net + 30 discount, tax 64.83, cogs 200), one purchase,
    one payroll."""
    SaleCompletedHandler(conn).handle({
        "event_id": new_uuid(), "operation_id": new_uuid(), "sale_id": new_uuid(),
        "folio": "V-1", "occurred_at": OCCURRED, "currency_code": "MXN",
        "gross_total": "500.00", "discount_total": "30.00", "net_total": "470.00",
        "tax_total": "64.83", "cogs_total": "200.00",
        "settlements": [{"type": "CASH", "amount": "470.00"}],
    })
    PurchaseReceivedHandler(conn).handle({
        "event_id": new_uuid(), "operation_id": new_uuid(), "purchase_id": new_uuid(),
        "supplier_id": new_uuid(), "folio": "C-1", "occurred_at": OCCURRED,
        "subtotal": "1000.00", "tax_total": "160.00", "total": "1160.00",
    })
    PayrollPaidHandler(conn).handle({
        "event_id": new_uuid(), "operation_id": new_uuid(), "payroll_run_id": new_uuid(),
        "occurred_at": OCCURRED, "gross_salaries": "300.00",
        "social_security": "45.00", "net_paid": "300.00",
    })


class TestStatements:
    def test_trial_balance_balances(self, bootstrapped_conn):
        _seed_activity(bootstrapped_conn)
        rows = FinancialStatementQueryService(bootstrapped_conn).trial_balance(
            date_from=FROM, date_to=TO)
        assert rows  # builder validates Σdebe == Σhaber or raises

    def test_income_statement_math(self, bootstrapped_conn):
        _seed_activity(bootstrapped_conn)
        result = FinancialStatementQueryService(bootstrapped_conn).income_statement(
            date_from=FROM, date_to=TO)
        assert result["revenue"] == "435.17"       # 500 - 64.83 tax
        assert result["contra_revenue"] == "30.00"
        assert result["cost_of_sales"] == "200.00"
        # 405.17 - 200 - (300 sueldos + 45 imss) = -139.83
        assert result["net_income"] == "-139.83"

    def test_balance_sheet_equation_holds(self, bootstrapped_conn):
        _seed_activity(bootstrapped_conn)
        result = FinancialStatementQueryService(bootstrapped_conn).balance_sheet(as_of=TO)
        # assert_accounting_equation did not raise; equity_total reflects the loss
        assert result["equity_total"] == result["period_net_income"]

    def test_generate_statements_use_case_emits_event(self, bootstrapped_conn):
        _seed_activity(bootstrapped_conn)
        result = GenerateFinancialStatementsUseCase().execute(
            bootstrapped_conn, date_from=FROM, date_to=TO, operation_id=new_uuid())
        assert set(result) >= {"trial_balance", "balance_sheet", "income_statement",
                               "cash_flow_statement"}
        events = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM finance_outbox"
            " WHERE event_name='FINANCIAL_STATEMENTS_GENERATED'").fetchone()[0]
        assert events == 1


class TestReadServices:
    def test_dashboard_overview(self, bootstrapped_conn):
        _seed_activity(bootstrapped_conn)
        overview = FinanceDashboardQueryService(bootstrapped_conn).overview(
            month_from=FROM, month_to=TO)
        assert overview["revenue"] == "435.17"
        assert overview["open_payables"] == "1160"

    def test_journal_query_lists_entries_and_lines(self, bootstrapped_conn):
        _seed_activity(bootstrapped_conn)
        service = JournalQueryService(bootstrapped_conn)
        entries = service.list_entries()
        assert len(entries) == 4  # sale + cogs + purchase + payroll
        lines = service.entry_lines(entries[0]["id"])
        assert lines and "account_code" in lines[0]

    def test_treasury_position_reflects_cash(self, bootstrapped_conn):
        _seed_activity(bootstrapped_conn)
        position = TreasuryQueryService(bootstrapped_conn).treasury_position()
        by_name = {row["name"]: row for row in position}
        assert float(by_name["Banco principal"]["balance"]) == -300.0  # nómina pagada

    def test_receivable_payable_services(self, bootstrapped_conn):
        _seed_activity(bootstrapped_conn)
        assert ReceivableQueryService(bootstrapped_conn).open_receivables() == []
        payables = PayableQueryService(bootstrapped_conn).open_payables()
        assert len(payables) == 1 and payables[0]["document_number"] == "C-1"

    def test_obligation_summary_service(self, bootstrapped_conn):
        from backend.application.event_handlers.finance.gift_card_sold_handler import (
            GiftCardSoldHandler,
        )
        GiftCardSoldHandler(bootstrapped_conn).handle({
            "event_id": new_uuid(), "operation_id": new_uuid(),
            "instrument_id": new_uuid(), "occurred_at": OCCURRED,
            "face_value": "500.00", "currency_code": "MXN",
        })
        summary = CommercialObligationQueryService(bootstrapped_conn).summary_by_instrument()
        assert summary[0]["instrument_type"] == "GIFT_CARD"
        assert float(summary[0]["outstanding"]) == 500.0
