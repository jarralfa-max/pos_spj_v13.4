"""FASE 4 — Flujo documental: RFQ → cotizaciones → comparación → adjudicación.
Before this, CaptureSupplierQuoteUseCase/AwardSupplierQuoteUseCase were fully
implemented and tested in isolation, but nothing read them back for a UI —
a buyer had no screen to record what a supplier quoted or to award it."""

from __future__ import annotations

import pytest

from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.queries.quotation_read_services import (
    RfqReadService,
)
from backend.application.procurement.use_cases.quotation_use_cases import (
    AwardSupplierQuoteUseCase, CaptureSupplierQuoteUseCase, CreateRfqUseCase,
)


class Allow:
    def has_permission(self, user_id, permission_code):
        return True


def auth():
    return PurchaseAuthorizationPolicy(Allow())


@pytest.fixture
def rfq_conn(proc_conn):
    proc_conn.execute("CREATE TABLE proveedores(id TEXT PRIMARY KEY, nombre TEXT, activo INTEGER)")
    proc_conn.execute("INSERT INTO proveedores VALUES ('sup-a','Proveedor A',1)")
    proc_conn.execute("INSERT INTO proveedores VALUES ('sup-b','Proveedor B',1)")
    return proc_conn


def _rfq_with_two_quotes(conn):
    rfq = CreateRfqUseCase(auth()).execute(
        conn, actor_user_id="buyer", operation_id="rfq-1",
        supplier_ids=["sup-a", "sup-b"])
    assert rfq.success
    quote_a = CaptureSupplierQuoteUseCase(auth()).execute(
        conn, actor_user_id="buyer", operation_id="quote-a", rfq_id=rfq.entity_id,
        supplier_id="sup-a", lead_time_days=5,
        lines=[{"product_id": "p1", "quantity": "10", "unit_price": "90"}])
    assert quote_a.success
    quote_b = CaptureSupplierQuoteUseCase(auth()).execute(
        conn, actor_user_id="buyer", operation_id="quote-b", rfq_id=rfq.entity_id,
        supplier_id="sup-b", lead_time_days=2,
        lines=[{"product_id": "p1", "quantity": "10", "unit_price": "80"}])
    assert quote_b.success
    return rfq.entity_id, quote_a.entity_id, quote_b.entity_id


def test_list_shows_invited_and_quoted_counts(rfq_conn):
    rfq_id, _, _ = _rfq_with_two_quotes(rfq_conn)
    rows = RfqReadService(rfq_conn).list()
    assert len(rows) == 1
    assert rows[0].id == rfq_id
    assert rows[0].invited_count == 2
    assert rows[0].quoted_count == 2
    assert rows[0].awarded is False


def test_detail_resolves_supplier_names_never_raw_ids(rfq_conn):
    rfq_id, _, _ = _rfq_with_two_quotes(rfq_conn)
    detail = RfqReadService(rfq_conn).detail(rfq_id)
    assert detail is not None
    names = {inv.supplier_name for inv in detail.invitations}
    assert names == {"Proveedor A", "Proveedor B"}
    assert all("sup-" not in inv.supplier_name for inv in detail.invitations)
    quote_names = {q.supplier_name for q in detail.quotes}
    assert quote_names == {"Proveedor A", "Proveedor B"}


def test_detail_reflects_award_status(rfq_conn):
    rfq_id, quote_a_id, _ = _rfq_with_two_quotes(rfq_conn)
    assert RfqReadService(rfq_conn).detail(rfq_id).awarded is False
    award = AwardSupplierQuoteUseCase(auth()).execute(
        rfq_conn, actor_user_id="jefe", operation_id="award-1", quote_id=quote_a_id,
        reason="mejor plazo")
    assert award.success
    assert RfqReadService(rfq_conn).detail(rfq_id).awarded is True


def test_comparison_ranks_cheapest_first_and_marks_best_price(rfq_conn):
    rfq_id, _, _ = _rfq_with_two_quotes(rfq_conn)
    rows = RfqReadService(rfq_conn).comparison(rfq_id)
    assert [r.supplier_name for r in rows] == ["Proveedor B", "Proveedor A"]
    assert rows[0].is_best is True and rows[0].unit_price == "80"
    assert rows[1].is_best is False


def test_award_from_comparison_can_split_across_suppliers(rfq_conn):
    """The domain supports mixed awards (different suppliers per product-line);
    the read model must expose enough (quote_line_id, supplier_id, quantity)
    for a UI to build that award without re-deriving it."""
    rfq_id, quote_a_id, quote_b_id = _rfq_with_two_quotes(rfq_conn)
    rows = RfqReadService(rfq_conn).comparison(rfq_id)
    best = next(r for r in rows if r.is_best)
    award = AwardSupplierQuoteUseCase(auth()).execute(
        rfq_conn, actor_user_id="jefe", operation_id="award-split",
        award_lines=[{"quote_line_id": best.quote_line_id, "supplier_id": best.supplier_id,
                      "awarded_quantity": best.quantity, "justification": "mejor precio"}])
    assert award.success
    assert RfqReadService(rfq_conn).detail(rfq_id).awarded is True
