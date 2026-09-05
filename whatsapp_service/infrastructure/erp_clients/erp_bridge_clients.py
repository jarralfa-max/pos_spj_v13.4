# infrastructure/erp_clients/erp_bridge_clients.py — WA-9
"""
Adaptadores reales de los contratos ERP (`domain/whatsapp/erp_ports.py`)
— envuelven `ERPBridge`/`ProductMatcher` (ambos ya reales y en producción,
ver `docs/refactor/WA-9_erp_contracts.md`). Solo traducen forma: nombres
de parámetro en inglés (el contrato del canal) hacia los nombres en
español que `ERPBridge` ya usa, y `Dict` crudo hacia los `Ref` tipados de
`erp_ports.py`. Ninguna regla de negocio vive aquí — eso ya lo decide
`ERPBridge`/el ERP real (§6 del prompt maestro).

Todos los métodos son `async def` por consistencia con el resto de los
puertos del canal (WA-5/WA-8) — las llamadas internas a `ERPBridge`/
`ProductMatcher` son síncronas (SQLite local), igual que el resto de este
árbol; no se envuelven en threads, mismo criterio pragmático que el propio
`ERPBridge` ya aplica en el código que ya existía antes de esta fase.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from domain.whatsapp.erp_ports import CustomerRef, OrderRef, ProductRef, QuoteRef


def _str_or_empty(value: Any) -> str:
    return str(value) if value is not None else ""


class ErpBridgeCustomersApiClient:
    def __init__(self, bridge) -> None:
        self._bridge = bridge

    async def find_by_phone(self, phone: str) -> Optional[CustomerRef]:
        row = self._bridge.find_by_phone(phone)
        if not row:
            return None
        return CustomerRef(
            external_id=_str_or_empty(row.get("id")),
            name=row.get("nombre", "") or "",
            phone=row.get("telefono", "") or "",
        )

    async def create_minimal(self, *, name: str, phone: str) -> CustomerRef:
        new_id = self._bridge.create_minimal(name, phone)
        return CustomerRef(external_id=_str_or_empty(new_id), name=name, phone=phone)


class ProductMatcherCatalogApiClient:
    """Envuelve `ProductMatcher` — ya hace búsqueda exacta→por-palabra→fuzzy
    y ya conoce stock/precio por sucursal (WA-9 no reimplementa nada de
    esto)."""

    def __init__(self, matcher) -> None:
        self._matcher = matcher

    @staticmethod
    def _to_ref(row: Dict[str, Any]) -> ProductRef:
        return ProductRef(
            external_id=_str_or_empty(row.get("id")),
            name=row.get("nombre", "") or "",
            unit=row.get("unidad", "") or "",
            price=float(row.get("precio", 0) or 0),
            stock=float(row.get("stock", 0) or 0),
        )

    async def search(self, query: str, *, max_results: int = 5) -> List[ProductRef]:
        rows = self._matcher.search(query, max_results=max_results)
        return [self._to_ref(r) for r in rows]

    async def get_by_id(self, product_id: str) -> Optional[ProductRef]:
        row = self._matcher.get_by_id(product_id)
        return self._to_ref(row) if row else None

    async def get_categories(self) -> List[str]:
        return list(self._matcher.get_categories())


class ErpBridgeOrdersApiClient:
    def __init__(self, bridge) -> None:
        self._bridge = bridge

    async def create(
        self, *, items: List[Dict[str, Any]], customer_id: str, branch_id: str, **extra: Any
    ) -> OrderRef:
        result = self._bridge.create(items=items, cliente_id=customer_id, sucursal_id=branch_id, **extra)
        row = result if isinstance(result, dict) else {"id": result}
        return OrderRef(
            external_id=_str_or_empty(row.get("id", result)),
            status=row.get("estado", "pendiente_wa") or "pendiente_wa",
            folio=row.get("folio", "") or "",
        )

    async def update_status(self, order_id: str, status: str, notes: str = "") -> bool:
        return bool(self._bridge.update_status(order_id, status, notes))

    async def get_status(self, folio: str) -> Optional[OrderRef]:
        row = self._bridge.get_by_folio(folio)
        if not row:
            return None
        return OrderRef(
            external_id=_str_or_empty(row.get("id")),
            status=row.get("estado", "") or "",
            folio=row.get("folio", folio) or folio,
        )


class ErpBridgeQuotesApiClient:
    def __init__(self, bridge) -> None:
        self._bridge = bridge

    async def create(self, *, items: List[Dict[str, Any]], customer_id: str, **extra: Any) -> QuoteRef:
        result = self._bridge.create(items=items, cliente_id=customer_id, **extra)
        row = result if isinstance(result, dict) else {"id": result}
        # Nombres de campo de folio/vigencia no verificados de forma
        # independiente contra el shape real de retorno de `ERPBridge`
        # (no se llegó a inspeccionar esa parte en esta fase) — se leen
        # de forma tolerante, con cadena vacía como default seguro en vez
        # de asumir un nombre de clave incorrecto.
        return QuoteRef(
            external_id=_str_or_empty(row.get("id", result)),
            folio=row.get("folio", "") or "",
            valid_until=row.get("vigencia_hasta", row.get("fecha_vigencia", "")) or "",
        )

    async def convert_to_order(self, quote_id: str, user: str = "whatsapp") -> OrderRef:
        result = self._bridge.convert_to_order(quote_id, user)
        row = result if isinstance(result, dict) else {"id": result}
        return OrderRef(
            external_id=_str_or_empty(row.get("id", result)),
            status=row.get("estado", "confirmada") or "confirmada",
            folio=row.get("folio", "") or "",
        )


class ErpBridgePaymentsApiClient:
    def __init__(self, bridge) -> None:
        self._bridge = bridge

    async def register_advance(self, *, order_id: str, amount: float, method: str = "mercadopago") -> str:
        result = self._bridge.register_advance(order_id, amount, method)
        return _str_or_empty(result)

    async def confirm_payment(
        self, *, order_id: str, amount: float, reference: str = "", method: str = "mercadopago"
    ) -> bool:
        return bool(self._bridge.confirm_payment(order_id, amount, reference, method))


class ErpBridgeDeliveryApiClient:
    def __init__(self, bridge) -> None:
        self._bridge = bridge

    async def schedule(
        self, *, order_id: str, address: str, delivery_date: str = "", customer_phone: str = ""
    ) -> bool:
        return bool(self._bridge.schedule(order_id, address, delivery_date, customer_phone))


class ErpBridgeStaffDirectoryApiClient:
    """WA-16 — envuelve `ERPBridge.get_staff_phones` (real, ya usado hoy
    por `middleware/handoff.py::HandoffService.escalar`)."""

    def __init__(self, bridge) -> None:
        self._bridge = bridge

    async def get_staff_phones(self, branch_id: str, *, role: str = "") -> List[str]:
        return list(self._bridge.get_staff_phones(branch_id, rol=role))
