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
    ) -> None:
        self._installation_status_query = installation_status_query
        self._setup_wizard_factory = setup_wizard_factory
        self._login_window_factory = login_window_factory
        self._build_application_context = build_application_context
        self._on_authenticated = on_authenticated
        self._recovery_required_dialog_factory = recovery_required_dialog_factory
        self._locked_dialog_factory = locked_dialog_factory

    def run(self) -> bool:
        """Returns True iff `on_authenticated` was invoked. False covers
        every other outcome (cancelled wizard/login, locked installation,
        recovery-required installation) — the caller (main.py, eventually)
        should treat False as "nothing more to do, exit."""
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

        if status is not ProvisioningStatus.PROVISIONED:
            return False

        login_window = self._login_window_factory()
        if login_window.exec_() != QDialog.Accepted:
            return False

        auth_result = login_window.authentication_result
        if auth_result is None:
            return False

        context = self._build_application_context(auth_result)
        self._on_authenticated(context)
        return True
