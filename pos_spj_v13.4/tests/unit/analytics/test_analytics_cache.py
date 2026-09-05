import pytest

from backend.application.analytics.services.analytics_cache import (
    AnalyticsCache,
    AnalyticsCacheKey,
)
from backend.domain.analytics.enums import ScopePolicy


def _key(**overrides) -> AnalyticsCacheKey:
    fields = dict(
        company_id="company-1",
        scope_policy=ScopePolicy.BRANCH,
        scope_value="branch-1",
        permissions_hash="perm-hash-a",
        filters_signature="period=month",
        metric_version=1,
        dataset_version="ds-1",
    )
    fields.update(overrides)
    return AnalyticsCacheKey(**fields)


@pytest.mark.parametrize("field_name", [
    "company_id", "scope_value", "permissions_hash", "filters_signature", "dataset_version",
])
def test_rejects_empty_required_fields(field_name):
    with pytest.raises(ValueError):
        _key(**{field_name: ""})


def test_different_permissions_hash_is_a_different_key():
    """§63: two users with different permissions must never collide on the
    same cache entry — that would leak data across scopes."""
    key_a = _key(permissions_hash="perm-hash-a")
    key_b = _key(permissions_hash="perm-hash-b")
    cache: AnalyticsCache[str] = AnalyticsCache()
    cache.set(key_a, "value-for-a")
    assert cache.get(key_b) is None
    assert cache.get(key_a) == "value-for-a"


def test_different_metric_version_is_a_different_key():
    cache: AnalyticsCache[str] = AnalyticsCache()
    cache.set(_key(metric_version=1), "v1-result")
    assert cache.get(_key(metric_version=2)) is None


def test_get_missing_key_returns_none():
    cache: AnalyticsCache[str] = AnalyticsCache()
    assert cache.get(_key()) is None


def test_entry_expires_after_ttl():
    clock = {"t": 0.0}
    cache: AnalyticsCache[str] = AnalyticsCache(ttl_seconds=10, clock=lambda: clock["t"])
    key = _key()
    cache.set(key, "fresh")
    clock["t"] = 5.0
    assert cache.get(key) == "fresh"
    clock["t"] = 11.0
    assert cache.get(key) is None


def test_invalidate_single_key_leaves_others():
    cache: AnalyticsCache[str] = AnalyticsCache()
    key_a, key_b = _key(scope_value="branch-1"), _key(scope_value="branch-2")
    cache.set(key_a, "a")
    cache.set(key_b, "b")
    cache.invalidate(key_a)
    assert cache.get(key_a) is None
    assert cache.get(key_b) == "b"


def test_invalidate_all_clears_everything():
    cache: AnalyticsCache[str] = AnalyticsCache()
    cache.set(_key(scope_value="branch-1"), "a")
    cache.set(_key(scope_value="branch-2"), "b")
    cache.invalidate()
    assert cache.get(_key(scope_value="branch-1")) is None
    assert cache.get(_key(scope_value="branch-2")) is None
