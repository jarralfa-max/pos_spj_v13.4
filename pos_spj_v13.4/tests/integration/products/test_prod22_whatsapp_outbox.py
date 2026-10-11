"""PROD-22 — cola de salida de alertas de Productos por WhatsApp (decisión: «cola
en el ERP»). Antes, sin conexión, la alerta se perdía."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from backend.application.products.notifications.whatsapp_outbox import (
    ProductWhatsAppOutboxQuery,
    RetryProductWhatsAppMessageUseCase,
)
from backend.domain.products.exceptions import ProductPermissionDeniedError
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.infrastructure.notifications.product_whatsapp_outbox_dispatcher import (
    BACKOFF_MINUTES,
    MAX_ATTEMPTS,
    ProductWhatsAppOutboxDispatcher,
)
from backend.infrastructure.notifications.whatsapp_product_notifier import (
    WhatsAppProductNotifier,
)

T0 = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


class _Client:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def enviar_mensaje(self, phone, message):
        self.calls.append(phone)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    create_products_schema(c)
    WhatsAppProductNotifier(c).send(channel="WHATSAPP", recipient_ref="5215512345678",
                                    message="Producto bloqueado por calidad",
                                    context={"alert_type": "QUALITY_BLOCKED", "entity_id": "p1"})
    c.execute("UPDATE product_whatsapp_outbox SET next_attempt_at=?",
              (T0.isoformat(timespec="seconds"),))
    c.commit()
    yield c
    c.close()


def _status(conn):
    return conn.execute("SELECT status, attempts, last_error FROM product_whatsapp_outbox"
                        ).fetchone()


def test_notifier_only_enqueues(conn):
    assert _status(conn)[:2] == ("PENDING", 0)


def test_delivered_message_is_marked_sent(conn):
    client = _Client([True])
    out = ProductWhatsAppOutboxDispatcher(conn, client=client, clock=_Clock()).run_once()
    assert out["sent"] == 1 and client.calls == ["5215512345678"]
    assert _status(conn)[0] == "SENT"
    # no se reenvía
    assert ProductWhatsAppOutboxDispatcher(conn, client=client, clock=_Clock()).run_once() \
        == {"sent": 0, "retry": 0, "failed": 0}


def test_offline_failure_is_retried_later_with_backoff(conn):
    clock = _Clock()
    client = _Client([ConnectionError("sin conexión"), True])
    dispatcher = ProductWhatsAppOutboxDispatcher(conn, client=client, clock=clock)
    assert dispatcher.run_once()["retry"] == 1
    status, attempts, error = _status(conn)
    assert (status, attempts) == ("PENDING", 1) and "sin conexión" in error
    assert dispatcher.run_once()["sent"] == 0          # aún no le toca
    clock.now = T0 + timedelta(minutes=BACKOFF_MINUTES[0])
    assert dispatcher.run_once()["sent"] == 1
    assert _status(conn)[0] == "SENT"


def test_after_max_attempts_it_fails_with_the_last_error(conn):
    clock = _Clock()
    client = _Client([False] * MAX_ATTEMPTS)
    dispatcher = ProductWhatsAppOutboxDispatcher(conn, client=client, clock=clock)
    for _ in range(MAX_ATTEMPTS):
        dispatcher.run_once()
        clock.now += timedelta(hours=5)
    status, attempts, error = _status(conn)
    assert (status, attempts) == ("FAILED", MAX_ATTEMPTS) and "no confirmó" in error


def test_failed_message_can_be_retried_by_hand_with_permission(conn):
    conn.execute("UPDATE product_whatsapp_outbox SET status='FAILED', attempts=8")
    message_id = ProductWhatsAppOutboxQuery(conn).recent()[0]["id"]
    ok, _ = RetryProductWhatsAppMessageUseCase(conn).execute(
        message_id=message_id, user_id="u1", operation_id="op")
    assert ok and _status(conn)[:2] == ("PENDING", 0)
    ok, message = RetryProductWhatsAppMessageUseCase(conn).execute(
        message_id=message_id, user_id="u1", operation_id="op2")
    assert not ok and "fallaron" in message


def test_retry_requires_the_whatsapp_permission(conn):
    from backend.application.products.authorization.policy import ProductsAuthorizationPolicy

    class _No:
        def has_permission(self, user_id, code):
            return False
    conn.execute("UPDATE product_whatsapp_outbox SET status='FAILED'")
    message_id = ProductWhatsAppOutboxQuery(conn).recent()[0]["id"]
    with pytest.raises(ProductPermissionDeniedError):
        RetryProductWhatsAppMessageUseCase(conn, ProductsAuthorizationPolicy(_No())).execute(
            message_id=message_id, user_id="u1", operation_id="op")


def test_queue_view_masks_the_phone(conn):
    assert ProductWhatsAppOutboxQuery(conn).recent()[0]["recipient"] == "•••• 5678"
