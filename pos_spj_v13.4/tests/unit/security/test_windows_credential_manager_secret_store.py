import sys
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="WindowsCredentialManagerSecretStore requires Windows"
)


@pytest.fixture
def store():
    from backend.security.secrets.windows_credential_manager_secret_store import (
        WindowsCredentialManagerSecretStore,
    )

    try:
        instance = WindowsCredentialManagerSecretStore()
    except Exception as exc:  # pragma: no cover - environment without Credential Manager access
        pytest.skip(f"Windows Credential Manager unavailable in this environment: {exc}")
        return
    yield instance


@pytest.fixture
def secret_name():
    # Namespaced + random so parallel test runs never collide and teardown
    # never touches a credential this test suite didn't create.
    name = f"test_secret_{uuid.uuid4().hex[:12]}"
    yield name
    from backend.security.secrets.windows_credential_manager_secret_store import (
        WindowsCredentialManagerSecretStore,
    )

    WindowsCredentialManagerSecretStore().delete_secret(name)


def test_set_and_get_secret_roundtrip(store, secret_name):
    store.set_secret(secret_name, "sk_live_abc123xyz")
    assert store.get_secret(secret_name) == "sk_live_abc123xyz"


def test_get_missing_secret_returns_none(store):
    assert store.get_secret(f"never_created_{uuid.uuid4().hex}") is None


def test_describe_never_exposes_raw_value(store, secret_name):
    store.set_secret(secret_name, "sk_live_abc123xyz")
    ref = store.describe(secret_name)
    assert ref.masked_value != "sk_live_abc123xyz"
    assert ref.masked_value.endswith("3xyz")
    assert ref.status == "ACTIVE"


def test_rotate_secret_changes_value(store, secret_name):
    store.set_secret(secret_name, "value-one")
    store.rotate_secret(secret_name, "value-two")
    assert store.get_secret(secret_name) == "value-two"


def test_delete_secret_is_idempotent(store, secret_name):
    store.set_secret(secret_name, "value")
    store.delete_secret(secret_name)
    assert store.get_secret(secret_name) is None
    store.delete_secret(secret_name)  # second delete must not raise
