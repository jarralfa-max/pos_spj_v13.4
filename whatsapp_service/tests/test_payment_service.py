# tests/test_payment_service.py — WA-12
"""`PaymentService` — Link/Status/Confirmation/Duplicate webhook, contra
un `idempotency` repository SQLite real (WA-10) y clientes ERP/proveedor
falsos (el contrato de WA-9/WA-12, no su implementación real)."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from application.payment_service import PaymentService
from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from domain.whatsapp.enums import IdempotencyStatus
from domain.whatsapp.erp_ports import OrderRef
from domain.whatsapp.payment_provider_ports import PaymentLinkRef
from infrastructure.persistence.sqlite_idempotency_repository import SqliteWhatsAppIdempotencyRepository


class _FakePaymentProvider:
    def __init__(self):
        self.calls = []

    async def create_preference(self, *, amount, external_reference, description=""):
        self.calls.append((amount, external_reference, description))
        return PaymentLinkRef(checkout_url="https://mp.example/checkout/1", preference_id="pref-1")


class _FakeOrders:
    def __init__(self, status_row=None):
        self._status_row = status_row or OrderRef(external_id="order-1", status="pendiente_wa", folio="F-001")

    async def get_status(self, folio):
        return self._status_row


class _FakePayments:
    def __init__(self, *, confirm_result=True, register_result="advance-1", should_raise=False):
        self.confirm_calls = []
        self.register_calls = []
        self._confirm_result = confirm_result
        self._register_result = register_result
        self._should_raise = should_raise

    async def register_advance(self, *, order_id, amount, method="mercadopago"):
        self.register_calls.append((order_id, amount, method))
        return self._register_result

    async def confirm_payment(self, *, order_id, amount, reference, method="mercadopago"):
        self.confirm_calls.append((order_id, amount, reference, method))
        if self._should_raise:
            raise RuntimeError("ERP no disponible")
        return self._confirm_result


class _FakeRoot:
    def __init__(self, conn, *, provider=None, orders=None, payments=None):
        self.idempotency = SqliteWhatsAppIdempotencyRepository(conn)
        self.payment_provider = provider or _FakePaymentProvider()
        self.orders = orders or _FakeOrders()
        self.payments = payments or _FakePayments()


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


def _run(coro):
    return asyncio.run(coro)


class TestCreatePaymentLink:
    def test_builds_external_reference_from_order_and_phone(self, conn):
        provider = _FakePaymentProvider()
        service = PaymentService(_FakeRoot(conn, provider=provider))
        result = _run(service.create_payment_link(order_external_id="order-1", amount=180.0, customer_phone="5551234567"))
        assert result.checkout_url == "https://mp.example/checkout/1"
        assert provider.calls[0][1] == "order-1:5551234567"


class TestPaymentStatus:
    def test_reuses_order_status_not_a_separate_concept(self, conn):
        orders = _FakeOrders(status_row=OrderRef(external_id="order-1", status="confirmada", folio="F-001"))
        service = PaymentService(_FakeRoot(conn, orders=orders))
        result = _run(service.get_order_payment_status("F-001"))
        assert result.status == "confirmada"


class TestRegisterAdvance:
    def test_delegates_to_payments_client(self, conn):
        payments = _FakePayments(register_result="advance-9")
        service = PaymentService(_FakeRoot(conn, payments=payments))
        result = _run(service.register_advance(order_external_id="order-1", amount=90.0))
        assert result == "advance-9"
        assert payments.register_calls == [("order-1", 90.0, "mercadopago")]


class TestConfirmPaymentAndDuplicateWebhook:
    def test_confirm_payment_succeeds(self, conn):
        payments = _FakePayments(confirm_result=True)
        service = PaymentService(_FakeRoot(conn, payments=payments))
        result = _run(service.confirm_payment(order_external_id="order-1", amount=90.0, payment_reference="MP-123"))
        assert result.confirmed is True
        assert result.deduplicated is False
        assert len(payments.confirm_calls) == 1

    def test_duplicate_webhook_delivery_does_not_confirm_twice(self, conn):
        """El caso real de WA-12: MercadoPago reintenta el mismo evento de
        webhook (red, timeout de nuestra respuesta, etc.) — la segunda
        entrega NO debe volver a llamar a `PaymentsApiClient.confirm_payment()`."""
        payments = _FakePayments(confirm_result=True)
        root = _FakeRoot(conn, payments=payments)
        service = PaymentService(root)

        first = _run(service.confirm_payment(order_external_id="order-1", amount=90.0, payment_reference="MP-123"))
        second = _run(service.confirm_payment(order_external_id="order-1", amount=90.0, payment_reference="MP-123"))

        assert first.deduplicated is False
        assert second.deduplicated is True
        assert len(payments.confirm_calls) == 1  # nunca se llamó una segunda vez

    def test_different_payment_reference_is_not_deduplicated(self, conn):
        payments = _FakePayments(confirm_result=True)
        service = PaymentService(_FakeRoot(conn, payments=payments))

        _run(service.confirm_payment(order_external_id="order-1", amount=90.0, payment_reference="MP-123"))
        result = _run(service.confirm_payment(order_external_id="order-1", amount=90.0, payment_reference="MP-456"))

        assert result.deduplicated is False
        assert len(payments.confirm_calls) == 2

    def test_failed_confirmation_marks_idempotency_failed_and_allows_retry(self, conn):
        payments = _FakePayments(should_raise=True)
        root = _FakeRoot(conn, payments=payments)
        service = PaymentService(root)

        with pytest.raises(RuntimeError):
            _run(service.confirm_payment(order_external_id="order-1", amount=90.0, payment_reference="MP-123"))

        from application.idempotency_fingerprint import compute_fingerprint

        record = root.idempotency.get_by_fingerprint(
            compute_fingerprint("CONFIRM_PAYMENT", "order-1", "MP-123")
        )
        assert record.status == IdempotencyStatus.FAILED

    def test_erp_returning_false_also_marks_failed_not_deduplicated_later(self, conn):
        """Si el ERP dice explícitamente "no confirmado" (sin excepción),
        el registro de idempotencia queda FAILED — un reintento posterior
        con la MISMA referencia no debe reportarse como deduplicado exitoso."""
        payments = _FakePayments(confirm_result=False)
        service = PaymentService(_FakeRoot(conn, payments=payments))

        first = _run(service.confirm_payment(order_external_id="order-1", amount=90.0, payment_reference="MP-999"))
        assert first.confirmed is False
        assert first.deduplicated is False
