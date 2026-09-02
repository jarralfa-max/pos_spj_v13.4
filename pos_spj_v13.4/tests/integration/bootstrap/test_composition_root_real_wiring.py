"""CompositionRoot wired with the real SHELL-5 providers — not fakes. Proves
the shared_wiring.py + security_wiring.py registrations actually resolve to
working services, including the cross-provider dependency
(AccountLockoutPolicy reading its thresholds from PasswordPolicy) and a real
password hash/verify round trip.
"""
import pytest

from backend.bootstrap.composition_root import CompositionRoot
from backend.bootstrap.wiring.security_wiring import SecurityModuleProvider
from backend.bootstrap.wiring.shared_wiring import SharedModuleProvider
from backend.security.credentials.password_hasher import Argon2idPasswordHasher, PasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.secrets.encrypted_local_secret_store import EncryptedLocalSecretStore
from backend.security.secrets.secret_store_gateway import SecretStoreGateway
from backend.security.sessions.account_lockout_policy import AccountLockoutPolicy
from backend.shared.app_paths import AppPaths


@pytest.fixture
def container(tmp_path, monkeypatch):
    monkeypatch.setenv("SPJ_APP_DATA_DIR", str(tmp_path / "app_data"))
    root = CompositionRoot([SharedModuleProvider(), SecurityModuleProvider()])
    return root.build()


def test_real_graph_validates_and_builds(container):
    assert container is not None


def test_app_paths_resolves_and_is_a_singleton(container):
    paths = container.resolve(AppPaths)
    assert paths is container.resolve(AppPaths)
    assert paths.user_data_dir.exists()


def test_secret_store_resolves_to_a_recognized_gateway_implementation(container):
    # Confirms the wiring constructs successfully (AppPaths dependency
    # resolved, platform branch taken) without exercising the real Windows
    # Credential Manager here — that backend already has its own dedicated,
    # cleaned-up test coverage in tests/unit/security/.
    store = container.resolve(SecretStoreGateway)
    assert isinstance(store, SecretStoreGateway)


def test_secret_store_portable_fallback_roundtrip_works(tmp_path):
    store = EncryptedLocalSecretStore(store_dir=tmp_path / "secrets_test")
    store.set_secret("smoke", "value123")
    assert store.get_secret("smoke") == "value123"


def test_password_hasher_resolves_to_argon2id_and_works(container):
    hasher = container.resolve(PasswordHasher)
    assert isinstance(hasher, Argon2idPasswordHasher)
    hashed = hasher.hash("Correct-Horse-9!")
    assert hasher.verify("Correct-Horse-9!", hashed) is True


def test_password_hasher_is_a_singleton(container):
    assert container.resolve(PasswordHasher) is container.resolve(PasswordHasher)


def test_password_policy_resolves_and_validates(container):
    policy = container.resolve(PasswordPolicy)
    policy.validate("Correct-Horse-9!")  # must not raise


def test_account_lockout_policy_reads_thresholds_from_password_policy(container):
    policy = container.resolve(PasswordPolicy)
    lockout = container.resolve(AccountLockoutPolicy)
    assert lockout.failed_attempt_limit == policy.failed_attempt_limit
    assert lockout.lockout_duration_seconds == policy.lockout_duration_seconds
