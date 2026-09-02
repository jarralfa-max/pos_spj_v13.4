import pytest

from backend.security.credentials.password_hasher import Argon2idPasswordHasher, BcryptPasswordHasher


@pytest.fixture
def hasher() -> Argon2idPasswordHasher:
    return Argon2idPasswordHasher()


def test_hash_produces_argon2id_prefix(hasher):
    hashed = hasher.hash("Correct-Horse-Battery-9")
    assert hashed.startswith("$argon2id$")


def test_hash_never_returns_plaintext(hasher):
    plaintext = "Correct-Horse-Battery-9"
    hashed = hasher.hash(plaintext)
    assert plaintext not in hashed


def test_verify_accepts_correct_password(hasher):
    hashed = hasher.hash("Correct-Horse-Battery-9")
    assert hasher.verify("Correct-Horse-Battery-9", hashed) is True


def test_verify_rejects_wrong_password(hasher):
    hashed = hasher.hash("Correct-Horse-Battery-9")
    assert hasher.verify("wrong-password", hashed) is False


def test_verify_rejects_foreign_hash_formats(hasher):
    # bcrypt-shaped and SHA-256-shaped hashes must never verify as valid —
    # no silent fallback to a weaker scheme.
    assert hasher.verify("admin123", "$2b$12$abcdefghijklmnopqrstuv") is False
    assert hasher.verify("admin123", "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a") is False


def test_verify_handles_empty_inputs_safely(hasher):
    assert hasher.verify("", "") is False
    assert hasher.verify("something", "") is False
    assert hasher.verify("", "$argon2id$v=19$m=19456,t=2,p=1$abc$def") is False


def test_two_hashes_of_same_password_differ(hasher):
    # Salted — must never produce identical ciphertext for identical input.
    first = hasher.hash("Correct-Horse-Battery-9")
    second = hasher.hash("Correct-Horse-Battery-9")
    assert first != second
    assert hasher.verify("Correct-Horse-Battery-9", first)
    assert hasher.verify("Correct-Horse-Battery-9", second)


def test_needs_rehash_true_for_foreign_hash(hasher):
    assert hasher.needs_rehash("$2b$12$abcdefghijklmnopqrstuv") is True
    assert hasher.needs_rehash("") is True


def test_needs_rehash_false_for_current_params(hasher):
    hashed = hasher.hash("Correct-Horse-Battery-9")
    assert hasher.needs_rehash(hashed) is False


def test_needs_rehash_true_when_parameters_weaken():
    strong = Argon2idPasswordHasher(time_cost=4, memory_cost_kib=32 * 1024)
    weak = Argon2idPasswordHasher(time_cost=1, memory_cost_kib=8 * 1024)
    hashed = weak.hash("Correct-Horse-Battery-9")
    assert strong.needs_rehash(hashed) is True


def test_hash_rejects_empty_password(hasher):
    with pytest.raises(ValueError):
        hasher.hash("")


# ── BcryptPasswordHasher — matches today's live verifier ────────────────────

@pytest.fixture
def bcrypt_hasher() -> BcryptPasswordHasher:
    return BcryptPasswordHasher()


def test_bcrypt_hash_produces_bcrypt_prefix(bcrypt_hasher):
    hashed = bcrypt_hasher.hash("Correct-Horse-Battery-9")
    assert hashed.startswith(("$2b$", "$2a$", "$2y$"))


def test_bcrypt_verify_accepts_correct_password(bcrypt_hasher):
    hashed = bcrypt_hasher.hash("Correct-Horse-Battery-9")
    assert bcrypt_hasher.verify("Correct-Horse-Battery-9", hashed) is True


def test_bcrypt_verify_rejects_wrong_password(bcrypt_hasher):
    hashed = bcrypt_hasher.hash("Correct-Horse-Battery-9")
    assert bcrypt_hasher.verify("wrong-password", hashed) is False


def test_bcrypt_verify_rejects_argon2id_hash(bcrypt_hasher):
    argon2_hash = Argon2idPasswordHasher().hash("Correct-Horse-Battery-9")
    assert bcrypt_hasher.verify("Correct-Horse-Battery-9", argon2_hash) is False


def test_bcrypt_needs_rehash_true_for_argon2id_hash(bcrypt_hasher):
    argon2_hash = Argon2idPasswordHasher().hash("Correct-Horse-Battery-9")
    assert bcrypt_hasher.needs_rehash(argon2_hash) is True


def test_bcrypt_needs_rehash_false_for_own_hash(bcrypt_hasher):
    hashed = bcrypt_hasher.hash("Correct-Horse-Battery-9")
    assert bcrypt_hasher.needs_rehash(hashed) is False


def test_argon2id_needs_rehash_true_for_bcrypt_hash():
    # This is the cross-hasher check that drives SHELL-7's on-login
    # migration: once the live app switches to Argon2idPasswordHasher, an
    # existing bcrypt hash must be flagged for rehash.
    bcrypt_hash = BcryptPasswordHasher().hash("Correct-Horse-Battery-9")
    assert Argon2idPasswordHasher().needs_rehash(bcrypt_hash) is True


def test_bcrypt_hash_rejects_empty_password(bcrypt_hasher):
    with pytest.raises(ValueError):
        bcrypt_hasher.hash("")
