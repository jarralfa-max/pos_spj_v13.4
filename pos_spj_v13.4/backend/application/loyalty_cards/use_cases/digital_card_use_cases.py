"""Loyalty digital card projection use cases (LOY-23, master prompt §48).

No dedicated `TARJETAS_FIDELIDAD.tarjeta_digital.*` permission was
pre-scaffolded by LOY-1 for this specific sub-feature — creating/refreshing
a projection reuses `CARD_CREATE` (it is a direct, tightly-coupled byproduct
of provisioning a DIGITAL card, not an independent write surface); reading
one reuses `CARD_VIEW`. Documented here rather than silently assumed.
"""

from __future__ import annotations

from backend.application.loyalty_cards.permissions import LoyaltyCardsPermissions
from backend.application.loyalty_cards.result import LoyaltyCardResult, fail_from_domain_error
from backend.application.loyalty_cards.use_cases._base import _LoyaltyCardsBaseUseCase
from backend.domain.loyalty_cards.entities.loyalty_digital_card_projection import (
    LoyaltyDigitalCardProjection,
)
from backend.domain.loyalty_cards.enums import LoyaltyCardType
from backend.domain.loyalty_cards.exceptions import (
    DigitalCardProjectionAlreadyExistsError,
    DigitalCardProjectionNotFoundError,
    InvalidDigitalCardProjectionError,
    LoyaltyCardDomainError,
    LoyaltyCardNotFoundError,
)
from backend.infrastructure.db.repositories.loyalty_cards.unit_of_work import LoyaltyCardsUnitOfWork


class CreateLoyaltyDigitalCardProjectionUseCase(_LoyaltyCardsBaseUseCase):
    def execute(
        self, connection, *, card_id: str, display_fields: dict[str, str], actor_user_id: str,
        operation_id: str,
    ) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.CARD_CREATE)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                card = uow.cards.get(card_id)
                if card is None:
                    return fail_from_domain_error(
                        LoyaltyCardNotFoundError(f"Tarjeta {card_id} no existe"),
                        operation_id=operation_id)
                if card.card_type is not LoyaltyCardType.DIGITAL:
                    return fail_from_domain_error(
                        InvalidDigitalCardProjectionError(
                            "Solo tarjetas DIGITAL tienen proyección digital"),
                        operation_id=operation_id)
                if uow.digital_projections.get_by_card(card_id) is not None:
                    return fail_from_domain_error(
                        DigitalCardProjectionAlreadyExistsError(
                            f"La tarjeta {card_id} ya tiene una proyección digital"),
                        operation_id=operation_id)
                token = uow.tokens.get_active_for_card(card_id)
                if token is None:
                    return fail_from_domain_error(
                        InvalidDigitalCardProjectionError(
                            "La tarjeta no tiene un token QR activo"),
                        operation_id=operation_id)
                projection = LoyaltyDigitalCardProjection.create(
                    card_id, card.customer_id, card.card_number, token.token,
                    display_fields=display_fields)
                uow.digital_projections.save(projection)
            return LoyaltyCardResult.ok(
                "Proyección de tarjeta digital creada", entity_id=projection.id,
                operation_id=operation_id)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class RefreshLoyaltyDigitalCardProjectionUseCase(_LoyaltyCardsBaseUseCase):
    def execute(
        self, connection, *, card_id: str, display_fields: dict[str, str], actor_user_id: str,
        operation_id: str,
    ) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.CARD_CREATE)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                projection = uow.digital_projections.get_by_card(card_id)
                if projection is None:
                    return fail_from_domain_error(
                        DigitalCardProjectionNotFoundError(
                            f"La tarjeta {card_id} no tiene proyección digital"),
                        operation_id=operation_id)
                active_token = uow.tokens.get_active_for_card(card_id)
                projection.refresh(
                    display_fields, qr_token=active_token.token if active_token else None)
                uow.digital_projections.save(projection)
            return LoyaltyCardResult.ok(
                "Proyección de tarjeta digital actualizada", entity_id=projection.id,
                operation_id=operation_id)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class GetLoyaltyDigitalCardProjectionUseCase(_LoyaltyCardsBaseUseCase):
    def execute(self, connection, *, card_id: str, actor_user_id: str,
                operation_id: str) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.CARD_VIEW)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                projection = uow.digital_projections.get_by_card(card_id)
                if projection is None:
                    return fail_from_domain_error(
                        DigitalCardProjectionNotFoundError(
                            f"La tarjeta {card_id} no tiene proyección digital"),
                        operation_id=operation_id)
            return LoyaltyCardResult.ok(
                "Proyección de tarjeta digital", entity_id=projection.id,
                operation_id=operation_id, card_number=projection.card_number,
                qr_token=projection.qr_token, display_fields=projection.display_fields,
                last_refreshed_at=projection.last_refreshed_at)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
