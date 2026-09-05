# application/order_draft_service.py — WA-10 (§34-36, §19 del prompt maestro)
"""
OrderDraftService — orquesta el carrito conversacional (`OrderDraft`,
dominio) contra el catálogo real (`CatalogApiClient`, WA-9) y, al
confirmar, contra `OrdersApiClient` (WA-9) con idempotencia de negocio
real (§19) — dos mensajes distintos del cliente para la misma acción
("confirmar pedido" / "sí, confirmar") no deben crear dos pedidos.

No calcula precio final por su cuenta más allá de sumar lo que el catálogo
ya dijo que cuesta cada línea (`ProductRef.price`, WA-9) — nunca inventa
un precio, nunca aplica descuentos/reglas de crédito (eso es Pricing/
Orders reales, fuera del canal, §6).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from application.idempotency_fingerprint import compute_fingerprint
from domain.whatsapp.entities.business_operation import BusinessOperationIdempotencyRecord
from domain.whatsapp.entities.order_draft import OrderDraft, OrderDraftLine
from domain.whatsapp.enums import DeliveryMethod, OrderDraftStatus
from domain.whatsapp.erp_ports import OrderRef, ProductRef


class ProductNotFoundError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConfirmOrderResult:
    order: OrderRef
    deduplicated: bool


def _fingerprint(draft: OrderDraft) -> str:
    """Determinístico sobre CONTENIDO, no sobre el texto del mensaje que lo
    disparó — dos redacciones distintas del cliente para la misma
    confirmación producen el mismo fingerprint."""
    line_signature = "|".join(
        f"{line.product_external_id}:{line.quantity}"
        for line in sorted(draft.lines, key=lambda l: l.product_external_id)
    )
    delivery = draft.delivery_method.value if draft.delivery_method else ""
    return compute_fingerprint("CREATE_ORDER", draft.conversation_id, line_signature, delivery)


class OrderDraftService:
    def __init__(self, root) -> None:
        self._root = root

    def start_draft(self, *, conversation_id: str, branch_id: Optional[str] = None) -> OrderDraft:
        draft = OrderDraft.start(conversation_id=conversation_id, branch_id=branch_id)
        self._root.order_drafts.save(draft)
        return draft

    async def add_product_by_search(
        self, draft: OrderDraft, *, query: str, quantity: float
    ) -> OrderDraftLine:
        """Capa "Product selection" (WA-10): busca en el catálogo real
        (WA-9) y agrega la primera coincidencia — el desambiguar entre
        varias coincidencias es responsabilidad de la capa conversacional
        (WA-7/8), no de este servicio."""
        results = await self._root.catalog.search(query, max_results=1)
        if not results:
            raise ProductNotFoundError(f"Sin coincidencias de catálogo para {query!r}")
        return self.add_product(draft, product=results[0], quantity=quantity)

    def add_product(self, draft: OrderDraft, *, product: ProductRef, quantity: float) -> OrderDraftLine:
        line = draft.add_line(
            product_external_id=product.external_id, product_name=product.name,
            quantity=quantity, unit=product.unit, unit_price=product.price,
        )
        self._root.order_drafts.save(draft)
        return line

    def set_delivery_method(self, draft: OrderDraft, method: DeliveryMethod) -> OrderDraft:
        draft.set_delivery_method(method)
        self._root.order_drafts.save(draft)
        return draft

    async def confirm(self, draft: OrderDraft, *, customer_external_id: str) -> ConfirmOrderResult:
        """Idempotente (§19): reintentos con el mismo contenido de carrito
        devuelven el pedido ya creado, nunca uno nuevo.

        El fingerprint se calcula ANTES de tocar el borrador — depende
        solo de contenido (conversación + líneas + método de entrega), no
        de `customer_external_id` ni del estado actual del borrador, así
        que puede resolverse contra un intento previo incluso si este
        objeto `draft` en memoria es una reconstrucción nueva del mismo
        contenido."""
        fingerprint = _fingerprint(draft)

        existing = self._root.idempotency.get_by_fingerprint(fingerprint)
        if existing is not None and existing.result_reference:
            if draft.status != OrderDraftStatus.CONFIRMED:
                draft.set_customer(customer_external_id)
                draft.confirm()
                self._root.order_drafts.save(draft)
            return ConfirmOrderResult(
                order=OrderRef(external_id=existing.result_reference, status="pendiente_wa"),
                deduplicated=True,
            )

        draft.set_customer(customer_external_id)
        record = existing or BusinessOperationIdempotencyRecord.start(
            operation_type="CREATE_ORDER", aggregate_type="ORDER_DRAFT",
            aggregate_id=draft.id, fingerprint=fingerprint,
        )
        if existing is None:
            self._root.idempotency.save(record)

        items = [
            {
                "producto_id": line.product_external_id, "cantidad": line.quantity,
                "unidad": line.unit, "precio_unitario": line.unit_price,
            }
            for line in draft.lines
        ]
        try:
            order_ref = await self._root.orders.create(
                items=items, customer_id=customer_external_id, branch_id=draft.branch_id or "",
                canal="whatsapp", tipo_entrega=(draft.delivery_method.value if draft.delivery_method else ""),
            )
        except Exception:
            record.fail()
            self._root.idempotency.save(record)
            raise

        record.complete(result_reference=order_ref.external_id)
        self._root.idempotency.save(record)

        draft.confirm()
        self._root.order_drafts.save(draft)
        return ConfirmOrderResult(order=order_ref, deduplicated=False)
