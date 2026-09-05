# application/delivery_request_service.py — WA-13 (§35, §19 del prompt maestro)
"""
DeliveryRequestService — orquesta "programar entrega a domicilio" para un
pedido ya confirmado (WA-10) contra `DeliveryApiClient.schedule()` (WA-9,
que ya envuelve el real `ERPBridge.schedule()` → `ventas.direccion_entrega`/
`fecha_entrega_programada`).

Idempotente (§19) sobre `(order_external_id, address, delivery_date)`: dos
mensajes del cliente pidiendo lo mismo ("programa mi entrega a la misma
dirección") no disparan dos llamadas al ERP — reutiliza el mismo
`compute_fingerprint()` que Orders/Quotes/Payments (WA-10/11/12), cuarto
consumidor real del mismo algoritmo compartido.

**Reintento tras fallo, explícito**: a diferencia de WA-12
(`PaymentService.confirm_payment`, sin test de reintento tras un fallo
previo), aquí sí se cubre: `BusinessOperationIdempotencyRecord.complete()`/
`.fail()` (WA-10) solo aceptan transicionar desde `PENDING` — si un intento
anterior con el MISMO fingerprint terminó en `FAILED`, el registro
existente se reactiva a `PENDING` antes de reintentar en vez de fallar al
reintentar (no se puede crear un segundo registro con el mismo
fingerprint: `whatsapp_business_operation_idempotency.fingerprint` es
`UNIQUE`).

No calcula ni valida ventana de entrega/ruta/repartidor — eso es
Orders/Delivery real (§6); este servicio solo transporta lo que el cliente
dictó por WhatsApp.
"""
from __future__ import annotations

from dataclasses import dataclass

from application.idempotency_fingerprint import compute_fingerprint
from domain.whatsapp.entities.business_operation import BusinessOperationIdempotencyRecord
from domain.whatsapp.entities.delivery_request import DeliveryRequest
from domain.whatsapp.enums import IdempotencyStatus


@dataclass(frozen=True)
class DeliveryRequestResult:
    request: DeliveryRequest
    scheduled: bool
    deduplicated: bool


def _fingerprint(order_external_id: str, address: str, delivery_date: str) -> str:
    return compute_fingerprint("SCHEDULE_DELIVERY", order_external_id, address.strip(), delivery_date)


class DeliveryRequestService:
    def __init__(self, root) -> None:
        self._root = root

    async def request_delivery(
        self, *, conversation_id: str, order_external_id: str, address: str,
        delivery_date: str = "", customer_phone: str = "",
    ) -> DeliveryRequestResult:
        fingerprint = _fingerprint(order_external_id, address, delivery_date)

        existing = self._root.idempotency.get_by_fingerprint(fingerprint)
        if existing is not None and existing.result_reference:
            request = self._root.delivery_requests.get_by_order_external_id(order_external_id)
            if request is None:
                # No debería ocurrir en operación normal (el fingerprint solo
                # se registra tras crear la solicitud) — degradar explícito
                # en vez de fingir un resultado.
                raise RuntimeError(
                    f"Idempotencia encontrada para {order_external_id!r} pero sin DeliveryRequest asociado"
                )
            return DeliveryRequestResult(request=request, scheduled=True, deduplicated=True)

        # Cada intento deja su propio registro `DeliveryRequest` (es un
        # rastro conversacional, no una fila que se edite in-place) — un
        # reintento tras un FAILED previo crea uno nuevo, nunca reabre uno
        # ya terminal (`mark_failed`/`mark_scheduled` rechazan reabrir un
        # `DeliveryRequest` terminal, igual que `OrderDraft`/`QuoteDraft`).
        request = DeliveryRequest.start(
            conversation_id=conversation_id, order_external_id=order_external_id,
            address=address, delivery_date=delivery_date, customer_phone=customer_phone,
        )
        self._root.delivery_requests.save(request)

        if existing is not None:
            record = existing
            record.status = IdempotencyStatus.PENDING  # reintento tras un FAILED previo
        else:
            record = BusinessOperationIdempotencyRecord.start(
                operation_type="SCHEDULE_DELIVERY", aggregate_type="DELIVERY_REQUEST",
                aggregate_id=request.id, fingerprint=fingerprint,
            )
        self._root.idempotency.save(record)

        try:
            ok = await self._root.delivery.schedule(
                order_id=order_external_id, address=address,
                delivery_date=delivery_date, customer_phone=customer_phone,
            )
        except Exception:
            request.mark_failed("Error al comunicar con el ERP")
            self._root.delivery_requests.save(request)
            record.fail()
            self._root.idempotency.save(record)
            raise

        if ok:
            request.mark_scheduled()
            record.complete(result_reference="SCHEDULED")
        else:
            request.mark_failed("El ERP no pudo programar la entrega")
            record.fail()

        self._root.delivery_requests.save(request)
        self._root.idempotency.save(record)
        return DeliveryRequestResult(request=request, scheduled=ok, deduplicated=False)
