"""Read model tests for cash movement reason catalogs."""

from __future__ import annotations

import unittest

from backend.application.cash_register.movement_reason_query_service import (
    CashMovementReasonQueryService,
)


class _Reader:
    def __init__(self) -> None:
        self.calls = []

    def list_active(self, *, movement_type: str, occurred_at: str) -> list[dict]:
        self.calls.append((movement_type, occurred_at))
        return [
            {
                "code": "EXCESS_CASH",
                "display_name": "Exceso de efectivo",
                "movement_type": movement_type,
                "requires_authorization": 0,
            }
        ]


class CashMovementReasonQueryServiceTests(unittest.TestCase):
    def test_lists_active_reason_options_for_movement_type(self):
        reader = _Reader()
        service = CashMovementReasonQueryService(reader)

        rows = service.list_active("safe_drop")

        self.assertEqual(reader.calls[0][0], "SAFE_DROP")
        self.assertEqual(rows[0].code, "EXCESS_CASH")
        self.assertEqual(rows[0].display_name, "Exceso de efectivo")
        self.assertFalse(rows[0].requires_authorization)

    def test_empty_movement_type_returns_no_options(self):
        service = CashMovementReasonQueryService(_Reader())
        self.assertEqual(service.list_active(""), ())


if __name__ == "__main__":
    unittest.main()
