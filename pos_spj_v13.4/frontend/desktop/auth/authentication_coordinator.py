"""AuthenticationCoordinator — SHELL-7 §38.

Resolves `InstallationStatusQuery` and routes to the matching screen:

    UNINITIALIZED / PROVISIONING → InitialSetupWizard (SHELL-2)
    PROVISIONED                 → LoginWindow
    RECOVERY_REQUIRED           → InstallationRecoveryRequiredDialog
    LOCKED                      → InstallationLockedDialog

After a successful login: AuthenticateUser (LoginWindow already did this)
→ BuildApplicationContext (`ApplicationContextBuilder`, which itself does
§38's "ResolveInstallationContext"/"ResolveBranchAccess" by reading
Installation + `sucursales` + the existing permission/feature-flag
services) → `on_authenticated(context)`.

"ResolveNavigation" and "Open ApplicationShellWindow" don't exist yet
(SHELL-9/11/12) — `on_authenticated` is where those will plug in once they
do; until then it's just an injected callback so this coordinator doesn't
have to import/construct anything from those unbuilt phases.

Every dependency is a factory (`Callable[[], QDialog]`) rather than a
constructed dialog — a fresh dialog per `run()` call, and it means this
class never has to import PyQt5 to be imported, only to be *run*.
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtWidgets import QDialog

from backend.bootstrap.application_context import ApplicationContext
from backend.bootstrap.application_context_errors import SiteAccessDeniedError
from backend.security.provisioning.installation import ProvisioningStatus
from backend.security.provisioning.installation_status_query import InstallationStatusQuery
from frontend.desktop.auth.login_window import LoginWindow


class AuthenticationCoordinator:
    def __init__(
        self,
        *,
        installation_status_query: InstallationStatusQuery,
        setup_wizard_factory: Callable[[], QDialog],
        login_window_factory: Callable[[], LoginWindow],
        build_application_context: Callable[[object], ApplicationContext],
        on_authenticated: Callable[[ApplicationContext], None],
        recovery_required_dialog_factory: Optional[Callable[[], QDialog]] = None,
        locked_dialog_factory: Optional[Callable[[], QDialog]] = None,
        revoke_session: Optional[Callable[[str], object]] = None,
        notify_access_denied: Optional[Callable[[str], object]] = None,
    ) -> None:
        self._installation_status_query = installation_status_query
        self._setup_wizard_factory = setup_wizard_factory
        self._login_window_factory = login_window_factory
        self._build_application_context = build_application_context
        self._on_authenticated = on_authenticated
        self._recovery_required_dialog_factory = recovery_required_dialog_factory
        self._locked_dialog_factory = locked_dialog_factory
        self._revoke_session = revoke_session
        #: Cómo se avisa que el usuario no tiene acceso al sitio de la estación
        #: (auditoría enterprise, Fase 2). Inyectable para las pruebas.
        self._notify_access_denied = notify_access_denied or _warn_access_denied

    def logout(self, session_id: str) -> None:
        """Use the existing session service before reopening authentication."""
        if self._revoke_session is None:
            raise RuntimeError("Session revocation is not configured")
        self._revoke_session(session_id)

    def run(self) -> bool:
        """Returns True iff `on_authenticated` was invoked. False covers
        every other outcome (cancelled wizard/login, locked installation,
        recovery-required installation) — the caller (main.py, eventually)
        should treat False as "nothing more to do, exit."""
        if not self.ensure_provisioned():
            return False

        while True:
            login_window = self._login_window_factory()
            if login_window.exec_() != QDialog.Accepted:
                return False

            auth_result = login_window.authentication_result
            if auth_result is None:
                return False

            try:
                context = self._build_application_context(auth_result)
            except SiteAccessDeniedError as exc:
                # Credenciales correctas, pero ningún rol suyo vale en el sitio de
                # esta estación: la sesión recién abierta se revoca y se vuelve
                # al inicio de sesión con el motivo.
                session = getattr(auth_result, "session", None)
                session_id = getattr(session, "session_id", "")
                if session_id and self._revoke_session is not None:
                    self._revoke_session(session_id)
                self._notify_access_denied(str(exc))
                continue
            self._on_authenticated(context)
            return True

    def ensure_provisioned(self) -> bool:
        """Resolve first-run/locked states before any operational UI is built."""
        status = self._installation_status_query.current_status()

        if status in (ProvisioningStatus.UNINITIALIZED, ProvisioningStatus.PROVISIONING):
            wizard = self._setup_wizard_factory()
            if wizard.exec_() != QDialog.Accepted:
                return False
            status = self._installation_status_query.current_status()

        if status is ProvisioningStatus.LOCKED:
            if self._locked_dialog_factory:
                self._locked_dialog_factory().exec_()
            return False

        if status is ProvisioningStatus.RECOVERY_REQUIRED:
            if self._recovery_required_dialog_factory:
                self._recovery_required_dialog_factory().exec_()
            return False

        return status is ProvisioningStatus.PROVISIONED


def _warn_access_denied(message: str) -> None:
    from frontend.desktop.components.dialogs import MessageDialog

    MessageDialog.warning(None, "Acceso a la sucursal", message)
