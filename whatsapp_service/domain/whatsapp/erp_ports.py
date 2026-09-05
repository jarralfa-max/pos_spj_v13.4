# domain/whatsapp/erp_ports.py — WA-9 (§52-53 del prompt maestro)
"""
Contratos ERP — WhatsApp SOLO consulta/solicita a través de estos puertos;
nunca calcula precio/stock/crédito ni escribe SQL directo contra tablas del
ERP (§6/§33-44: "WhatsApp conversa, los bounded contexts deciden").

**Decisión de pipeline (2026-09-01, confirmada por el usuario dado el
hallazgo de tres pipelines paralelas en WA-0)**: la autoritativa es el
microservicio oficial (`whatsapp_service/`, el que WA-1..8 vienen
reconstruyendo) escribiendo contra `ventas`/`detalles_venta`/
`cotizaciones`/`anticipos`/`clientes` — las mismas tablas que `ERPBridge`
(`whatsapp_service/erp/bridge.py`) ya escribe hoy en producción. Estos
puertos envuelven `ERPBridge` (Customers/Orders/Quotes/Payments/Delivery)
y `ProductMatcher` (Catalog) — implementaciones REALES y ya en producción
— no inventan un segundo camino de escritura. El stack legacy
ERP-embedded (`core/services/whatsapp_service.py`+`bot_pedidos.py`) y Rasa
quedan sin tocar, candidatos a retiro en una fase posterior (WA-21), no
ahora.

Sin puerto separado de Pricing/Inventory: `ProductRef.price`/`.stock` ya
cubre la necesidad real (mostrar precio, validar disponibilidad antes de
confirmar) — un puerto adicional envolvería exactamente el mismo dato bajo
otro nombre.

**`LoyaltyApiClient` (WA-15)**: WA-9 lo dejó solo como contrato — no
existía ningún gateway de fidelidad real en `erp/` para envolver.
`LoyaltySummaryRef` (agregado en WA-15, cuando sí existió una
implementación real que envolver: `loyalty_snapshots`, la misma tabla que
ya lee `LoyaltyCustomerSummaryQuery` del lado ERP) reemplaza el `Dict`
crudo original del Protocol por un tipo propio, mismo criterio que el
resto de los Ref de este módulo.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol


@dataclass(frozen=True)
class CustomerRef:
    external_id: str
    name: str
    phone: str


@dataclass(frozen=True)
class ProductRef:
    external_id: str
    name: str
    unit: str
    price: float
    stock: float


@dataclass(frozen=True)
class OrderRef:
    external_id: str
    status: str
    folio: str = ""


@dataclass(frozen=True)
class QuoteRef:
    external_id: str
    folio: str = ""
    valid_until: str = ""


@dataclass(frozen=True)
class LoyaltySummaryRef:
    """WA-15 — espejo de `LoyaltyCustomerSummaryQuery`'s
    `LoyaltyCustomerSummary` (lado ERP, `backend/application/customers/
    queries/loyalty_customer_summary_query.py`, CRM-21), pero sin la capa
    de autorización de staff (`actor_user_id`) — aquí es el propio cliente
    consultando su saldo por WhatsApp, no un empleado consultando el de un
    tercero."""

    customer_id: str
    enrolled: bool
    points: int
    tier: str
    visits: int


class CustomersApiClient(Protocol):
    async def find_by_phone(self, phone: str) -> Optional[CustomerRef]: ...
    async def create_minimal(self, *, name: str, phone: str) -> CustomerRef: ...


class CatalogApiClient(Protocol):
    async def search(self, query: str, *, max_results: int = 5) -> List[ProductRef]: ...
    async def get_by_id(self, product_id: str) -> Optional[ProductRef]: ...
    async def get_categories(self) -> List[str]: ...


class OrdersApiClient(Protocol):
    async def create(
        self, *, items: List[Dict[str, Any]], customer_id: str, branch_id: str, **extra: Any
    ) -> OrderRef: ...
    async def update_status(self, order_id: str, status: str, notes: str = "") -> bool: ...
    async def get_status(self, folio: str) -> Optional[OrderRef]: ...


class QuotesApiClient(Protocol):
    async def create(
        self, *, items: List[Dict[str, Any]], customer_id: str, **extra: Any
    ) -> QuoteRef: ...
    async def convert_to_order(self, quote_id: str, user: str = "whatsapp") -> OrderRef: ...


class PaymentsApiClient(Protocol):
    async def register_advance(
        self, *, order_id: str, amount: float, method: str = "mercadopago"
    ) -> str: ...
    async def confirm_payment(
        self, *, order_id: str, amount: float, reference: str = "", method: str = "mercadopago"
    ) -> bool: ...


class DeliveryApiClient(Protocol):
    async def schedule(
        self, *, order_id: str, address: str, delivery_date: str = "", customer_phone: str = ""
    ) -> bool: ...


class StaffDirectoryApiClient(Protocol):
    """WA-16 — resolver a quién notificar cuando se escala una
    conversación a un humano. Envuelve `ERPBridge.get_staff_phones`
    (ya real, usado hoy por `middleware/handoff.py`)."""

    async def get_staff_phones(self, branch_id: str, *, role: str = "") -> List[str]: ...


class LoyaltyApiClient(Protocol):
    async def get_summary(self, customer_id: str) -> LoyaltySummaryRef:
        """Nunca `None` — un cliente sin fila en `loyalty_snapshots`
        devuelve `LoyaltySummaryRef(enrolled=False, ...)`, una respuesta
        con significado propio, no la ausencia de una."""
        ...
