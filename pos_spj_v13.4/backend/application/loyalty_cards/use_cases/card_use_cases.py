"""Loyalty Cards lifecycle use cases (LOY-16, master prompt §31: emisión,
asignación, activación, bloqueo, reposición).

`membership_id`/`customer_id` are stored unchecked — never cross-validated
against `backend.domain.loyalty`'s own tables, same bounded-context-
isolation convention `CouponDefinition.source_program_id` established in
LOY-12 (see the card entity's own docstring)."""

from __future__ import annotations

from backend.application.loyalty_cards.permissions import LoyaltyCardsPermissions
from backend.application.loyalty_cards.result import LoyaltyCardResult, fail_from_domain_error
from backend.application.loyalty_cards.use_cases._base import _LoyaltyCardsBaseUseCase
from backend.domain.loyalty_cards.entities.loyalty_card import LoyaltyCard
from backend.domain.loyalty_cards.entities.loyalty_card_token import LoyaltyCardPublicToken
from backend.domain.loyalty_cards.enums import LoyaltyCardType
from backend.domain.loyalty_cards.events import LoyaltyCardEvents
from backend.domain.loyalty_cards.exceptions import (
    LoyaltyCardDomainError,
    LoyaltyCardNotFoundError,
)
from backend.infrastructure.db.repositories.loyalty_cards.unit_of_work import LoyaltyCardsUnitOfWork


def _next_card_number(uow) -> str:
    sequence = uow.cards.count_all() + 1
    return f"LC-{sequence:08d}"


class IssueLoyaltyCardUseCase(_LoyaltyCardsBaseUseCase):
    def execute(
        self, connection, *, customer_id: str, membership_id: str, card_type: LoyaltyCardType,
        actor_user_id: str, actor_branch_id: str, operation_id: str,
    ) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.CARD_CREATE)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                card = LoyaltyCard.issue(
                    _next_card_number(uow), card_type, customer_id, membership_id)
                uow.cards.save(card)
                token = LoyaltyCardPublicToken.issue(card.id)
                uow.tokens.save(token)
                self._emit(uow, LoyaltyCardEvents.CARD_ISSUED, entity_id=card.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id, card_number=card.card_number)
            return LoyaltyCardResult.ok(
                "Tarjeta emitida", entity_id=card.id, operation_id=operation_id,
                card_number=card.card_number, token=token.token)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class ActivateLoyaltyCardUseCase(_LoyaltyCardsBaseUseCase):
    def execute(self, connection, *, card_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.CARD_ACTIVATE)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                card = uow.cards.get(card_id)
                if card is None:
                    return fail_from_domain_error(
                        LoyaltyCardNotFoundError(f"Tarjeta {card_id} no existe"),
                        operation_id=operation_id)
                card.activate()
                uow.cards.save(card)
                self._emit(uow, LoyaltyCardEvents.CARD_ACTIVATED, entity_id=card.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id)
            return LoyaltyCardResult.ok("Tarjeta activada", entity_id=card.id,
                                        operation_id=operation_id)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class BlockLoyaltyCardUseCase(_LoyaltyCardsBaseUseCase):
    def execute(self, connection, *, card_id: str, reason: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.CARD_BLOCK)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                card = uow.cards.get(card_id)
                if card is None:
                    return fail_from_domain_error(
                        LoyaltyCardNotFoundError(f"Tarjeta {card_id} no existe"),
                        operation_id=operation_id)
                card.block(reason)
                uow.cards.save(card)
                active_token = uow.tokens.get_active_for_card(card_id)
                if active_token is not None:
                    active_token.revoke()
                    uow.tokens.save(active_token)
                    self._emit(uow, LoyaltyCardEvents.TOKEN_REVOKED, entity_id=active_token.id,
                               operation_id=operation_id, branch_id=actor_branch_id,
                               actor_user_id=actor_user_id, card_id=card.id)
                self._emit(uow, LoyaltyCardEvents.CARD_BLOCKED, entity_id=card.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id, reason=reason)
            return LoyaltyCardResult.ok("Tarjeta bloqueada", entity_id=card.id,
                                        operation_id=operation_id)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class UnblockLoyaltyCardUseCase(_LoyaltyCardsBaseUseCase):
    def execute(self, connection, *, card_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.CARD_BLOCK)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                card = uow.cards.get(card_id)
                if card is None:
                    return fail_from_domain_error(
                        LoyaltyCardNotFoundError(f"Tarjeta {card_id} no existe"),
                        operation_id=operation_id)
                card.unblock()
                uow.cards.save(card)
                new_token = LoyaltyCardPublicToken.issue(card.id)
                uow.tokens.save(new_token)
                self._emit(uow, LoyaltyCardEvents.CARD_UNBLOCKED, entity_id=card.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id)
            return LoyaltyCardResult.ok("Tarjeta desbloqueada", entity_id=card.id,
                                        operation_id=operation_id, token=new_token.token)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class ReplaceLoyaltyCardUseCase(_LoyaltyCardsBaseUseCase):
    def execute(self, connection, *, card_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.CARD_REPLACE)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                old_card = uow.cards.get(card_id)
                if old_card is None:
                    return fail_from_domain_error(
                        LoyaltyCardNotFoundError(f"Tarjeta {card_id} no existe"),
                        operation_id=operation_id)
                old_active_token = uow.tokens.get_active_for_card(card_id)
                if old_active_token is not None:
                    old_active_token.revoke()
                    uow.tokens.save(old_active_token)

                new_card = LoyaltyCard.issue_replacement(old_card, _next_card_number(uow))
                uow.cards.save(new_card)
                new_token = LoyaltyCardPublicToken.issue(new_card.id)
                uow.tokens.save(new_token)

                old_card.mark_replaced(new_card.id)
                uow.cards.save(old_card)

                self._emit(uow, LoyaltyCardEvents.CARD_REPLACED, entity_id=new_card.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id, replaces_card_id=old_card.id)
            return LoyaltyCardResult.ok(
                "Tarjeta repuesta", entity_id=new_card.id, operation_id=operation_id,
                card_number=new_card.card_number, token=new_token.token)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class CancelLoyaltyCardUseCase(_LoyaltyCardsBaseUseCase):
    def execute(self, connection, *, card_id: str, reason: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.CARD_CANCEL)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                card = uow.cards.get(card_id)
                if card is None:
                    return fail_from_domain_error(
                        LoyaltyCardNotFoundError(f"Tarjeta {card_id} no existe"),
                        operation_id=operation_id)
                card.cancel(reason)
                uow.cards.save(card)
                active_token = uow.tokens.get_active_for_card(card_id)
                if active_token is not None:
                    active_token.revoke()
                    uow.tokens.save(active_token)
                self._emit(uow, LoyaltyCardEvents.CARD_CANCELLED, entity_id=card.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id, reason=reason)
            return LoyaltyCardResult.ok("Tarjeta cancelada", entity_id=card.id,
                                        operation_id=operation_id)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
