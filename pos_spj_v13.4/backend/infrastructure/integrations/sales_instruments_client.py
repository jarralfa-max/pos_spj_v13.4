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
        instancia = uow.coupon_instances.get_by_code(code)
        if instancia is None:
            return _rejected(f"No existe un cupón con el código {code}")
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
        instancia = uow.voucher_instances.get_by_code(str(code or "").strip())
        if instancia is None:
            return {"found": False, "balance": _ZERO, "status": ""}
        saldo = VoucherBalancePolicy.balance(uow.voucher_transactions.list_for_instance(instancia.id))
        return {"found": True, "balance": saldo,
                "status": getattr(instancia.status, "value", instancia.status)}

    def reserve_voucher(self, *, sale, code: str, amount: Decimal,
                        actor_user_id: str) -> dict[str, Any]:
        code = str(code or "").strip()
        if not code:
            return _rejected("Captura el código del vale")
        uow = CommercialInstrumentsUnitOfWork(self._conn)
        instancia = uow.voucher_instances.get_by_code(code)
        if instancia is None:
            return _rejected(f"No existe un vale con el código {code}")
        if instancia.customer_id and sale.customer_id and instancia.customer_id != sale.customer_id:
            return _rejected("El vale es de otro cliente")
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


__all__ = ["SalesInstrumentsClient"]
