"""Consumidores de Fidelidad para los eventos de Ventas (2026-10-02).

`SALE_COMPLETED` acredita los puntos de la compra; `SALE_RETURNED` y
`SALE_REVERSED` los retiran en proporción. `SALE_CANCELLED` y `SALE_REVERSED`
devuelven además lo que el cliente canjeó en esa venta. Viven del lado de Fidelidad (dueña
de los puntos); Ventas sólo publica. La autorización es la DELEGADA de
`sale_points_use_cases.SALES_GRANT`, en nombre del cajero que originó el
evento.
"""

from __future__ import annotations

from decimal import Decimal

from backend.shared.ids import new_uuid
from backend.application.loyalty.use_cases.sale_points_use_cases import (
    AccrueSalePointsUseCase,
    RemoveSalePointsUseCase,
    RestoreSaleRedemptionUseCase,
    delegated_policy,
)


def _dec(value) -> Decimal:
    return Decimal(str(value or "0"))


def _fail_loud(result, evento: str) -> None:
    """Un fallo de Fidelidad deja el evento PENDIENTE en el outbox de Ventas
    (se reintenta en el siguiente despacho) en vez de perder los puntos."""
    if not result.success:
        raise RuntimeError(f"Fidelidad no procesó {evento}: {result.message}")


class SaleLoyaltyEventHandlers:
    def __init__(self, connection) -> None:
        self._conn = connection

    def on_sale_completed(self, envelope: dict) -> None:
        datos = dict(envelope.get("payload") or {})
        actor = str(envelope.get("user_id") or "")
        credito = sum((_dec(p.get("amount")) for p in datos.get("payments") or []
                       if str(p.get("method")) == "CREDIT"), Decimal("0"))
        # Comprar un vale prepagado no acumula puntos (se acumulan al gastarlo).
        prepagados = sum((_dec(v.get("amount")) for v in datos.get("prepaid_vouchers") or ()),
                         Decimal("0"))
        _fail_loud(AccrueSalePointsUseCase(delegated_policy(actor)).execute(
            self._conn, sale_id=str(envelope.get("entity_id")),
            customer_id=datos.get("customer_id"),
            total=max(_dec(datos.get("total")) - prepagados, Decimal("0")),
            credit_amount=credito, branch_id=str(envelope.get("branch_id")),
            actor_user_id=actor, operation_id=str(envelope.get("event_id")),
            occurred_at=envelope.get("timestamp"), lines=datos.get("lines") or (),
            payments=datos.get("payments") or (),
            channel=str(datos.get("channel") or "POS")), "SALE_COMPLETED")
        self._confirm_instruments(envelope)

    def on_sale_returned(self, envelope: dict) -> None:
        datos = dict(envelope.get("payload") or {})
        actor = str(envelope.get("user_id") or "")
        self._refund_vouchers(envelope, datos.get("voucher_refunds") or (),
                              str(datos.get("return_id") or envelope.get("event_id")))
        _fail_loud(RemoveSalePointsUseCase(delegated_policy(actor)).execute(
            self._conn, sale_id=str(envelope.get("entity_id")),
            customer_id=datos.get("customer_id"),
            document_id=str(datos.get("return_id") or envelope.get("event_id")),
            sale_total=_dec(datos.get("sale_total")),
            refunded_total=_dec(datos.get("refunded_total") or datos.get("amount")),
            branch_id=str(envelope.get("branch_id")), actor_user_id=actor,
            operation_id=str(envelope.get("event_id"))), "SALE_RETURNED")

    def on_sale_reversed(self, envelope: dict) -> None:
        datos = dict(envelope.get("payload") or {})
        actor = str(envelope.get("user_id") or "")
        total = _dec(datos.get("sale_total"))
        _fail_loud(RemoveSalePointsUseCase(delegated_policy(actor)).execute(
            self._conn, sale_id=str(envelope.get("entity_id")),
            customer_id=datos.get("customer_id"), document_id=str(envelope.get("entity_id")),
            sale_total=total, refunded_total=total, branch_id=str(envelope.get("branch_id")),
            actor_user_id=actor, operation_id=str(envelope.get("event_id"))), "SALE_REVERSED")
        self._restore_redemption(envelope, "SALE_REVERSED")
        # Un reverso regresa a cada vale todo lo que pagó y anula los vales
        # prepagados que vendió (el reverso ya verificó que no se usaron).
        self._refund_vouchers(envelope, datos.get("voucher_payments") or (),
                              str(envelope.get("entity_id")))
        if datos.get("prepaid_vouchers"):
            self._cancel_prepaid(str(envelope.get("entity_id")), "Venta reversada")

    def on_sale_cancelled(self, envelope: dict) -> None:
        self._restore_redemption(envelope, "SALE_CANCELLED")
        self._release_instruments(envelope)

    # ── cupones y vales (2026-10-03) ─────────────────────────────────────
    def _confirm_instruments(self, envelope: dict) -> None:
        """Al completar: el cupón apartado pasa a canjeado (con el importe que
        la venta aplicó) y el apartado de cada vale se confirma. Idempotente:
        lo ya confirmado no vuelve a tocarse."""
        from backend.application.commercial_instruments.use_cases.coupon_use_cases import (
            ConfirmCouponRedemptionUseCase,
        )
        from backend.application.commercial_instruments.use_cases.voucher_use_cases import (
            ConfirmVoucherRedemptionUseCase,
        )
        from backend.infrastructure.db.repositories.commercial_instruments.unit_of_work import (
            CommercialInstrumentsUnitOfWork,
        )

        datos = dict(envelope.get("payload") or {})
        if datos.get("prepaid_vouchers"):
            from backend.application.commercial_instruments.use_cases.voucher_use_cases import (
                ActivatePrepaidVouchersForSaleUseCase,
            )
            _fail_loud(ActivatePrepaidVouchersForSaleUseCase(
                delegated_policy(str(envelope.get("user_id") or ""))).execute(
                self._conn, sale_id=str(envelope.get("entity_id")),
                vouchers=datos["prepaid_vouchers"],
                actor_user_id=str(envelope.get("user_id") or ""),
                actor_branch_id=str(envelope.get("branch_id") or ""),
                customer_id=datos.get("customer_id")), "SALE_COMPLETED (vale prepagado)")
        if not (datos.get("coupons") or datos.get("voucher_payments")):
            return
        venta = str(envelope.get("entity_id"))
        actor = str(envelope.get("user_id") or "")
        sucursal = str(envelope.get("branch_id") or "")
        uow = CommercialInstrumentsUnitOfWork(self._conn)
        apartados = {c.id for c in uow.coupon_instances.list_reserved_for_sale(venta)}
        for cupon in datos.get("coupons") or ():
            if cupon.get("coupon_instance_id") not in apartados:
                continue
            _fail_loud(ConfirmCouponRedemptionUseCase(delegated_policy(actor)).execute(
                self._conn, coupon_instance_id=cupon["coupon_instance_id"],
                amount_applied=_dec(cupon.get("amount")), redeemed_by_user_id=actor,
                actor_branch_id=sucursal, operation_id=new_uuid()), "SALE_COMPLETED (cupón)")
        for reserva in uow.voucher_transactions.list_reserved_for_sale(venta):
            _fail_loud(ConfirmVoucherRedemptionUseCase(delegated_policy(actor)).execute(
                self._conn, reservation_transaction_id=reserva.id, redeemed_by_user_id=actor,
                actor_branch_id=sucursal, operation_id=new_uuid()), "SALE_COMPLETED (vale)")

    def _release_instruments(self, envelope: dict) -> None:
        """Venta cancelada: cupones y vales apartados vuelven a estar libres."""
        from backend.infrastructure.db.repositories.commercial_instruments.unit_of_work import (
            CommercialInstrumentsUnitOfWork,
        )
        from backend.infrastructure.integrations.sales_instruments_client import (
            SalesInstrumentsClient,
        )

        if self._conn.execute("SELECT 1 FROM sqlite_master WHERE type='table'"
                              " AND name='coupon_instances'").fetchone() is None:
            return   # base sin Instrumentos comerciales: nada que liberar
        venta = str(envelope.get("entity_id"))
        actor = str(envelope.get("user_id") or "")
        uow = CommercialInstrumentsUnitOfWork(self._conn)
        cliente = SalesInstrumentsClient(self._conn,
                                         actor_branch_id=str(envelope.get("branch_id") or ""))
        for cupon in uow.coupon_instances.list_reserved_for_sale(venta):
            cliente.release_coupon(coupon_instance_id=cupon.id, actor_user_id=actor)
        for reserva in uow.voucher_transactions.list_reserved_for_sale(venta):
            cliente.release_voucher(reservation_id=reserva.id, actor_user_id=actor)
        self._cancel_prepaid(venta, "Venta cancelada")

    def _cancel_prepaid(self, venta: str, motivo: str) -> None:
        from backend.application.commercial_instruments.use_cases.voucher_use_cases import (
            CancelPrepaidVouchersForSaleUseCase,
        )
        CancelPrepaidVouchersForSaleUseCase().execute(self._conn, sale_id=venta, reason=motivo)

    def _refund_vouchers(self, envelope: dict, vouchers, document_id: str) -> None:
        from backend.application.commercial_instruments.use_cases.voucher_use_cases import (
            RefundToVoucherUseCase,
        )

        actor = str(envelope.get("user_id") or "")
        for vale in vouchers:
            _fail_loud(RefundToVoucherUseCase(delegated_policy(actor)).execute(
                self._conn, voucher_instance_id=str(vale["voucher_instance_id"]),
                amount=_dec(vale.get("amount")), sale_id=str(envelope.get("entity_id")),
                document_id=document_id, actor_user_id=actor,
                actor_branch_id=str(envelope.get("branch_id") or ""),
                operation_id=new_uuid()), "abono a vale")

    def _restore_redemption(self, envelope: dict, evento: str) -> None:
        datos = dict(envelope.get("payload") or {})
        actor = str(envelope.get("user_id") or "")
        _fail_loud(RestoreSaleRedemptionUseCase(delegated_policy(actor)).execute(
            self._conn, sale_id=str(envelope.get("entity_id")),
            customer_id=datos.get("customer_id"), branch_id=str(envelope.get("branch_id")),
            actor_user_id=actor, operation_id=str(envelope.get("event_id"))), evento)
