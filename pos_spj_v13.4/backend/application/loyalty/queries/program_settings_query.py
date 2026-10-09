"""Los ajustes del programa de puntos: acumulación, caducidad y canje.

Son parámetros gobernados de Configuración (catálogo en
`backend/application/settings/catalog.py`): se leen con `ConfigurationReader`
y se cambian con `GovernedSettingsWriter`, que versiona y audita. Antes vivían
como texto en `configuraciones`; la migración 303 los movió con su valor.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.loyalty.queries.redemption_preview_query import (
    MAX_PERCENT_KEY,
    MIN_POINTS_KEY,
    POINT_VALUE_KEY,
    LoyaltyRedemptionPreviewQuery,
)
from backend.application.settings.configuration_reader import ConfigurationReader
from backend.domain.loyalty.policies.accrual_policy import AccrualSettings
from backend.domain.loyalty.policies.redemption_policy import RedemptionSettings

PESOS_PER_POINT_KEY = "loyalty.pesos_per_point"
CREDIT_EARNS_KEY = "loyalty.credit_earns"
EXPIRATION_MONTHS_KEY = "loyalty.points_expiration_months"


@dataclass(frozen=True)
class LoyaltyProgramSettings:
    accrual: AccrualSettings
    redemption: RedemptionSettings


class LoyaltyProgramSettingsQuery:
    def __init__(self, connection) -> None:
        self._conn = connection

    def accrual(self) -> AccrualSettings:
        reader = ConfigurationReader(self._conn)
        return AccrualSettings(
            pesos_per_point=reader.get(PESOS_PER_POINT_KEY),
            credit_earns=reader.get(CREDIT_EARNS_KEY),
            expiration_months=reader.get(EXPIRATION_MONTHS_KEY))

    def current(self) -> LoyaltyProgramSettings:
        return LoyaltyProgramSettings(
            accrual=self.accrual(),
            redemption=LoyaltyRedemptionPreviewQuery(self._conn).settings())


__all__ = [
    "CREDIT_EARNS_KEY", "EXPIRATION_MONTHS_KEY", "LoyaltyProgramSettings",
    "LoyaltyProgramSettingsQuery", "MAX_PERCENT_KEY", "MIN_POINTS_KEY", "PESOS_PER_POINT_KEY",
    "POINT_VALUE_KEY",
]
