"""ORD-25 — the driver PWA API, end-to-end against a real orders_delivery+
inventory SQLite schema and the real `OrdersDeliveryDriverWorkflow` (only
the login credential check is faked, same pattern
`tests/integration/logistics/test_mobile_api.py` already uses for
procurement's own mobile router — password verification itself is not this
router's concern)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.api.mobile_session import MobileIdentity, MobileSessionTokenService
from backend.application.orders_delivery.integrations.driver_pwa_workflow import (
    OrdersDeliveryDriverWorkflow,
)
from backend.application.orders_delivery.use_cases.cash_collection_use_cases import (
    CreateCashCollectionRequestUseCase,
)
from backend.application.orders_delivery.use_cases.delivery_job_use_cases import (
    CreateDeliveryJobUseCase,
)
from backend.application.orders_delivery.use_cases.driver_use_cases import (
    ProposeAssignmentUseCase,
    RegisterDriverProfileUseCase,
)
from backend.application.orders_delivery.use_cases.inventory_use_cases import (
    ReserveOrderInventoryUseCase,
)
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
from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from backend.shared.ids import new_uuid

ALL_DELIVERY_PERMISSIONS = (
    "DELIVERY.repartidor.asignar", "DELIVERY.repartidor.estado_gestionar",
    "DELIVERY.entrega.ver", "DELIVERY.despacho.ejecutar", "DELIVERY.llegada.confirmar",
    "DELIVERY.entrega.confirmar", "DELIVERY.cobro.registrar",
    "DELIVERY.pedido.crear", "DELIVERY.pedido.confirmar", "DELIVERY.entrega.crear",
)


class _Verifier:
    def __init__(self, driver_id: str, branch_id: str) -> None:
        self._driver_id = driver_id
        self._branch_id = branch_id

    def authenticate_mobile(self, username, password, device_id):
        if password != "secret":
            return None
        return MobileIdentity(
            self._driver_id, "Repartidor", self._branch_id, "Centro", self._branch_id,
            "Centro", device_id, ALL_DELIVERY_PERMISSIONS)


@pytest.fixture
def conn():
    # `check_same_thread=False` matches the REAL production connection
    # factory (`core/db/connection.py`) — FastAPI dispatches sync route
    # handlers to a worker thread pool, so a connection built in the test's
    # own thread must be usable from there too, exactly like production.
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    create_orders_delivery_schema(connection)
    create_inventory_schema(connection)
    yield connection
    connection.close()


def _allow_all() -> OrdersDeliveryAuthorizationPolicy:
    return OrdersDeliveryAuthorizationPolicy.permissive_for_tests()


def _seed_balance(conn, *, product_id: str, branch_id: str) -> None:
    conn.execute(
        "INSERT INTO inventory_balances (id, product_id, branch_id, warehouse_id,"
        " location_id, lot_id, serial_id, inventory_status, quantity, weight,"
        " reserved_quantity, reserved_weight, version, updated_at)"
        " VALUES (?,?,?,?,'','','','AVAILABLE','100','100','0','0',0,?)",
        (new_uuid(), product_id, branch_id, branch_id, "t"))


def _proposed_assignment(conn, *, branch_id: str, driver_id: str) -> tuple[str, str]:
    """Returns (delivery_job_id, assignment_id) for a HOME_DELIVERY order
    with a driver assignment still PROPOSED (awaiting the driver's PWA
    response)."""
    product_id = new_uuid()
    _seed_balance(conn, product_id=product_id, branch_id=branch_id)
    order_result = CreateCustomerOrderUseCase(_allow_all()).execute(
        conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
        fulfillment_type="HOME_DELIVERY", contact_phone="+525512345678",
        lines=[{"product_id": product_id, "unit_price": "10.00", "requested_quantity": "1"}],
        actor_user_id=new_uuid(), operation_id=new_uuid())
    order_id = order_result.entity_id
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
        operation_id=new_uuid(), cash_to_collect=Decimal("10.00"),
        payment_method_expected="CASH")
    job_id = job_result.entity_id
    RegisterDriverProfileUseCase(_allow_all()).execute(
        conn, driver_id=driver_id, branch_id=branch_id, actor_user_id=new_uuid(),
        operation_id=new_uuid())
    assignment_result = ProposeAssignmentUseCase(_allow_all()).execute(
        conn, delivery_job_id=job_id, driver_id=driver_id, actor_user_id=new_uuid(),
        operation_id=new_uuid())
    return job_id, assignment_result.entity_id


def _client(conn):
    app = create_app()
    driver_id, branch_id = new_uuid(), new_uuid()
    app.state.mobile_session_service = MobileSessionTokenService(b"d" * 32, _Verifier(driver_id, branch_id))
    app.state.driver_pwa_workflow = OrdersDeliveryDriverWorkflow(connection_factory=lambda: conn)
    return TestClient(app), driver_id, branch_id


def _login(api) -> dict:
    response = api.post("/api/mobile/session",
                        json={"username": "driver1", "password": "secret", "deviceId": "phone-1"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}


def _command(headers, operation_id, **extra):
    import base64, json
    token = headers["Authorization"].split(" ", 1)[1]
    payload = token.split(".", 1)[0]
    payload += "=" * (-len(payload) % 4)
    identity = json.loads(base64.urlsafe_b64decode(payload))
    return {"clientOperationId": operation_id, "deviceId": identity["device_id"],
            "userId": identity["user_id"], "createdAt": "2026-08-31T00:00:00Z",
            "payloadVersion": 1, **extra}


class TestDriverPwaJobsAndAssignments:
    def test_requires_authentication(self, conn):
        api, _, _ = _client(conn)
        assert api.get("/api/delivery/mobile/jobs").status_code == 401

    def test_serves_the_driver_pwa_shell(self, conn):
        api, _, _ = _client(conn)
        page = api.get("/mobile/delivery/")
        assert page.status_code == 200 and "Repartidor" in page.text

    def test_lists_pending_assignment_and_job(self, conn):
        api, driver_id, branch_id = _client(conn)
        job_id, assignment_id = _proposed_assignment(conn, branch_id=branch_id, driver_id=driver_id)
        headers = _login(api)

        pending = api.get("/api/delivery/mobile/assignments/pending", headers=headers)
        assert pending.status_code == 200
        assert pending.json()["assignments"][0]["assignmentId"] == assignment_id

        jobs = api.get("/api/delivery/mobile/jobs", headers=headers)
        assert jobs.status_code == 200
        assert jobs.json()["jobs"] == []  # not yet assigned/accepted

    def test_accept_assignment_then_job_appears(self, conn):
        api, driver_id, branch_id = _client(conn)
        job_id, assignment_id = _proposed_assignment(conn, branch_id=branch_id, driver_id=driver_id)
        headers = _login(api)
        operation_id = new_uuid()

        response = api.post(
            f"/api/delivery/mobile/assignments/{assignment_id}/accept",
            json=_command(headers, operation_id), headers={**headers, "Idempotency-Key": operation_id})

        assert response.status_code == 200
        assert response.json()["status"] == "ACCEPTED"
        jobs = api.get("/api/delivery/mobile/jobs", headers=headers).json()["jobs"]
        assert jobs[0]["deliveryJobId"] == job_id
        assert jobs[0]["contactPhone"] == "+525512345678"

    def test_reject_assignment(self, conn):
        api, driver_id, branch_id = _client(conn)
        _, assignment_id = _proposed_assignment(conn, branch_id=branch_id, driver_id=driver_id)
        headers = _login(api)
        operation_id = new_uuid()

        response = api.post(
            f"/api/delivery/mobile/assignments/{assignment_id}/reject",
            json=_command(headers, operation_id), headers={**headers, "Idempotency-Key": operation_id})

        assert response.status_code == 200
        assert response.json()["status"] == "REJECTED"

    def test_accepting_unknown_assignment_returns_404(self, conn):
        api, _, _ = _client(conn)
        headers = _login(api)
        operation_id = new_uuid()
        response = api.post(
            f"/api/delivery/mobile/assignments/{new_uuid()}/accept",
            json=_command(headers, operation_id), headers={**headers, "Idempotency-Key": operation_id})
        assert response.status_code == 404

    def test_idempotency_key_must_be_uuidv7(self, conn):
        api, driver_id, branch_id = _client(conn)
        _, assignment_id = _proposed_assignment(conn, branch_id=branch_id, driver_id=driver_id)
        headers = _login(api)
        response = api.post(
            f"/api/delivery/mobile/assignments/{assignment_id}/accept",
            json=_command(headers, "not-a-uuid"), headers={**headers, "Idempotency-Key": "not-a-uuid"})
        assert response.status_code == 422


class TestDriverPwaDeliveryLifecycle:
    def _accepted_job(self, conn, api, headers, driver_id, branch_id):
        job_id, assignment_id = _proposed_assignment(conn, branch_id=branch_id, driver_id=driver_id)
        op = new_uuid()
        api.post(f"/api/delivery/mobile/assignments/{assignment_id}/accept",
                json=_command(headers, op), headers={**headers, "Idempotency-Key": op})
        return job_id

    def test_full_dispatch_to_delivery_pipeline(self, conn):
        api, driver_id, branch_id = _client(conn)
        headers = _login(api)
        job_id = self._accepted_job(conn, api, headers, driver_id, branch_id)

        op0 = new_uuid()
        dispatch = api.post(f"/api/delivery/mobile/jobs/{job_id}/dispatch",
                            json=_command(headers, op0), headers={**headers, "Idempotency-Key": op0})
        assert dispatch.status_code == 200 and dispatch.json()["status"] == "DISPATCHED"

        op1 = new_uuid()
        depart = api.post(f"/api/delivery/mobile/jobs/{job_id}/depart",
                          json=_command(headers, op1), headers={**headers, "Idempotency-Key": op1})
        assert depart.status_code == 200 and depart.json()["status"] == "IN_TRANSIT"

        op2 = new_uuid()
        arrive = api.post(f"/api/delivery/mobile/jobs/{job_id}/arrive",
                          json=_command(headers, op2), headers={**headers, "Idempotency-Key": op2})
        assert arrive.status_code == 200 and arrive.json()["status"] == "ARRIVED"

        op3 = new_uuid()
        attempt = api.post(
            f"/api/delivery/mobile/jobs/{job_id}/attempts",
            json=_command(headers, op3, successful=True, recipientName="Juan Pérez",
                         signatureReference="sig-1", photoReference=None, pinVerified=False,
                         latitude=19.4, longitude=-99.1, notes=None, failureReason=None),
            headers={**headers, "Idempotency-Key": op3})
        assert attempt.status_code == 200
        assert attempt.json()["successful"] is True

    def test_cash_collection_record(self, conn):
        api, driver_id, branch_id = _client(conn)
        headers = _login(api)
        job_id = self._accepted_job(conn, api, headers, driver_id, branch_id)
        collection_result = CreateCashCollectionRequestUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, payment_method="CASH", actor_user_id=new_uuid(),
            operation_id=new_uuid())
        collection_id = collection_result.entity_id

        op = new_uuid()
        response = api.post(
            f"/api/delivery/mobile/cash-collections/{collection_id}/record",
            json=_command(headers, op, collectedAmount="10.00", reference=None),
            headers={**headers, "Idempotency-Key": op})

        assert response.status_code == 200
        assert response.json()["collectionId"] == collection_id
