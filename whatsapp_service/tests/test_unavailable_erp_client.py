# tests/test_unavailable_erp_client.py — WA-9
from __future__ import annotations

import asyncio

import pytest

from infrastructure.erp_clients.unavailable_client import ErpClientUnavailableError, UnavailableErpClient


class TestUnavailableErpClient:
    def test_any_method_call_raises(self):
        client = UnavailableErpClient("CustomersApiClient")
        with pytest.raises(ErpClientUnavailableError):
            asyncio.run(client.find_by_phone("5512345678"))

    def test_error_message_includes_client_and_method_name(self):
        client = UnavailableErpClient("OrdersApiClient")
        with pytest.raises(ErpClientUnavailableError, match="OrdersApiClient.create"):
            asyncio.run(client.create(items=[], customer_id="c1", branch_id="b1"))

    def test_reason_included_when_provided(self):
        client = UnavailableErpClient("PaymentsApiClient", reason="sin esquema legacy")
        with pytest.raises(ErpClientUnavailableError, match="sin esquema legacy"):
            asyncio.run(client.register_advance(order_id="o1", amount=10.0))

    def test_arbitrary_method_names_all_raise(self):
        client = UnavailableErpClient("CatalogApiClient")
        with pytest.raises(ErpClientUnavailableError):
            asyncio.run(client.get_categories())
