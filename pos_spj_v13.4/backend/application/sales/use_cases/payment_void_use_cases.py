"""Anular pagos de una venta en cobro (auditoría de Ventas cebf67a, V02/V03).

MEDIDO 2026-10-15 en el código de la auditoría: cada pago se guardaba al
momento (el de crédito apuntaba la deuda en CxC en ese mismo instante) y
cancelar la venta sólo cambiaba su estado — la venta quedaba CANCELLED con
$30 de efectivo "pagados" y la deuda a crédito viva. Tampoco había forma de
quitar un pago ya registrado: el cobro sólo podía terminarse o abandonarse.

Decisión del usuario: **compensar y avisar**. Anular un pago:

* lo saca de la venta y deja su rastro (`SalePaymentVoid`, tabla de la 341);
* CRÉDITO → retira su cargo de CxC (Finanzas, misma transacción);
* VALE → suelta el apartado del vale (Fidelidad);
* EFECTIVO, TARJETA, TRANSFERENCIA, MERCADO PAGO → todavía no tocaron Caja
  (Caja registra al COMPLETAR la venta), así que el sistema no tiene nada que
  revertir: lo que falta es que el cajero devuelva el dinero. Por eso cada
  anulación devuelve la instrucción para el cajero, que la pantalla muestra.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.sales.dto import SaleDTO
from backend.application.sales.result import SaleResult, fail_from_domain_error
from backend.application.sales.use_cases._base import _SalesBaseUseCase
from backend.domain.sales.enums import PaymentMethod
from backend.domain.sales.events import SaleEvents
from backend.domain.sales.exceptions import SalesDomainError
from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork

_LABELS = {
    PaymentMethod.CASH: "efectivo",
    PaymentMethod.CARD: "tarjeta",
    PaymentMethod.TRANSFER: "transferencia",
    PaymentMethod.MERCADO_PAGO: "Mercado Pago",
    PaymentMethod.CREDIT: "crédito",
    PaymentMethod.VOUCHER: "vale",
}


def _money(amount: Decimal) -> str:
    return f"${amount:,.2f}"


def refund_instruction(void) -> dict:
    """Qué hacer con el dinero de un pago anulado. `action`:
    RETURN_TO_CUSTOMER (lo hace el cajero) o SYSTEM (ya lo hizo el sistema)."""
    amount, ref = void.amount, f" (ref. {void.reference})" if void.reference else ""
    method = void.method
    if method is PaymentMethod.CASH:
        text, action = f"Devuelve {_money(amount)} en efectivo al cliente", "RETURN_TO_CUSTOMER"
    elif method is PaymentMethod.CARD:
        text = f"Cancela en la terminal el cargo de tarjeta por {_money(amount)}{ref}"
        action = "RETURN_TO_CUSTOMER"
    elif method is PaymentMethod.TRANSFER:
        text, action = f"Devuelve la transferencia de {_money(amount)}{ref}", "RETURN_TO_CUSTOMER"
    elif method is PaymentMethod.MERCADO_PAGO:
        text = f"Reembolsa {_money(amount)} desde Mercado Pago{ref}"
        action = "RETURN_TO_CUSTOMER"
    elif method is PaymentMethod.CREDIT:
        text = f"Se retiraron {_money(amount)} de la cuenta por cobrar del cliente"
        action = "SYSTEM"
    else:
        text, action = f"El vale recuperó {_money(amount)}", "SYSTEM"
    return {"payment_id": void.payment_id, "method": method.value, "amount": amount,
            "reference": void.reference, "action": action, "text": text}


class _PaymentCompensation(_SalesBaseUseCase):
    """Compensación de un pago anulado, compartida por la anulación suelta y la
    cancelación de la venta."""

    def _compensate(self, connection, sale, void, *, actor_user_id: str) -> dict:
        if void.method is PaymentMethod.CREDIT:
            self._credit_client(connection, actor_user_id).void(
                sale_id=sale.id, payment_id=void.payment_id)
        elif void.method is PaymentMethod.VOUCHER and void.reference:
            from backend.infrastructure.integrations.sales_instruments_client import (
                SalesInstrumentsClient,
            )
            instance = void.reference.split(":", 1)[-1]
            SalesInstrumentsClient(connection, actor_branch_id=sale.branch_id) \
                .release_voucher_payment(sale_id=sale.id, voucher_instance_id=instance,
                                         amount=void.amount, actor_user_id=actor_user_id)
        return refund_instruction(void)

    def _void_and_compensate(self, connection, uow, sale, payment_id: str, *, reason: str,
                             actor_user_id: str, operation_id: str) -> dict:
        void = sale.void_payment(payment_id, reason=reason, voided_by_user_id=actor_user_id)
        instruction = self._compensate(connection, sale, void, actor_user_id=actor_user_id)
        self._emit(uow, SaleEvents.PAYMENT_VOIDED, entity_id=sale.id,
                   operation_id=operation_id, branch_id=sale.branch_id,
                   actor_user_id=actor_user_id, payment_id=void.payment_id,
                   method=void.method.value, amount=str(void.amount), reason=void.reason)
        return instruction


class VoidSalePaymentUseCase(_PaymentCompensation):
    """Quita UN pago ya registrado de una venta en cobro. Lo puede hacer quien
    puede cobrar con ese método (sin permiso nuevo); queda auditado."""

    def execute(self, connection, *, sale_id: str, payment_id: str, reason: str,
                actor_user_id: str, operation_id: str) -> SaleResult:
        from backend.application.sales.use_cases.payment_use_cases import _PERMISSION_BY_METHOD

        with SalesUnitOfWork(connection) as uow:
            sale, denied = self._load_sale(uow, sale_id, actor_user_id, operation_id)
            if denied is not None:
                return denied
            payment = next((p for p in sale.payments if p.id == payment_id), None)
            if payment is None:
                already = next((v for v in sale.voided_payments
                                if v.payment_id == payment_id), None)
                if already is not None:     # reintento
                    return SaleResult.ok("El pago ya estaba anulado", entity_id=sale.id,
                                         operation_id=operation_id,
                                         refund=refund_instruction(already),
                                         sale=SaleDTO.from_entity(sale))
            try:
                if payment is not None:
                    self._auth.require(actor_user_id, _PERMISSION_BY_METHOD[payment.method])
                instruction = self._void_and_compensate(
                    connection, uow, sale, payment_id, reason=reason,
                    actor_user_id=actor_user_id, operation_id=operation_id)
            except SalesDomainError as exc:
                uow.rollback()
                return fail_from_domain_error(exc, operation_id=operation_id)
            except Exception as exc:  # noqa: BLE001 - Finanzas/Fidelidad: se deshace todo
                uow.rollback()
                return SaleResult.fail(f"No se pudo anular el pago: {exc}",
                                       "PAYMENT_VOID_FAILED", operation_id=operation_id)
            uow.sales.save(sale)
        return SaleResult.ok("Pago anulado", entity_id=sale.id, operation_id=operation_id,
                             refund=instruction, sale=SaleDTO.from_entity(sale))
