"""ProvisionInstallationUseCase — SHELL-2 security foundation.

Top-level orchestrator behind `InitialSetupWizard`'s "finish" step: creates
the initial branch (reusing the existing `sucursales` schema — this app is
single-tenant/single-company, so "company" has no dedicated table yet and is
recorded as `configuraciones` entries plus a minted `company_id`), the first
owner account (`CreateInitialOwnerUseCase`), the installation's recovery kit,
and transitions `Installation` from UNINITIALIZED to PROVISIONED.

Runs inside the caller's transaction (`conn`) — commit/rollback is the
caller's responsibility, matching "toda operación crítica debe pasar por Use
Case" + "servicios no deben crear ni alterar schema" (this only inserts
rows; migration 206 owns the schema).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.security.audit.security_events import (
    INSTALLATION_PROVISIONED,
    INSTALLATION_PROVISIONING_STARTED,
)
from backend.security.credentials.password_hasher import PasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.provisioning.create_initial_owner_use_case import CreateInitialOwnerUseCase
from backend.security.provisioning.errors import (
    InstallationAlreadyProvisionedError,
    InstallationLockedError,
)
from backend.security.provisioning.installation import Installation, ProvisioningStatus
from backend.security.provisioning.installation_recovery_kit import InstallationRecoveryKit
from backend.security.provisioning.installation_repository import InstallationRepository
from backend.security.provisioning.recovery_code_repository import RecoveryCodeRepository
from backend.shared.ids import new_uuid

AuditSink = Callable[[str, dict], None]


@dataclass(frozen=True)
class ProvisioningResult:
    installation: Installation
    owner_user_id: str
    recovery_codes: list[str]


class ProvisionInstallationUseCase:
    def __init__(
        self,
        conn,
        *,
        installation_repository: InstallationRepository,
        recovery_code_repository: RecoveryCodeRepository,
        password_hasher: PasswordHasher,
        password_policy: PasswordPolicy,
        audit_sink: Optional[AuditSink] = None,
    ) -> None:
        self._conn = conn
        self._installations = installation_repository
        self._recovery_kit = InstallationRecoveryKit(code_repository=recovery_code_repository)
        self._hasher = password_hasher
        self._policy = password_policy
        self._audit = audit_sink or (lambda event, payload: None)

    def execute(
        self,
        *,
        company_name: str,
        company_rfc: str = "",
        branch_name: str,
        branch_address: str = "",
        workstation_name: str = "",
        owner_username: str,
        owner_password: str,
        owner_full_name: str,
        owner_recovery_contact: str = "",
        recovery_code_count: int = 10,
        now: datetime | None = None,
    ) -> ProvisioningResult:
        now = now or datetime.now(timezone.utc)
        installation = self._installations.get() or Installation.uninitialized(
            installation_code=new_uuid(), now=now,
        )

        if installation.provisioning_status is ProvisioningStatus.PROVISIONED:
            raise InstallationAlreadyProvisionedError(
                "Esta instalación ya fue aprovisionada; el asistente no puede ejecutarse de nuevo."
            )
        if installation.provisioning_status in (
            ProvisioningStatus.LOCKED, ProvisioningStatus.RECOVERY_REQUIRED,
        ):
            raise InstallationLockedError(
                f"No se puede aprovisionar: la instalación está en estado "
                f"{installation.provisioning_status.value}."
            )

        if installation.provisioning_status is ProvisioningStatus.UNINITIALIZED:
            installation = installation.start_provisioning(now=now)
            self._installations.save(installation)
            self._audit(INSTALLATION_PROVISIONING_STARTED, {"installation_id": installation.id})

        branch_id = new_uuid()
        self._conn.execute(
            "INSERT OR IGNORE INTO sucursales (id, nombre, direccion, activa) VALUES (?,?,?,1)",
            (branch_id, branch_name.strip(), (branch_address or "").strip()),
        )

        company_id = new_uuid()
        for clave, valor in (
            ("company_id", company_id),
            ("empresa_nombre", company_name.strip()),
            ("empresa_rfc", (company_rfc or "").strip()),
        ):
            self._conn.execute(
                "INSERT INTO configuraciones (clave, valor) VALUES (?, ?) "
                "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                (clave, valor),
            )

        workstation_id = new_uuid()
        self._conn.execute(
            "INSERT INTO configuraciones (clave, valor) VALUES (?, ?) "
            "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            ("workstation_nombre", (workstation_name or "").strip()),
        )

        owner_use_case = CreateInitialOwnerUseCase(
            self._conn, password_hasher=self._hasher, password_policy=self._policy,
        )
        owner_user_id = owner_use_case.execute(
            username=owner_username,
            password=owner_password,
            full_name=owner_full_name,
            branch_id=branch_id,
            recovery_contact=owner_recovery_contact,
        )

        recovery_codes = self._recovery_kit.generate(
            installation.id, count=recovery_code_count, now=now,
        )

        installation = installation.complete_provisioning(
            company_id=company_id, initial_branch_id=branch_id, workstation_id=workstation_id,
            provisioned_by_user_id=owner_user_id, now=now,
        )
        self._installations.save(installation)
        self._audit(INSTALLATION_PROVISIONED, {"installation_id": installation.id})

        return ProvisioningResult(
            installation=installation, owner_user_id=owner_user_id, recovery_codes=recovery_codes,
        )
