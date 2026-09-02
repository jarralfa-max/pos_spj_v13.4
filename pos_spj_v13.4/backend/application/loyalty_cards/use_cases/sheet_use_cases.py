"""Loyalty Card sheet + imposition profile use cases (LOY-20, master
prompt §38-40). Both are configuration entities — creation only, no
lifecycle beyond a sheet profile's active/inactive flag."""

from __future__ import annotations

from decimal import Decimal

from backend.application.loyalty_cards.permissions import LoyaltyCardsPermissions
from backend.application.loyalty_cards.result import LoyaltyCardResult, fail_from_domain_error
from backend.application.loyalty_cards.use_cases._base import _LoyaltyCardsBaseUseCase
from backend.domain.loyalty_cards.entities.loyalty_card_imposition_profile import (
    LoyaltyCardImpositionProfile,
)
from backend.domain.loyalty_cards.entities.loyalty_card_sheet_profile import (
    LoyaltyCardSheetProfile,
)
from backend.domain.loyalty_cards.events import LoyaltyCardEvents
from backend.domain.loyalty_cards.exceptions import (
    LoyaltyCardDomainError,
    LoyaltyCardSheetProfileNotFoundError,
)
from backend.infrastructure.db.repositories.loyalty_cards.unit_of_work import LoyaltyCardsUnitOfWork


class CreateSheetProfileUseCase(_LoyaltyCardsBaseUseCase):
    def execute(
        self, connection, *, code: str, name: str, width_mm: Decimal, height_mm: Decimal,
        actor_user_id: str, actor_branch_id: str, operation_id: str, **profile_kwargs,
    ) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.SHEET_MANAGE)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                profile = LoyaltyCardSheetProfile.create(
                    code, name, width_mm, height_mm, **profile_kwargs)
                uow.sheet_profiles.save(profile)
                self._emit(uow, LoyaltyCardEvents.SHEET_PROFILE_CREATED, entity_id=profile.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id)
            return LoyaltyCardResult.ok(
                "Pliego creado", entity_id=profile.id, operation_id=operation_id,
                printable_width_mm=str(profile.printable_width_mm()),
                printable_height_mm=str(profile.printable_height_mm()))
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class CreateStandard12x18SheetProfileUseCase(_LoyaltyCardsBaseUseCase):
    """Convenience wrapper for the phase's own reference sheet size — still
    goes through the same real conversion factor as any other sheet
    (`LoyaltyCardSheetProfile.standard_12x18()`), never a separate hardcoded
    path."""

    def execute(self, connection, *, actor_user_id: str, actor_branch_id: str,
                operation_id: str) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.SHEET_MANAGE)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                profile = LoyaltyCardSheetProfile.standard_12x18()
                uow.sheet_profiles.save(profile)
                self._emit(uow, LoyaltyCardEvents.SHEET_PROFILE_CREATED, entity_id=profile.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id)
            return LoyaltyCardResult.ok(
                "Pliego 12x18 creado", entity_id=profile.id, operation_id=operation_id)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class CreateImpositionProfileUseCase(_LoyaltyCardsBaseUseCase):
    def execute(
        self, connection, *, sheet_profile_id: str, card_width_mm: Decimal,
        card_height_mm: Decimal, actor_user_id: str, actor_branch_id: str, operation_id: str,
        **imposition_kwargs,
    ) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.SHEET_MANAGE)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                sheet = uow.sheet_profiles.get(sheet_profile_id)
                if sheet is None:
                    return fail_from_domain_error(
                        LoyaltyCardSheetProfileNotFoundError(
                            f"Pliego {sheet_profile_id} no existe"),
                        operation_id=operation_id)
                imposition = LoyaltyCardImpositionProfile.create(
                    sheet_profile_id, printable_width_mm=sheet.printable_width_mm(),
                    printable_height_mm=sheet.printable_height_mm(), card_width_mm=card_width_mm,
                    card_height_mm=card_height_mm, **imposition_kwargs)
                uow.imposition_profiles.save(imposition)
                self._emit(uow, LoyaltyCardEvents.IMPOSITION_PROFILE_CREATED,
                           entity_id=imposition.id, operation_id=operation_id,
                           branch_id=actor_branch_id, actor_user_id=actor_user_id,
                           cards_per_sheet=imposition.cards_per_sheet)
            return LoyaltyCardResult.ok(
                "Perfil de imposición creado", entity_id=imposition.id, operation_id=operation_id,
                columns=imposition.columns, rows=imposition.rows,
                cards_per_sheet=imposition.cards_per_sheet)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
