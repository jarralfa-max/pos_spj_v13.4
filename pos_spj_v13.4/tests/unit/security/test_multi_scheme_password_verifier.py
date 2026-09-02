import pytest

from backend.security.credentials.password_hasher import Argon2idPasswordHasher, BcryptPasswordHasher
from backend.security.credentials.password_verification import MultiSchemePasswordVerifier


@pytest.fixture
def verifier() -> MultiSchemePasswordVerifier:
    return MultiSchemePasswordVerifier(
        primary=Argon2idPasswordHasher(), legacy=(BcryptPasswordHasher(),),
    )


def test_verifies_primary_scheme_hash_without_rehash(verifier):
    hashed = Argon2idPasswordHasher().hash("Correct-Horse-9!")
    result = verifier.verify("Correct-Horse-9!", hashed)
    assert result.valid is True
    assert result.needs_rehash is False


def test_verifies_legacy_scheme_hash_and_flags_rehash(verifier):
    hashed = BcryptPasswordHasher().hash("Correct-Horse-9!")
    result = verifier.verify("Correct-Horse-9!", hashed)
    assert result.valid is True
    assert result.needs_rehash is True


def test_rejects_wrong_password_against_primary_hash(verifier):
    hashed = Argon2idPasswordHasher().hash("Correct-Horse-9!")
    result = verifier.verify("wrong", hashed)
    assert result.valid is False
    assert result.needs_rehash is False


def test_rejects_wrong_password_against_legacy_hash(verifier):
    hashed = BcryptPasswordHasher().hash("Correct-Horse-9!")
    result = verifier.verify("wrong", hashed)
    assert result.valid is False


def test_rejects_unrecognized_hash_format(verifier):
    result = verifier.verify("Correct-Horse-9!", "not-a-real-hash")
    assert result.valid is False
    assert result.needs_rehash is False


def test_hash_always_uses_primary_scheme(verifier):
    hashed = verifier.hash("Correct-Horse-9!")
    assert hashed.startswith("$argon2id$")


def test_verifier_with_no_legacy_hashers_only_accepts_primary():
    verifier = MultiSchemePasswordVerifier(primary=Argon2idPasswordHasher())
    bcrypt_hash = BcryptPasswordHasher().hash("Correct-Horse-9!")
    result = verifier.verify("Correct-Horse-9!", bcrypt_hash)
    assert result.valid is False


def test_tries_legacy_hashers_in_order():
    calls = []

    class TrackingHasher:
        def __init__(self, name, matches):
            self.name = name
            self._matches = matches

        def verify(self, password, hashed):
            calls.append(self.name)
            return self._matches

        def hash(self, password):
            return f"${self.name}$fake"

        def needs_rehash(self, hashed):
            return False

    primary = TrackingHasher("primary", matches=False)
    legacy_a = TrackingHasher("legacy_a", matches=False)
    legacy_b = TrackingHasher("legacy_b", matches=True)

    verifier = MultiSchemePasswordVerifier(primary=primary, legacy=(legacy_a, legacy_b))
    result = verifier.verify("pw", "somehash")

    assert result.valid is True
    assert calls == ["primary", "legacy_a", "legacy_b"]
