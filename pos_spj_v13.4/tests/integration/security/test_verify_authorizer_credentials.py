"""VerifyAuthorizerCredentialsUseCase — el autorizador se prueba con su clave.

Antes el POS identificaba al autorizador por un UUID tecleado y Caja descartaba
la contraseña que capturaba: el "segundo par de ojos" era el nombre del gerente
escrito por el cajero. Estas pruebas fijan que se aplican las reglas del login
(clave, cuenta activa, bloqueo por intentos) sin abrir sesión.
"""

from datetime import datetime, timedelta, timezone

import pytest

from backend.security.authentication.authentication_attempt_repository import (
    SqliteAuthenticationAttemptRepository,
)
from backend.security.authentication.errors import AuthenticationFailedError
from backend.security.authentication.user_credentials import SqliteUserCredentialsRepository
from backend.security.authentication.verify_authorizer_credentials_use_case import (
    VerifyAuthorizerCredentialsUseCase,
    build_authorizer_credentials_verifier,
)
from backend.security.credentials.password_hasher import (
    Argon2idPasswordHasher,
    BcryptPasswordHasher,
)
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.credentials.password_verification import MultiSchemePasswordVerifier
from backend.security.provisioning.installation_repository import SqliteInstallationRepository
from backend.security.provisioning.provision_installation_use_case import (
    ProvisionInstallationUseCase,
)
from backend.security.provisioning.recovery_code_repository import SqliteRecoveryCodeRepository
from backend.security.sessions.account_lockout_policy import AccountLockoutPolicy
from backend.security.sessions.errors import AccountLockedError
from tests.integration._born_clean_db import make_db

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
PASSWORD = "Correct-Horse-9!"


@pytest.fixture
def conn():
    c = make_db()
    ProvisionInstallationUseCase(
        c, installation_repository=SqliteInstallationRepository(c),
        recovery_code_repository=SqliteRecoveryCodeRepository(c),
        password_hasher=BcryptPasswordHasher(), password_policy=PasswordPolicy(),
    ).execute(company_name="SPJ", branch_name="Centro", owner_username="gerente",
              workstation_name="Caja 1", owner_password=PASSWORD,
              owner_full_name="Gerente", now=T0)
    c.commit()
    yield c
    c.close()


def _verifier(conn, *, limit=5):
    return VerifyAuthorizerCredentialsUseCase(
        credentials_repository=SqliteUserCredentialsRepository(conn),
        attempt_repository=SqliteAuthenticationAttemptRepository(conn),
        password_verifier=MultiSchemePasswordVerifier(
            primary=Argon2idPasswordHasher(), legacy=(BcryptPasswordHasher(),)),
        lockout_policy=AccountLockoutPolicy(failed_attempt_limit=limit,
                                            lockout_duration_seconds=900))


def _user_id(conn, username="gerente"):
    return conn.execute("SELECT id FROM usuarios WHERE usuario=?", (username,)).fetchone()[0]


def test_usuario_y_clave_correctos_devuelven_su_id(conn):
    assert _verifier(conn).execute(username="gerente", password=PASSWORD, now=T0) == \
        _user_id(conn)


def test_una_clave_mala_no_autoriza(conn):
    with pytest.raises(AuthenticationFailedError):
        _verifier(conn).execute(username="gerente", password="otra", now=T0)


def test_un_usuario_inexistente_falla_igual_que_una_clave_mala(conn):
    with pytest.raises(AuthenticationFailedError) as inexistente:
        _verifier(conn).execute(username="fantasma", password=PASSWORD, now=T0)
    with pytest.raises(AuthenticationFailedError) as mala:
        _verifier(conn).execute(username="gerente", password="otra", now=T0)
    assert str(inexistente.value) == str(mala.value)


def test_sin_clave_no_hay_autorizacion(conn):
    """El defecto que cierra: el usuario solo, sin clave, ya no basta."""
    with pytest.raises(AuthenticationFailedError):
        _verifier(conn).execute(username="gerente", password="", now=T0)


def test_una_cuenta_inactiva_no_autoriza(conn):
    conn.execute("UPDATE usuarios SET activo=0 WHERE usuario='gerente'")
    conn.commit()
    with pytest.raises(AuthenticationFailedError):
        _verifier(conn).execute(username="gerente", password=PASSWORD, now=T0)


def test_adivinar_la_clave_desde_el_mostrador_bloquea_la_cuenta(conn):
    """Los intentos cuentan igual que en el login: probar claves del gerente
    desde el mostrador lo bloquea, y durante el bloqueo ni la clave buena sirve."""
    verifier = _verifier(conn, limit=3)
    for i in range(3):
        with pytest.raises(AuthenticationFailedError):
            verifier.execute(username="gerente", password=f"mala-{i}",
                             now=T0 + timedelta(seconds=i))
    with pytest.raises(AccountLockedError):
        verifier.execute(username="gerente", password=PASSWORD, now=T0 + timedelta(seconds=5))


def test_verificar_no_abre_sesion_ni_cambia_la_clave(conn):
    """Sólo prueba identidad: no hay sesión nueva y el hash no se reescribe
    (el rehash del login es efecto del login, no de autorizar)."""
    antes = conn.execute("SELECT password_hash FROM usuarios WHERE usuario='gerente'").fetchone()[0]
    _verifier(conn).execute(username="gerente", password=PASSWORD, now=T0)
    despues = conn.execute("SELECT password_hash FROM usuarios WHERE usuario='gerente'").fetchone()[0]
    assert antes == despues


def test_la_fabrica_usa_las_piezas_del_login(conn):
    assert build_authorizer_credentials_verifier(conn).execute(
        username="gerente", password=PASSWORD) == _user_id(conn)
