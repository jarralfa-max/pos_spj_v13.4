"""ORD-23 — OrdersDeliveryWhatsAppClient: thin adapter over the real legacy
`core.integrations.whatsapp_client.WhatsAppClient`. A fake stands in for the
underlying client so these tests never touch the real network."""

from __future__ import annotations

import pytest

from backend.infrastructure.integrations.orders_delivery_whatsapp_client import (
    OrdersDeliveryWhatsAppClient,
)


class _FakeLegacyClient:
    def __init__(self, *, ok: bool = True, raise_on: str | None = None) -> None:
        self.ok = ok
        self.raise_on = raise_on
        self.calls: list[tuple] = []

    def notificar_pedido_listo(self, phone, folio, sucursal=""):
        self.calls.append(("pedido_listo", phone, folio, sucursal))
        if self.raise_on == "pedido_listo":
            raise ConnectionError("microservicio no disponible")
        return self.ok

    def enviar_mensaje(self, phone, mensaje):
        self.calls.append(("enviar_mensaje", phone, mensaje))
        if self.raise_on == "enviar_mensaje":
            raise ConnectionError("microservicio no disponible")
        return self.ok


class TestNotifyReadyForPickup:
    def test_delegates_to_legacy_client(self):
        fake = _FakeLegacyClient(ok=True)
        client = OrdersDeliveryWhatsAppClient(fake)
        assert client.notify_ready_for_pickup(
            phone="+525512345678", order_number="P-1", branch_name="Centro") is True
        assert fake.calls == [("pedido_listo", "+525512345678", "P-1", "Centro")]

    def test_empty_phone_never_calls_legacy_client(self):
        fake = _FakeLegacyClient(ok=True)
        client = OrdersDeliveryWhatsAppClient(fake)
        assert client.notify_ready_for_pickup(phone="", order_number="P-1") is False
        assert fake.calls == []

    def test_swallows_legacy_client_exceptions(self):
        fake = _FakeLegacyClient(raise_on="pedido_listo")
        client = OrdersDeliveryWhatsAppClient(fake)
        assert client.notify_ready_for_pickup(phone="+525512345678", order_number="P-1") is False


class TestNotifyCustomerApprovalRequired:
    def test_delegates_to_legacy_client(self):
        fake = _FakeLegacyClient(ok=True)
        client = OrdersDeliveryWhatsAppClient(fake)
        assert client.notify_customer_approval_required(
            phone="+525512345678", order_number="P-1", reason="ajuste de peso") is True
        assert fake.calls[0][0] == "enviar_mensaje"
        assert "P-1" in fake.calls[0][2]
        assert "ajuste de peso" in fake.calls[0][2]

    def test_empty_phone_never_calls_legacy_client(self):
        fake = _FakeLegacyClient(ok=True)
        client = OrdersDeliveryWhatsAppClient(fake)
        assert client.notify_customer_approval_required(
            phone="   ", order_number="P-1", reason="motivo") is False
        assert fake.calls == []

    def test_swallows_legacy_client_exceptions(self):
        fake = _FakeLegacyClient(raise_on="enviar_mensaje")
        client = OrdersDeliveryWhatsAppClient(fake)
        assert client.notify_customer_approval_required(
            phone="+525512345678", order_number="P-1", reason="motivo") is False
