from datetime import datetime, timezone

import pytest

from backend.security.provisioning.installation_recovery_kit import InstallationRecoveryKit
from backend.security.provisioning.recovery_code_repository import InMemoryRecoveryCodeRepository

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def kit() -> InstallationRecoveryKit:
    return InstallationRecoveryKit(code_repository=InMemoryRecoveryCodeRepository())


def test_generate_returns_requested_count(kit):
    codes = kit.generate("install-1", count=10, now=T0)
    assert len(codes) == 10
    assert len(set(codes)) == 10  # all unique


def test_generate_rejects_non_positive_count(kit):
    with pytest.raises(ValueError):
        kit.generate("install-1", count=0)


def test_redeem_valid_code_returns_true(kit):
    codes = kit.generate("install-1", count=3, now=T0)
    assert kit.redeem("install-1", codes[0], now=T0) is True


def test_redeem_same_code_twice_second_returns_false(kit):
    codes = kit.generate("install-1", count=3, now=T0)
    assert kit.redeem("install-1", codes[0], now=T0) is True
    assert kit.redeem("install-1", codes[0], now=T0) is False


def test_redeem_unknown_code_returns_false(kit):
    kit.generate("install-1", count=3, now=T0)
    assert kit.redeem("install-1", "zzzzz-99999", now=T0) is False


def test_redeem_code_for_wrong_installation_returns_false(kit):
    codes = kit.generate("install-1", count=3, now=T0)
    assert kit.redeem("install-2", codes[0], now=T0) is False


def test_revoke_all_deactivates_every_active_code(kit):
    kit.generate("install-1", count=5, now=T0)
    revoked_count = kit.revoke_all("install-1")
    assert revoked_count == 5


def test_codes_are_unusable_after_revoke_all(kit):
    codes = kit.generate("install-1", count=3, now=T0)
    kit.revoke_all("install-1")
    assert kit.redeem("install-1", codes[0], now=T0) is False


def test_rotate_replaces_all_codes(kit):
    old_codes = kit.generate("install-1", count=5, now=T0)
    new_codes = kit.rotate("install-1", count=5, now=T0)

    assert len(new_codes) == 5
    assert set(old_codes).isdisjoint(set(new_codes))
    assert kit.redeem("install-1", old_codes[0], now=T0) is False
    assert kit.redeem("install-1", new_codes[0], now=T0) is True


def test_revoke_all_on_empty_installation_returns_zero(kit):
    assert kit.revoke_all("no-such-install") == 0
