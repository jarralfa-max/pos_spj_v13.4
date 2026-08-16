from decimal import Decimal
import unittest

from backend.application.cash_register.permissions import CashPermissions
from backend.application.cash_register.z_cut_query_service import CashZCutQueryService


class _Auth:
    def __init__(self, *, sensitive: bool = True):
        self.calls = []
        self.sensitive = sensitive

    def require(self, **kwargs):
        self.calls.append(kwargs)

    def has_permission(self, **kwargs):
        self.calls.append(kwargs)
        return self.sensitive


class _Repo:
    def __init__(self, connection):
        pass

    def list_z_for_branch(self, *, branch_id: str, limit: int = 100):
        return [{
            "id": "z-1", "shift_id": "shift-1", "branch_id": branch_id,
            "cut_type": "Z", "document_number": "Z-0001",
            "expected_cash": "500.25", "counted_cash": "450.25",
            "difference": "-50.00", "blind_count_id": "count-1",
            "generated_by": "supervisor-1", "generated_at": "2026-08-12T12:00:00+00:00",
            "is_final": 1, "snapshot_json": '{"movement.CASH_SALE":"950.50"}',
        }]

    def get(self, cut_id: str):
        row = self.list_z_for_branch(branch_id="branch-1")[0]
        row["id"] = cut_id
        return row


class CashZCutQueryServiceTests(unittest.TestCase):
    def test_lists_z_cuts_as_decimal_dtos_and_requires_view_permission(self):
        import backend.application.cash_register.z_cut_query_service as module
        original = module.CashCutRepository
        module.CashCutRepository = _Repo
        auth = _Auth()
        try:
            rows = CashZCutQueryService(object(), auth).list_for_branch(
                branch_id="branch-1", requester_user_id="user-1")
        finally:
            module.CashCutRepository = original

        self.assertEqual(auth.calls[0]["permission_code"], CashPermissions.Z_CUT_VIEW)
        self.assertEqual(rows[0].document_number, "Z-0001")
        self.assertEqual(rows[0].expected_cash, Decimal("500.25"))
        self.assertEqual(rows[0].counted_cash, Decimal("450.25"))
        self.assertEqual(rows[0].difference, Decimal("-50.00"))
        self.assertEqual(rows[0].snapshot, {"movement.CASH_SALE": "950.50"})
        self.assertTrue(rows[0].sensitive_amounts_visible)
        self.assertTrue(rows[0].is_final)

    def test_redacts_z_cut_sensitive_amounts_without_permission(self):
        import backend.application.cash_register.z_cut_query_service as module
        original = module.CashCutRepository
        module.CashCutRepository = _Repo
        auth = _Auth(sensitive=False)
        try:
            rows = CashZCutQueryService(object(), auth).list_for_branch(
                branch_id="branch-1", requester_user_id="user-1")
        finally:
            module.CashCutRepository = original

        self.assertEqual(auth.calls[0]["permission_code"], CashPermissions.Z_CUT_VIEW)
        self.assertEqual(auth.calls[1]["permission_code"], CashPermissions.VIEW_SENSITIVE_AMOUNTS)
        self.assertEqual(rows[0].document_number, "Z-0001")
        self.assertIsNone(rows[0].expected_cash)
        self.assertIsNone(rows[0].counted_cash)
        self.assertIsNone(rows[0].difference)
        self.assertIsNone(rows[0].snapshot)
        self.assertFalse(rows[0].sensitive_amounts_visible)


if __name__ == "__main__":
    unittest.main()
