from decimal import Decimal
import unittest

from backend.application.cash_register.permissions import CashPermissions
from backend.application.cash_register.x_cut_query_service import XCutQueryService


class _Auth:
    def __init__(self, *, sensitive: bool = True):
        self.calls = []
        self.sensitive = sensitive

    def require(self, **kwargs):
        self.calls.append(kwargs)

    def has_permission(self, **kwargs):
        return self.sensitive


class _Repo:
    def __init__(self, connection):
        pass

    def list_x_for_branch(self, *, branch_id: str, limit: int = 100):
        return [{
            "id": "x-1", "shift_id": "shift-1", "branch_id": branch_id,
            "cut_type": "X", "document_number": "X-0001",
            "expected_cash": "825.50", "snapshot_json": '{"movement_count":"4"}',
            "generated_by": "cashier-1", "generated_at": "2026-08-12T12:00:00+00:00",
        }]

    def get(self, cut_id: str):
        row = self.list_x_for_branch(branch_id="branch-1")[0]
        row["id"] = cut_id
        return row


class CashXCutQueryServiceTests(unittest.TestCase):
    def test_lists_x_cuts_with_sensitive_amounts_when_authorized(self):
        import backend.application.cash_register.x_cut_query_service as module
        original = module.CashCutRepository
        module.CashCutRepository = _Repo
        auth = _Auth(sensitive=True)
        try:
            rows = XCutQueryService(object(), auth).list_for_branch(
                branch_id="branch-1", requester_user_id="user-1")
        finally:
            module.CashCutRepository = original

        self.assertEqual(auth.calls[0]["permission_code"], CashPermissions.X_CUT_VIEW)
        self.assertEqual(rows[0].document_number, "X-0001")
        self.assertEqual(rows[0].expected_cash, Decimal("825.50"))
        self.assertEqual(rows[0].snapshot, {"movement_count": "4"})
        self.assertFalse(rows[0].final)

    def test_redacts_sensitive_amounts_without_sensitive_permission(self):
        import backend.application.cash_register.x_cut_query_service as module
        original = module.CashCutRepository
        module.CashCutRepository = _Repo
        try:
            rows = XCutQueryService(object(), _Auth(sensitive=False)).list_for_branch(
                branch_id="branch-1", requester_user_id="user-1")
        finally:
            module.CashCutRepository = original

        self.assertIsNone(rows[0].expected_cash)
        self.assertIsNone(rows[0].snapshot)
        self.assertFalse(rows[0].sensitive_amounts_visible)


if __name__ == "__main__":
    unittest.main()
