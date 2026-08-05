import sqlite3
import unittest
from datetime import date

from backend.application.event_handlers.finance.cash_finance_router import CashFinanceEventRouter
from backend.application.services.finance.finance_bootstrap import bootstrap_finance
from backend.domain.finance.enums import PostingPurpose
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.infrastructure.db.schema.finance_schema import create_finance_schema
from backend.shared.ids import new_uuid


OCCURRED = "2026-07-16T20:00:00+00:00"


def event(name, *, entity_id=None, operation_id=None, **payload):
    return {
        "event_id": new_uuid(), "event_name": name,
        "operation_id": operation_id or new_uuid(),
        "entity_id": entity_id or new_uuid(), "branch_id": new_uuid(),
        "user_id": new_uuid(), "timestamp": OCCURRED, "payload": payload,
    }


class CashFinanceTreasuryIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys=ON")
        create_finance_schema(self.db)
        bootstrap_finance(self.db, today=date(2026, 7, 16))
        self.router = CashFinanceEventRouter(self.db)

    def tearDown(self): self.db.close()

    def test_z_cut_posts_counted_cash_and_difference_once(self):
        shift = new_uuid()
        source = event("CASH_Z_CUT_GENERATED", shift_id=shift,
                       expected_cash="5000.00", counted_cash="4950.00")
        self.router.handle(source); self.router.handle(source)
        with FinanceUnitOfWork(self.db) as uow:
            entry = uow.journal_entries.find_by_posting_reference(
                "cash", shift, PostingPurpose.CASH_SHIFT_CLOSE)
        self.assertIsNotNone(entry)
        self.assertTrue(entry.is_balanced())
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM journal_entries WHERE posting_purpose='CASH_SHIFT_CLOSE'"
        ).fetchone()[0], 1)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM finance_outbox WHERE event_name='CASH_DIFFERENCE_DETECTED'"
        ).fetchone()[0], 0)

    def test_difference_refund_and_handover_are_traced_without_double_posting(self):
        messages = [
            event("CASH_DIFFERENCE_DETECTED", shift_id=new_uuid(), amount="-50.00"),
            event("CASH_REFUND_PROCESSED", sale_id=new_uuid(), cash_amount="100.00",
                  finance_event="SALE_REFUNDED"),
            event("CASH_HANDOVER_RECEIVED", shift_id=new_uuid(), received_amount="900.00",
                  treasury_transfer_required=True),
        ]
        for message in messages:
            self.router.handle(message); self.router.handle(message)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM finance_processed_events WHERE event_name LIKE 'CASH_%'"
        ).fetchone()[0], 3)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0], 0)

    def test_confirmed_deposit_moves_general_cash_to_bank_idempotently(self):
        deposit_id, operation_id = new_uuid(), new_uuid()
        source = event("TREASURY_CASH_DEPOSIT_CONFIRMED", entity_id=deposit_id,
                       operation_id=operation_id, amount="2500.00")
        self.router.handle(source); self.router.handle(source)
        with FinanceUnitOfWork(self.db) as uow:
            entry = uow.journal_entries.find_by_posting_reference(
                "treasury", deposit_id, PostingPurpose.CASH_DEPOSIT)
        self.assertIsNotNone(entry)
        self.assertTrue(entry.is_balanced())
        self.assertEqual(entry.total_debits().to_string(), "2500.00")


if __name__ == "__main__": unittest.main()
