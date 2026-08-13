from decimal import Decimal
import unittest

from backend.application.cash_register.difference_query_service import CashDifferenceQueryService


class _Auth:
    def require(self, **kwargs):
        return None


class _Repo:
    def __init__(self, connection):
        pass

    def list_for_branch(self, *, branch_id: str, limit: int = 100):
        return [{
            "id": "diff-1", "shift_id": "shift-1", "z_cut_id": "z-1",
            "branch_id": branch_id, "expected_amount": "500",
            "counted_amount": "450", "amount": "-50",
            "detected_by": "cashier", "responsible_user_id": "cashier",
            "classification": "SHORTAGE", "severity": "REVIEW",
            "tolerance_amount": "10", "recurrence_count": 2,
            "status": "DETECTED", "explanation": None,
            "explained_by": None, "reviewed_by": None,
            "resolution": None, "resolved_by": None,
        }]

    def get(self, difference_id: str):
        row = self.list_for_branch(branch_id="branch-1")[0]
        row["id"] = difference_id
        return row


class CashDifferenceQueryServiceTests(unittest.TestCase):
    def test_lists_branch_differences_as_decimal_dtos(self):
        import backend.application.cash_register.difference_query_service as module
        original = module.CashDifferenceRepository
        module.CashDifferenceRepository = _Repo
        try:
            rows = CashDifferenceQueryService(object(), _Auth()).list_for_branch(
                branch_id="branch-1", requester_user_id="user-1")
        finally:
            module.CashDifferenceRepository = original

        self.assertEqual(rows[0].id, "diff-1")
        self.assertEqual(rows[0].amount, Decimal("-50"))
        self.assertEqual(rows[0].expected_amount, Decimal("500"))
        self.assertEqual(rows[0].recurrence_count, 2)


if __name__ == "__main__":
    unittest.main()
