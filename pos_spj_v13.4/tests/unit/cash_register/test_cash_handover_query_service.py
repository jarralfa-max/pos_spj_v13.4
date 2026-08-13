from decimal import Decimal
import unittest

from backend.application.cash_register.handover_query_service import CashHandoverQueryService


class _Reader:
    def list_for_branch(self, *, branch_id: str, limit: int = 100) -> list[dict]:
        return [{
            "id": "handover-1", "shift_id": "shift-1", "amount": "250.00",
            "status": "PREPARED", "prepared_by": "cashier",
            "delivered_by": None, "received_by": None,
            "prepared_at": "2026-08-03T00:00:00+00:00",
            "delivered_at": None, "received_at": None, "dispute_reason": None,
        }]

    def list_denominations(self, handover_id: str) -> list[dict]:
        return [{"denomination_id": "d50", "quantity": 5}]


class CashHandoverQueryServiceTests(unittest.TestCase):
    def test_lists_handovers_and_denominations(self):
        service = CashHandoverQueryService(_Reader())
        rows = service.list_for_branch("branch-1")

        self.assertEqual(rows[0].id, "handover-1")
        self.assertEqual(rows[0].amount, Decimal("250.00"))
        self.assertEqual(rows[0].status, "PREPARED")
        self.assertEqual(service.denomination_quantities("handover-1"), {"d50": 5})

    def test_empty_branch_returns_no_rows(self):
        self.assertEqual(CashHandoverQueryService(_Reader()).list_for_branch(""), ())


if __name__ == "__main__":
    unittest.main()
