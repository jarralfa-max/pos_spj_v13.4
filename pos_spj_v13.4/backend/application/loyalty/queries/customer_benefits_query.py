"""EvaluateCustomerBenefitsQuery (§25): lo que Fidelidad le dice a Ventas.

Decisión del usuario (2026-10-03): "las reglas salen de Fidelidad y el POS las
ejecuta". Ventas pregunta aquí —con el carrito, la sucursal, el canal y la
forma de pago— y recibe la respuesta completa: puntos a ganar con su desglose
por regla, puntos a canjear, cupones y vales aplicables, qué se descartó y por
qué (incluida la política de combinación §24) y el efecto financiero previsto.
Ventas no replica ninguna regla; Fidelidad no toca el carrito.

`LoyaltyAccrualEvaluator` es el mismo cálculo que acredita al cobrar
(`AccrueSalePointsUseCase`): lo que el POS muestra como "puntos a ganar" es lo
que después se acredita.

Sin efectos secundarios: el cajero lo consulta mientras arma la venta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable

from backend.application.loyalty.queries.program_settings_query import LoyaltyProgramSettingsQuery
from backend.application.loyalty.queries.redemption_preview_query import (
    LoyaltyRedemptionPreviewQuery,
)
from backend.domain.loyalty.policies.accrual_policy import LoyaltyAccrualPolicy
from backend.domain.loyalty.policies.stacking_policy import Benefit, StackingPolicy
from backend.domain.loyalty.services.rule_engine import (
    AccrualContext,
    AccrualLine,
    LoyaltyRuleEngine,
    RuleEvaluation,
)
from backend.infrastructure.db.repositories.loyalty.rule_repository import (
    LoyaltyAccrualContextReader,
    LoyaltyRuleRepository,
)

_CENT = Decimal("0.01")
_ZERO = Decimal("0")
#: Beneficios que PAGAN (saldo del cliente), no descuentan.
_TENDER_KINDS = frozenset({"VOUCHER", "STORE_CREDIT", "GIFT_CARD"})


def _dec(value: Any) -> Decimal:
    if isinstance(value, float):
        raise ValueError("Los importes viajan como texto decimal, nunca float")
    return Decimal(str(value if value not in (None, "") else "0"))


def _moment(value: datetime | str | None) -> datetime:
    if isinstance(value, datetime):
        return value
    if value:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


class LoyaltyAccrualEvaluator:
    """Puntos de una compra con las reglas activas de Fidelidad."""

    def __init__(self, connection) -> None:
        self._conn = connection
        self._rules = LoyaltyRuleRepository(connection)
        self._reader = LoyaltyAccrualContextReader(connection)

    def evaluate(self, *, customer_id: str | None, branch_id: str | None, total: Any,
                 credit_amount: Any = 0, lines: Iterable[dict] = (), payments: Iterable = (),
                 channel: str = "POS", occurred_at: datetime | str | None = None,
                 sale_id: str | None = None) -> RuleEvaluation:
        momento = _moment(occurred_at)
        ajustes = LoyaltyProgramSettingsQuery(self._conn).accrual()
        elegible = LoyaltyAccrualPolicy.eligible_amount(
            total=_dec(total), credit_amount=_dec(credit_amount), settings=ajustes)
        lineas = [dict(ln) for ln in lines or ()]
        categorias = self._reader.category_ids(
            [str(ln.get("product_id")) for ln in lineas if ln.get("product_id")])
        pagos = tuple((str(p.get("method") if isinstance(p, dict) else p[0]),
                       _dec(p.get("amount") if isinstance(p, dict) else p[1]))
                      for p in payments or ())
        previas = tuple(_moment(f) for f in (
            self._rules.previous_purchases(customer_id, momento.isoformat(timespec="seconds"),
                                           exclude_sale_id=sale_id)
            if customer_id else ()))
        contexto = AccrualContext(
            occurred_at=momento, eligible_amount=elegible,
            lines=tuple(AccrualLine(
                product_id=str(ln.get("product_id") or ""), quantity=_dec(ln.get("quantity")),
                amount=_dec(ln.get("amount", ln.get("line_total"))),
                category_ids=categorias.get(str(ln.get("product_id")), frozenset()))
                for ln in lineas),
            customer_id=customer_id, branch_id=branch_id, channel=str(channel or "POS").upper(),
            payments=pagos, segment_ids=self._reader.segment_ids(customer_id),
            program_ids=self._reader.program_ids(customer_id), previous_purchases=previas)
        reglas = self._rules.list_active()
        uso = self._rules.usage([r.id for r in reglas], customer_id, momento)
        return LoyaltyRuleEngine(pesos_per_point=ajustes.pesos_per_point).evaluate(
            reglas, contexto, uso)


# ── contrato con Ventas (§25) ──────────────────────────────────────────────
@dataclass(frozen=True)
class CustomerBenefitsRequest:
    customer_id: str | None
    branch_id: str | None
    subtotal: Decimal
    channel: str = "POS"
    sale_lines: tuple[dict, ...] = ()
    #: Método único ("CASH") o pagos [{"method", "amount"}].
    payment_method: Any = None
    occurred_at: datetime | str | None = None
    coupon_codes: tuple[str, ...] = ()
    voucher_codes: tuple[str, ...] = ()
    requested_points: int = 0
    promotion_total: Decimal = _ZERO
    employee_discount: Decimal = _ZERO


@dataclass(frozen=True)
class CustomerBenefits:
    eligible_benefits: tuple[dict, ...] = ()
    ineligible_benefits: tuple[dict, ...] = ()
    discount_breakdown: dict = field(default_factory=dict)
    points_to_earn: int = 0
    earn_breakdown: tuple[dict, ...] = ()
    points_to_redeem: int = 0
    coupons_to_reserve: tuple[str, ...] = ()
    vouchers_to_reserve: tuple[dict, ...] = ()
    warnings: tuple[str, ...] = ()
    financial_effects_preview: dict = field(default_factory=dict)


class EvaluateCustomerBenefitsQuery:
    def __init__(self, connection) -> None:
        self._conn = connection

    def execute(self, request: CustomerBenefitsRequest) -> CustomerBenefits:
        avisos: list[str] = []
        no_elegibles: list[dict] = []
        subtotal = _dec(request.subtotal)
        candidatos: list[Benefit] = []
        if _dec(request.promotion_total) > 0:
            candidatos.append(Benefit("PROMOTION", "promotion", _dec(request.promotion_total),
                                      "Promoción"))
        if _dec(request.employee_discount) > 0:
            candidatos.append(Benefit("EMPLOYEE_DISCOUNT", "employee",
                                      _dec(request.employee_discount), "Descuento de empleado"))

        for codigo in request.coupon_codes:
            beneficio, motivo = self._coupon(str(codigo), subtotal, request.customer_id)
            if beneficio is None:
                no_elegibles.append({"kind": "COUPON", "reference": codigo, "reason": motivo})
            else:
                candidatos.append(beneficio)
        for codigo in request.voucher_codes:
            beneficio, motivo = self._voucher(str(codigo))
            if beneficio is None:
                no_elegibles.append({"kind": "VOUCHER", "reference": codigo, "reason": motivo})
            else:
                candidatos.append(beneficio)

        canje = LoyaltyRedemptionPreviewQuery(self._conn)
        valor_punto = canje.settings().point_value
        puntos_canje = 0
        if request.requested_points:
            if not request.customer_id:
                no_elegibles.append({"kind": "POINTS", "reference": "points",
                                     "reason": "Una venta sin cliente no canjea puntos"})
            else:
                vista = canje.preview(customer_id=request.customer_id, subtotal=subtotal,
                                      requested_points=int(request.requested_points))
                if vista.requested_points > 0:
                    candidatos.append(Benefit("POINTS", "points", vista.discount,
                                              f"{vista.requested_points} puntos"))
                    puntos_canje = vista.requested_points
                else:
                    no_elegibles.append({
                        "kind": "POINTS", "reference": "points",
                        "reason": (f"Puede canjear hasta {vista.max_redeemable_points} puntos "
                                   f"(saldo {vista.available_points})")})

        resultado = StackingPolicy(LoyaltyRuleRepository(self._conn).stacking_settings()) \
            .resolve(candidatos)
        for beneficio, motivo in resultado.rejected:
            no_elegibles.append({"kind": beneficio.kind, "reference": beneficio.reference,
                                 "reason": motivo})
            if beneficio.kind == "POINTS":
                puntos_canje = 0
        for beneficio, pedido in resultado.capped:
            avisos.append(f"{beneficio.label or beneficio.kind}: recortado de ${pedido} "
                          f"a ${beneficio.value} por el tope de combinación")
            if beneficio.kind == "POINTS" and valor_punto > 0:
                puntos_canje = int(beneficio.value / valor_punto)

        aceptados = resultado.accepted
        por_tipo: dict[str, Decimal] = {}
        for b in aceptados:
            por_tipo[b.kind] = por_tipo.get(b.kind, _ZERO) + b.value
        descuento = sum((v for k, v in por_tipo.items() if k not in _TENDER_KINDS), _ZERO)
        vales = sum((v for k, v in por_tipo.items() if k in _TENDER_KINDS), _ZERO)
        a_pagar = max(subtotal - descuento - vales, _ZERO)

        pagos = request.payment_method
        if isinstance(pagos, str) and pagos:
            pagos = [{"method": pagos, "amount": str(a_pagar)}]
        credito = sum((_dec(p.get("amount")) for p in pagos or () if isinstance(p, dict)
                       and str(p.get("method")) == "CREDIT"), _ZERO)
        if not request.customer_id:
            ganar, desglose = 0, ()
            avisos.append("Sin cliente: la compra no acumula puntos")
        else:
            evaluacion = LoyaltyAccrualEvaluator(self._conn).evaluate(
                customer_id=request.customer_id, branch_id=request.branch_id, total=a_pagar,
                credit_amount=credito, lines=request.sale_lines, payments=pagos or (),
                channel=request.channel, occurred_at=request.occurred_at)
            ganar = evaluacion.points
            desglose = tuple({"rule_id": a.rule_id, "code": a.code, "name": a.name,
                              "points": a.points} for a in evaluacion.applied)

        cupones = tuple(b.reference for b in aceptados if b.kind == "COUPON")
        vales_reserva = tuple({"voucher_instance_id": b.reference, "amount": str(b.value)}
                              for b in aceptados if b.kind in ("VOUCHER", "STORE_CREDIT"))
        return CustomerBenefits(
            eligible_benefits=tuple({"kind": b.kind, "reference": b.reference,
                                     "label": b.label, "amount": str(b.value)} for b in aceptados),
            ineligible_benefits=tuple(no_elegibles),
            discount_breakdown={k: str(v) for k, v in por_tipo.items()},
            points_to_earn=ganar, earn_breakdown=desglose,
            points_to_redeem=puntos_canje, coupons_to_reserve=cupones,
            vouchers_to_reserve=vales_reserva, warnings=tuple(avisos),
            financial_effects_preview={
                "points_liability_to_recognize": str(
                    (Decimal(ganar) * valor_punto).quantize(_CENT, ROUND_HALF_UP)),
                "points_liability_to_release": str(por_tipo.get("POINTS", _ZERO)),
                "coupon_discount": str(por_tipo.get("COUPON", _ZERO)),
                "voucher_liability_to_release": str(vales),
            })

    # ── instrumentos ─────────────────────────────────────────────────────
    def _coupon(self, code: str, subtotal: Decimal, customer_id: str | None):
        from backend.domain.commercial_instruments.enums import CommercialBenefitType
        from backend.infrastructure.db.repositories.commercial_instruments.unit_of_work import (
            CommercialInstrumentsUnitOfWork,
        )

        uow = CommercialInstrumentsUnitOfWork(self._conn)
        instancia = uow.coupon_instances.get_by_code(code)
        if instancia is None:
            return None, "El cupón no existe"
        estado = getattr(instancia.status, "value", instancia.status)
        if estado not in ("ISSUED", "ACTIVE"):
            return None, f"El cupón no está vigente ({estado})"
        if instancia.customer_id and customer_id and instancia.customer_id != customer_id:
            return None, "El cupón es de otro cliente"
        definicion = uow.coupon_definitions.get(instancia.definition_id)
        if definicion is None or not definicion.active:
            return None, "La definición del cupón no está activa"
        ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if definicion.valid_from and ahora < str(definicion.valid_from):
            return None, "El cupón aún no entra en vigencia"
        if definicion.valid_to and ahora[:len(str(definicion.valid_to))] > str(definicion.valid_to):
            return None, "El cupón ya venció"
        tipo = getattr(definicion.benefit_type, "value", definicion.benefit_type)
        valor = _dec(definicion.benefit_value)
        if tipo == CommercialBenefitType.FIXED_AMOUNT.value:
            monto = min(valor, subtotal)
        elif tipo == CommercialBenefitType.PERCENTAGE.value:
            monto = (subtotal * valor / Decimal("100")).quantize(_CENT, ROUND_HALF_UP)
        else:
            return None, f"El beneficio {tipo} no se descuenta del total"
        if monto <= 0:
            return None, "El cupón no descuenta nada en esta venta"
        return Benefit("COUPON", instancia.id, monto, f"Cupón {code}"), ""

    def _voucher(self, code: str):
        from backend.domain.commercial_instruments.policies.voucher_balance_policy import (
            VoucherBalancePolicy,
        )
        from backend.infrastructure.db.repositories.commercial_instruments.unit_of_work import (
            CommercialInstrumentsUnitOfWork,
        )

        uow = CommercialInstrumentsUnitOfWork(self._conn)
        instancia = uow.voucher_instances.get_by_code(code)
        if instancia is None:
            return None, "El vale no existe"
        estado = getattr(instancia.status, "value", instancia.status)
        if estado not in ("ISSUED", "ACTIVE", "PARTIALLY_REDEEMED"):
            return None, f"El vale no está vigente ({estado})"
        saldo = VoucherBalancePolicy.balance(uow.voucher_transactions.list_for_instance(instancia.id))
        if saldo <= 0:
            return None, "El vale no tiene saldo"
        definicion = uow.voucher_definitions.get(instancia.definition_id)
        tipo = getattr(getattr(definicion, "voucher_type", None), "value", "")
        kind = "STORE_CREDIT" if tipo == "STORE_CREDIT" else "VOUCHER"
        return Benefit(kind, instancia.id, saldo, f"Vale {code}"), ""


__all__ = ["CustomerBenefits", "CustomerBenefitsRequest", "EvaluateCustomerBenefitsQuery",
           "LoyaltyAccrualEvaluator"]
