# tests/test_sqlite_delivery_request_repository.py — WA-13
from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from domain.whatsapp.entities.delivery_request import DeliveryRequest
from domain.whatsapp.enums import DeliveryRequestStatus
from infrastructure.persistence.sqlite_delivery_request_repository import (
    SqliteWhatsAppDeliveryRequestRepository,
)


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


@pytest.fixture()
def repo(conn):
    return SqliteWhatsAppDeliveryRequestRepository(conn)


class TestRoundTrip:
    def test_save_and_get_by_id(self, repo):
        request = DeliveryRequest.start(
            conversation_id="conv-1", order_external_id="order-1", address="Calle 1 #23",
            delivery_date="2026-09-05", customer_phone="+525512345678",
        )
        repo.save(request)

        fetched = repo.get_by_id(request.id)
        assert fetched is not None
        assert fetched.order_external_id == "order-1"
        assert fetched.address == "Calle 1 #23"
        assert fetched.delivery_date == "2026-09-05"
        assert fetched.customer_phone == "+525512345678"
        assert fetched.status == DeliveryRequestStatus.REQUESTED

    def test_get_by_id_missing_returns_none(self, repo):
        assert repo.get_by_id("does-not-exist") is None

    def test_update_persists_status_transition(self, repo):
        request = DeliveryRequest.start(
            conversation_id="conv-1", order_external_id="order-1", address="Calle 1 #23",
        )
        repo.save(request)
        request.mark_scheduled()
        repo.save(request)

        fetched = repo.get_by_id(request.id)
        assert fetched.status == DeliveryRequestStatus.SCHEDULED

    def test_get_by_order_external_id_returns_most_recent(self, repo):
        older = DeliveryRequest.start(
            conversation_id="conv-1", order_external_id="order-1", address="Dirección vieja",
        )
        repo.save(older)
        newer = DeliveryRequest.start(
            conversation_id="conv-1", order_external_id="order-1", address="Dirección nueva",
        )
        repo.save(newer)

        fetched = repo.get_by_order_external_id("order-1")
        assert fetched.id == newer.id

    def test_get_by_order_external_id_missing_returns_none(self, repo):
        assert repo.get_by_order_external_id("does-not-exist") is None
