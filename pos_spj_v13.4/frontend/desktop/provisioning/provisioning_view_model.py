"""ProvisioningViewModel — SHELL-2 InitialSetupWizard.

Plain data accumulated across wizard pages. No PyQt import here on purpose:
this is what `ProvisioningPresenter` hands to
`ProvisionInstallationUseCase.execute()`, and keeping it Qt-free means the
presenter is unit-testable without a QApplication.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProvisioningViewModel:
    company_name: str = ""
    company_rfc: str = ""
    branch_name: str = ""
    branch_address: str = ""
    workstation_name: str = ""
    owner_full_name: str = ""
    owner_username: str = ""
    owner_password: str = ""
    owner_recovery_contact: str = ""
    recovery_code_count: int = 10
