"""Set installation branch use case — the single canonical route to anchor
THIS station to a branch (`configuraciones.sucursal_instalacion_id`, read by
`ApplicationContextBuilder` at login).

SDLC-ARQ-TERM-002: re-anchoring moves where this station's sales, cash and
inventory land, so it is guarded HERE, not in the screen:

1. permission `CONFIGURACION.estacion.reanclar`, checked in backend (fails
   closed when no policy is wired);
2. inside one unit of work: the anchor is written first (that takes SQLite's
   write lock, so nothing can open a shift or enqueue a fact in between), then
   - a station enrolled in the central registry is rejected: the central
     reassigns it (decision 2026-11-02: central approval when a central
     registry exists, otherwise the local permission is enough);
   - an unfinished cash shift in another branch is rejected;
   - facts still pending synchronization are rejected;
   and a violation rolls everything back;
3. every attempt that reaches here is audited in `audit_logs`
   (`instalacion.reanclar`): applied together with the anchor, rejected in its
   own transaction after the rollback.

Re-anchoring to the branch already anchored is a no-op (double click, retry).

Integración ronda 1: `execute` empieza por `require()` como exige la guardia de
SDLC-ARQ-PERM-001 (`tests/architecture/test_configuracion_use_cases_are_authorized.py`);
para un comando válido el orden observable es el mismo de TERM-002.
"""

from __future__ import annotations

from typing import Callable

from backend.application.commands.settings_commands import SetInstallationBranchCommand
from backend.application.configuracion.authorization import ConfiguracionAuthorizationPolicy
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

    def __init__(self, uow_factory: Callable[[], object], authorization=None) -> None:
        """`uow_factory()` returns a unit of work exposing `.installation_branch`
        and `.audit_log` (`InstallationBranchUnitOfWork` in production)."""
        self._uow_factory = uow_factory
        self._auth = authorization or unwired(ConfiguracionAuthorizationPolicy)

    def execute(self, command: SetInstallationBranchCommand) -> UseCaseResult:
        try:
            self._auth.require(str(command.user_name or ""),
                               ConfiguracionPermissions.ESTACION_REANCLAR)
        except ConfigurationPermissionDeniedError:
            command.validate_context()
            self._record_rejection(command, validate_uuidv7(command.branch_id),
                                   PERMISSION_DENIED)
            raise
        command.validate_context()
        target = validate_uuidv7(command.branch_id)

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
