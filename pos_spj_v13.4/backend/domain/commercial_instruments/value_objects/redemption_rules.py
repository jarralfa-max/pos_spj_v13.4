"""Reglas de canje de una pieza de vale emitida por lote (auditoría de Fidelidad
968e0bc, ampliación «lotes físicos de vales y cupones»).

Se fijan EN CADA PIEZA al emitirla (fotografía): cambiar el lote después no
revaloriza piezas ya entregadas. Un vale sin reglas (los emitidos uno por uno,
los de devolución, el saldo a favor) se comporta como siempre: saldo libre en
varias ventas.

Cálculo del importe aplicable en UNA venta:

    min(saldo_disponible, lo_que_falta_por_pagar,
        porcentaje × base_elegible, presupuesto_de_margen_si_es_promocional)

redondeado a centavos hacia abajo (nunca se aplica un centavo de más).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from enum import Enum

from backend.domain.commercial_instruments.exceptions import CommercialInstrumentDomainError

_CENT = Decimal("0.01")
_HUNDRED = Decimal("100")


class RedemptionMode(str, Enum):
    #: Un solo canje cierra la pieza.
    ONE_EVENT = "ONE_EVENT"
    #: Varias ventas, hasta agotar saldo, vencer o llegar al número de canjes.
    MULTI_EVENT = "MULTI_EVENT"


class PercentBase(str, Enum):
    #: El porcentaje se calcula sobre el subtotal antes de descuentos.
    GROSS = "GROSS"
    #: … o después de descuentos (cupones, puntos, descuento manual).
    NET = "NET"


class LeftoverPolicy(str, Enum):
    """Qué pasa en UN EVENTO si el saldo no cabe completo en la venta."""

    #: No se deja canjear: el cliente perdería saldo. Opción conservadora.
    REQUIRE_FULL_USE = "REQUIRE_FULL_USE"
    #: Se canjea lo que cabe y el sobrante se pierde (queda en el libro).
    FORFEIT = "FORFEIT"


class FundingSource(str, Enum):
    #: Ya se cobró: cancela un pasivo, NO es un descuento sobre el margen.
    PREPAID = "PREPAID"
    #: Lo financia el negocio: está sujeto al margen protegido (FID-03).
    PROMOTIONAL = "PROMOTIONAL"
    COMPENSATION = "COMPENSATION"
    #: Lo financia un tercero (proveedor): su recuperación se modela aparte.
    THIRD_PARTY = "THIRD_PARTY"

    @property
    def consumes_margin(self) -> bool:
        return self in (FundingSource.PROMOTIONAL, FundingSource.COMPENSATION)


class RedemptionRulesError(CommercialInstrumentDomainError):
    """La pieza no se puede canjear en esta venta; el mensaje es para el cajero."""


@dataclass(frozen=True)
class RedemptionRules:
    mode: RedemptionMode = RedemptionMode.MULTI_EVENT
    #: `None` = sin límite de canjes (sólo el saldo). En UN EVENTO siempre 1.
    max_redemptions: int | None = None
    #: `None` = sin tope porcentual. Ej. `Decimal("20")` = hasta 20 % de la venta.
    max_percent_per_sale: Decimal | None = None
    percent_base: PercentBase = PercentBase.GROSS
    leftover_policy: LeftoverPolicy = LeftoverPolicy.REQUIRE_FULL_USE
    funding_source: FundingSource = FundingSource.PROMOTIONAL

    def __post_init__(self) -> None:
        if self.mode is RedemptionMode.ONE_EVENT and self.max_redemptions not in (None, 1):
            raise RedemptionRulesError("Un vale de un solo evento se canjea una sola vez")
        if self.max_redemptions is not None and self.max_redemptions < 1:
            raise RedemptionRulesError("El número de canjes debe ser al menos 1")
        if self.max_percent_per_sale is not None:
            if not isinstance(self.max_percent_per_sale, Decimal):
                raise RedemptionRulesError("El porcentaje debe ser Decimal")
            if not Decimal("0") < self.max_percent_per_sale <= _HUNDRED:
                raise RedemptionRulesError("El porcentaje por venta va de 0 a 100")

    @property
    def effective_max_redemptions(self) -> int | None:
        return 1 if self.mode is RedemptionMode.ONE_EVENT else self.max_redemptions

    def applicable_amount(self, *, balance: Decimal, requested: Decimal, gross_base: Decimal,
                          net_base: Decimal, prior_redemptions: int,
                          margin_budget: Decimal | None = None) -> Decimal:
        """Importe que esta pieza puede pagar en ESTA venta.

        `margin_budget` sólo aplica a piezas financiadas por el negocio; `None`
        significa que no hay tope de margen (prepago, tercero)."""
        if balance <= 0:
            raise RedemptionRulesError("El vale ya no tiene saldo")
        tope_canjes = self.effective_max_redemptions
        if tope_canjes is not None and prior_redemptions >= tope_canjes:
            raise RedemptionRulesError(
                "El vale ya se usó" if tope_canjes == 1
                else f"El vale ya alcanzó sus {tope_canjes} canjes")
        candidatos = [balance, requested]
        if self.max_percent_per_sale is not None:
            base = gross_base if self.percent_base is PercentBase.GROSS else net_base
            candidatos.append(max(Decimal("0"), base) * self.max_percent_per_sale / _HUNDRED)
        if margin_budget is not None and self.funding_source.consumes_margin:
            candidatos.append(max(Decimal("0"), margin_budget))
        importe = min(candidatos).quantize(_CENT, rounding=ROUND_DOWN)
        if importe <= 0:
            raise RedemptionRulesError("Esta venta no admite pagar con el vale")
        if (self.mode is RedemptionMode.ONE_EVENT
                and self.leftover_policy is LeftoverPolicy.REQUIRE_FULL_USE
                and importe < balance):
            raise RedemptionRulesError(
                f"El vale es de un solo uso y su saldo (${balance:,.2f}) no cabe completo en "
                f"esta venta (máximo ${importe:,.2f}); se perdería el resto.")
        return importe

    def closes_after(self, *, redemptions_after: int, remaining: Decimal) -> bool:
        """¿La pieza queda cerrada tras este canje?"""
        if remaining <= 0:
            return True
        tope = self.effective_max_redemptions
        return tope is not None and redemptions_after >= tope


__all__ = [
    "FundingSource", "LeftoverPolicy", "PercentBase", "RedemptionMode", "RedemptionRules",
    "RedemptionRulesError",
]
