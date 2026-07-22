"""INV-22 unit — RetryPolicy exponential backoff (§57)."""

from backend.domain.inventory.services.retry_policy import RetryPolicy


class TestRetryPolicy:
    def test_exponential_backoff(self):
        p = RetryPolicy(base_seconds=2, factor=2, max_seconds=3600)
        assert p.next_delay_seconds(1) == 2
        assert p.next_delay_seconds(2) == 4
        assert p.next_delay_seconds(3) == 8
        assert p.next_delay_seconds(4) == 16

    def test_delay_is_capped(self):
        p = RetryPolicy(base_seconds=10, factor=10, max_seconds=100)
        assert p.next_delay_seconds(5) == 100  # would be 100000, capped

    def test_should_retry_until_cap(self):
        p = RetryPolicy(max_attempts=3)
        assert p.should_retry(1) and p.should_retry(2)
        assert not p.should_retry(3)

    def test_delay_floor_at_first_attempt(self):
        p = RetryPolicy(base_seconds=5)
        assert p.next_delay_seconds(0) == 5  # treated as first attempt
