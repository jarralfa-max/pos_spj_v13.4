"""Tests for delivery defects 5,6 — auto-printing on transitions.

Defect 5: print the driver operative ticket when the order goes out for delivery.
Defect 6: print the customer receipt when the order is delivered.
Both must be idempotent (a retry never prints twice) and must never revert a
committed state change on printer failure.
"""
from __future__ import annotations

import sqlite3

import pytest

from core.delivery.application.print_coordinator import DeliveryPrintCoordinator
from core.delivery.domain.print_policy import DeliveryDocument, DeliveryPrintPolicy


# ── DeliveryPrintPolicy (pure domain) ────────────────────────────────────────

@pytest.fixture
def policy():
    return DeliveryPrintPolicy()


def test_dispatch_prints_driver_ticket(policy):
    """Defect 5: en_ruta (dispatch) → driver operative ticket for delivery flow."""
    docs = policy.documents_for("en_ruta", "delivery")
    assert docs == (DeliveryDocument.DRIVER_OPERATIVE,)


def test_dispatch_no_driver_ticket_for_counter(policy):
    """Counter/pickup flow has no dispatch → no driver ticket."""
    assert policy.documents_for("en_ruta", "counter") == ()
    assert policy.documents_for("en_ruta", "pickup") == ()


def test_delivered_prints_customer_receipt(policy):
    """Defect 6: entregado → customer receipt."""
    assert policy.documents_for("entregado", "delivery") == (DeliveryDocument.CUSTOMER_RECEIPT,)
    assert policy.documents_for("entregado", "counter") == (DeliveryDocument.CUSTOMER_RECEIPT,)


def test_other_statuses_print_nothing(policy):
    assert policy.documents_for("pendiente", "delivery") == ()
    assert policy.documents_for("preparacion", "delivery") == ()
    assert policy.documents_for("cancelado", "delivery") == ()


# ── DeliveryPrintCoordinator (idempotency + failure isolation) ───────────────

class _FakePrinter:
    def __init__(self, ok=True):
        self.ok = ok
        self.driver_calls = 0
        self.customer_calls = 0

    def print_driver_ticket(self, order_id):
        self.driver_calls += 1
        return self.ok

    def print_customer_ticket(self, order_id):
        self.customer_calls += 1
        return self.ok


@pytest.fixture
def print_db():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE delivery_print_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delivery_id INTEGER NOT NULL,
            document_type TEXT NOT NULL,
            operation_id TEXT,
            printer_id TEXT,
            status TEXT DEFAULT 'printed',
            printed_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        "CREATE UNIQUE INDEX uq_delivery_print_doc ON delivery_print_log(delivery_id, document_type)"
    )
    conn.commit()
    return conn


def test_coordinator_prints_driver_on_dispatch(print_db):
    printer = _FakePrinter(ok=True)
    coord = DeliveryPrintCoordinator(print_db, printer_factory=lambda: printer)
    coord.print_for_transition({"id": 1, "workflow_type": "delivery"}, "en_ruta")
    assert printer.driver_calls == 1
    assert printer.customer_calls == 0


def test_coordinator_prints_customer_on_delivered(print_db):
    printer = _FakePrinter(ok=True)
    coord = DeliveryPrintCoordinator(print_db, printer_factory=lambda: printer)
    coord.print_for_transition({"id": 1, "workflow_type": "delivery"}, "entregado")
    assert printer.customer_calls == 1


def test_coordinator_idempotent_no_double_print(print_db):
    """Defect 5/6: a retry must not print the same document twice."""
    printer = _FakePrinter(ok=True)
    coord = DeliveryPrintCoordinator(print_db, printer_factory=lambda: printer)
    order = {"id": 1, "workflow_type": "delivery"}
    coord.print_for_transition(order, "en_ruta")
    coord.print_for_transition(order, "en_ruta")  # retry
    assert printer.driver_calls == 1


def test_coordinator_failure_records_pending_and_allows_reprint(print_db):
    """A printer failure records 'pending' and a later attempt re-prints."""
    failing = _FakePrinter(ok=False)
    coord = DeliveryPrintCoordinator(print_db, printer_factory=lambda: failing)
    order = {"id": 1, "workflow_type": "delivery"}
    coord.print_for_transition(order, "entregado")
    assert failing.customer_calls == 1
    row = print_db.execute(
        "SELECT status FROM delivery_print_log WHERE delivery_id=1 AND document_type='customer_receipt'"
    ).fetchone()
    assert row[0] == "pending"
    # Now the printer works → re-print succeeds and promotes to 'printed'
    ok_printer = _FakePrinter(ok=True)
    coord2 = DeliveryPrintCoordinator(print_db, printer_factory=lambda: ok_printer)
    coord2.print_for_transition(order, "entregado")
    assert ok_printer.customer_calls == 1
    row = print_db.execute(
        "SELECT status FROM delivery_print_log WHERE delivery_id=1 AND document_type='customer_receipt'"
    ).fetchone()
    assert row[0] == "printed"


def test_coordinator_never_raises_on_printer_exception(print_db):
    class _Boom:
        def print_customer_ticket(self, order_id):
            raise RuntimeError("printer offline")

    coord = DeliveryPrintCoordinator(print_db, printer_factory=lambda: _Boom())
    # Must not raise
    coord.print_for_transition({"id": 1, "workflow_type": "delivery"}, "entregado")
    row = print_db.execute(
        "SELECT status FROM delivery_print_log WHERE delivery_id=1"
    ).fetchone()
    assert row[0] == "pending"


def test_change_status_uc_accepts_print_coordinator():
    """The UC exposes a print_coordinator parameter (wiring guard)."""
    import inspect
    from core.delivery.application.change_delivery_status import ChangeDeliveryStatusUseCase
    sig = inspect.signature(ChangeDeliveryStatusUseCase.__init__)
    assert "print_coordinator" in sig.parameters
