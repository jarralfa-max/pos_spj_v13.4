from frontend.desktop.shell.routing.cache_policy import CachePolicy
from frontend.desktop.shell.routing.offline_policy import OfflinePolicy


def test_cache_policy_has_the_four_master_plan_values():
    assert {p.value for p in CachePolicy} == {
        "KEEP_ALIVE", "RECREATE_ON_NAVIGATION", "RECREATE_ON_CONTEXT_CHANGE", "SINGLETON",
    }


def test_offline_policy_has_three_values():
    assert {p.value for p in OfflinePolicy} == {
        "AVAILABLE_OFFLINE", "DEGRADED_OFFLINE", "REQUIRES_ONLINE",
    }
