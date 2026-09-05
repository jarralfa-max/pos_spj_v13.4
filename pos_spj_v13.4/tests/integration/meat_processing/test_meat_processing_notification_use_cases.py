"""PROC-20 e2e: requesting a WhatsApp/notification alert — Procesamiento
never sends one directly, only asks and records the reference."""

import importlib
import sqlite3

import pytest

from backend.application.meat_processing.use_cases import RequestProductionAlertUseCase
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    importlib.import_module(
        "migrations.standalone.187_meat_processing_bounded_context_schema").run(c)
    yield c
    c.close()


class FakeNotificationPort:
    def __init__(self):
        self.calls = []

    def send_alert(self, **kwargs):
        self.calls.append(kwargs)
        return new_uuid()


class TestRequestProductionAlert:
    def test_without_port_reports_pending_integration(self, conn):
        result = RequestProductionAlertUseCase().execute(
            conn, operation_id=new_uuid(), alert_type="YIELD_CRITICAL", severity="CRITICAL",
            message="Rendimiento fuera de tolerancia", branch_id=new_uuid(),
            actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "NOTIFICATION_INTEGRATION_PENDING"

    def test_with_fake_port_succeeds_and_is_audited(self, conn):
        port = FakeNotificationPort()
        result = RequestProductionAlertUseCase(notification_port=port).execute(
            conn, operation_id=new_uuid(), alert_type="EQUIPMENT_FAILURE", severity="WARNING",
            message="Sierra fuera de servicio", branch_id=new_uuid(), actor_user_id=new_uuid())
        assert result.success
        assert result.data["notification_reference"]
        assert len(port.calls) == 1
        with MeatProcessingUnitOfWork(conn) as uow:
            entries = uow.audit.list_for_entity("ProductionAlert", result.entity_id)
            assert any(e["action"] == "REQUESTED" for e in entries)
            pending = uow.outbox.list_pending()
            names = {row["event_name"] for row in pending}
            assert "PROCESSING_ALERT_REQUESTED" in names

    def test_is_idempotent_on_same_operation_id(self, conn):
        port = FakeNotificationPort()
        operation_id = new_uuid()
        first = RequestProductionAlertUseCase(notification_port=port).execute(
            conn, operation_id=operation_id, alert_type="INCIDENT_CRITICAL", severity="CRITICAL",
            message="Incidente critico", branch_id=new_uuid(), actor_user_id=new_uuid())
        second = RequestProductionAlertUseCase(notification_port=port).execute(
            conn, operation_id=operation_id, alert_type="INCIDENT_CRITICAL", severity="CRITICAL",
            message="Incidente critico", branch_id=new_uuid(), actor_user_id=new_uuid())
        assert first.success
        assert second.data["already_processed"] is True
        assert len(port.calls) == 1

    def test_rejects_unknown_severity(self, conn):
        port = FakeNotificationPort()
        result = RequestProductionAlertUseCase(notification_port=port).execute(
            conn, operation_id=new_uuid(), alert_type="OTHER", severity="URGENTE",
            message="x", branch_id=new_uuid(), actor_user_id=new_uuid())
        assert not result.success
        assert result.error_code == "INVALID_SEVERITY"
        assert port.calls == []
