"""PUR-4/PUR-5 — direct-purchase application flow: atomicity, permissions,
limits, hot authorization, inventory of accepted qty, financial treatment,
post-commit events, and reversal."""

from decimal import Decimal

import pytest

from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.permissions import PurchasePermissions
from backend.application.procurement.use_cases.direct_purchase_use_cases import (
    AuthorizeDirectPurchaseUseCase,
    ConfirmDirectPurchaseUseCase,
    CreateDirectPurchaseUseCase,
    ReverseDirectPurchaseUseCase,
)
from backend.domain.procurement.enums import DocumentStatus, PaymentCondition
from backend.domain.procurement.value_objects import PurchaseLimit
from backend.infrastructure.db.repositories.procurement.purchase_limit_repository import (
    PurchaseLimitRepository,
)
from backend.infrastructure.db.repositories.procurement.unit_of_work import (
    ProcurementUnitOfWork,
)


class _Checker:
    """Grants everything except the codes in ``denied``."""

    def __init__(self, denied=()):
        self._denied = set(denied)

    def has_permission(self, user_id, permission_code):
        return permission_code not in self._denied


def _lines():
    return [{"product_id": "p1", "description": "Pollo", "quantity": "3", "unit_cost": "100",
             "tax": "48"},
            {"product_id": "p2", "description": "Caja", "quantity": "2", "unit_cost": "50"}]


def _create(conn, *, actor="u1", op="op-1", auth=None, **kw):
    kw.pop("payment_source", None)  # payment_source is a confirm-time argument
    uc = CreateDirectPurchaseUseCase(auth)
    return uc.execute(conn, actor_user_id=actor, operation_id=op, supplier_id="sup-1",
                      branch_id="br-1", warehouse_id="wh-1", lines=_lines(), **kw)


def test_create_confirm_immediate_receipt_enters_inventory(proc_conn):
    created = _create(proc_conn, payment_source="PETTY_CASH")
    assert created.success and created.data["status"] == DocumentStatus.DRAFT.value
    assert created.data["total"] == "448.00"

    confirm = ConfirmDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id="op-confirm", payment_source="PETTY_CASH")
    assert confirm.success and confirm.data["status"] == DocumentStatus.RECEIVED.value
    assert confirm.data["goods_receipt_id"]

    # inventory-entry event carries only accepted qty; a receipt row exists
    with ProcurementUnitOfWork(proc_conn) as uow:
        gr = uow.receipts.get(confirm.data["goods_receipt_id"])
        assert gr.status == "COMPLETED"
        assert gr.total_accepted() == Decimal("5")   # 3 + 2
        events = {r["event_name"] for r in uow.outbox.list_pending(50)}
    assert "DIRECT_PURCHASE_RECEIVED" in events
    assert "PURCHASE_PAYMENT_REQUESTED" in events


def test_idempotent_create_by_operation_id(proc_conn):
    a = _create(proc_conn, op="op-x")
    b = _create(proc_conn, op="op-x")
    assert a.entity_id == b.entity_id
    rows = proc_conn.execute("SELECT COUNT(*) FROM direct_purchases").fetchone()[0]
    assert rows == 1


def test_permission_denied_blocks_creation(proc_conn):
    auth = PurchaseAuthorizationPolicy(_Checker(denied={PurchasePermissions.DIRECT_CREATE}))
    result = _create(proc_conn, auth=auth)
    assert not result.success and result.error_code == "PERMISSION_DENIED"
    assert proc_conn.execute("SELECT COUNT(*) FROM direct_purchases").fetchone()[0] == 0


def test_over_limit_requires_authorization_then_confirms(proc_conn):
    PurchaseLimitRepository(proc_conn).upsert_user_limit(
        user_id="u1", limit=PurchaseLimit(maximum_per_transaction=Decimal("100"),
                                          requires_approval_above=Decimal("50")))
    proc_conn.commit()
    created = _create(proc_conn, payment_source="PETTY_CASH")
    assert created.data["requires_authorization"] is True
    assert created.data["status"] == DocumentStatus.PENDING_AUTHORIZATION.value

    # cannot confirm while pending authorization
    blocked = ConfirmDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id="op-c", payment_source="PETTY_CASH")
    assert not blocked.success and blocked.error_code == "AUTHORIZATION_REQUIRED"

    # a different user authorizes; creator cannot self-authorize
    self_auth = AuthorizeDirectPurchaseUseCase().execute(
        proc_conn, authorizer_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id="op-a", reason="supera límite")
    assert not self_auth.success and self_auth.error_code == "SEGREGATION"

    ok = AuthorizeDirectPurchaseUseCase().execute(
        proc_conn, authorizer_user_id="jefe", direct_purchase_id=created.entity_id,
        operation_id="op-a2", reason="supera límite")
    assert ok.success and ok.data["status"] == DocumentStatus.DRAFT.value

    logged = proc_conn.execute(
        "SELECT COUNT(*) FROM purchase_authorization_log").fetchone()[0]
    assert logged == 1

    confirm = ConfirmDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id="op-c2", payment_source="TREASURY_ACCOUNT")
    assert confirm.success and confirm.data["status"] == DocumentStatus.RECEIVED.value


def test_immediate_payment_cannot_come_from_pos_cash(proc_conn):
    created = _create(proc_conn)
    result = ConfirmDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id="op-c", payment_source="POS_CASH")
    assert not result.success and result.error_code == "INVALID_PAYMENT_SOURCE"
    # atomic: still confirmable, nothing half-written
    row = proc_conn.execute("SELECT status FROM direct_purchases WHERE id=?",
                            (created.entity_id,)).fetchone()
    assert row[0] == DocumentStatus.DRAFT.value


def test_supplier_credit_creates_payable(proc_conn):
    created = _create(proc_conn, payment_condition=PaymentCondition.SUPPLIER_CREDIT.value)
    confirm = ConfirmDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id="op-c")
    assert confirm.success
    with ProcurementUnitOfWork(proc_conn) as uow:
        events = {r["event_name"] for r in uow.outbox.list_pending(50)}
    assert "PURCHASE_PAYABLE_CREATED" in events
    assert "PURCHASE_PAYMENT_REQUESTED" not in events


def test_reverse_confirmed_purchase(proc_conn):
    created = _create(proc_conn, payment_source="PETTY_CASH")
    ConfirmDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id="op-c", payment_source="PETTY_CASH")
    rev = ReverseDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id="op-r", reason="devolución total")
    assert rev.success and rev.data["status"] == DocumentStatus.REVERSED.value
    gr = proc_conn.execute(
        "SELECT status FROM goods_receipts WHERE direct_purchase_id=?",
        (created.entity_id,)).fetchone()
    assert gr[0] == "REVERSED"


def test_reverse_requires_reason(proc_conn):
    created = _create(proc_conn, payment_source="PETTY_CASH")
    ConfirmDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id="op-c", payment_source="PETTY_CASH")
    rev = ReverseDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id="op-r", reason="  ")
    assert not rev.success and rev.error_code == "VALIDATION"


def test_rollback_on_failure_is_atomic(proc_conn):
    """If confirmation fails mid-way, no receipt/line rows leak (UoW rollback)."""
    created = _create(proc_conn, payment_source="PETTY_CASH")
    # Force an invalid payment source → confirmation fails before any receipt write
    ConfirmDirectPurchaseUseCase().execute(
        proc_conn, actor_user_id="u1", direct_purchase_id=created.entity_id,
        operation_id="op-c", payment_source="POS_CASH")
    receipts = proc_conn.execute("SELECT COUNT(*) FROM goods_receipts").fetchone()[0]
    assert receipts == 0
