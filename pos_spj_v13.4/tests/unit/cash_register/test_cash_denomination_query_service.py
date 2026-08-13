"""Read model tests for cash denomination catalogs."""

from __future__ import annotations

from decimal import Decimal
import unittest

from backend.application.cash_register.denomination_query_service import (
    CashDenominationQueryService,
)


class _Reader:
    def list_active_denominations(self) -> list[dict]:
        return [
            {
                "id": "denom-50",
                "display_name": "$50",
                "denomination_value": "50.00",
            }
        ]


class CashDenominationQueryServiceTests(unittest.TestCase):
    def test_lists_active_denominations_as_decimal_options(self):
        rows = CashDenominationQueryService(_Reader()).list_active()

        self.assertEqual(rows[0].id, "denom-50")
        self.assertEqual(rows[0].display_name, "$50")
        self.assertEqual(rows[0].value, Decimal("50.00"))


if __name__ == "__main__":
    unittest.main()
