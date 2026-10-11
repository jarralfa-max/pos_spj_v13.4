"""QuoteQueryService — lecturas de Cotizaciones con permiso y alcance (CRM-43).

Alcance como el CRM (decisión del usuario): propias para el cajero, su
sucursal para el gerente, toda la empresa para dueño/admin.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.application.crm.data_scope import CRMDataScopeResolver, CRMScopeContext
from backend.application.quotes.authorization import QuotesAuthorizationPolicy
from backend.application.quotes.permissions import (
    QUOTE_VIEW_SCOPE_PERMISSIONS,
    QuotePermissions,
)
from backend.domain.quotes.entities import Quote
from backend.domain.quotes.enums import QuoteStatus
from backend.domain.quotes.exceptions import QuoteNotFoundError
from backend.infrastructure.db.repositories.quotes.unit_of_work import QuotesUnitOfWork

#: Cuántas cotizaciones trae una bandeja.
QUOTE_LIST_LIMIT = 500


@dataclass(frozen=True, slots=True)
class QuoteRow:
    id: str
    quote_number: str
    revision: int
    customer_id: str
    opportunity_id: str | None
    branch_id: str
    status: QuoteStatus
    valid_until: date
    total: Decimal
    discount_total: Decimal
    requires_approval: bool
    created_by_user_id: str
    created_at: str
    sent_at: str | None
    converted_order_id: str | None
    line_count: int


@dataclass(frozen=True, slots=True)
class QuoteDetail:
    quote: Quote
    trail: tuple[dict, ...]
    #: Pedido de la conversión, como lo identifica Pedidos (folio o id corto).
    order_reference: str | None = None
    order_status: str | None = None


def _row(raw: dict) -> QuoteRow:
    return QuoteRow(
        id=raw["id"], quote_number=raw["quote_number"], revision=int(raw["revision"]),
        customer_id=raw["customer_id"], opportunity_id=raw["opportunity_id"],
        branch_id=raw["branch_id"], status=QuoteStatus(raw["status"]),
        valid_until=date.fromisoformat(str(raw["valid_until"])[:10]),
        total=Decimal(raw["total"] or "0"), discount_total=Decimal(raw["discount_total"] or "0"),
        requires_approval=bool(raw["requires_approval"]),
        created_by_user_id=raw["created_by_user_id"], created_at=raw["created_at"],
        sent_at=raw["sent_at"], converted_order_id=raw["converted_order_id"],
        line_count=int(raw.get("line_count") or 0))


class QuoteQueryService:
    def __init__(self, connection, scope_resolver: CRMDataScopeResolver,
                 authorization: QuotesAuthorizationPolicy, *, pricing_factory=None) -> None:
        self._conn = connection
        self._scopes = scope_resolver
        self._auth = authorization
        self._pricing_factory = pricing_factory

    def _scope(self, context: CRMScopeContext):
        self._auth.require(context.user_id, QuotePermissions.VIEW)
        return self._scopes.resolve_view_scope(context, QUOTE_VIEW_SCOPE_PERMISSIONS)

    def list_rows(self, context: CRMScopeContext, *, statuses: tuple[str, ...] = (),
                  customer_id: str | None = None, opportunity_id: str | None = None
                  ) -> list[QuoteRow]:
        scope = self._scope(context)
        rows = QuotesUnitOfWork(self._conn).quotes.list_in_scope(
            scope, statuses=tuple(statuses), customer_id=customer_id,
            opportunity_id=opportunity_id, limit=QUOTE_LIST_LIMIT)
        return [_row(r) for r in rows]

    def pending_approval(self, context: CRMScopeContext) -> list[QuoteRow]:
        self._auth.require(context.user_id, QuotePermissions.APPROVE)
        return self.list_rows(context, statuses=(QuoteStatus.PENDING_APPROVAL.value,))

    def get(self, quote_id: str, context: CRMScopeContext) -> QuoteDetail:
        scope = self._scope(context)
        uow = QuotesUnitOfWork(self._conn)
        quote = uow.quotes.get(quote_id)
        if quote is None or not scope.includes(
                responsible_user_id=quote.created_by_user_id,
                created_by_user_id=quote.created_by_user_id, branch_id=quote.branch_id):
            raise QuoteNotFoundError("La cotización no existe o está fuera de tu alcance.")
        reference = status = None
        if quote.converted_order_id:
            from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
                CustomerOrderRepository,
            )
            order = CustomerOrderRepository(self._conn).get(quote.converted_order_id)
            if order is not None:
                reference = order.order_number or order.id[:8]
                status = getattr(order.status, "value", order.status)
        return QuoteDetail(quote=quote, trail=tuple(uow.audit.list_for_quote(quote_id)),
                           order_reference=reference, order_status=status)

    def search_products(self, context: CRMScopeContext, *, branch_id: str, text: str,
                        limit: int):
        """Productos que se pueden cotizar en la sucursal (precio de vitrina)."""
        self._auth.require(context.user_id, QuotePermissions.VIEW)
        return self._pricing().search(branch_id=branch_id, text=text, limit=limit)

    def explain_no_products(self, *, branch_id: str, text: str) -> str | None:
        return self._pricing().explain_empty(branch_id=branch_id, text=text)

    def _pricing(self):
        if self._pricing_factory is None:
            from backend.application.quotes.pricing import QuotePricing
            self._pricing_factory = QuotePricing
        return self._pricing_factory(self._conn)
