"""Loyalty Card QR token rotation use case (LOY-16, master prompt §32)."""

from __future__ import annotations

from backend.application.loyalty_cards.permissions import LoyaltyCardsPermissions
from backend.application.loyalty_cards.result import LoyaltyCardResult, fail_from_domain_error
from backend.application.loyalty_cards.use_cases._base import _LoyaltyCardsBaseUseCase
from backend.domain.loyalty_cards.events import LoyaltyCardEvents
from backend.domain.loyalty_cards.exceptions import (
    LoyaltyCardDomainError,
    LoyaltyCardNotFoundError,
    LoyaltyCardTokenNotFoundError,
)
from backend.infrastructure.db.repositories.loyalty_cards.unit_of_work import LoyaltyCardsUnitOfWork


class RotateLoyaltyCardTokenUseCase(_LoyaltyCardsBaseUseCase):
    """§32: rotate a card's public QR token — e.g. after a suspected leak —
    without touching the card's own identity, status, or history."""

    def execute(self, connection, *, card_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.QR_ROTATE)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                card = uow.cards.get(card_id)
                if card is None:
                    return fail_from_domain_error(
                        LoyaltyCardNotFoundError(f"Tarjeta {card_id} no existe"),
                        operation_id=operation_id)
                old_token = uow.tokens.get_active_for_card(card_id)
                if old_token is None:
                    return fail_from_domain_error(
                        LoyaltyCardTokenNotFoundError(
                            f"La tarjeta {card_id} no tiene un token activo"),
                        operation_id=operation_id)
                new_token = old_token.rotate()
                uow.tokens.save(old_token)
                uow.tokens.save(new_token)
                self._emit(uow, LoyaltyCardEvents.TOKEN_ROTATED, entity_id=new_token.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id, card_id=card.id,
                           previous_token_id=old_token.id)
            return LoyaltyCardResult.ok(
                "Token QR rotado", entity_id=new_token.id, operation_id=operation_id,
                token=new_token.token)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
