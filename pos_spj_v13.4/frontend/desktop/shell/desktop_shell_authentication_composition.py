"""build_authentication_coordinator() — SHELL-16½ piece 4b of 4: the
authentication half of the composition-root job piece 4a (`desktop_shell_
window_composition.py`) deliberately left out.

Wires a real `AuthenticationCoordinator` (SHELL-7) from a real SQLite
`connection` and a `ServiceContainer` already built with (at least)
`SecurityModuleProvider` registered — `PasswordPolicy`/`AccountLockoutPolicy`
are resolved from it, matching what that provider exists for. Password
HASHERS are deliberately NOT resolved from the container: production's
real owner-provisioning/recovery flow (`CreateInitialOwnerUseCase`) still
constructs `BcryptPasswordHasher()` directly today, and
`AuthenticateUserUseCase` verifies against BOTH `Argon2idPasswordHasher`
(primary) and `BcryptPasswordHasher` (legacy) via
`MultiSchemePasswordVerifier` — the exact pattern
`tests/ui/test_login_window.py` already exercises against a real
connection. `SecurityModuleProvider`'s own docstring says resolving
`PasswordHasher` uniformly is SHELL-7's job, not yet done; this file
mirrors today's real behavior rather than getting ahead of it.

`on_authenticated` is the caller's to define — typically something that
calls `desktop_shell_window_composition.py::build_application_window()`
with a `LegacySessionAdapter` wrapping the just-built `ApplicationContext`,
then `.show()`s the result. That wiring is deliberately NOT this file's
job: `AuthenticationCoordinator.run()` already treats `on_authenticated`
as an opaque callback (its own docstring says as much —
"ResolveNavigation"/"Open ApplicationShellWindow" didn't exist when it was
built), and this file has no opinion on what happens after login beyond
handing back a coordinator that will eventually call it.

There is no persistent session-repository implementation anywhere in this
codebase yet — `SessionManager` is wired here with `InMemorySessionRepository`
because that is the only one that exists, not a shortcut taken for this
file. A desktop app that re-authenticates on every launch (which this one
already does, login being the first screen every time) has no present need
for sessions to survive a restart.
"""
from __future__ import annotations

from typing import Callable

from PyQt5.QtWidgets import QDialog

from backend.bootstrap.application_context import ApplicationContext
from backend.bootstrap.application_context_builder import ApplicationContextBuilder
from backend.bootstrap.service_container import ServiceContainer
from backend.security.authentication.authenticate_user_use_case import AuthenticateUserUseCase
from backend.security.authentication.authentication_attempt_repository import (
    SqliteAuthenticationAttemptRepository,
)
from backend.security.authentication.user_credentials import SqliteUserCredentialsRepository
from backend.security.credentials.password_hasher import Argon2idPasswordHasher, BcryptPasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.credentials.password_verification import MultiSchemePasswordVerifier
from backend.security.provisioning.installation_repository import SqliteInstallationRepository
from backend.security.provisioning.installation_status_query import InstallationStatusQuery
from backend.security.provisioning.installation_summary_query import InstallationSummaryQueryService
from backend.security.provisioning.provision_installation_use_case import ProvisionInstallationUseCase
from backend.security.provisioning.recovery_code_repository import SqliteRecoveryCodeRepository
from backend.security.recovery.account_recovery_service import AccountRecoveryService
from backend.security.recovery.begin_account_recovery_use_case import BeginAccountRecoveryUseCase
from backend.security.recovery.complete_account_recovery_use_case import CompleteAccountRecoveryUseCase
from backend.security.recovery.recovery_token_repository import SqliteRecoveryTokenRepository
from backend.security.sessions.account_lockout_policy import AccountLockoutPolicy
from backend.security.sessions.session_manager import SessionManager
from backend.security.sessions.session_repository import InMemorySessionRepository
from frontend.desktop.auth.authentication_coordinator import AuthenticationCoordinator
from frontend.desktop.auth.installation_status_dialogs import (
    InstallationLockedDialog,
    InstallationRecoveryRequiredDialog,
)
from frontend.desktop.auth.login_window import LoginWindow
from frontend.desktop.provisioning.initial_setup_wizard import InitialSetupWizard
from frontend.desktop.provisioning.provisioning_presenter import ProvisioningPresenter


def build_authentication_coordinator(
    *, connection, container: ServiceContainer,
    on_authenticated: Callable[[ApplicationContext], None],
    workstation_id: str = "",
) -> AuthenticationCoordinator:
    password_policy: PasswordPolicy = container.resolve(PasswordPolicy)
    lockout_policy: AccountLockoutPolicy = container.resolve(AccountLockoutPolicy)

    installation_status_query = InstallationStatusQuery(SqliteInstallationRepository(connection))
    session_manager = SessionManager(session_repository=InMemorySessionRepository())

    def setup_wizard_factory() -> QDialog:
        provision_use_case = ProvisionInstallationUseCase(
            connection,
            installation_repository=SqliteInstallationRepository(connection),
            recovery_code_repository=SqliteRecoveryCodeRepository(connection),
            password_hasher=BcryptPasswordHasher(),
            password_policy=password_policy,
        )
        return InitialSetupWizard(
            presenter=ProvisioningPresenter(provision_use_case), password_policy=password_policy,
        )

    def login_window_factory() -> LoginWindow:
        authenticate_use_case = AuthenticateUserUseCase(
            credentials_repository=SqliteUserCredentialsRepository(connection),
            attempt_repository=SqliteAuthenticationAttemptRepository(connection),
            password_verifier=MultiSchemePasswordVerifier(
                primary=Argon2idPasswordHasher(), legacy=(BcryptPasswordHasher(),),
            ),
            lockout_policy=lockout_policy,
            session_manager=session_manager,
        )
        recovery_service = AccountRecoveryService(
            token_repository=SqliteRecoveryTokenRepository(connection),
            password_hasher=BcryptPasswordHasher(), password_policy=password_policy,
        )
        return LoginWindow(
            authenticate_use_case=authenticate_use_case,
            begin_recovery_use_case=BeginAccountRecoveryUseCase(recovery_service),
            complete_recovery_use_case=CompleteAccountRecoveryUseCase(recovery_service),
            installation_summary_query=InstallationSummaryQueryService(connection),
            workstation_id=workstation_id,
        )

    return AuthenticationCoordinator(
        installation_status_query=installation_status_query,
        setup_wizard_factory=setup_wizard_factory,
        login_window_factory=login_window_factory,
        build_application_context=ApplicationContextBuilder(connection).build,
        on_authenticated=on_authenticated,
        recovery_required_dialog_factory=InstallationRecoveryRequiredDialog,
        locked_dialog_factory=InstallationLockedDialog,
    )
