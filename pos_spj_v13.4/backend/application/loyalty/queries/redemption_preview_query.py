"""Qué puede canjear un cliente en esta venta — sin efectos secundarios.

Compone tres piezas que no se conocen entre sí: los ajustes del programa
(`configuraciones`), el saldo de puntos (que abarca los dos libros que
conviven) y la política de topes (pura, en el dominio).

SIN EFECTOS SECUNDARIOS, y no es un detalle de estilo: la caja llama a esto
mientras el cajero teclea, para pintar "tienes N puntos, puedes ahorrar $X".
Si acumulara o descontara algo, cada tecla movería el saldo del cliente. El
canje de verdad es `RedeemLoyaltyPointsUseCase`, y ocurre una sola vez al
cobrar.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from backend.domain.loyalty.policies.redemption_policy import (
    LoyaltyRedemptionPolicy,
    RedemptionPreview,
    RedemptionSettings,
)
from backend.infrastructure.db.repositories.loyalty.points_balance_repository import (
    LoyaltyPointsBalanceRepository,
)

#: Claves en `configuraciones`. Los nombres son los que ya usa una instalación
#: en marcha; renombrarlos dejaría el programa con los valores por omisión sin
#: avisar de nada.
POINT_VALUE_KEY = "loyalty_valor_estrella"
MIN_POINTS_KEY = "loyalty_min_puntos_canje"
MAX_PERCENT_KEY = "loyalty_max_pct_canje"


class LoyaltyRedemptionPreviewQuery:
    def __init__(self, connection) -> None:
        self._conn = connection

    def settings(self) -> RedemptionSettings:
        """Ajustes del programa, con los del esquema base como respaldo.

        Un valor ilegible (texto donde debía ir un número, fila borrada a
        medias) cae al de omisión en lugar de propagar la excepción: dejar el
        cobro tirado porque un ajuste está corrupto es peor que canjear con los
        parámetros de fábrica, y el respaldo es conservador.
        """
        defaults = RedemptionSettings()
        return RedemptionSettings(
            point_value=self._decimal(POINT_VALUE_KEY, defaults.point_value),
            min_points=int(self._decimal(MIN_POINTS_KEY, Decimal(defaults.min_points))),
            max_percent=self._decimal(MAX_PERCENT_KEY, defaults.max_percent),
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

    def _decimal(self, key: str, default: Decimal) -> Decimal:
        try:
            row = self._conn.execute(
                "SELECT valor FROM configuraciones WHERE clave=? LIMIT 1", (key,)).fetchone()
        except Exception:
            return default
        if row is None or str(row[0] or "").strip() == "":
            return default
        try:
            return Decimal(str(row[0]).strip())
        except (InvalidOperation, ValueError):
            return default
