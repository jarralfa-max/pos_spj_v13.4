"""LOY-4 — LoyaltyProgram use cases: Create, Approve, Activate, Suspend
(master prompt §9, phase list "LOY-4 — Programas").

A program is not branch-scoped by default (§9's own `branch_scope` field is
optional — a program can be company-wide) but every use case still requires
`actor_branch_id`: it records the branch context the ACTING USER was in when
they performed the action (audit/event traceability), not "which branch the
program applies to" — same convention every other module in this app
already follows (`audit_write`'s `sucursal_id` is mandatory even for
company-wide config changes, and `LoyaltySessionPermissionChecker` itself
already fails closed without an active branch on the session).
"""

from __future__ import annotations

from backend.application.loyalty.dto import LoyaltyProgramDTO
from backend.application.loyalty.result import LoyaltyResult, fail_from_domain_error
from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.application.loyalty.use_cases._base import _LoyaltyBaseUseCase
from backend.domain.loyalty.entities.loyalty_program import LoyaltyProgram
from backend.domain.loyalty.events import LoyaltyEvents
from backend.domain.loyalty.exceptions import LoyaltyDomainError, LoyaltyProgramNotFoundError
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork


class CreateLoyaltyProgramUseCase(_LoyaltyBaseUseCase):
    """Creates a program and immediately submits it for approval (DRAFT →
    PENDING_APPROVAL). The master prompt's own LOY-4 phase list names only
    4 steps ("1. Crear. 2. Aprobar. 3. Activar. 4. Suspender.") — no
    separate "enviar a aprobación" action/permission exists in §59's
    catalog, so create folds that transition in rather than leaving a new
    program stranded in DRAFT with no use case able to move it forward."""

    def execute(
        self, connection, *, code: str, name: str, currency_name: str,
        actor_user_id: str, actor_branch_id: str, operation_id: str,
        description: str = "", currency_symbol: str = "",
    ) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.PROGRAM_CREATE)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            if uow.programs.get_by_code(code) is not None:
                return fail_from_domain_error(
                    LoyaltyDomainError(f"Ya existe un programa con el código {code}"),
                    operation_id=operation_id)
            try:
                program = LoyaltyProgram.create(
                    code, name, currency_name, description=description,
                    currency_symbol=currency_symbol, created_by_user_id=actor_user_id)
                program.submit_for_approval()
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.programs.save(program)
            self._emit(uow, LoyaltyEvents.PROGRAM_CREATED, entity_id=program.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_user_id)
        return LoyaltyResult.ok("Programa creado", entity_id=program.id,
                                operation_id=operation_id,
                                program=LoyaltyProgramDTO.from_entity(program))


class _ProgramTransitionUseCase(_LoyaltyBaseUseCase):
    """Shared fetch/authorize/transition/save/emit shape for the three
    simple program transitions below — each supplies its own permission
    code, entity method, and success message.

    ``event_name`` is deliberately optional (``None`` by default): master
    prompt §62's own canonical event list only names `LOYALTY_PROGRAM_CREATED`
    and `LOYALTY_PROGRAM_ACTIVATED` — there is no dedicated APPROVED/
    SUSPENDED event in that vocabulary. Reusing `PROGRAM_CREATED` for those
    would put a misleading event name in the outbox; skipping the emission
    entirely for `approve()`/`suspend()` is the honest choice until/unless a
    future phase extends `LoyaltyEvents` deliberately (not fabricated here).
    """

    permission_code: str = ""
    event_name: str | None = None
    success_message: str = ""

    def _transition(self, program: LoyaltyProgram, **kwargs) -> None:
        raise NotImplementedError

    def execute(self, connection, *, program_id: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str, **kwargs) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, self.permission_code)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            program = uow.programs.get(program_id)
            if program is None:
                return fail_from_domain_error(
                    LoyaltyProgramNotFoundError(f"Programa {program_id} no existe"),
                    operation_id=operation_id)
            try:
                self._transition(program, **kwargs)
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.programs.save(program)
            if self.event_name is not None:
                self._emit(uow, self.event_name, entity_id=program.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id)
        return LoyaltyResult.ok(self.success_message, entity_id=program.id,
                                operation_id=operation_id,
                                program=LoyaltyProgramDTO.from_entity(program))


class ApproveLoyaltyProgramUseCase(_ProgramTransitionUseCase):
    permission_code = LoyaltyPermissions.PROGRAM_APPROVE
    success_message = "Programa aprobado"

    def execute(self, connection, *, program_id: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str) -> LoyaltyResult:
        return super().execute(
            connection, program_id=program_id, actor_user_id=actor_user_id,
            actor_branch_id=actor_branch_id, operation_id=operation_id,
            approved_by_user_id=actor_user_id)

    def _transition(self, program: LoyaltyProgram, *, approved_by_user_id: str) -> None:
        program.approve(approved_by_user_id)


class ActivateLoyaltyProgramUseCase(_ProgramTransitionUseCase):
    permission_code = LoyaltyPermissions.PROGRAM_ACTIVATE
    event_name = LoyaltyEvents.PROGRAM_ACTIVATED
    success_message = "Programa activado"

    def _transition(self, program: LoyaltyProgram) -> None:
        program.activate()


class SuspendLoyaltyProgramUseCase(_ProgramTransitionUseCase):
    permission_code = LoyaltyPermissions.PROGRAM_SUSPEND
    success_message = "Programa suspendido"

    def execute(self, connection, *, program_id: str, reason: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str) -> LoyaltyResult:
        return super().execute(
            connection, program_id=program_id, actor_user_id=actor_user_id,
            actor_branch_id=actor_branch_id, operation_id=operation_id, reason=reason)

    def _transition(self, program: LoyaltyProgram, *, reason: str) -> None:
        program.suspend(reason)
