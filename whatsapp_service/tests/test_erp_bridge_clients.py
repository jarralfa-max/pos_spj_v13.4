# tests/test_erp_bridge_clients.py — WA-9
"""Los adaptadores solo traducen forma (inglés<->español, Dict->Ref) — se
prueban con objetos falsos de `bridge`/`matcher` duck-typed, sin SQLite
real ni el `ERPBridge` real (eso ya lo prueba, si acaso, su propia suite
existente; WA-9 no la duplica)."""
from __future__ import annotations

import asyncio

from domain.whatsapp.erp_ports import CustomerRef, OrderRef, ProductRef, QuoteRef
from infrastructure.erp_clients.erp_bridge_clients import (
    ErpBridgeCustomersApiClient,
    ErpBridgeDeliveryApiClient,
    ErpBridgeOrdersApiClient,
    ErpBridgePaymentsApiClient,
    ErpBridgeQuotesApiClient,
    ProductMatcherCatalogApiClient,
)


class _FakeBridge:
    def __init__(self):
        self.calls = []

    def find_by_phone(self, phone):
        self.calls.append(("find_by_phone", phone))
        if phone == "unknown":
            return None
        return {"id": "cust-1", "nombre": "Juan", "telefono": phone}

    def create_minimal(self, nombre, telefono):
        self.calls.append(("create_minimal", nombre, telefono))
        return "cust-new-1"

    def create(self, **kwargs):
        self.calls.append(("create", kwargs))
        return {"id": "order-1", "estado": "pendiente_wa", "folio": "F-001"}

    def update_status(self, order_id, status, notes=""):
        self.calls.append(("update_status", order_id, status, notes))
        return True

    def get_by_folio(self, folio):
        self.calls.append(("get_by_folio", folio))
        if folio == "missing":
            return None
        return {"id": "order-9", "estado": "en_preparacion", "folio": folio}

    def convert_to_order(self, quote_id, user):
        self.calls.append(("convert_to_order", quote_id, user))
        return {"id": "order-from-quote", "estado": "confirmada", "folio": "F-002"}

    def register_advance(self, order_id, amount, method):
        self.calls.append(("register_advance", order_id, amount, method))
        return "advance-1"

    def confirm_payment(self, order_id, amount, reference, method):
        self.calls.append(("confirm_payment", order_id, amount, reference, method))
        return True

    def schedule(self, order_id, address, delivery_date, customer_phone):
        self.calls.append(("schedule", order_id, address, delivery_date, customer_phone))
        return True


class _FakeMatcher:
    def __init__(self):
        self._products = [
            {"id": "prod-1", "nombre": "Bistec de res", "precio": 180.0, "stock": 12.0, "unidad": "kg"},
        ]

    def search(self, query, max_results=5):
        return self._products[:max_results]

    def get_by_id(self, product_id):
        for p in self._products:
            if p["id"] == product_id:
                return p
        return None

    def get_categories(self):
        return ["Carnes", "Embutidos"]


def _run(coro):
    return asyncio.run(coro)


class TestErpBridgeCustomersApiClient:
    def test_find_by_phone_translates_to_customer_ref(self):
        bridge = _FakeBridge()
        client = ErpBridgeCustomersApiClient(bridge)
        result = _run(client.find_by_phone("5512345678"))
        assert result == CustomerRef(external_id="cust-1", name="Juan", phone="5512345678")

    def test_find_by_phone_returns_none_when_not_found(self):
        client = ErpBridgeCustomersApiClient(_FakeBridge())
        assert _run(client.find_by_phone("unknown")) is None

    def test_create_minimal_returns_customer_ref(self):
        bridge = _FakeBridge()
        client = ErpBridgeCustomersApiClient(bridge)
        result = _run(client.create_minimal(name="Ana", phone="5559998888"))
        assert result == CustomerRef(external_id="cust-new-1", name="Ana", phone="5559998888")
        assert bridge.calls == [("create_minimal", "Ana", "5559998888")]


class TestProductMatcherCatalogApiClient:
    def test_search_returns_product_refs(self):
        client = ProductMatcherCatalogApiClient(_FakeMatcher())
        results = _run(client.search("bistec"))
        assert results == [ProductRef(external_id="prod-1", name="Bistec de res", unit="kg", price=180.0, stock=12.0)]

    def test_get_by_id_found(self):
        client = ProductMatcherCatalogApiClient(_FakeMatcher())
        result = _run(client.get_by_id("prod-1"))
        assert result.name == "Bistec de res"

    def test_get_by_id_not_found(self):
        client = ProductMatcherCatalogApiClient(_FakeMatcher())
        assert _run(client.get_by_id("missing")) is None

    def test_get_categories(self):
        client = ProductMatcherCatalogApiClient(_FakeMatcher())
        assert _run(client.get_categories()) == ["Carnes", "Embutidos"]


class TestErpBridgeOrdersApiClient:
    def test_create_translates_customer_and_branch_to_spanish_kwargs(self):
        bridge = _FakeBridge()
        client = ErpBridgeOrdersApiClient(bridge)
        result = _run(client.create(items=[{"producto_id": "p1"}], customer_id="c1", branch_id="b1"))
        assert result == OrderRef(external_id="order-1", status="pendiente_wa", folio="F-001")
        assert bridge.calls[0] == ("create", {"items": [{"producto_id": "p1"}], "cliente_id": "c1", "sucursal_id": "b1"})

    def test_update_status(self):
        bridge = _FakeBridge()
        client = ErpBridgeOrdersApiClient(bridge)
        assert _run(client.update_status("order-1", "en_preparacion", "notas")) is True
        assert bridge.calls == [("update_status", "order-1", "en_preparacion", "notas")]

    def test_get_status_found(self):
        client = ErpBridgeOrdersApiClient(_FakeBridge())
        result = _run(client.get_status("F-001"))
        assert result.status == "en_preparacion"

    def test_get_status_not_found(self):
        client = ErpBridgeOrdersApiClient(_FakeBridge())
        assert _run(client.get_status("missing")) is None


class TestErpBridgeQuotesApiClient:
    def test_convert_to_order_returns_order_ref(self):
        bridge = _FakeBridge()
        client = ErpBridgeQuotesApiClient(bridge)
        result = _run(client.convert_to_order("quote-1", "whatsapp"))
        assert result == OrderRef(external_id="order-from-quote", status="confirmada", folio="F-002")


class TestErpBridgePaymentsApiClient:
    def test_register_advance_returns_reference_id(self):
        bridge = _FakeBridge()
        client = ErpBridgePaymentsApiClient(bridge)
        result = _run(client.register_advance(order_id="order-1", amount=90.0, method="mercadopago"))
        assert result == "advance-1"

    def test_confirm_payment(self):
        bridge = _FakeBridge()
        client = ErpBridgePaymentsApiClient(bridge)
        result = _run(client.confirm_payment(order_id="order-1", amount=90.0, reference="MP-1", method="mercadopago"))
        assert result is True


class TestErpBridgeDeliveryApiClient:
    def test_schedule(self):
        bridge = _FakeBridge()
        client = ErpBridgeDeliveryApiClient(bridge)
        result = _run(client.schedule(order_id="order-1", address="Calle 1", delivery_date="", customer_phone="555"))
        assert result is True
        assert bridge.calls == [("schedule", "order-1", "Calle 1", "", "555")]
