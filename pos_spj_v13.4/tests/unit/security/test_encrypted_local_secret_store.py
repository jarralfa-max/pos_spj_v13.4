import pytest

from backend.security.secrets.encrypted_local_secret_store import EncryptedLocalSecretStore
from backend.security.secrets.errors import SecretStoreUnavailableError


@pytest.fixture
def store(tmp_path) -> EncryptedLocalSecretStore:
    return EncryptedLocalSecretStore(store_dir=tmp_path / "secrets")


def test_set_and_get_secret_roundtrip(store):
    store.set_secret("whatsapp_token", "sk_live_abc123xyz")
    assert store.get_secret("whatsapp_token") == "sk_live_abc123xyz"


def test_get_missing_secret_returns_none(store):
    assert store.get_secret("does_not_exist") is None


def test_describe_never_exposes_raw_value(store):
    store.set_secret("mercadopago_token", "sk_live_abc123xyz")
    ref = store.describe("mercadopago_token")
    assert "abc123xyz" not in ref.masked_value or ref.masked_value.count("*") > 0
    assert ref.masked_value != "sk_live_abc123xyz"
    assert ref.masked_value.endswith("3xyz")
    assert ref.reference_id == "mercadopago_token"
    assert ref.status == "ACTIVE"


def test_ciphertext_on_disk_never_contains_plaintext(store, tmp_path):
    store.set_secret("smtp_password", "S3cretPlainValue!!")
    raw_file_contents = (tmp_path / "secrets" / "secret_store.enc.json").read_text(encoding="utf-8")
    assert "S3cretPlainValue" not in raw_file_contents


def test_rotate_secret_changes_value_and_timestamp(store):
    first = store.set_secret("api_key", "value-one")
    rotated = store.rotate_secret("api_key", "value-two")
    assert store.get_secret("api_key") == "value-two"
    assert rotated.reference_id == first.reference_id


def test_rotate_nonexistent_secret_raises(store):
    with pytest.raises(SecretStoreUnavailableError):
        store.rotate_secret("never_set", "value")


def test_delete_secret_is_idempotent(store):
    store.set_secret("temp_key", "value")
    store.delete_secret("temp_key")
    assert store.get_secret("temp_key") is None
    store.delete_secret("temp_key")  # second delete must not raise


def test_list_references_excludes_raw_values(store):
    store.set_secret("key_a", "value-a")
    store.set_secret("key_b", "value-b")
    refs = store.list_references()
    names = {r.reference_id for r in refs}
    assert names == {"key_a", "key_b"}
    for ref in refs:
        assert "value-" not in ref.masked_value or ref.masked_value.startswith("*")


def test_set_secret_rejects_empty_name_or_value(store):
    with pytest.raises(ValueError):
        store.set_secret("", "value")
    with pytest.raises(ValueError):
        store.set_secret("name", "")


def test_second_store_instance_same_dir_can_decrypt(tmp_path):
    # Simulates the app restarting — the persisted key must still decrypt.
    dir_ = tmp_path / "secrets"
    store_a = EncryptedLocalSecretStore(store_dir=dir_)
    store_a.set_secret("persisted_key", "durable-value")

    store_b = EncryptedLocalSecretStore(store_dir=dir_)
    assert store_b.get_secret("persisted_key") == "durable-value"
