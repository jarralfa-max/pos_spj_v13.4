from datetime import datetime, timezone

import pytest

from backend.security.provisioning.recovery_code import (
    RecoveryCode,
    RecoveryCodeStatus,
    generate_backup_code,
    hash_backup_code,
)

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_generate_backup_code_has_expected_shape():
    code = generate_backup_code()
    assert len(code) == 11  # 5 + '-' + 5
    assert code[5] == "-"


def test_generate_backup_code_is_unique():
    assert generate_backup_code() != generate_backup_code()


def test_hash_backup_code_is_case_and_whitespace_insensitive():
    raw = generate_backup_code()
    assert hash_backup_code(raw) == hash_backup_code(raw.upper())
    assert hash_backup_code(raw) == hash_backup_code(f"  {raw}  ")


def test_hash_backup_code_rejects_empty():
    with pytest.raises(ValueError):
        hash_backup_code("")


def test_issue_creates_active_code():
    code = RecoveryCode.issue("install-1", raw_code="abcde-12345", now=T0)
    assert code.status is RecoveryCodeStatus.ACTIVE
    assert code.is_active() is True
    assert code.code_hash == hash_backup_code("abcde-12345")


def test_redeem_marks_used():
    code = RecoveryCode.issue("install-1", raw_code="abcde-12345", now=T0)
    redeemed = code.redeem(now=T0)
    assert redeemed.status is RecoveryCodeStatus.USED
    assert redeemed.used_at == T0
    assert code.status is RecoveryCodeStatus.ACTIVE  # original untouched


def test_redeem_twice_raises():
    code = RecoveryCode.issue("install-1", raw_code="abcde-12345", now=T0).redeem(now=T0)
    with pytest.raises(ValueError):
        code.redeem(now=T0)


def test_revoke_marks_revoked():
    code = RecoveryCode.issue("install-1", raw_code="abcde-12345", now=T0)
    revoked = code.revoke()
    assert revoked.status is RecoveryCodeStatus.REVOKED
    assert revoked.is_active() is False


def test_revoke_is_idempotent_no_op_on_already_used():
    used = RecoveryCode.issue("install-1", raw_code="abcde-12345", now=T0).redeem(now=T0)
    still_used = used.revoke()
    assert still_used.status is RecoveryCodeStatus.USED
