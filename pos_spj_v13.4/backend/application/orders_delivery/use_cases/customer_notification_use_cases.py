"""Customer notification use cases (master prompt §27/§30, ORD-23). The
automatic FIRST notification for a pending weight-adjustment/substitution
already fires as a best-effort side effect inside `EvaluateCatchWeightUseCase`/
`ProposeSubstitutionUseCase` (catch_weight_use_cases.py/substitution_use_cases.py) —
this module is the MANUAL "reenviar" action a staff member triggers when a
customer says they never got the WhatsApp message, gated by the dedicated
`CUSTOMER_APPROVAL_RESEND` permission ORD-1 minted for exactly this and that
nothing had used until now.
"""

from __future__ import annotations

from backend.application.orders_delivery.dto import CustomerOrderDTO
from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.result import OrderResult, fail_from_domain_error
from backend.application.orders_delivery.use_cases._base import _OrdersDeliveryBaseUseCase
from backend.domain.orders_delivery.enums import CustomerApprovalStatus, OrderLineStatus
from backend.domain.orders_delivery.exceptions import (
    CustomerApprovalRequiredError,
    OrderNotFoundError,
    OrdersDeliveryDomainError,
)
from backend.infrastructure.db.repositories.orders_delivery.unit_of_work import (
    OrdersDeliveryUnitOfWork,
)
from backend.infrastructure.integrations.orders_delivery_whatsapp_client import (
    OrdersDeliveryWhatsAppClient,
)


class ResendCustomerApprovalNotificationUseCase(_OrdersDeliveryBaseUseCase):
    def __init__(self, authorization=None, *,
                 whatsapp_client: OrdersDeliveryWhatsAppClient | None = None) -> None:
        super().__init__(authorization)
        self._whatsapp = whatsapp_client or OrdersDeliveryWhatsAppClient()

    def execute(self, connection, *, order_id: str, actor_user_id: str,
                operation_id: str) -> OrderResult:
        try:
            self._auth.require(actor_user_id, OrdersDeliveryPermissions.CUSTOMER_APPROVAL_RESEND)
        except OrdersDeliveryDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with OrdersDeliveryUnitOfWork(connection) as uow:
            order = uow.orders.get(order_id)
            if order is None:
                return fail_from_domain_error(
                    OrderNotFoundError(f"Pedido {order_id} no existe"), operation_id=operation_id)
            if order.customer_approval_status != CustomerApprovalStatus.PENDING:
                return fail_from_domain_error(
                    CustomerApprovalRequiredError(
                        "El pedido no tiene una aprobación de cliente pendiente"),
                    operation_id=operation_id)
            pending_lines = [
                line for line in order.lines
                if line.status == OrderLineStatus.PENDING_CUSTOMER_APPROVAL]

        reasons = [
            f"sustitución de producto ({line.substitution_reason or 'sin motivo'})"
            if line.substitute_product_id else "ajuste de peso fuera de tolerancia"
            for line in pending_lines
        ]
        reason = "; ".join(reasons) or "ajuste pendiente de tu aprobación"
        notification_sent = self._whatsapp.notify_customer_approval_required(
            phone=order.contact_phone or "", order_number=order.order_number or order.id,
            reason=reason)
        return OrderResult.ok(
            "Notificación reenviada" if notification_sent else "No se pudo reenviar la notificación",
            entity_id=order.id, operation_id=operation_id,
            order=CustomerOrderDTO.from_entity(order), notification_sent=notification_sent)
