import pytest

from backend.security.credentials.errors import PasswordPolicyViolationError
from backend.security.credentials.password_policy import PasswordPolicy


@pytest.fixture
def policy() -> PasswordPolicy:
    return PasswordPolicy()


def test_accepts_strong_password(policy):
    policy.validate("Correct-Horse-9!")  # does not raise


def test_rejects_too_short_password(policy):
    with pytest.raises(PasswordPolicyViolationError) as exc:
        policy.validate("Ab1!ab1!")
    assert any("caracteres" in v for v in exc.value.violations)


def test_rejects_missing_uppercase(policy):
    with pytest.raises(PasswordPolicyViolationError) as exc:
        policy.validate("correct-horse-9!")
    assert any("mayúscula" in v for v in exc.value.violations)


def test_rejects_missing_lowercase(policy):
    with pytest.raises(PasswordPolicyViolationError) as exc:
        policy.validate("CORRECT-HORSE-9!")
    assert any("minúscula" in v for v in exc.value.violations)


def test_rejects_missing_number(policy):
    with pytest.raises(PasswordPolicyViolationError) as exc:
        policy.validate("Correct-Horse-Battery!")
    assert any("número" in v for v in exc.value.violations)


def test_rejects_missing_symbol(policy):
    with pytest.raises(PasswordPolicyViolationError) as exc:
        policy.validate("CorrectHorseBattery9")
    assert any("símbolo" in v for v in exc.value.violations)


def test_rejects_common_password(policy):
    with pytest.raises(PasswordPolicyViolationError) as exc:
        policy.validate("admin123")
    assert any("uso común" in v for v in exc.value.violations)


def test_rejects_username_embedded_in_password(policy):
    with pytest.raises(PasswordPolicyViolationError) as exc:
        policy.validate("Jarralfa-2024!", username="jarralfa")
    assert any("nombre de usuario" in v for v in exc.value.violations)


def test_reports_all_violations_at_once(policy):
    # a password that fails length, uppercase, number, and symbol simultaneously
    with pytest.raises(PasswordPolicyViolationError) as exc:
        policy.validate("abc")
    assert len(exc.value.violations) >= 4


def test_is_valid_returns_bool_without_raising(policy):
    assert policy.is_valid("Correct-Horse-9!") is True
    assert policy.is_valid("weak") is False


def test_relaxed_policy_allows_shorter_password():
    relaxed = PasswordPolicy(
        minimum_length=4, require_uppercase=False, require_lowercase=False,
        require_number=False, require_symbol=False, prevent_common_passwords=False,
    )
    relaxed.validate("abcd")  # does not raise
