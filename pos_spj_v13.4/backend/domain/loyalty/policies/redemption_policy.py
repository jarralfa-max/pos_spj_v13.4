"""Cuántos puntos puede canjear un cliente en una venta, y por cuánto descuento.

Función pura sobre saldo, subtotal y la configuración del programa. Sin E/S:
quién lee el saldo y de dónde salen los ajustes es problema de la capa de
aplicación.

LAS REGLAS NO SON INVENTADAS. Vivían en `core/services/loyalty_service.py::
preview_redemption`, borrado, pero su contrato completo sobrevive en
`tests/test_loyalty_redemption_source.py` — nombres de campo, topes y aritmética
incluidos. Los ajustes que las parametrizan tampoco se inventan: son filas de
`configuraciones` (`loyalty_valor_estrella`, `loyalty_min_puntos_canje`,
`loyalty_max_pct_canje`), que ese mismo test siembra.

TRES TOPES, EN ESTE ORDEN
-------------------------
1. Mínimo: por debajo de `min_points` no se canjea NADA. No es "canjea lo que
   tengas": un programa con mínimo de 100 puntos y un cliente con 50 no canjea
   50, canjea cero.
2. Porcentaje del ticket: el descuento no puede pasar de `max_percent` del
   subtotal. Es lo que impide que una venta se pague entera con puntos.
3. Saldo: no se canja más de lo que se tiene.

El orden importa para el primero. Los otros dos son un mínimo entre ambos, pero
el de mínimo es una puerta: o se abre o no hay canje.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal


@dataclass(frozen=True)
class RedemptionSettings:
    """Parámetros del programa. Valores por omisión = los del esquema base."""

    #: Pesos que vale cada punto al canjearlo (`loyalty_valor_estrella`).
    point_value: Decimal = Decimal("0.10")
    #: Saldo mínimo para poder canjear (`loyalty_min_puntos_canje`).
    min_points: int = 0
    #: Fracción máxima del subtotal pagadera con puntos (`loyalty_max_pct_canje`).
    max_percent: Decimal = Decimal("0.5")


@dataclass(frozen=True)
class RedemptionPreview:
    available_points: int
    max_redeemable_points: int
    max_discount: Decimal
    requested_points: int
    discount: Decimal
    subtotal: Decimal

    @property
    def total_after_discount(self) -> Decimal:
        return self.subtotal - self.discount


class LoyaltyRedemptionPolicy:
    @staticmethod
    def max_redeemable_points(
        *, balance: int, subtotal: Decimal, settings: RedemptionSettings,
    ) -> int:
        """Techo de puntos canjeables en esta venta.

        Un `point_value` de cero o negativo devuelve cero en vez de dividir:
        un programa mal configurado no puede convertirse en descuento infinito.
        """
        if balance <= 0 or subtotal <= 0:
            return 0
        if balance < settings.min_points:
            return 0
        if settings.point_value <= 0:
            return 0

        tope_por_importe = (subtotal * settings.max_percent) / settings.point_value
        # Se trunca hacia abajo: redondear hacia arriba dejaría pasar un punto
        # más de lo que el tope de porcentaje permite.
        por_importe = int(tope_por_importe.to_integral_value(rounding=ROUND_DOWN))
        return max(0, min(balance, por_importe))

    @classmethod
    def preview(
        cls, *, balance: int, subtotal: Decimal, settings: RedemptionSettings,
        requested_points: int = 0,
    ) -> RedemptionPreview:
        """Qué pasaría si se canjearan `requested_points`.

        Lo solicitado se RECORTA al techo en lugar de rechazarse: la caja pide
        una cantidad y el sistema responde con la que de verdad aplica. Este
        recorte es la única fuente de la cantidad aprobada — si quien llama
        usara su propio número en lugar del que sale de aquí, se saltaría los
        topes sin que nada lo impidiera.

        Sin cantidad solicitada devuelve cero canjeados: una previsualización
        no decide por el cliente cuántos puntos gastar.
        """
        maximo = cls.max_redeemable_points(
            balance=balance, subtotal=subtotal, settings=settings)
        solicitados = max(0, min(int(requested_points or 0), maximo))
        return RedemptionPreview(
            available_points=max(0, balance),
            max_redeemable_points=maximo,
            max_discount=maximo * settings.point_value,
            requested_points=solicitados,
            discount=solicitados * settings.point_value,
            subtotal=subtotal,
        )
