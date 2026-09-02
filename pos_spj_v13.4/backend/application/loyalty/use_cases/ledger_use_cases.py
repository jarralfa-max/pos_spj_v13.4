"""LOY-6 — Points ledger use cases: Accrue, Reserve, Confirm/Release,
Redeem, Expire, Adjust, Reverse (master prompt §11-§12/§26, phase list
"LOY-6 — Ledger de puntos").

Every use case:
- re-validates its permission via LOY-1's `LoyaltyAuthorizationPolicy`;
- checks idempotency via `exists_for_source()`/`get_by_operation_id()`
  BEFORE writing, so a caller gets a clean domain error instead of a raw
  `sqlite3.IntegrityError` bubbling from the schema's own UNIQUE constraints
  (LOY-3/LOY-4) — the DB constraint remains the real safety net;
- computes the account's balance via `LoyaltyBalancePolicy.balance()`
  (LOY-2) fresh from the ledger on every call — never a cached figure;
- shapes its `LOYALTY_POINTS_ISSUED` event payload to match the fields
  Finance's already-built `LoyaltyPointsIssuedHandler._handle()` expects
  (`loyalty_transaction_id`, `estimated_fair_value`, `currency_code`,
  `customer_id`, `program_id`, `expires_at`) — LOY-0's own "highest value"
  finding. This does NOT mean the event is actually consumed yet: no
  dispatcher/bridge calls the Finance handler from this outbox (same
  confirmed-dead-code gap as every other bounded context's own outbox in
  this repo) — only the payload SHAPE is forward-compatible, wiring the
  real call is a future phase's job.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.loyalty.dto import LoyaltyTransactionDTO
from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.application.loyalty.result import LoyaltyResult, fail_from_domain_error
from backend.application.loyalty.use_cases._base import _LoyaltyBaseUseCase
from backend.domain.loyalty.entities.loyalty_transaction import LoyaltyTransaction
from backend.domain.loyalty.enums import TransactionType
from backend.domain.loyalty.events import SYSTEM_ACTOR_ID, LoyaltyEvents
from backend.domain.loyalty.exceptions import (
    InsufficientLoyaltyPointsError,
    LoyaltyAccountNotFoundError,
    LoyaltyDomainError,
    LoyaltyTransactionNotFoundError,
)
from backend.domain.loyalty.policies.balance_policy import LoyaltyBalancePolicy
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork
from backend.shared.ids import new_uuid


class AccrueLoyaltyPointsUseCase(_LoyaltyBaseUseCase):
    def execute(
        self, connection, *, loyalty_account_id: str, points_amount: Decimal,
        operation_id: str, actor_user_id: str, actor_branch_id: str,
        source_module: str, reason_code: str | None = None,
        source_document_id: str | None = None, sale_id: str | None = None,
        membership_id: str | None = None, available_at: str | None = None,
        expires_at: str | None = None, estimated_fair_value: Decimal | None = None,
        currency_code: str = "MXN", program_id: str | None = None,
    ) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.POINTS_CREDIT)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            account = uow.accounts.get(loyalty_account_id)
            if account is None:
                return fail_from_domain_error(
                    LoyaltyAccountNotFoundError(f"Cuenta {loyalty_account_id} no existe"),
                    operation_id=operation_id)
            if uow.transactions.exists_for_source(
                source_module=source_module, source_document_id=source_document_id,
                transaction_type=TransactionType.EARN, reason_code=reason_code,
            ):
                return fail_from_domain_error(
                    LoyaltyDomainError(
                        "Ya existe una acreditación registrada para este documento"),
                    operation_id=operation_id)
            try:
                earn = LoyaltyTransaction.earn(
                    loyalty_account_id=loyalty_account_id, points_amount=points_amount,
                    operation_id=operation_id, membership_id=membership_id,
                    source_module=source_module, source_document_id=source_document_id,
                    sale_id=sale_id, branch_id=actor_branch_id, reason_code=reason_code,
                    created_by_user_id=actor_user_id, available_at=available_at,
                    expires_at=expires_at,
                )
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.transactions.save(earn)
            extra = {"points_amount": str(points_amount), "currency_code": currency_code}
            if estimated_fair_value is not None:
                extra["estimated_fair_value"] = str(estimated_fair_value)
            if program_id is not None:
                extra["program_id"] = program_id
            if expires_at is not None:
                extra["expires_at"] = expires_at
            self._emit(uow, LoyaltyEvents.POINTS_ISSUED, entity_id=earn.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_user_id, loyalty_transaction_id=earn.id,
                       customer_id=account.customer_id, **extra)
        return LoyaltyResult.ok("Puntos acreditados", entity_id=earn.id,
                                operation_id=operation_id,
                                transaction=LoyaltyTransactionDTO.from_entity(earn))


class ReserveLoyaltyPointsUseCase(_LoyaltyBaseUseCase):
    def execute(
        self, connection, *, loyalty_account_id: str, points_amount: Decimal,
        operation_id: str, actor_user_id: str, actor_branch_id: str,
        source_module: str = "", reason_code: str | None = None,
        membership_id: str | None = None, sale_id: str | None = None,
    ) -> LoyaltyResult:
        if points_amount <= 0:
            return fail_from_domain_error(
                LoyaltyDomainError("El monto a reservar debe ser positivo"),
                operation_id=operation_id)
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.POINTS_REDEEM)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            account = uow.accounts.get(loyalty_account_id)
            if account is None:
                return fail_from_domain_error(
                    LoyaltyAccountNotFoundError(f"Cuenta {loyalty_account_id} no existe"),
                    operation_id=operation_id)
            ledger = uow.transactions.list_for_account(loyalty_account_id)
            balance = LoyaltyBalancePolicy.balance(ledger)
            if balance < points_amount:
                return fail_from_domain_error(
                    InsufficientLoyaltyPointsError(
                        f"Saldo insuficiente: disponible {balance}, solicitado {points_amount}"),
                    operation_id=operation_id)
            try:
                reservation = LoyaltyTransaction.reserve(
                    loyalty_account_id=loyalty_account_id, points_amount=-points_amount,
                    operation_id=operation_id, membership_id=membership_id,
                    source_module=source_module, reason_code=reason_code, sale_id=sale_id,
                    branch_id=actor_branch_id, created_by_user_id=actor_user_id,
                )
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.transactions.save(reservation)
            self._emit(uow, LoyaltyEvents.POINTS_RESERVED, entity_id=reservation.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_user_id, points_amount=str(points_amount))
        return LoyaltyResult.ok(
            "Puntos reservados", entity_id=reservation.id, operation_id=operation_id,
            transaction=LoyaltyTransactionDTO.from_entity(reservation))


class ConfirmReservedLoyaltyPointsUseCase(_LoyaltyBaseUseCase):
    """Finalizes a reservation (RESERVED → CONSUMED) — the reservation's own
    negative amount already reduced the balance the moment it was created
    (LOY-2's balance policy); confirming changes no numbers, only status."""

    def execute(self, connection, *, transaction_id: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.POINTS_REDEEM)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            reservation = uow.transactions.get(transaction_id)
            if reservation is None:
                return fail_from_domain_error(
                    LoyaltyTransactionNotFoundError(f"Transacción {transaction_id} no existe"),
                    operation_id=operation_id)
            try:
                reservation.mark_consumed()
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.transactions.save(reservation)
            self._emit(uow, LoyaltyEvents.POINTS_REDEEMED, entity_id=reservation.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_user_id,
                       points_amount=str(-reservation.points_amount))
        return LoyaltyResult.ok(
            "Canje confirmado", entity_id=reservation.id, operation_id=operation_id,
            transaction=LoyaltyTransactionDTO.from_entity(reservation))


class ReleaseLoyaltyPointsUseCase(_LoyaltyBaseUseCase):
    """Cancels a reservation (RESERVED → CANCELLED) and creates the
    offsetting RELEASE row that actually restores the balance (§26: 'en
    cancelación: RESERVED → RELEASED')."""

    def execute(self, connection, *, transaction_id: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.POINTS_REDEEM)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            reservation = uow.transactions.get(transaction_id)
            if reservation is None:
                return fail_from_domain_error(
                    LoyaltyTransactionNotFoundError(f"Transacción {transaction_id} no existe"),
                    operation_id=operation_id)
            try:
                release = LoyaltyTransaction.release_of(
                    reservation, operation_id=operation_id, created_by_user_id=actor_user_id)
                reservation.cancel_reservation()
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.transactions.save(reservation)
            uow.transactions.save(release)
            self._emit(uow, LoyaltyEvents.POINTS_RELEASED, entity_id=release.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_user_id, reservation_id=reservation.id,
                       points_amount=str(release.points_amount))
        return LoyaltyResult.ok(
            "Reserva liberada", entity_id=release.id, operation_id=operation_id,
            transaction=LoyaltyTransactionDTO.from_entity(release))


class RedeemLoyaltyPointsUseCase(_LoyaltyBaseUseCase):
    """Direct, one-step redemption (no prior reservation) — master prompt
    §11 lists REDEEM as its own transaction type distinct from RESERVE; not
    every canje needs the two-phase reserve/confirm dance (e.g. a simple
    in-store points-for-discount at checkout)."""

    def execute(
        self, connection, *, loyalty_account_id: str, points_amount: Decimal,
        operation_id: str, actor_user_id: str, actor_branch_id: str,
        source_module: str = "", reason_code: str | None = None,
        membership_id: str | None = None, sale_id: str | None = None,
    ) -> LoyaltyResult:
        if points_amount <= 0:
            return fail_from_domain_error(
                LoyaltyDomainError("El monto a canjear debe ser positivo"),
                operation_id=operation_id)
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.POINTS_REDEEM)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            account = uow.accounts.get(loyalty_account_id)
            if account is None:
                return fail_from_domain_error(
                    LoyaltyAccountNotFoundError(f"Cuenta {loyalty_account_id} no existe"),
                    operation_id=operation_id)
            ledger = uow.transactions.list_for_account(loyalty_account_id)
            balance = LoyaltyBalancePolicy.balance(ledger)
            if balance < points_amount:
                return fail_from_domain_error(
                    InsufficientLoyaltyPointsError(
                        f"Saldo insuficiente: disponible {balance}, solicitado {points_amount}"),
                    operation_id=operation_id)
            try:
                redeem = LoyaltyTransaction.redeem(
                    loyalty_account_id=loyalty_account_id, points_amount=-points_amount,
                    operation_id=operation_id, membership_id=membership_id,
                    source_module=source_module, reason_code=reason_code, sale_id=sale_id,
                    branch_id=actor_branch_id, created_by_user_id=actor_user_id,
                )
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.transactions.save(redeem)
            self._emit(uow, LoyaltyEvents.POINTS_REDEEMED, entity_id=redeem.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_user_id, points_amount=str(points_amount))
        return LoyaltyResult.ok(
            "Puntos canjeados", entity_id=redeem.id, operation_id=operation_id,
            transaction=LoyaltyTransactionDTO.from_entity(redeem))


class AdjustLoyaltyPointsUseCase(_LoyaltyBaseUseCase):
    """Manual adjustment — master prompt §60: 'quien ajusta puntos no
    aprueba su propio ajuste' is unconditional, not a threshold-gated rule
    (no threshold concept exists anywhere in this repo's Loyalty config
    yet). Every adjustment therefore always requires hot authorization from
    a distinct second user via LOY-1's `authorize_exception()` — the
    requester never needs `POINTS_ADJUST` directly, only the authorizer
    does."""

    def execute(
        self, connection, *, loyalty_account_id: str, points_amount: Decimal,
        reason_code: str, requested_by: str, authorizer_user_id: str,
        actor_branch_id: str, operation_id: str, membership_id: str | None = None,
    ) -> LoyaltyResult:
        try:
            self._auth.authorize_exception(
                authorizer_user_id=authorizer_user_id, requested_by=requested_by,
                permission_code=LoyaltyPermissions.POINTS_ADJUST,
                operation_id=operation_id, reason=reason_code, amount=points_amount,
                entity_id=loyalty_account_id,
            )
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            account = uow.accounts.get(loyalty_account_id)
            if account is None:
                return fail_from_domain_error(
                    LoyaltyAccountNotFoundError(f"Cuenta {loyalty_account_id} no existe"),
                    operation_id=operation_id)
            try:
                adjustment = LoyaltyTransaction.adjustment(
                    loyalty_account_id=loyalty_account_id, points_amount=points_amount,
                    operation_id=operation_id, reason_code=reason_code,
                    membership_id=membership_id, branch_id=actor_branch_id,
                    created_by_user_id=authorizer_user_id,
                )
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.transactions.save(adjustment)
            self._emit(uow, LoyaltyEvents.POINTS_ADJUSTED, entity_id=adjustment.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=authorizer_user_id, requested_by=requested_by,
                       points_amount=str(points_amount), reason_code=reason_code)
        return LoyaltyResult.ok(
            "Ajuste registrado", entity_id=adjustment.id, operation_id=operation_id,
            transaction=LoyaltyTransactionDTO.from_entity(adjustment))


class ReverseLoyaltyTransactionUseCase(_LoyaltyBaseUseCase):
    def execute(
        self, connection, *, transaction_id: str, reason_code: str, actor_user_id: str,
        actor_branch_id: str, operation_id: str,
    ) -> LoyaltyResult:
        try:
            self._auth.require(actor_user_id, LoyaltyPermissions.POINTS_REVERSE)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        with LoyaltyUnitOfWork(connection) as uow:
            original = uow.transactions.get(transaction_id)
            if original is None:
                return fail_from_domain_error(
                    LoyaltyTransactionNotFoundError(f"Transacción {transaction_id} no existe"),
                    operation_id=operation_id)
            try:
                reversal = LoyaltyTransaction.reversal_of(
                    original, operation_id=operation_id, reason_code=reason_code,
                    created_by_user_id=actor_user_id)
                original.mark_reversed(reversal.id)
            except LoyaltyDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            # `original.reversal_transaction_id` now points at `reversal.id` —
            # the reversal row must exist first, or the schema's own
            # `REFERENCES loyalty_transactions(id)` FK on that column fails
            # (caught by test_cannot_reverse_twice/test_reverse_nets_balance_to_zero
            # against a real `PRAGMA foreign_keys = ON` connection).
            uow.transactions.save(reversal)
            uow.transactions.save(original)
            self._emit(uow, LoyaltyEvents.TRANSACTION_REVERSED, entity_id=reversal.id,
                       operation_id=operation_id, branch_id=actor_branch_id,
                       actor_user_id=actor_user_id, original_transaction_id=original.id,
                       reason_code=reason_code)
        return LoyaltyResult.ok(
            "Transacción reversada", entity_id=reversal.id, operation_id=operation_id,
            transaction=LoyaltyTransactionDTO.from_entity(reversal))


class ExpireLoyaltyPointsUseCase(_LoyaltyBaseUseCase):
    """System sweep — no `actor_user_id` gate (mirrors
    `ExpireOrphanedInventoryReservationsUseCase`/CRM-26's time-based-trigger
    sweep: a maintenance hook, not a per-user action).

    **Known simplification, flagged not hidden**: expires the FULL original
    amount of any AVAILABLE EARN/BONUS transaction whose `expires_at` has
    passed — there is no lot-level FIFO tracking of which specific earn a
    later redemption drew down from, so a partially-redeemed earn still
    expires for its full original amount rather than only its remaining
    portion. A correct partial-expiry system needs per-lot consumption
    tracking that does not exist anywhere in this bounded context yet (the
    master prompt gives no algorithm for this either) — real gap, not
    fabricated sophistication.
    """

    def execute(self, connection, *, before_iso: str, operation_id_prefix: str,
                limit: int = 500) -> LoyaltyResult:
        with LoyaltyUnitOfWork(connection) as uow:
            expirable = uow.transactions.list_expirable(before_iso=before_iso, limit=limit)
            expired_ids: list[str] = []
            for original in expirable:
                op_id = new_uuid()
                expiry = LoyaltyTransaction.expire_of(
                    original, points_amount=-original.points_amount, operation_id=op_id)
                original.mark_expired()
                uow.transactions.save(original)
                uow.transactions.save(expiry)
                self._emit(uow, LoyaltyEvents.POINTS_EXPIRED, entity_id=expiry.id,
                           operation_id=op_id, branch_id=original.branch_id or SYSTEM_ACTOR_ID,
                           actor_user_id=SYSTEM_ACTOR_ID, original_transaction_id=original.id,
                           points_amount=str(-original.points_amount))
                expired_ids.append(original.id)
        return LoyaltyResult.ok(
            f"{len(expired_ids)} transacciones expiradas", operation_id=operation_id_prefix,
            expired_transaction_ids=expired_ids)
