"""Purchase-return (devolución a proveedor) application flow: schema bootstrap
via migrations, atomicity, permissions, audit trail, and post-commit outbox
events. Mirrors test_direct_purchase_flow.py's composition style."""

import sqlite3

import pytest

from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.permissions import PurchasePermissions
from backend.application.procurement.use_cases.purchase_return_use_cases import (
    CancelPurchaseReturnUseCase,
    ConfirmPurchaseReturnUseCase,
    CreatePurchaseReturnUseCase,
)
from backend.domain.procurement.enums import PurchaseReturnStatus
from backend.infrastructure.db.schema.document_output_schema import create_document_numbering_schema
from backend.infrastructure.db.schema.procurement_schema import (
    create_procurement_schema,
    create_purchase_returns_schema,
)
from backend.infrastructure.db.repositories.procurement.unit_of_work import (
    ProcurementUnitOfWork,
)


class _Checker:
    """Grants everything except the codes in ``denied`` (mirrors direct-purchase tests)."""

    def __init__(self, denied=()):
        self._denied = set(denied)

    def has_permission(self, user_id, permission_code):
        return permission_code not in self._denied


@pytest.fixture
def return_conn():
    """A clean in-memory DB with the canonical procurement schema (migration 120)
    PLUS purchase_returns/purchase_return_lines (migration 205) — proves 205 is
    additive and does not require re-running 120."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_procurement_schema(conn)
    create_purchase_returns_schema(conn)
    create_document_numbering_schema(conn)
    yield conn
    conn.close()


def _lines():
    return [{"product_id": "p1", "quantity": "3", "unit_cost": "100", "lot": "L-1"}]


def _create(conn, *, actor="u1", op="op-1", auth=None, **kw):
    uc = CreatePurchaseReturnUseCase(auth)
    return uc.execute(conn, actor_user_id=actor, operation_id=op, supplier_id="sup-1",
                      branch_id="br-1", warehouse_id="wh-1", reason="DAMAGED",
                      lines=_lines(), **kw)


def _seed_receipt_and_order(conn, *, goods_receipt_id="gr-1", purchase_order_id="po-1"):
    """Insert minimal parent rows so FK-constrained goods_receipt_id/purchase_order_id
    columns on purchase_returns can reference them (PRAGMA foreign_keys=ON)."""
    conn.execute(
        "INSERT INTO purchase_orders (id, document_number, supplier_id, branch_id,"
        " warehouse_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (purchase_order_id, "OC-2026-000001", "sup-1", "br-1", "wh-1", "t", "t"))
    conn.execute(
        "INSERT INTO goods_receipts (id, document_number, supplier_id, branch_id,"
        " warehouse_id, purchase_order_id, created_at) VALUES (?,?,?,?,?,?,?)",
        (goods_receipt_id, "REC-2026-000001", "sup-1", "br-1", "wh-1", purchase_order_id, "t"))


def test_create_persists_confirms_and_records_audit_and_outbox(return_conn):
    _seed_receipt_and_order(return_conn)
    created = _create(return_conn, goods_receipt_id="gr-1", purchase_order_id="po-1")
    assert created.success
    assert created.data["status"] == PurchaseReturnStatus.DRAFT.value
    assert created.data["document_number"].startswith("DEV-")

    with ProcurementUnitOfWork(return_conn) as uow:
        pr = uow.returns.get(created.entity_id)
        assert pr is not None
        assert pr.goods_receipt_id == "gr-1"
        assert pr.purchase_order_id == "po-1"
        assert len(pr.lines) == 1
        assert pr.lines[0].product_id == "p1"

    confirmed = ConfirmPurchaseReturnUseCase().execute(
        return_conn, actor_user_id="u1", purchase_return_id=created.entity_id,
        operation_id="op-confirm")
    assert confirmed.success
    assert confirmed.data["status"] == PurchaseReturnStatus.CONFIRMED.value

    with ProcurementUnitOfWork(return_conn) as uow:
        audit_actions = {row["action"] for row in uow.audit.list_for_document(created.entity_id)}
        events = {row["event_name"] for row in uow.outbox.list_pending(50)}
    assert "PURCHASE_RETURN_CREATED" in audit_actions
    assert "PURCHASE_RETURN_CONFIRMED" in audit_actions
    assert "PURCHASE_RETURN_CREATED" in events
    assert "PURCHASE_RETURN_CONFIRMED" in events

    # the original goods receipt is never deleted / touched by a return
    receipt_row = return_conn.execute(
        "SELECT id, status FROM goods_receipts WHERE id=?", ("gr-1",)).fetchone()
    assert receipt_row is not None


def test_idempotent_create_by_operation_id(return_conn):
    a = _create(return_conn, op="op-x")
    b = _create(return_conn, op="op-x")
    assert a.entity_id == b.entity_id
    rows = return_conn.execute("SELECT COUNT(*) FROM purchase_returns").fetchone()[0]
    assert rows == 1


def test_permission_denied_blocks_creation(return_conn):
    auth = PurchaseAuthorizationPolicy(_Checker(denied={PurchasePermissions.RETURN}))
    result = _create(return_conn, auth=auth)
    assert not result.success
    assert result.error_code == "PERMISSION_DENIED"
    assert return_conn.execute("SELECT COUNT(*) FROM purchase_returns").fetchone()[0] == 0


def test_permission_denied_blocks_confirm(return_conn):
    created = _create(return_conn)
    assert created.success
    auth = PurchaseAuthorizationPolicy(_Checker(denied={PurchasePermissions.RETURN}))
    result = ConfirmPurchaseReturnUseCase(auth).execute(
        return_conn, actor_user_id="u1", purchase_return_id=created.entity_id,
        operation_id="op-confirm")
    assert not result.success
    assert result.error_code == "PERMISSION_DENIED"
    with ProcurementUnitOfWork(return_conn) as uow:
        assert uow.returns.get(created.entity_id).status is PurchaseReturnStatus.DRAFT


def test_empty_lines_rejected(return_conn):
    uc = CreatePurchaseReturnUseCase()
    result = uc.execute(return_conn, actor_user_id="u1", operation_id="op-empty",
                        supplier_id="sup-1", branch_id="br-1", warehouse_id="wh-1",
                        reason="DAMAGED", lines=[])
    assert not result.success
    assert result.error_code == "EMPTY"


def test_invalid_reason_rejected(return_conn):
    uc = CreatePurchaseReturnUseCase()
    result = uc.execute(return_conn, actor_user_id="u1", operation_id="op-bad-reason",
                        supplier_id="sup-1", branch_id="br-1", warehouse_id="wh-1",
                        reason="NOT_A_REAL_REASON", lines=_lines())
    assert not result.success
    assert result.error_code == "VALIDATION"


def test_cancel_draft_return(return_conn):
    created = _create(return_conn, op="op-cancel")
    result = CancelPurchaseReturnUseCase().execute(
        return_conn, actor_user_id="u1", purchase_return_id=created.entity_id,
        operation_id="op-cancel-2", reason="captured by mistake")
    assert result.success
    assert result.data["status"] == PurchaseReturnStatus.CANCELLED.value


def test_cannot_confirm_cancelled_return(return_conn):
    created = _create(return_conn, op="op-cancel-then-confirm")
    CancelPurchaseReturnUseCase().execute(
        return_conn, actor_user_id="u1", purchase_return_id=created.entity_id,
        operation_id="op-c1")
    result = ConfirmPurchaseReturnUseCase().execute(
        return_conn, actor_user_id="u1", purchase_return_id=created.entity_id,
        operation_id="op-c2")
    assert not result.success
    assert result.error_code == "INVALID_STATE"


def test_confirm_nonexistent_return_not_found(return_conn):
    result = ConfirmPurchaseReturnUseCase().execute(
        return_conn, actor_user_id="u1", purchase_return_id="does-not-exist",
        operation_id="op-nf")
    assert not result.success
    assert result.error_code == "NOT_FOUND"


def test_document_number_sequence_uses_dev_prefix(return_conn):
    first = _create(return_conn, op="op-seq-1")
    second = _create(return_conn, op="op-seq-2")
    assert first.data["document_number"] == "DEV-" + first.data["document_number"].split("-", 1)[1]
    assert first.data["document_number"] != second.data["document_number"]
