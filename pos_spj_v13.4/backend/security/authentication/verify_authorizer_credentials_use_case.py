"""VerifyAuthorizerCredentialsUseCase — quién AUTORIZA, probado con su clave.

QUÉ PASABA (medido el 2026-09-18)
---------------------------------
Toda autorización en caliente del sistema identificaba al autorizador por un
dato que cualquiera puede teclear: el POS pedía el UUID del autorizador en una
caja de texto, y Caja capturaba usuario y contraseña pero **descartaba la
contraseña** (sólo pasaba el usuario). El segundo par de ojos que exige el §62
era, en la práctica, el nombre del gerente escrito por el propio cajero.

QUÉ HACE
--------
Las mismas reglas que el login (`AuthenticateUserUseCase`), sin abrir sesión:

  1. bloqueo por intentos ANTES de mirar si la cuenta existe (no se enumeran
     usuarios);
  2. cuenta inexistente o inactiva → el mismo fallo genérico que una clave mala;
  3. verificación multiesquema (Argon2id + bcrypt heredado);
  4. cada intento se registra, así que adivinar la clave del gerente desde el
     mostrador bloquea su cuenta igual que en el login.

Devuelve el id del usuario. El PERMISO para autorizar lo decide después el
caso de uso con `AuthorizerPermissionChecker`: aquí sólo se prueba quién es.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.security.audit.security_events import (
    USER_AUTHENTICATION_FAILED,
    USER_AUTHENTICATION_SUCCEEDED,
)
from backend.security.authentication.authentication_attempt_repository import (
    AuthenticationAttemptRepository,
    SqliteAuthenticationAttemptRepository,
)
from backend.security.authentication.errors import AuthenticationFailedError
from backend.security.authentication.user_credentials import (
    SqliteUserCredentialsRepository,
    UserCredentialsRepository,
)
from backend.security.credentials.password_hasher import (
    Argon2idPasswordHasher,
    BcryptPasswordHasher,
)
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.credentials.password_verification import MultiSchemePasswordVerifier
from backend.security.sessions.account_lockout_policy import AccountLockoutPolicy
from backend.security.sessions.authentication_attempt import AuthenticationAttempt

_GENERIC_FAILURE_MESSAGE = "Usuario o contraseña del autorizador incorrectos."


class VerifyAuthorizerCredentialsUseCase:
    def __init__(self, *, credentials_repository: UserCredentialsRepository,
                 attempt_repository: AuthenticationAttemptRepository,
                 password_verifier: MultiSchemePasswordVerifier,
                 lockout_policy: AccountLockoutPolicy, audit_sink=None) -> None:
        self._credentials = credentials_repository
        self._attempts = attempt_repository
        self._verifier = password_verifier
        self._lockout = lockout_policy
        self._audit = audit_sink or (lambda event, payload: None)

    def execute(self, *, username: str, password: str, workstation_id: str = "",
                now: datetime | None = None) -> str:
        now = now or datetime.now(timezone.utc)
        username = (username or "").strip()
        if not username or not password:
            raise AuthenticationFailedError(_GENERIC_FAILURE_MESSAGE)

        self._lockout.require_not_locked_out(
            self._attempts.recent_for_user(username), now=now)

        credentials = self._credentials.find_by_username(username)
        if credentials is None or not credentials.active:
            self._record_failure(username, workstation_id, "unknown_or_inactive_account", now)
            raise AuthenticationFailedError(_GENERIC_FAILURE_MESSAGE)

        if not self._verifier.verify(password, credentials.password_hash).valid:
            self._record_failure(username, workstation_id, "invalid_password", now)
            raise AuthenticationFailedError(_GENERIC_FAILURE_MESSAGE)

        self._attempts.record(AuthenticationAttempt.succeeded(
            username, workstation_id=workstation_id, occurred_at=now))
        self._audit(USER_AUTHENTICATION_SUCCEEDED,
                    {"user_id": credentials.id, "username": username, "purpose": "authorizer"})
        return credentials.id

    def _record_failure(self, username: str, workstation_id: str, reason: str,
                        now: datetime) -> None:
        self._attempts.record(AuthenticationAttempt.failure(
            username, workstation_id=workstation_id, reason=reason, occurred_at=now))
        self._audit(USER_AUTHENTICATION_FAILED,
                    {"username": username, "reason": reason, "purpose": "authorizer"})


def build_authorizer_credentials_verifier(connection) -> VerifyAuthorizerCredentialsUseCase:
    """El verificador con las mismas piezas que el login de producción
    (`desktop_shell_authentication_composition.py`): mismos hashers y el mismo
    bloqueo, derivado de `PasswordPolicy` como en `security_wiring.py`."""
    policy = PasswordPolicy()
    return VerifyAuthorizerCredentialsUseCase(
        credentials_repository=SqliteUserCredentialsRepository(connection),
        attempt_repository=SqliteAuthenticationAttemptRepository(connection),
        password_verifier=MultiSchemePasswordVerifier(
            primary=Argon2idPasswordHasher(), legacy=(BcryptPasswordHasher(),)),
        lockout_policy=AccountLockoutPolicy(
            failed_attempt_limit=policy.failed_attempt_limit,
            lockout_duration_seconds=policy.lockout_duration_seconds),
    )
