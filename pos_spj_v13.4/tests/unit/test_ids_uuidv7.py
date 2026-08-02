"""§4.1 — real UUIDv7 generation + validation (version checked, not just pattern)."""

import uuid

import pytest

from backend.shared.ids import (
    INSTALL_BRANCH_UUID,
    is_uuidv7,
    new_uuid,
    new_uuidv7,
    validate_uuidv7,
)


def test_new_uuidv7_is_a_real_v7():
    value = new_uuidv7()
    parsed = uuid.UUID(value)
    assert parsed.version == 7
    assert parsed.variant == uuid.RFC_4122
    assert str(parsed) == value  # canonical lowercase hyphenated
    assert is_uuidv7(value)
    assert validate_uuidv7(value) == value


def test_new_uuid_and_new_uuidv7_are_equivalent_contract():
    for _ in range(50):
        assert is_uuidv7(new_uuid())
        assert is_uuidv7(new_uuidv7())


def test_install_constants_are_valid_v7():
    assert is_uuidv7(INSTALL_BRANCH_UUID)


def test_rejects_uuid4():
    v4 = str(uuid.uuid4())
    assert not is_uuidv7(v4)
    with pytest.raises(ValueError):
        validate_uuidv7(v4)


def test_rejects_int_like_and_empty_and_non_str():
    for bad in ("1", "", "MAIN", "not-a-uuid", None, 1, 123):
        assert not is_uuidv7(bad)
        with pytest.raises(ValueError):
            validate_uuidv7(bad)  # type: ignore[arg-type]


def test_rejects_uppercase_and_urn_forms():
    v7 = new_uuidv7()
    assert not is_uuidv7(v7.upper())        # canonical form is lowercase
    assert not is_uuidv7(f"urn:uuid:{v7}")  # urn form is not canonical
