"""InstallationStateStep — SHELL-3.

Resolves `context.installation_status` via `InstallationStatusQuery`
(SHELL-2) so a later phase (SHELL-7's AuthenticationCoordinator) can route
to `InitialSetupWizard` vs. normal login vs. a locked/recovery screen
without querying the database itself. Never fatal on its own — an
UNINITIALIZED installation is an expected, normal state on a fresh install,
not a failure. A LOCKED installation is *not* treated as fatal here either:
it's a legitimate state the shell must still be able to reach (to show the
locked screen), not a boot-time error — SHELL-7's AuthenticationCoordinator
enforces `InstallationLockedError` at the point that actually matters
(attempting to log in or re-provision).
"""
from __future__ import annotations

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.bootstrap_severity import BootstrapFailureReason
from backend.bootstrap.bootstrap_state import BootstrapState
from backend.bootstrap.bootstrap_step_result import BootstrapStepResult
from backend.security.provisioning.installation_repository import SqliteInstallationRepository
from backend.security.provisioning.installation_status_query import InstallationStatusQuery


class InstallationStateStep:
    name = "installation_state"
    resulting_state = BootstrapState.INSTALLATION_RESOLVING

    def run(self, context: BootstrapContext) -> BootstrapStepResult:
        if context.conn is None:
            return BootstrapStepResult.fatal(
                self.name, BootstrapFailureReason.BOOTSTRAP_INVALID,
                "installation_state ejecutado sin una conexión abierta.",
            )

        query = InstallationStatusQuery(SqliteInstallationRepository(context.conn))
        status = query.current_status()
        context.installation_status = status
        return BootstrapStepResult.ok(self.name, f"Estado de instalación: {status.value}.")
