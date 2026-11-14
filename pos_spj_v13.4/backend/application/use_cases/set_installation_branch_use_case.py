"""Set installation branch use case — single canonical route to anchor
THIS terminal to a branch (`configuraciones.sucursal_instalacion_id`,
read by `core/app_container.py`/`branch_resolution.py` at startup).
Wraps the already-correct, UoW-wrapped
`core/services/configuration_settings_service.py::CompanyProfileService
.set_installation_branch()`, which validates the branch exists and is
active before persisting.

SDLC-ARQ-PERM-001: re-anclar la terminal exige `CONFIGURACION.empresa.editar`
también aquí, no sólo en la pantalla; sin autorizador falla cerrado.
TERM-002 (aprobación central del re-anclaje) queda fuera."""

from __future__ import annotations

from typing import Callable

from backend.application.commands.settings_commands import SetInstallationBranchCommand
from backend.application.configuracion.authorization import ConfiguracionActionAuthorizer
from backend.application.configuracion.permissions import ConfiguracionPermissions
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.security.unwired_policy import unwired
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.domain.settings.exceptions import (
    ConfigurationPermissionDeniedError,
    InstallationBranchChangeRejectedError,
)
from backend.shared.ids import validate_uuidv7

AUDIT_ACTION = "instalacion.reanclar"
AUDIT_ENTITY = "instalacion"
APPLIED = "APLICADO"
REJECTED = "RECHAZADO"
PERMISSION_DENIED = "PERMISSION_DENIED"


class SetInstallationBranchUseCase(BaseUseCase[SetInstallationBranchCommand]):
    name = "SetInstallationBranchUseCase"

    def __init__(self, company_profile_service, *, authorization=None) -> None:
        self._authz = authorization or unwired(ConfiguracionActionAuthorizer)
        self._service = company_profile_service

    def execute(self, command: SetInstallationBranchCommand) -> UseCaseResult:
        self._authz.require(ConfiguracionPermissions.EMPRESA_EDITAR,
                            claimed_actor=command.user_name)
        command.validate_context()
        actor = str(command.user_name or "")
        target = validate_uuidv7(command.branch_id)
        try:
            self._auth.require(actor, ConfiguracionPermissions.ESTACION_REANCLAR)
        except ConfigurationPermissionDeniedError:
            self._record_rejection(command, target, PERMISSION_DENIED)
            raise

        try:
            with self._uow_factory() as uow:
                repo = uow.installation_branch
                previous = repo.get()
                if previous is not None and previous[0] == target:
                    return UseCaseResult(
                        success=True, operation_id=command.operation_id, entity_id=target,
                        data={"branch_name": previous[1], "previous_branch_id": target,
                              "changed": False},
                    )
                branch_id, branch_name = repo.set(target)
                self._guard(repo, branch_id)
                self._audit(uow, command, previous=previous,
                            after={"branch_id": branch_id, "branch_name": branch_name},
                            result=APPLIED)
        except InstallationBranchChangeRejectedError as exc:
            self._record_rejection(command, target, exc.code)
            raise
        return UseCaseResult(
            success=True, operation_id=command.operation_id, entity_id=branch_id,
            data={"branch_name": branch_name,
                  "previous_branch_id": previous[0] if previous else "", "changed": True},
        )

    # ── reglas ────────────────────────────────────────────────────────────
    @staticmethod
    def _guard(repo, branch_id: str) -> None:
        if repo.central_enrollment_active():
            raise InstallationBranchChangeRejectedError(
                InstallationBranchChangeRejectedError.CENTRAL_APPROVAL_REQUIRED,
                "Esta estación está vinculada al servidor central: su sucursal se "
                "reasigna desde el registro central de equipos, no desde aquí.")
        shifts = repo.open_cash_shifts_outside(branch_id)
        if shifts:
            raise InstallationBranchChangeRejectedError(
                InstallationBranchChangeRejectedError.OPEN_CASH_SHIFT,
                f"Hay {shifts} turno(s) de caja sin cerrar en la sucursal actual. "
                "Ciérrelos antes de cambiar la sucursal de esta estación.")
        pending = repo.pending_sync_count()
        if pending:
            raise InstallationBranchChangeRejectedError(
                InstallationBranchChangeRejectedError.PENDING_SYNC,
                f"Hay {pending} movimiento(s) sin sincronizar con el servidor central. "
                "Sincronice antes de cambiar la sucursal de esta estación.")

    # ── auditoría ─────────────────────────────────────────────────────────
    @staticmethod
    def _audit(uow, command, *, previous, after: dict, result: str, reason: str = "") -> None:
        details = f"terminal={command.workstation_id or '-'} resultado={result}"
        if reason:
            details += f" motivo={reason}"
        uow.audit_log.record(
            action=AUDIT_ACTION, entity=AUDIT_ENTITY, entity_id=after["branch_id"],
            actor=str(command.user_name or ""), operation_id=command.operation_id,
            details=details,
            before=({"branch_id": previous[0], "branch_name": previous[1]}
                    if previous else {}),
            after=after, branch_id=after["branch_id"],
        )

    def _record_rejection(self, command, target: str, reason: str) -> None:
        with self._uow_factory() as uow:
            previous = uow.installation_branch.get()
            self._audit(uow, command, previous=previous, after={"branch_id": target},
                        result=REJECTED, reason=reason)
