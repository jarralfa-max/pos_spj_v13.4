"""PROC-23 — ProcessingOrderPresenter over the real backend (offscreen Qt
not required here: the presenter itself has no PyQt dependency)."""

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.meat_processing.authorization import (
    AllowAllMeatProcessingPermissionCheckerForTests,
    MeatProcessingAuthorizationPolicy,
)
from backend.application.meat_processing.queries import ProcessingOrderQueryService
from backend.application.meat_processing.use_cases import (
    ApproveProcessingOrderUseCase,
    CloseProcessingOrderUseCase,
    CreateProcessingOrderUseCase,
    ReleaseProcessingOrderUseCase,
)
from backend.shared.ids import new_uuid
from frontend.desktop.modules.meat_processing.presenters import ProcessingOrderPresenter


class _Session:
    def __init__(self, *, user_id, branch_id, warehouse_id):
        self.user_id = user_id
        self.active_branch_id = branch_id
        self.warehouse_id = warehouse_id


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    importlib.import_module(
        "migrations.standalone.187_meat_processing_bounded_context_schema").run(c)
    yield c
    c.close()


def _presenter(conn, *, session=None, wired=True):
    authorization = MeatProcessingAuthorizationPolicy(
        AllowAllMeatProcessingPermissionCheckerForTests())
    kwargs = dict(
        connection_provider=lambda: conn,
        query_factory=ProcessingOrderQueryService,
        session_context=session or _Session(
            user_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid()))
    if wired:
        kwargs.update(
            create_uc=CreateProcessingOrderUseCase(authorization),
            approve_uc=ApproveProcessingOrderUseCase(authorization),
            release_uc=ReleaseProcessingOrderUseCase(authorization),
            close_uc=CloseProcessingOrderUseCase(authorization))
    return ProcessingOrderPresenter(**kwargs)


class TestOrdersQuery:
    def test_empty_without_branch(self, conn):
        pres = ProcessingOrderPresenter(
            connection_provider=lambda: conn, query_factory=ProcessingOrderQueryService)
        assert pres.orders().total == 0

    def test_lists_created_order(self, conn):
        pres = _presenter(conn)
        pres.create_order(
            process_type="CUTTING", target_product_id=new_uuid(),
            planned_quantity=Decimal("10"), planned_weight=Decimal("10"))
        vm = pres.orders()
        assert vm.total == 1
        assert vm.rows[0][0] == "Corte"
        assert vm.rows[0][1] == "Por aprobar"


class TestCreateOrder:
    def test_creates_and_submits_for_approval(self, conn):
        pres = _presenter(conn)
        ok, message, data = pres.create_order(
            process_type="CUTTING", target_product_id=new_uuid(),
            planned_quantity=Decimal("10"), planned_weight=Decimal("10"))
        assert ok, message
        assert data.get("entity_id")
        assert data["status"] == "PENDING_APPROVAL"

    def test_without_product_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.create_order(
            process_type="CUTTING", target_product_id="",
            planned_quantity=Decimal("10"), planned_weight=Decimal("10"))
        assert not ok
        assert "Selecciona" in message

    def test_invalid_process_type_fails(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.create_order(
            process_type="NOT_A_TYPE", target_product_id=new_uuid(),
            planned_quantity=Decimal("10"), planned_weight=Decimal("10"))
        assert not ok
        assert "proceso" in message.lower()

    def test_without_quantity_or_weight_fails(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.create_order(
            process_type="CUTTING", target_product_id=new_uuid(),
            planned_quantity=0, planned_weight=0)
        assert not ok
        assert "cantidad" in message.lower() or "peso" in message.lower()

    def test_unavailable_when_not_wired(self, conn):
        pres = _presenter(conn, wired=False)
        ok, message, _ = pres.create_order(
            process_type="CUTTING", target_product_id=new_uuid(),
            planned_quantity=Decimal("10"), planned_weight=Decimal("10"))
        assert not ok
        assert "no disponible" in message


class TestOrderTransitions:
    def _created_order_id(self, conn, *, creator_session):
        pres = _presenter(conn, session=creator_session)
        ok, _msg, data = pres.create_order(
            process_type="CUTTING", target_product_id=new_uuid(),
            planned_quantity=Decimal("10"), planned_weight=Decimal("10"))
        assert ok
        return data["entity_id"]

    def test_approve_requires_independent_actor(self, conn):
        branch, warehouse = new_uuid(), new_uuid()
        creator = _Session(user_id=new_uuid(), branch_id=branch, warehouse_id=warehouse)
        approver = _Session(user_id=new_uuid(), branch_id=branch, warehouse_id=warehouse)
        order_id = self._created_order_id(conn, creator_session=creator)
        pres = _presenter(conn, session=approver)
        ok, message, _ = pres.approve_order(order_id=order_id)
        assert ok, message

    def test_approve_same_actor_as_creator_is_denied(self, conn):
        session = _Session(user_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid())
        order_id = self._created_order_id(conn, creator_session=session)
        pres = _presenter(conn, session=session)
        ok, message, _ = pres.approve_order(order_id=order_id)
        assert not ok
        assert "aprobarla" in message.lower() or "segregac" in message.lower()

    def test_approve_without_selection_does_not_call_backend(self, conn):
        pres = _presenter(conn)
        ok, message, _ = pres.approve_order(order_id="")
        assert not ok
        assert "Selecciona" in message

    def test_release_before_approval_fails(self, conn):
        session = _Session(user_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid())
        order_id = self._created_order_id(conn, creator_session=session)
        pres = _presenter(conn, session=session)
        ok, message, _ = pres.release_order(order_id=order_id)
        assert not ok

    def test_close_before_completion_fails(self, conn):
        session = _Session(user_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid())
        order_id = self._created_order_id(conn, creator_session=session)
        pres = _presenter(conn, session=session)
        ok, message, _ = pres.close_order(order_id=order_id)
        assert not ok
        assert "completada" in message.lower()

    def test_transitions_unavailable_when_not_wired(self, conn):
        pres = _presenter(conn, wired=False)
        for method in (pres.approve_order, pres.release_order, pres.close_order):
            ok, message, _ = method(order_id="anything")
            assert not ok
            assert "no disponible" in message
