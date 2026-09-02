"""ORD-26 — the customer WhatsApp notification (dispatched/completed/failed)
and internal staff alert (failed delivery) wired into
`DispatchDeliveryJobUseCase`/`RecordDeliveryAttemptUseCase`, end-to-end
through the full real pipeline. `test_orders_delivery_dispatch_use_cases.py`
(ORD-18) already covers the domain-state assertions for these use cases with
a no-op WhatsApp stub — this file is specifically about the notification
side effects those tests deliberately silence."""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.orders_delivery.use_cases.delivery_job_use_cases import (
    CreateDeliveryJobUseCase,
)
from backend.application.orders_delivery.use_cases.dispatch_use_cases import (
    ConfirmArrivalUseCase,
    DispatchDeliveryJobUseCase,
    MarkInTransitUseCase,
    RecordDeliveryAttemptUseCase,
)
from backend.application.orders_delivery.use_cases.driver_use_cases import (
    AcceptAssignmentUseCase,
    ProposeAssignmentUseCase,
    RegisterDriverProfileUseCase,
)
from backend.application.orders_delivery.use_cases.inventory_use_cases import (
    ReserveOrderInventoryUseCase,
)
from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    ConfirmCustomerOrderUseCase,
    CreateCustomerOrderUseCase,
)
from backend.application.orders_delivery.use_cases.preparation_use_cases import (
    AssignPreparationUseCase,
    CompletePreparationUseCase,
    RecordPreparedLineUseCase,
    StartPreparationUseCase,
)
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


class _FakeWhatsAppClient:
    def __init__(self, *, deliver: bool = True) -> None:
        self.deliver = deliver
        self.sent: list[dict] = []

    def send_message(self, *, phone: str, message: str) -> bool:
        self.sent.append({"phone": phone, "message": message})
        return self.deliver and bool(phone)


def _allow_all() -> OrdersDeliveryAuthorizationPolicy:
    return OrdersDeliveryAuthorizationPolicy.permissive_for_tests()


def _seed_balance(conn, *, product_id: str, branch_id: str) -> None:
    conn.execute(
        "INSERT INTO inventory_balances (id, product_id, branch_id, warehouse_id,"
        " location_id, lot_id, serial_id, inventory_status, quantity, weight,"
        " reserved_quantity, reserved_weight, version, updated_at)"
        " VALUES (?,?,?,?,'','','','AVAILABLE','100','100','0','0',0,?)",
        (new_uuid(), product_id, branch_id, branch_id, "t"))


def _dispatch_ready_job(conn, *, branch_id: str) -> tuple[str, str]:
    product_id, driver_id = new_uuid(), new_uuid()
    _seed_balance(conn, product_id=product_id, branch_id=branch_id)
    result = CreateCustomerOrderUseCase(_allow_all()).execute(
        conn, branch_id=branch_id, channel="WHATSAPP", order_type="STANDARD",
        fulfillment_type="HOME_DELIVERY", contact_phone="+525512345678",
        lines=[{"product_id": product_id, "unit_price": "10.00", "requested_quantity": "1"}],
        actor_user_id=new_uuid(), operation_id=new_uuid())
    order_id = result.entity_id
    ConfirmCustomerOrderUseCase(_allow_all()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    ReserveOrderInventoryUseCase(_allow_all()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    AssignPreparationUseCase(_allow_all()).execute(
        conn, order_id=order_id, assigned_to_user_id=new_uuid(),
        actor_user_id=new_uuid(), operation_id=new_uuid())
    StartPreparationUseCase(_allow_all()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    line_id = CustomerOrderRepository(conn).get(order_id).lines[0].id
    RecordPreparedLineUseCase(_allow_all()).execute(
        conn, order_id=order_id, line_id=line_id, quantity="1",
        actor_user_id=new_uuid(), operation_id=new_uuid())
    CompletePreparationUseCase(_allow_all()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    job_result = CreateDeliveryJobUseCase(_allow_all()).execute(
        conn, order_id=order_id, branch_id=branch_id, actor_user_id=new_uuid(),
        operation_id=new_uuid())
    job_id = job_result.entity_id
    RegisterDriverProfileUseCase(_allow_all()).execute(
        conn, driver_id=driver_id, branch_id=branch_id, actor_user_id=new_uuid(),
        operation_id=new_uuid())
    propose = ProposeAssignmentUseCase(_allow_all()).execute(
        conn, delivery_job_id=job_id, driver_id=driver_id, actor_user_id=new_uuid(),
        operation_id=new_uuid())
    AcceptAssignmentUseCase(_allow_all()).execute(
        conn, assignment_id=propose.entity_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    return job_id, order_id


class TestDispatchNotifiesCustomer:
    @pytest.fixture
    def conn(self):
        connection = sqlite3.connect(":memory:")
        create_orders_delivery_schema(connection)
        create_inventory_schema(connection)
        yield connection
        connection.close()

    def test_dispatch_sends_customer_message(self, conn):
        branch_id = new_uuid()
        job_id, _ = _dispatch_ready_job(conn, branch_id=branch_id)
        fake = _FakeWhatsAppClient()

        result = DispatchDeliveryJobUseCase(_allow_all(), whatsapp_client=fake).execute(
            conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())

        assert result.success
        assert result.data["notification_sent"] is True
        assert fake.sent[0]["phone"] == "+525512345678"
        assert "camino" in fake.sent[0]["message"]


class TestFailedDeliveryNotifiesCustomerAndStaff:
    @pytest.fixture
    def conn(self):
        # Full canonical schema (usuarios/roles/notification_inbox) layered
        # with orders_delivery/inventory — needed to exercise the REAL
        # internal-alert write, not just its safe no-op path.
        connection = make_db()
        create_orders_delivery_schema(connection)
        create_inventory_schema(connection)
        yield connection
        connection.close()

    def _seed_admin(self, conn, *, branch_id: str) -> str:
        user_id = new_uuid()
        role_id = conn.execute(
            "SELECT id FROM roles WHERE LOWER(nombre)='admin'").fetchone()[0]
        conn.execute(
            "INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id, activo)"
            " VALUES (?,?,?,?,?,?,1)",
            (user_id, "Admin", f"admin-{user_id[:8]}", "hash", "admin", branch_id))
        conn.execute(
            "INSERT INTO usuarios_roles (usuario_id, rol_id, sucursal_id) VALUES (?, ?, ?)",
            (user_id, role_id, branch_id))
        conn.commit()
        return user_id

    def _dispatched_job(self, conn, *, branch_id: str) -> tuple[str, str]:
        job_id, order_id = _dispatch_ready_job(conn, branch_id=branch_id)
        DispatchDeliveryJobUseCase(_allow_all(), whatsapp_client=_FakeWhatsAppClient()).execute(
            conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        MarkInTransitUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        ConfirmArrivalUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        return job_id, order_id

    def test_failed_attempt_notifies_customer_and_alerts_admin(self, conn):
        branch_id = new_uuid()
        admin_id = self._seed_admin(conn, branch_id=branch_id)
        job_id, order_id = self._dispatched_job(conn, branch_id=branch_id)
        fake = _FakeWhatsAppClient()

        result = RecordDeliveryAttemptUseCase(_allow_all(), whatsapp_client=fake).execute(
            conn, delivery_job_id=job_id, successful=False, actor_user_id=new_uuid(),
            operation_id=new_uuid(), failure_reason="CUSTOMER_NOT_HOME")

        assert result.success
        assert result.data["notification_sent"] is True
        assert "No pudimos" in fake.sent[0]["message"]
        alert = conn.execute(
            "SELECT empleado_id, tipo FROM notification_inbox WHERE empleado_id=?",
            (admin_id,)).fetchone()
        assert alert is not None
        assert alert[1] == "entrega_fallida"

    def test_successful_attempt_notifies_customer_without_internal_alert(self, conn):
        branch_id = new_uuid()
        self._seed_admin(conn, branch_id=branch_id)
        job_id, order_id = self._dispatched_job(conn, branch_id=branch_id)
        fake = _FakeWhatsAppClient()

        result = RecordDeliveryAttemptUseCase(_allow_all(), whatsapp_client=fake).execute(
            conn, delivery_job_id=job_id, successful=True, actor_user_id=new_uuid(),
            operation_id=new_uuid(), recipient_name="Juan Pérez", signature_reference="sig-1")

        assert result.success
        assert result.data["notification_sent"] is True
        assert "entregado" in fake.sent[0]["message"]
        assert conn.execute("SELECT COUNT(*) FROM notification_inbox").fetchone()[0] == 0
