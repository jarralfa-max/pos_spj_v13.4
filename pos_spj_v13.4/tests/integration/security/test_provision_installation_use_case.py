from datetime import datetime, timezone

import pytest

from backend.security.credentials.password_hasher import BcryptPasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.provisioning.errors import InstallationAlreadyProvisionedError
from backend.security.provisioning.installation import ProvisioningStatus
from backend.security.provisioning.installation_repository import SqliteInstallationRepository
from backend.security.provisioning.installation_status_query import InstallationStatusQuery
from backend.security.provisioning.provision_installation_use_case import ProvisionInstallationUseCase
from backend.security.provisioning.recovery_code_repository import SqliteRecoveryCodeRepository
from tests.integration._born_clean_db import make_db

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _build_use_case(conn, *, audit_sink=None):
    return ProvisionInstallationUseCase(
        conn,
        installation_repository=SqliteInstallationRepository(conn),
        recovery_code_repository=SqliteRecoveryCodeRepository(conn),
        password_hasher=BcryptPasswordHasher(),
        password_policy=PasswordPolicy(),
        audit_sink=audit_sink,
    )


def _execute(uc, **overrides):
    kwargs = dict(
        company_name="Carnicería SPJ", company_rfc="SPJ010101AAA",
        branch_name="Sucursal Centro", branch_address="Av. Principal 123",
        workstation_name="Caja 1",
        owner_username="jarralfa", owner_password="Correct-Horse-9!",
        owner_full_name="Jose Alfaro", owner_recovery_contact="jarr.alfa@gmail.com",
        now=T0,
    )
    kwargs.update(overrides)
    return uc.execute(**kwargs)


def test_provisioning_transitions_installation_to_provisioned():
    conn = make_db()
    uc = _build_use_case(conn)
    status_query = InstallationStatusQuery(SqliteInstallationRepository(conn))

    assert status_query.current_status() is ProvisioningStatus.UNINITIALIZED

    result = _execute(uc)
    conn.commit()

    assert status_query.current_status() is ProvisioningStatus.PROVISIONED
    assert status_query.login_is_available() is True
    assert result.installation.provisioning_status is ProvisioningStatus.PROVISIONED


def test_provisioning_creates_branch_company_and_owner():
    conn = make_db()
    uc = _build_use_case(conn)
    result = _execute(uc)
    conn.commit()

    branch = conn.execute(
        "SELECT nombre FROM sucursales WHERE id = ?", (result.installation.initial_branch_id,)
    ).fetchone()
    assert branch["nombre"] == "Sucursal Centro"

    empresa_nombre = conn.execute(
        "SELECT valor FROM configuraciones WHERE clave='empresa_nombre'"
    ).fetchone()[0]
    assert empresa_nombre == "Carnicería SPJ"

    owner = conn.execute(
        "SELECT usuario, rol FROM usuarios WHERE id = ?", (result.owner_user_id,)
    ).fetchone()
    assert owner["usuario"] == "jarralfa"
    assert owner["rol"] == "system_owner"


def test_provisioning_generates_recovery_codes():
    conn = make_db()
    uc = _build_use_case(conn)
    result = _execute(uc, recovery_code_count=10)
    conn.commit()

    assert len(result.recovery_codes) == 10
    stored_count = conn.execute(
        "SELECT COUNT(*) FROM installation_recovery_codes WHERE installation_id = ? AND status='ACTIVE'",
        (result.installation.id,),
    ).fetchone()[0]
    assert stored_count == 10


def test_owner_account_can_log_in_through_the_live_auth_service():
    conn = make_db()
    uc = _build_use_case(conn)
    _execute(uc)
    conn.commit()

    from core.services.audit_service import AuditService
    from core.services.auth_service import AuthService
    from core.services.security_service import SecurityService
    from repositories.audit_repository import AuditRepository
    from repositories.auth_repository import AuthRepository
    from repositories.security_repository import SecurityRepository

    auth_service = AuthService(
        auth_repo=AuthRepository(conn),
        security_service=SecurityService(SecurityRepository(conn)),
        audit_service=AuditService(AuditRepository(conn)),
    )
    result = auth_service.authenticate("jarralfa", "Correct-Horse-9!")
    assert result["username"] == "jarralfa"
    assert result["rol"] == "system_owner"


def test_double_provisioning_raises():
    conn = make_db()
    uc = _build_use_case(conn)
    _execute(uc)
    conn.commit()

    with pytest.raises(InstallationAlreadyProvisionedError):
        _execute(uc, owner_username="someone_else")


def test_audit_sink_receives_started_and_completed_events():
    conn = make_db()
    events = []
    uc = _build_use_case(conn, audit_sink=lambda e, p: events.append((e, p)))
    _execute(uc)
    conn.commit()

    names = [e for e, _ in events]
    assert "INSTALLATION_PROVISIONING_STARTED" in names
    assert "INSTALLATION_PROVISIONED" in names
    for _, payload in events:
        assert "Correct-Horse-9!" not in str(payload)


def test_rejects_weak_owner_password():
    conn = make_db()
    uc = _build_use_case(conn)
    with pytest.raises(Exception):
        _execute(uc, owner_password="weak")
