"""Qué puede canjear un cliente en esta venta — sin efectos secundarios.

Compone tres piezas que no se conocen entre sí: los ajustes del programa
(parámetros gobernados de Configuración), el saldo de puntos (que abarca los dos libros que
conviven) y la política de topes (pura, en el dominio).

SIN EFECTOS SECUNDARIOS, y no es un detalle de estilo: la caja llama a esto
mientras el cajero teclea, para pintar "tienes N puntos, puedes ahorrar $X".
Si acumulara o descontara algo, cada tecla movería el saldo del cliente. El
canje de verdad es `RedeemLoyaltyPointsUseCase`, y ocurre una sola vez al
cobrar.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.settings.configuration_reader import ConfigurationReader

from backend.domain.loyalty.policies.redemption_policy import (
    LoyaltyRedemptionPolicy,
    RedemptionPreview,
    RedemptionSettings,
)
from backend.infrastructure.db.repositories.loyalty.points_balance_repository import (
    LoyaltyPointsBalanceRepository,
)

#: Parámetros del catálogo de Configuración (`backend/application/settings/
#: catalog.py`). Antes eran `loyalty_valor_estrella`, `loyalty_min_puntos_canje`
#: y `loyalty_max_pct_canje` en `configuraciones`; la migración 303 los movió.
POINT_VALUE_KEY = "loyalty.point_value"
MIN_POINTS_KEY = "loyalty.min_points_to_redeem"
MAX_PERCENT_KEY = "loyalty.max_redeem_fraction"


class LoyaltyRedemptionPreviewQuery:
    def __init__(self, connection) -> None:
        self._conn = connection

    def settings(self) -> RedemptionSettings:
        """Ajustes del programa, ya tipados y validados por el gobierno de
        configuración: un valor ilegible no puede llegar a guardarse, y sin
        valor guardado rige el de omisión del catálogo."""
        reader = ConfigurationReader(self._conn)
        return RedemptionSettings(
            point_value=reader.get(POINT_VALUE_KEY),
            min_points=reader.get(MIN_POINTS_KEY),
            max_percent=reader.get(MAX_PERCENT_KEY),
        )

    def balance(self, customer_id: str) -> int:
        return LoyaltyPointsBalanceRepository(self._conn).balance_for_customer(customer_id)

    def preview(
        self, *, customer_id: str, subtotal: Decimal, requested_points: int = 0,
    ) -> RedemptionPreview:
        """Previsualización completa. Un cliente sin identificar no canjea.

        Una venta a público general no tiene a quién abonarle ni de quién
        descontar: se devuelve una previsualización en ceros, no un error —
        vender sin cliente es lo normal, no una excepción.
        """
        if not str(customer_id or "").strip():
            return LoyaltyRedemptionPolicy.preview(
                balance=0, subtotal=subtotal, settings=self.settings())
        return LoyaltyRedemptionPolicy.preview(
            balance=self.balance(customer_id), subtotal=subtotal,
            settings=self.settings(), requested_points=requested_points)
