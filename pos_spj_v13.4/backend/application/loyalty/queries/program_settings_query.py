"""Los ajustes del programa de puntos: acumulación, caducidad y canje.

Viven en `configuraciones`, junto a los de canje que ya leía
`LoyaltyRedemptionPreviewQuery` (mismas claves; renombrarlas dejaría una
instalación en marcha con los valores de fábrica sin avisar). Las tres claves
de acumulación son nuevas (2026-10-02); sus valores iniciales los decidió el
usuario y los siembra la migración 289.

Un valor ilegible cae al de omisión en vez de reventar el cobro: el respaldo
es el mismo que siembra la migración.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from backend.application.loyalty.queries.redemption_preview_query import (
    MAX_PERCENT_KEY,
    MIN_POINTS_KEY,
    POINT_VALUE_KEY,
    LoyaltyRedemptionPreviewQuery,
)
from backend.domain.loyalty.policies.accrual_policy import AccrualSettings
from backend.domain.loyalty.policies.redemption_policy import RedemptionSettings

PESOS_PER_POINT_KEY = "loyalty_pesos_por_punto"
CREDIT_EARNS_KEY = "loyalty_credito_acumula"
EXPIRATION_MONTHS_KEY = "loyalty_meses_caducidad"


@dataclass(frozen=True)
class LoyaltyProgramSettings:
    accrual: AccrualSettings
    redemption: RedemptionSettings


class LoyaltyProgramSettingsQuery:
    def __init__(self, connection) -> None:
        self._conn = connection

    def accrual(self) -> AccrualSettings:
        defaults = AccrualSettings()
        pesos = self._decimal(PESOS_PER_POINT_KEY, defaults.pesos_per_point)
        meses = self._decimal(EXPIRATION_MONTHS_KEY, Decimal(defaults.expiration_months))
        try:
            return AccrualSettings(
                pesos_per_point=pesos if pesos > 0 else defaults.pesos_per_point,
                credit_earns=self._flag(CREDIT_EARNS_KEY, defaults.credit_earns),
                expiration_months=max(int(meses), 0))
        except ValueError:
            return defaults

    def current(self) -> LoyaltyProgramSettings:
        return LoyaltyProgramSettings(
            accrual=self.accrual(),
            redemption=LoyaltyRedemptionPreviewQuery(self._conn).settings())

    def _raw(self, key: str) -> str | None:
        try:
            row = self._conn.execute(
                "SELECT valor FROM configuraciones WHERE clave=? LIMIT 1", (key,)).fetchone()
        except Exception:
            return None
        if row is None or str(row[0] or "").strip() == "":
            return None
        return str(row[0]).strip()

    def _decimal(self, key: str, default: Decimal) -> Decimal:
        raw = self._raw(key)
        if raw is None:
            return default
        try:
            return Decimal(raw)
        except (InvalidOperation, ValueError):
            return default

    def _flag(self, key: str, default: bool) -> bool:
        raw = self._raw(key)
        if raw is None:
            return default
        return raw.lower() in ("1", "true", "si", "sí", "yes")


__all__ = [
    "CREDIT_EARNS_KEY", "EXPIRATION_MONTHS_KEY", "LoyaltyProgramSettings",
    "LoyaltyProgramSettingsQuery", "MAX_PERCENT_KEY", "MIN_POINTS_KEY", "PESOS_PER_POINT_KEY",
    "POINT_VALUE_KEY",
]
