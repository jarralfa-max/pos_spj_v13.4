"""LOY-5 — LoyaltyMembership use cases: Enroll, Suspend, Close (master
prompt §10, phase list "LOY-5 — Membresías").

Enrolling also implicitly creates the customer's LoyaltyAccount on first use
(§10: ``Customer → LoyaltyAccount → LoyaltyMembership`` — a customer's very
first program enrollment is exactly when the account first needs to exist;
there is no separate "open a loyalty account" action anywhere in the master
prompt's own use-case list). Subsequent enrollments in other programs reuse
the same account.
"""

from __future__ import annotations

from backend.application.loyalty.dto import LoyaltyMembershipDTO
from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.application.loyalty.result import LoyaltyResult, fail_from_domain_error
from backend.application.loyalty.use_cases._base import _LoyaltyBaseUseCase
from backend.domain.loyalty.entities.loyalty_account import LoyaltyAccount
from backend.domain.loyalty.entities.loyalty_membership import LoyaltyMembership
from backend.domain.loyalty.events import LoyaltyEvents
from backend.domain.loyalty.exceptions import (
    LoyaltyAccountSuspendedError,
    LoyaltyDomainError,
    LoyaltyMembershipNotFoundError,
    LoyaltyProgramInactiveError,
    LoyaltyProgramNotFoundError,
)
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork


class EnrollLoyaltyMembershipUseCase(_LoyaltyBaseUseCase):
    def execute(
        self, connection, *, customer_id: str, program_id: str, actor_user_id: str,
        actor_branch_id: str, operation_id: str,
    ) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.MEMBERSHIP_ENROLL)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            program = uow.programs.get(program_id)
            if program is None:
                return fail_from_domain_error(
                    LoyaltyProgramNotFoundError(f"Programa {program_id} no existe"),
                    operation_id=operation_id)
            if not program.is_active():
                return fail_from_domain_error(
                    LoyaltyProgramInactiveError(
                        f"El programa {program.code} no está activo"),
                    operation_id=operation_id)

            account = uow.accounts.get_by_customer_id(customer_id)
            if account is None:
                account = LoyaltyAccount.create(customer_id)
                uow.accounts.save(account)
            elif not account.is_operational():
                return fail_from_domain_error(
                    LoyaltyAccountSuspendedError(
                        f"La cuenta de fidelidad de {customer_id} no está activa"),
                    operation_id=operation_id)

            existing = uow.memberships.get_by_account_and_program(account.id, program_id)
            if existing is not None:
                return fail_from_domain_error(
                    LoyaltyDomainError(
                        f"El cliente ya está inscrito en el programa {program.code}"),
                    operation_id=operation_id)

            membership = LoyaltyMembership.enroll(account.id, program_id)
            uow.memberships.save(membership)
            self._emit(uow, LoyaltyEvents.MEMBERSHIP_ENROLLED, entity_id=membership.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_user_id, loyalty_account_id=account.id,
                       program_id=program_id)
        return LoyaltyResult.ok(
            "Membresía inscrita", entity_id=membership.id, operation_id=operation_id,
            membership=LoyaltyMembershipDTO.from_entity(membership))


class _MembershipTransitionUseCase(_LoyaltyBaseUseCase):
    permission_code: str = ""
    event_name: str | None = None
    success_message: str = ""

    def _transition(self, membership: LoyaltyMembership, **kwargs) -> None:
        raise NotImplementedError

    def execute(self, connection, *, membership_id: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str, **kwargs) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, self.permission_code)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            membership = uow.memberships.get(membership_id)
            if membership is None:
                return fail_from_domain_error(
                    LoyaltyMembershipNotFoundError(f"Membresía {membership_id} no existe"),
                    operation_id=operation_id)
            try:
                self._transition(membership, **kwargs)
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.memberships.save(membership)
            if self.event_name is not None:
                self._emit(uow, self.event_name, entity_id=membership.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id)
        return LoyaltyResult.ok(self.success_message, entity_id=membership.id,
                                operation_id=operation_id,
                                membership=LoyaltyMembershipDTO.from_entity(membership))


class SuspendLoyaltyMembershipUseCase(_MembershipTransitionUseCase):
    permission_code = LoyaltyPermissions.MEMBERSHIP_SUSPEND
    event_name = LoyaltyEvents.MEMBERSHIP_SUSPENDED
    success_message = "Membresía suspendida"

    def execute(self, connection, *, membership_id: str, reason: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str) -> LoyaltyResult:
        return super().execute(
            connection, membership_id=membership_id, actor_user_id=actor_user_id,
            actor_branch_id=actor_branch_id, operation_id=operation_id, reason=reason)

    def _transition(self, membership: LoyaltyMembership, *, reason: str) -> None:
        membership.suspend(reason)


class CloseLoyaltyMembershipUseCase(_MembershipTransitionUseCase):
    """No dedicated `MEMBERSHIP_CLOSED` in master prompt §62's own event
    list — same honest gap already documented for Program's approve/suspend,
    no event emitted."""

    permission_code = LoyaltyPermissions.MEMBERSHIP_CLOSE
    success_message = "Membresía cerrada"

    def execute(self, connection, *, membership_id: str, reason: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str) -> LoyaltyResult:
        return super().execute(
            connection, membership_id=membership_id, actor_user_id=actor_user_id,
            actor_branch_id=actor_branch_id, operation_id=operation_id, reason=reason)

    def _transition(self, membership: LoyaltyMembership, *, reason: str) -> None:
        membership.close(reason)
