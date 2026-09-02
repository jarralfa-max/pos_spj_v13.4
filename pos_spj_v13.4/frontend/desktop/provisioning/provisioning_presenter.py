"""ProvisioningPresenter — SHELL-2 InitialSetupWizard.

The only place the wizard touches `ProvisionInstallationUseCase`. Pages
never call the use case directly, and never see the database connection or
`PasswordHasher` — they only read/write `ProvisioningViewModel` fields and
call `finish()` here. Keeps "sin lógica de negocio en UI" true for a screen
that is otherwise easy to turn into a god-widget.
"""
from __future__ import annotations

from backend.security.provisioning.provision_installation_use_case import (
    ProvisioningResult,
    ProvisionInstallationUseCase,
)
from frontend.desktop.provisioning.provisioning_view_model import ProvisioningViewModel


class ProvisioningPresenter:
    def __init__(self, provision_use_case: ProvisionInstallationUseCase) -> None:
        self._use_case = provision_use_case

    def finish(self, view_model: ProvisioningViewModel) -> ProvisioningResult:
        """Runs the actual provisioning. Raises the use case's own errors
        (PasswordPolicyViolationError, OwnerUsernameTakenError,
        InstallationAlreadyProvisionedError, InstallationLockedError, plain
        ValueError for empty required fields) — the wizard's finish handler
        is responsible for turning those into a Spanish error message."""
        return self._use_case.execute(
            company_name=view_model.company_name,
            company_rfc=view_model.company_rfc,
            branch_name=view_model.branch_name,
            branch_address=view_model.branch_address,
            workstation_name=view_model.workstation_name,
            owner_username=view_model.owner_username,
            owner_password=view_model.owner_password,
            owner_full_name=view_model.owner_full_name,
            owner_recovery_contact=view_model.owner_recovery_contact,
            recovery_code_count=view_model.recovery_code_count,
        )
