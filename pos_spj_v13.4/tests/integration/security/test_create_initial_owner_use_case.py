import pytest

from backend.security.credentials.password_hasher import BcryptPasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.provisioning.create_initial_owner_use_case import (
    CreateInitialOwnerUseCase,
    OwnerUsernameTakenError,
)
from backend.shared.ids import INSTALL_BRANCH_UUID, SYSTEM_ROLE_UUIDS
from tests.integration._born_clean_db import make_db


@pytest.fixture
def use_case():
    conn = make_db()
    uc = CreateInitialOwnerUseCase(
        conn, password_hasher=BcryptPasswordHasher(), password_policy=PasswordPolicy(),
    )
    return conn, uc


def test_creates_user_with_system_owner_role(use_case):
    conn, uc = use_case
    user_id = uc.execute(
        username="jarralfa", password="Correct-Horse-9!", full_name="Jose Alfaro",
        branch_id=INSTALL_BRANCH_UUID,
    )
    row = conn.execute(
        "SELECT id, nombre, usuario, rol, sucursal_id, activo, recovery_contact "
        "FROM usuarios WHERE id = ?", (user_id,),
    ).fetchone()
    assert row["usuario"] == "jarralfa"
    assert row["rol"] == "system_owner"
    assert row["activo"] == 1
    assert row["sucursal_id"] == INSTALL_BRANCH_UUID


def test_password_is_hashed_not_stored_plaintext(use_case):
    conn, uc = use_case
    user_id = uc.execute(
        username="jarralfa", password="Correct-Horse-9!", full_name="Jose Alfaro",
        branch_id=INSTALL_BRANCH_UUID,
    )
    stored_hash = conn.execute(
        "SELECT password_hash FROM usuarios WHERE id = ?", (user_id,)
    ).fetchone()[0]
    assert "Correct-Horse-9!" not in stored_hash
    assert stored_hash.startswith(("$2b$", "$2a$", "$2y$"))


def test_recovery_contact_is_persisted(use_case):
    conn, uc = use_case
    user_id = uc.execute(
        username="jarralfa", password="Correct-Horse-9!", full_name="Jose Alfaro",
        branch_id=INSTALL_BRANCH_UUID, recovery_contact="jarr.alfa@gmail.com",
    )
    contact = conn.execute(
        "SELECT recovery_contact FROM usuarios WHERE id = ?", (user_id,)
    ).fetchone()[0]
    assert contact == "jarr.alfa@gmail.com"


def test_duplicate_username_raises(use_case):
    conn, uc = use_case
    uc.execute(username="jarralfa", password="Correct-Horse-9!", full_name="Jose",
               branch_id=INSTALL_BRANCH_UUID)
    with pytest.raises(OwnerUsernameTakenError):
        uc.execute(username="jarralfa", password="Another-Strong-9!", full_name="Jose 2",
                   branch_id=INSTALL_BRANCH_UUID)


def test_rejects_weak_password(use_case):
    conn, uc = use_case
    with pytest.raises(Exception):
        uc.execute(username="jarralfa", password="weak", full_name="Jose",
                   branch_id=INSTALL_BRANCH_UUID)


def test_owner_role_id_matches_system_role_uuids(use_case):
    _, uc = use_case
    assert uc.owner_role_id() == SYSTEM_ROLE_UUIDS["system_owner"]


def test_created_owner_has_full_permission_grants(use_case):
    conn, uc = use_case
    uc.execute(username="jarralfa", password="Correct-Horse-9!", full_name="Jose",
               branch_id=INSTALL_BRANCH_UUID)
    role_id = SYSTEM_ROLE_UUIDS["system_owner"]
    grant_count = conn.execute(
        "SELECT COUNT(*) FROM rol_permisos WHERE rol_id = ? AND permitido = 1", (role_id,)
    ).fetchone()[0]
    assert grant_count > 0
