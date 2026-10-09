"""Privacidad de lo que se imprime en una tarjeta (LOY-29, §37, §58).

Cómo se imprime el nombre (completo, sólo nombre, iniciales o nada) y si se
imprime el saldo de puntos (por omisión, NO). Son parámetros gobernados de
Configuración (`GovernedSettingsWriter`); antes vivían en `configuraciones`, las
lee `LoyaltyCardRenderDataQuery` al armar cada tarjeta y la proyección digital.

Exige `TARJETAS_FIDELIDAD.configuracion.editar`; el antes y el después quedan en
la auditoría.
"""

from __future__ import annotations

from backend.application.loyalty_cards.permissions import LoyaltyCardsPermissions
from backend.application.loyalty_cards.queries.card_render_data_query import (
    NAME_MODE_KEY,
    PRINT_POINTS_KEY,
    LoyaltyCardRenderDataQuery,
)
from backend.application.loyalty_cards.result import LoyaltyCardResult, fail_from_domain_error
from backend.application.loyalty_cards.use_cases._base import _LoyaltyCardsBaseUseCase
from backend.application.settings.governance import GovernedSettingsWriter
from backend.domain.loyalty_cards.exceptions import LoyaltyCardDomainError
from backend.domain.loyalty_cards.policies.privacy_policy import CardNameMode
from backend.domain.settings.exceptions import ConfigurationDomainError
from backend.infrastructure.db.repositories.loyalty_cards.unit_of_work import LoyaltyCardsUnitOfWork
from backend.shared.ids import new_uuid


class UpdateLoyaltyCardPrivacySettingsUseCase(_LoyaltyCardsBaseUseCase):
    def execute(self, connection, *, name_mode: CardNameMode, print_points_balance: bool,
                actor_user_id: str, actor_branch_id: str, operation_id: str) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.CONFIG_EDIT)
            modo = CardNameMode(name_mode)
        except (LoyaltyCardDomainError, ValueError) as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        antes = LoyaltyCardRenderDataQuery(connection).privacy_settings()
        nuevos = {NAME_MODE_KEY: modo.value, PRINT_POINTS_KEY: bool(print_points_balance)}
        writer = GovernedSettingsWriter(connection)
        try:
            with LoyaltyCardsUnitOfWork(connection) as uow:
                writer.stage(nuevos, actor_user_id=actor_user_id, operation_id=operation_id,
                             reason="Tarjetas → Privacidad")
                self._audit(uow, "UpdateLoyaltyCardPrivacySettings", entity_id=new_uuid(),
                            operation_id=operation_id, branch_id=actor_branch_id,
                            actor_user_id=actor_user_id,
                            before={NAME_MODE_KEY: antes.name_mode.value,
                                    PRINT_POINTS_KEY: antes.print_points_balance},
                            after=nuevos)
        except ConfigurationDomainError as exc:
            return fail_from_domain_error(LoyaltyCardDomainError(str(exc)), operation_id=operation_id)
        writer.publish()
        return LoyaltyCardResult.ok("Privacidad de tarjetas guardada", operation_id=operation_id)


__all__ = ["UpdateLoyaltyCardPrivacySettingsUseCase"]
