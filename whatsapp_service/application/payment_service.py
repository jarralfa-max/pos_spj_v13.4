# application/payment_service.py — WA-12 (§38-39, §19 del prompt maestro)
"""
PaymentService — cubre Link/Status/Confirmation/Duplicate-webhook del
checklist de WA-12. WhatsApp NUNCA calcula el anticipo ni confirma un pago
por su cuenta (§38) — todo pasa por `PaymentsApiClient` (WA-9, el ERP) o
`PaymentProviderGateway` (WA-12, MercadoPago).

**Status** deliberadamente NO agrega un método nuevo a `PaymentsApiClient`
— `ERPBridge` (WA-9) no expone ninguna consulta de "estado de anticipo"
propia; el estado real y consultable ya es el de la ORDEN
(`OrdersApiClient.get_status()`, WA-9: `pendiente_wa` → `confirmada` tras
el pago) — inventar un segundo concepto de estado duplicaría lo que ya
existe.

**Duplicate webhook** (§19): `confirm_payment()` es idempotente sobre la
referencia real del proveedor (`payment_reference` — el ID de pago de
MercadoPago), no sobre el contenido del pedido — dos entregas del mismo
evento de webhook (reintento de red, replay dentro de la ventana que WA-1
no puede cerrar del todo para Meta pero MercadoPago sí firma con
timestamp) no deben confirmar el pago dos veces.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from application.idempotency_fingerprint import compute_fingerprint
from domain.whatsapp.entities.business_operation import BusinessOperationIdempotencyRecord
from domain.whatsapp.erp_ports import OrderRef
from domain.whatsapp.payment_provider_ports import PaymentLinkRef


@dataclass(frozen=True)
class ConfirmPaymentResult:
    confirmed: bool
    deduplicated: bool


class PaymentService:
    def __init__(self, root) -> None:
        self._root = root

    # ── Link (§38) ───────────────────────────────────────────────────────────

    async def create_payment_link(
        self, *, order_external_id: str, amount: float, customer_phone: str
    ) -> PaymentLinkRef:
        external_reference = f"{order_external_id}:{customer_phone}"
        return await self._root.payment_provider.create_preference(
            amount=amount, external_reference=external_reference,
            description=f"Pedido {order_external_id}",
        )

    # ── Status (§38) — reutiliza el estado de la orden, no inventa uno nuevo ──

    async def get_order_payment_status(self, folio: str) -> Optional[OrderRef]:
        return await self._root.orders.get_status(folio)

    # ── Confirmation + Duplicate webhook (§38, §19) ─────────────────────────

    async def register_advance(self, *, order_external_id: str, amount: float, method: str = "mercadopago") -> str:
        return await self._root.payments.register_advance(order_id=order_external_id, amount=amount, method=method)

    async def confirm_payment(
        self, *, order_external_id: str, amount: float, payment_reference: str, method: str = "mercadopago"
    ) -> ConfirmPaymentResult:
        fingerprint = compute_fingerprint("CONFIRM_PAYMENT", order_external_id, payment_reference)

        existing = self._root.idempotency.get_by_fingerprint(fingerprint)
        if existing is not None and existing.result_reference:
            return ConfirmPaymentResult(confirmed=True, deduplicated=True)

        record = existing or BusinessOperationIdempotencyRecord.start(
            operation_type="CONFIRM_PAYMENT", aggregate_type="ORDER",
            aggregate_id=order_external_id, fingerprint=fingerprint,
        )
        if existing is None:
            self._root.idempotency.save(record)

        try:
            confirmed = await self._root.payments.confirm_payment(
                order_id=order_external_id, amount=amount, reference=payment_reference, method=method,
            )
        except Exception:
            record.fail()
            self._root.idempotency.save(record)
            raise

        if confirmed:
            record.complete(result_reference=payment_reference)
        else:
            record.fail()
        self._root.idempotency.save(record)

        return ConfirmPaymentResult(confirmed=confirmed, deduplicated=False)
