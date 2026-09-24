"""NewOrderPresenter (PASS 6) — "Nuevo pedido".

Busca productos con `OrderCaptureCatalogQueryService` y crea el pedido con
`CaptureOrderUseCase`, que revalida el permiso, fija el precio desde Pricing y
guarda la dirección en la misma transacción. El subtotal que enseña la pantalla es
una estimación con el precio vigente; el total real lo calcula el pedido.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from backend.application.orders_delivery.queries.order_capture_catalog_query_service import (
    CaptureCatalogItem,
    OrderCaptureCatalogQueryService,
)
from backend.application.orders_delivery.use_cases.capture_order_use_cases import (
    CaptureOrderUseCase,
)
from backend.domain.orders_delivery.policies.order_lifecycle_policy import OrderConfirmationPolicy
from backend.shared.ids import new_uuid
from frontend.desktop.components.search_selector import SearchOption

CHANNEL_OPTIONS = [
    ("POS", "Mostrador (POS)"), ("WHATSAPP", "WhatsApp"), ("COUNTER", "Ventanilla"),
    ("PHONE", "Teléfono"), ("BACKOFFICE", "Backoffice"),
]

FULFILLMENT_OPTIONS = [
    ("COUNTER", "Recoger en mostrador"), ("PICKUP", "Recoger programado"),
    ("HOME_DELIVERY", "Entrega a domicilio"), ("SCHEDULED_DELIVERY", "Entrega programada"),
    ("EXPRESS_DELIVERY", "Entrega exprés"),
]


logger = logging.getLogger("spj.orders_delivery.new_order_presenter")


def _dinero(valor: Decimal) -> str:
    return f"${valor:,.2f}"


class NewOrderPresenter:
    def __init__(self, connection, *, branch_id: str, actor_user_id: str | None,
                 authorization=None, customer_lookup=None) -> None:
        self._conn = connection
        self._branch_id = branch_id
        self._actor_user_id = actor_user_id or ""
        self._authorization = authorization
        #: `CustomerLookupQueryService` de la sesión (la misma búsqueda que el
        #: mostrador). Sin él el pedido se captura sin cliente.
        self._customer_lookup = customer_lookup
        self._clientes: dict[str, object] = {}
        self._productos: dict[str, CaptureCatalogItem] = {}

    def can_create(self) -> bool:
        return bool(
            self._authorization is not None and self._actor_user_id
            and self._authorization.has_permission(
                self._actor_user_id, OrdersDeliveryPermissions.ORDER_CREATE))

    @staticmethod
    def requires_address(fulfillment_type: str | None) -> bool:
        return bool(fulfillment_type) and fulfillment_type in {
            tipo.value for tipo in OrderConfirmationPolicy.ADDRESS_REQUIRED_FULFILLMENT_TYPES}

    def address_search_service(self):
        """El servicio estándar de direcciones (Configuración → Integraciones).
        `None` si no se pudo preparar: el componente deja capturar a mano."""
        try:
            from backend.infrastructure.maps.address_search_factory import (
                build_address_search_service,
            )
            return build_address_search_service(self._conn)
        except Exception:
            import logging
            logging.getLogger("spj.orders_delivery.new_order").exception(
                "No se pudo preparar la búsqueda de direcciones")
            return None

    def search_products(self, query: str) -> list[SearchOption]:
        items = OrderCaptureCatalogQueryService(self._conn).search(
            branch_id=self._branch_id, query=query)
        self._productos.update({item.product_id: item for item in items})
        return [
            SearchOption(
                item.product_id, item.name,
                f"{item.code} · {_dinero(item.price)} / {item.unit_code or 'PZA'}"
                if item.price is not None else f"{item.code} · Sin precio vigente")
            for item in items
        ]

    def product_search_reason(self, query: str) -> str | None:
        """Por qué no hay productos que ofrecer. Diagnóstico: nunca lanza."""
        try:
            return OrderCaptureCatalogQueryService(self._conn).explain_empty(
                branch_id=self._branch_id, query=query)
        except Exception:
            logger.exception("product search reason failed")
            return None

    # cliente (opcional) --------------------------------------------------------
    def search_customers(self, query: str) -> list[SearchOption]:
        """Clientes para el pedido. El cliente es OPCIONAL (decisión del usuario,
        2026-09-18): con él aplican sus listas de precio, igual que en el mostrador.
        Sin permiso de búsqueda no hay resultados, y el motivo lo da
        `customer_search_reason`."""
        if self._customer_lookup is None or not (query or "").strip():
            return []
        try:
            resultados = self._customer_lookup.lookup(query, actor_user_id=self._actor_user_id)
        except Exception as exc:
            if type(exc).__name__ == "CustomerPermissionDeniedError":
                return []
            raise
        self._clientes.update({r.customer_id: r for r in resultados})
        return [SearchOption(r.customer_id, r.display_name,
                             " · ".join(x for x in (r.code, r.phone_e164) if x))
                for r in resultados]

    def customer_search_reason(self, query: str) -> str | None:
        if self._customer_lookup is None:
            return "La búsqueda de clientes no está disponible en esta pantalla."
        try:
            self._customer_lookup.lookup(query, actor_user_id=self._actor_user_id, limit=1)
        except Exception as exc:
            if type(exc).__name__ == "CustomerPermissionDeniedError":
                return "No tienes permiso para buscar clientes (CLIENTES.buscar)."
            return None
        return None

    def customer(self, customer_id: str | None):
        """El resultado de búsqueda elegido: nombre y teléfono para el contacto."""
        return self._clientes.get(customer_id) if customer_id else None

    def product(self, product_id: str | None) -> CaptureCatalogItem | None:
        return self._productos.get(product_id) if product_id else None

    @staticmethod
    def line_row(item: CaptureCatalogItem, quantity: Decimal) -> list[str]:
        unidad = item.unit_code or "PZA"
        return [
            item.name, f"{quantity} {unidad}",
            _dinero(item.price) if item.price is not None else "—",
            _dinero(item.price * quantity) if item.price is not None else "—",
        ]

    def create(self, data: dict) -> tuple[bool, str]:
        resultado = CaptureOrderUseCase(self._authorization).execute(
            self._conn, branch_id=self._branch_id, channel=data.get("channel"),
            fulfillment_type=data.get("fulfillment_type"), lines=data.get("lines") or [],
            actor_user_id=self._actor_user_id, operation_id=new_uuid(),
            contact_name=data.get("contact_name"), contact_phone=data.get("contact_phone"),
            address=data.get("address"), customer_id=data.get("customer_id"))
        return resultado.success, resultado.message
