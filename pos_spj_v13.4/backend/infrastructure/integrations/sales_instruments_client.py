"""Ventas ↔ Instrumentos comerciales: cupones y vales en la caja (2026-10-03).

Decisiones del usuario: el cupón es un DESCUENTO del ticket; el vale (o saldo a
favor) es una FORMA DE PAGO que cancela su pasivo, sin entrar al cajón.

Ventas no replica reglas (§25): pregunta a `EvaluateCustomerBenefitsQuery`
—vigencia, dueño, saldo y la combinación con lo que la venta ya trae (§24)— y,
si Fidelidad lo aprueba, aparta el instrumento para ESTA venta. El canje se
confirma al completar la venta (por el bus, del lado de Fidelidad) y el apartado
se libera si la venta se cancela.

Mismo patrón y frontera que `SalesLoyaltyClient`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.application.commercial_instruments.queries.piece_resolver import (
    resolve_instrument,
)
from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.loyalty.queries.customer_benefits_query import (
    CustomerBenefitsRequest,
    EvaluateCustomerBenefitsQuery,
)
from backend.infrastructure.db.repositories.commercial_instruments.unit_of_work import (
    CommercialInstrumentsUnitOfWork,
)
from backend.shared.ids import new_uuid

_ZERO = Decimal("0")


def _rejected(reason: str) -> dict[str, Any]:
    return {"approved": False, "reason": reason}


def _prior_benefits(sale, *, include_payments: bool) -> tuple[dict, ...]:
    """Lo que la venta ya trae, en el orden en que se aplicó: canje de puntos,
    cupones y (al cobrar) vales ya registrados."""
    previos: list[dict] = []
    puntos = Decimal(str(getattr(sale, "loyalty_redeemed_amount", _ZERO) or _ZERO))
    if puntos > 0:
        previos.append({"kind": "POINTS", "reference": "points", "value": puntos,
                        "label": "Puntos canjeados"})
    for cupon in getattr(sale, "coupons", ()) or ():
        previos.append({"kind": "COUPON", "reference": cupon.coupon_instance_id,
                        "value": cupon.amount, "label": f"Cupón {cupon.code}"})
    if include_payments:
        for pago in sale.voucher_payments():
            previos.append({"kind": "STORE_CREDIT" if pago["instrument_type"] == "STORE_CREDIT"
                            else "VOUCHER", "reference": pago["voucher_instance_id"],
                            "value": pago["amount"], "label": "Vale"})
    return tuple(previos)


class SalesInstrumentsClient:
    def __init__(self, connection, *, actor_branch_id: str = "",
                 authorization: LoyaltyAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._branch = actor_branch_id
        # Apartar y liberar no exigen permiso de Fidelidad (es parte de cobrar,
        # §6); la política sólo se pasa por la firma de los casos de uso.
        self._auth = authorization or LoyaltyAuthorizationPolicy()

    # ── cupones ──────────────────────────────────────────────────────────
    def apply_coupon(self, *, sale, code: str, actor_user_id: str) -> dict[str, Any]:
        code = str(code or "").strip()
        if not code:
            return _rejected("Captura el código del cupón")
        uow = CommercialInstrumentsUnitOfWork(self._conn)
        # Código de pieza de lote (por su huella), o código de un cupón suelto. Un
        # folio no sirve para canjear (auditoría de Fidelidad 968e0bc).
        resuelto, motivo = resolve_instrument(uow, code, kind="COUPON",
                                              branch_id=sale.branch_id)
        if resuelto is None:
            return _rejected(motivo)
        instancia = resuelto.instance
        code = instancia.code   # el resto del flujo busca la pieza por su código interno
        base = sale.totals.gross_subtotal - sale.totals.discount_total
        evaluacion = EvaluateCustomerBenefitsQuery(self._conn).execute(CustomerBenefitsRequest(
            customer_id=sale.customer_id, branch_id=sale.branch_id, subtotal=base,
            channel=sale.channel, coupon_codes=(code,),
            prior_benefits=_prior_benefits(sale, include_payments=False)))
        aceptado = next((b for b in evaluacion.eligible_benefits
                         if b["kind"] == "COUPON" and b["reference"] == instancia.id), None)
        if aceptado is None:
            motivo = next((b["reason"] for b in evaluacion.ineligible_benefits
                           if b["reference"] in (code, instancia.id)), "El cupón no aplica")
            return _rejected(motivo)

        from backend.application.commercial_instruments.use_cases.coupon_use_cases import (
            ValidateAndReserveCouponUseCase,
        )

        reserva = ValidateAndReserveCouponUseCase(self._auth).execute(
            self._conn, code=code, sale_id=sale.id, actor_user_id=actor_user_id,
            actor_branch_id=self._branch or sale.branch_id, operation_id=new_uuid(),
            customer_id=sale.customer_id)
        if not reserva.success:
            return _rejected(reserva.message)
        return {"approved": True, "reason": "", "coupon_instance_id": instancia.id, "code": code,
                "benefit_type": str(reserva.data.get("benefit_type") or ""),
                "benefit_value": Decimal(str(reserva.data.get("benefit_value") or "0")),
                "amount": Decimal(str(aceptado["amount"]))}

    def release_coupon(self, *, coupon_instance_id: str, actor_user_id: str) -> None:
        from backend.application.commercial_instruments.use_cases.coupon_use_cases import (
            ReleaseCouponReservationUseCase,
        )

        ReleaseCouponReservationUseCase(self._auth).execute(
            self._conn, coupon_instance_id=coupon_instance_id,
            actor_branch_id=self._branch, operation_id=new_uuid(), actor_user_id=actor_user_id)

    # ── vales ────────────────────────────────────────────────────────────
    def voucher_balance(self, *, code: str) -> dict[str, Any]:
        """Saldo y vigencia de un vale, para mostrarlo antes de cobrar."""
        from backend.domain.commercial_instruments.policies.voucher_balance_policy import (
            VoucherBalancePolicy,
        )

        uow = CommercialInstrumentsUnitOfWork(self._conn)
        resuelto, motivo = resolve_instrument(uow, code, kind="VOUCHER",
                                              branch_id=self._branch or None)
        if resuelto is None:
            return {"found": False, "balance": _ZERO, "status": "", "reason": motivo}
        instancia = resuelto.instance
        saldo = VoucherBalancePolicy.balance(uow.voucher_transactions.list_for_instance(instancia.id))
        reglas = uow.voucher_rules.get(instancia.id)
        return {"found": True, "balance": saldo,
                "status": getattr(instancia.status, "value", instancia.status),
                "folio": instancia.code, "rules": reglas["rules"] if reglas else None}

    def reserve_voucher(self, *, sale, code: str, amount: Decimal,
                        actor_user_id: str) -> dict[str, Any]:
        code = str(code or "").strip()
        if not code:
            return _rejected("Captura el código del vale")
        uow = CommercialInstrumentsUnitOfWork(self._conn)
        resuelto, motivo = resolve_instrument(uow, code, kind="VOUCHER",
                                              branch_id=sale.branch_id)
        if resuelto is None:
            return _rejected(motivo)
        instancia = resuelto.instance
        code = instancia.code
        # Un vale personal exige al cliente identificado. Antes sólo se comparaba
        # si la venta TENÍA cliente: sin cliente, cualquiera lo cobraba
        # (auditoría de Fidelidad 968e0bc).
        if instancia.customer_id and instancia.customer_id != sale.customer_id:
            return _rejected("El vale es personal: asigna a su titular a la venta"
                             if not sale.customer_id else "El vale es de otro cliente")
        if (instancia.status.value == "RESERVED"
                and getattr(instancia, "sale_id", None) == sale.id):
            # Escanear dos veces en la misma venta no es un segundo canje.
            return _rejected("Ese vale ya está aplicado en esta venta")
        evaluacion = EvaluateCustomerBenefitsQuery(self._conn).execute(CustomerBenefitsRequest(
            customer_id=sale.customer_id, branch_id=sale.branch_id,
            subtotal=sale.totals.gross_subtotal, channel=sale.channel, voucher_codes=(code,),
            prior_benefits=_prior_benefits(sale, include_payments=True)))
        aceptado = next((b for b in evaluacion.eligible_benefits
                         if b["reference"] == instancia.id), None)
        if aceptado is None:
            motivo = next((b["reason"] for b in evaluacion.ineligible_benefits
                           if b["reference"] in (code, instancia.id)), "El vale no aplica")
            return _rejected(motivo)
        importe = min(Decimal(str(amount)), Decimal(str(aceptado["amount"])))
        if importe <= 0:
            return _rejected("El vale no tiene saldo")
        reglas = uow.voucher_rules.get(instancia.id)
        if reglas is not None:
            importe, motivo = self._apply_batch_rules(uow, sale, instancia, reglas["rules"],
                                                      requested=importe)
            if importe is None:
                return _rejected(motivo)

        from backend.application.commercial_instruments.use_cases.voucher_use_cases import (
            ReserveVoucherAmountUseCase,
        )
        from backend.application.loyalty.integrations.finance_posting import VOUCHER_INSTRUMENT

        reserva = ReserveVoucherAmountUseCase(self._auth).execute(
            self._conn, voucher_instance_id=instancia.id, amount=importe, sale_id=sale.id,
            actor_branch_id=self._branch or sale.branch_id, operation_id=new_uuid())
        if not reserva.success:
            return _rejected(reserva.message)
        definicion = uow.voucher_definitions.get(instancia.definition_id)
        tipo = getattr(getattr(definicion, "voucher_type", None), "value", "REFUND_VOUCHER")
        instrumento = VOUCHER_INSTRUMENT.get(tipo)
        return {"approved": True, "reason": "", "voucher_instance_id": instancia.id,
                "amount": importe, "reservation_id": reserva.entity_id,
                "instrument_type": instrumento.value if instrumento else "REFUND_VOUCHER"}


    def _apply_batch_rules(self, uow, sale, instancia, reglas, *, requested: Decimal):
        """Reglas de la pieza (fotografía del lote): un evento / varios, tope % por
        venta y margen protegido si lo financia el negocio. `(importe, "")` o
        `(None, motivo)`."""
        from backend.domain.commercial_instruments.policies.voucher_balance_policy import (
            VoucherBalancePolicy,
        )
        from backend.domain.commercial_instruments.value_objects.redemption_rules import (
            RedemptionRulesError,
        )

        saldo = VoucherBalancePolicy.balance(uow.voucher_transactions.list_for_instance(instancia.id))
        previos = len(uow.voucher_redemptions.list_for_instance(instancia.id))
        bruto = sale.totals.gross_subtotal
        neto = bruto - sale.totals.discount_total
        margen = None
        if reglas.funding_source.consumes_margin:
            # FID-03: un vale que regala el negocio no se come el margen protegido.
            from backend.application.sales.queries.benefit_budget_query import (
                SaleBenefitBudgetQuery,
            )
            presupuesto = SaleBenefitBudgetQuery(self._conn).for_sale(sale)
            if presupuesto.lines_without_cost:
                return None, presupuesto.explain()
            margen = presupuesto.available
        try:
            return reglas.applicable_amount(
                balance=saldo, requested=requested, gross_base=bruto, net_base=neto,
                prior_redemptions=previos, margin_budget=margen), ""
        except RedemptionRulesError as exc:
            return None, str(exc)

    # ── vales prepagados vendidos en caja ────────────────────────────────
    def prepaid_definitions(self) -> list[dict]:
        uow = CommercialInstrumentsUnitOfWork(self._conn)
        try:
            return uow.voucher_instances.list_prepaid_definitions()
        except Exception:   # noqa: BLE001 - base sin Instrumentos comerciales
            return []

    def prepare_prepaid(self, *, sale, definition_id: str) -> dict[str, Any]:
        from backend.application.commercial_instruments.use_cases.voucher_use_cases import (
            PreparePrepaidVoucherForSaleUseCase,
        )

        code = f"VAP-{new_uuid()[-8:].upper()}"
        r = PreparePrepaidVoucherForSaleUseCase(self._auth).execute(
            self._conn, definition_id=definition_id, code=code, sale_id=sale.id,
            actor_branch_id=self._branch or sale.branch_id, operation_id=new_uuid(),
            customer_id=sale.customer_id)
        if not r.success:
            return _rejected(r.message)
        return {"approved": True, "reason": "", "voucher_instance_id": r.entity_id,
                "code": r.data.get("code", code)}

    def prepaid_unused(self, *, sale) -> str | None:
        """None si los vales prepagados de la venta siguen intactos; si no, por
        qué no se puede reversar."""
        from backend.domain.commercial_instruments.policies.voucher_balance_policy import (
            VoucherBalancePolicy,
        )

        uow = CommercialInstrumentsUnitOfWork(self._conn)
        for vale in sale.prepaid_vouchers():
            saldo = VoucherBalancePolicy.balance(
                uow.voucher_transactions.list_for_instance(vale["voucher_instance_id"]))
            if saldo < Decimal(str(vale["amount"])):
                return (f"El vale prepagado {vale['code']} ya se usó (saldo ${saldo:,.2f} de "
                        f"${Decimal(str(vale['amount'])):,.2f}); no se puede reversar la venta.")
        return None

    def release_voucher(self, *, reservation_id: str, actor_user_id: str) -> None:
        from backend.application.commercial_instruments.use_cases.voucher_use_cases import (
            ReleaseVoucherReservationUseCase,
        )

        ReleaseVoucherReservationUseCase(self._auth).execute(
            self._conn, reservation_transaction_id=reservation_id,
            actor_branch_id=self._branch, operation_id=new_uuid(), actor_user_id=actor_user_id)

    def release_voucher_payment(self, *, sale_id: str, voucher_instance_id: str,
                                amount: Decimal, actor_user_id: str) -> bool:
        """Suelta el apartado del vale de UN pago anulado (auditoría V02). True
        si había algo que soltar; reintentar no hace nada."""
        uow = CommercialInstrumentsUnitOfWork(self._conn)
        reservas = [r for r in uow.voucher_transactions.list_reserved_for_sale(sale_id)
                    if r.voucher_instance_id == voucher_instance_id]
        reserva = next((r for r in reservas if Decimal(str(r.amount)) == Decimal(str(amount))),
                       reservas[0] if reservas else None)
        if reserva is None:
            return False
        self.release_voucher(reservation_id=reserva.id, actor_user_id=actor_user_id)
        return True


__all__ = ["SalesInstrumentsClient"]
