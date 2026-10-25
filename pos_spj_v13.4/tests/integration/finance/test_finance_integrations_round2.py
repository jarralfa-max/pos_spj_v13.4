"""FIN-ERP FASE 6/15 — integraciones que no llegaban al mayor.

- La merma valuada (``LOSS_FINANCE_RECOGNITION_REQUESTED``) se encolaba en
  ``loss_outbox`` y nadie la entregaba ni la consumía: ahora el ciclo de
  Finanzas la despacha y ``LossRecognitionHandler`` la asienta.
- La rentabilidad (§33) no tenía productor: la venta, la devolución y la
  cancelación registran sus hechos y su suma cuadra con el mayor.
"""

import json
from datetime import date
from decimal import Decimal

import pytest

from backend.application.event_handlers.finance.loss_recognition_handler import (
    LOSS_FINANCE_RECOGNITION_REQUESTED,
    LossRecognitionHandler,
)
from backend.application.event_handlers.finance.sale_completed_handler import (
    SaleCompletedHandler,
)
from backend.application.event_handlers.finance.sale_returned_handler import SaleReturnedHandler
from backend.application.event_handlers.finance.sale_reversed_handler import SaleReversedHandler
from backend.application.finance.wiring import finance_periodic_tick, wire_finance
from backend.application.queries.finance.profitability_query_service import (
    ProfitabilityQueryService,
)
from backend.domain.finance.enums import PostingPurpose
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.events.application_bus import ApplicationEventBus
from backend.shared.ids import new_uuid
from tests.integration.finance.conftest import account_id

TODAY = date(2026, 7, 16)
OCCURRED = "2026-07-16T18:00:00+00:00"


def _balance(conn, code):
    rows = conn.execute(
        "SELECT jl.base_debit_amount, jl.base_credit_amount FROM journal_lines jl"
        " JOIN journal_entries je ON je.id = jl.journal_entry_id"
        " WHERE jl.account_id = ? AND je.status IN ('POSTED','REVERSED')",
        (account_id(conn, code),)).fetchall()
    return sum((Decimal(d) - Decimal(c) for d, c in rows), Decimal("0"))


def _loss_event(**overrides):
    event = {"event_id": new_uuid(), "event_name": LOSS_FINANCE_RECOGNITION_REQUESTED,
             "operation_id": new_uuid(), "entity_id": new_uuid(), "loss_case_id": new_uuid(),
             "branch_id": new_uuid(), "warehouse_id": new_uuid(), "user_id": new_uuid(),
             "timestamp": OCCURRED, "source_module": "losses", "currency_code": "MXN",
             "amount": "350.00"}
    event.update(overrides)
    return event


class TestLossReachesTheLedger:
    def test_net_loss_is_a_cost_never_cash(self, bootstrapped_conn):
        event = _loss_event()
        LossRecognitionHandler(bootstrapped_conn).handle(event)
        LossRecognitionHandler(bootstrapped_conn).handle(event)  # reentrega: un efecto
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            entry = uow.journal_entries.find_by_posting_reference(
                "losses", event["entity_id"], PostingPurpose.WASTE)
        assert entry.is_balanced() and entry.total_debits().to_string() == "350.00"
        assert {line.branch_id for line in entry.lines} == {event["branch_id"]}
        assert _balance(bootstrapped_conn, "5110") == Decimal("350.00")
        assert _balance(bootstrapped_conn, "1150") == Decimal("-350.00")
        facts = bootstrapped_conn.execute(
            "SELECT fact_type, direct_cost, journal_entry_id FROM profitability_facts").fetchall()
        assert facts == [("WASTE", "350.00", entry.id)]

    def test_fully_recovered_loss_posts_nothing(self, bootstrapped_conn):
        LossRecognitionHandler(bootstrapped_conn).handle(_loss_event(amount="0.00"))
        assert bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM journal_entries").fetchone()[0] == 0


@pytest.fixture
def loss_outbox(bootstrapped_conn):
    bootstrapped_conn.execute(
        "CREATE TABLE loss_outbox (id TEXT PRIMARY KEY, event_id TEXT NOT NULL UNIQUE,"
        " event_name TEXT NOT NULL, aggregate_id TEXT NOT NULL, operation_id TEXT NOT NULL,"
        " causation_id TEXT, correlation_id TEXT NOT NULL, payload_json TEXT NOT NULL,"
        " status TEXT NOT NULL DEFAULT 'PENDING', attempt_count INTEGER NOT NULL DEFAULT 0,"
        " created_at TEXT NOT NULL, next_attempt_at TEXT, dispatched_at TEXT, last_error TEXT)")

    def enqueue(event):
        bootstrapped_conn.execute(
            "INSERT INTO loss_outbox (id, event_id, event_name, aggregate_id, operation_id,"
            " correlation_id, payload_json, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (new_uuid(), event["event_id"], event["event_name"], event["loss_case_id"],
             event["operation_id"], event["event_id"], json.dumps(event), OCCURRED))
        bootstrapped_conn.commit()
    return enqueue


class TestLossOutboxDelivery:
    def test_wired_cycle_delivers_the_pending_loss(self, bootstrapped_conn, loss_outbox):
        event = _loss_event()
        loss_outbox(event)
        bus = ApplicationEventBus()
        wire_finance(bus, bootstrapped_conn)
        result = finance_periodic_tick(bootstrapped_conn, bus, today=TODAY)
        assert result["losses"]["dispatched"] == 1
        assert bootstrapped_conn.execute("SELECT status FROM loss_outbox").fetchone()[0] \
            == "DISPATCHED"
        assert _balance(bootstrapped_conn, "5110") == Decimal("350.00")
        assert finance_periodic_tick(bootstrapped_conn, bus, today=TODAY)["losses"]["pending"] == 0

    def test_without_finance_the_loss_stays_visible(self, bootstrapped_conn, loss_outbox):
        loss_outbox(_loss_event())
        result = finance_periodic_tick(bootstrapped_conn, ApplicationEventBus(), today=TODAY)
        assert result["losses"]["failed"] == 1
        status, attempts, error = bootstrapped_conn.execute(
            "SELECT status, attempt_count, last_error FROM loss_outbox").fetchone()
        assert (status, attempts) == ("FAILED", 1) and "consumidor" in error


def _sale(**overrides):
    payload = {
        "event_id": new_uuid(), "operation_id": new_uuid(), "sale_id": new_uuid(),
        "folio": "V-R2", "occurred_at": "2026-07-16T12:00:00", "branch_id": new_uuid(),
        "customer_id": new_uuid(), "channel": "POS", "currency_code": "MXN",
        "gross_total": "330.00", "discount_total": "30.00", "net_total": "300.00",
        "tax_total": "0.00", "cogs_total": "130.00",
        "settlements": [{"type": "CASH", "amount": "300.00"}],
        "lines": [
            {"product_id": "p-res", "quantity": "1.5", "amount": "200.00", "unit_cost": "60"},
            {"product_id": "p-pollo", "quantity": "2", "amount": "130.00", "unit_cost": "20"},
        ],
    }
    payload.update(overrides)
    return payload


class TestProfitabilityFacts:
    def _facts(self, conn, fact_type="SALE"):
        return conn.execute(
            "SELECT product_id, net_revenue, discount, cost_of_sales FROM profitability_facts"
            " WHERE fact_type=? ORDER BY line_reference", (fact_type,)).fetchall()

    def test_sale_lines_reconcile_with_the_ledger(self, bootstrapped_conn):
        sale = _sale()
        SaleCompletedHandler(bootstrapped_conn).handle(sale)
        facts = self._facts(bootstrapped_conn)
        assert [f[0] for f in facts] == ["p-res", "p-pollo"]
        revenue = sum((Decimal(f[1]) for f in facts), Decimal("0"))
        discount = sum((Decimal(f[2]) for f in facts), Decimal("0"))
        cost = sum((Decimal(f[3]) for f in facts), Decimal("0"))
        # El mayor: ingreso 330 (sin IVA) - descuento 30; costo 130.
        assert (revenue, discount, cost) == (Decimal("300.00"), Decimal("30.00"),
                                             Decimal("130.00"))
        assert -_balance(bootstrapped_conn, "4101") - _balance(bootstrapped_conn, "4201") \
            == revenue
        assert facts[0][3] == "90.00"  # 1.5 × 60

    def test_redelivered_sale_does_not_duplicate_facts(self, bootstrapped_conn):
        sale = _sale()
        SaleCompletedHandler(bootstrapped_conn).handle(sale)
        SaleCompletedHandler(bootstrapped_conn).handle({**sale, "event_id": new_uuid()})
        assert len(self._facts(bootstrapped_conn)) == 2

    def test_by_product_and_return_and_cancellation(self, bootstrapped_conn):
        sale = _sale()
        SaleCompletedHandler(bootstrapped_conn).handle(sale)
        service = ProfitabilityQueryService(bootstrapped_conn)
        by_product = {r["key"]: r for r in service.by_dimension(
            "product", date_from="2026-07-01", date_to="2026-07-31")}
        assert by_product["p-res"]["gross_margin"] == "91.82"
        SaleReturnedHandler(bootstrapped_conn).handle({
            "event_id": new_uuid(), "operation_id": new_uuid(), "sale_id": sale["sale_id"],
            "return_id": new_uuid(), "folio": "V-R2", "occurred_at": "2026-07-17T12:00:00",
            "branch_id": sale["branch_id"], "currency_code": "MXN", "amount": "50.00",
            "gross_amount": "50.00", "tax_amount": "0.00", "cogs_amount": "20.00",
            "refunds": [{"type": "CASH", "amount": "50.00"}]})
        by_branch = service.by_dimension("branch", date_from="2026-07-01",
                                         date_to="2026-07-31")
        assert by_branch[0]["net_revenue"] == "250.00"
        SaleReversedHandler(bootstrapped_conn).handle({
            "event_id": new_uuid(), "operation_id": new_uuid(), "sale_id": sale["sale_id"],
            "occurred_at": "2026-07-18T12:00:00", "reason": "Cancelada"})
        by_branch = service.by_dimension("branch", date_from="2026-07-01",
                                         date_to="2026-07-31")
        assert by_branch[0]["net_revenue"] == "-50.00"  # sólo queda la devolución
