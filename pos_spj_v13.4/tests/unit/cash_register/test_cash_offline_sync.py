import unittest
from datetime import datetime, timezone

from backend.application.cash_register.offline_sync import retry_at


class CashOfflineSyncPolicyTest(unittest.TestCase):
    def test_retry_is_exponential_and_capped(self):
        now = datetime(2026, 8, 4, tzinfo=timezone.utc)
        self.assertEqual((retry_at(now, 1) - now).total_seconds(), 2)
        self.assertEqual((retry_at(now, 8) - now).total_seconds(), 256)
        self.assertEqual((retry_at(now, 50) - now).total_seconds(), 900)


if __name__ == "__main__": unittest.main()
