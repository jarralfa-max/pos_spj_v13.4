from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.shared.ids import new_uuid
from backend.application.procurement.queries.supplier_directory_query_service import (
    SupplierDirectoryQueryService,
)
from backend.application.procurement.queries.enterprise_read_services import (
    OrderReadService, RequisitionReadService,
)
from backend.application.procurement.use_cases.purchase_order_use_cases import (
    CreatePurchaseOrderUseCase,
)
from backend.application.procurement.use_cases.direct_purchase_use_cases import (
    CreateDirectPurchaseUseCase,
)
from backend.application.procurement.use_cases.quotation_use_cases import (
    AwardSupplierQuoteUseCase, CaptureSupplierQuoteUseCase, CreateRfqUseCase,
)
from backend.application.procurement.use_cases.requisition_use_cases import (
    ApprovePurchaseRequisitionUseCase, CreatePurchaseRequisitionUseCase,
    SubmitPurchaseRequisitionUseCase,
)


class Allow:
    def has_permission(self, user_id, permission_code):
        return True


def auth():
    return PurchaseAuthorizationPolicy(Allow())


def approved_requisition(proc_conn):
    created = CreatePurchaseRequisitionUseCase(auth()).execute(
        proc_conn, actor_user_id="requester", operation_id=new_uuid(),
        branch_id="branch", purchase_type="INVENTORY",
        lines=[{"product_id": "p1", "quantity": "2",
                "estimated_unit_cost": "10", "purchase_nature": "INVENTORY"}])
    SubmitPurchaseRequisitionUseCase(auth()).execute(
        proc_conn, actor_user_id="requester", requisition_id=created.entity_id,
        operation_id=new_uuid())
    approved = ApprovePurchaseRequisitionUseCase(auth()).execute(
        proc_conn, approver_user_id="approver", requisition_id=created.entity_id,
        operation_id=new_uuid(), approve=True)
    assert approved.success
    return created.entity_id


def test_supplier_directory_reads_only_canonical_proveedores(proc_conn):
    proc_conn.execute("CREATE TABLE proveedores (id TEXT PRIMARY KEY, nombre TEXT, activo INTEGER)")
    proc_conn.execute("INSERT INTO proveedores VALUES ('supplier','Proveedor',1)")
    directory = SupplierDirectoryQueryService(proc_conn)
    assert directory.get_eligibility("supplier").active
    assert directory.get_eligibility("missing") is None


def test_purchase_nature_is_persisted_per_line(proc_conn):
    result = CreatePurchaseRequisitionUseCase(auth()).execute(
        proc_conn, actor_user_id="requester", operation_id="nature-op", branch_id="branch",
        purchase_type="INVENTORY", lines=[
            {"product_id": "stock", "quantity": "2", "purchase_nature": "INVENTORY"},
            {"product_id": "repair", "quantity": "1", "purchase_nature": "MAINTENANCE"},
        ])
    assert result.success
    assert proc_conn.execute(
        "SELECT purchase_nature FROM purchase_requisition_lines"
        " WHERE requisition_id=? ORDER BY product_id", (result.entity_id,)).fetchall() == [
            ("MAINTENANCE",), ("INVENTORY",)]


def test_direct_purchase_can_reference_only_approved_requisition(proc_conn):
    req = CreatePurchaseRequisitionUseCase(auth()).execute(
        proc_conn, actor_user_id="requester", operation_id="req-source", branch_id="branch",
        purchase_type="INVENTORY", lines=[{"product_id": "p1", "quantity": "1"}])
    blocked = CreateDirectPurchaseUseCase(auth()).execute(
        proc_conn, actor_user_id="buyer", operation_id="dp-blocked", supplier_id="supplier",
        branch_id="branch", warehouse_id="warehouse", source_requisition_id=req.entity_id,
        lines=[{"product_id": "p1", "quantity": "1", "unit_cost": "10"}])
    assert blocked.error_code == "INVALID_REQUISITION"
    SubmitPurchaseRequisitionUseCase(auth()).execute(
        proc_conn, actor_user_id="requester", requisition_id=req.entity_id,
        operation_id="req-submit")
    ApprovePurchaseRequisitionUseCase(auth()).execute(
        proc_conn, approver_user_id="approver", requisition_id=req.entity_id,
        operation_id="req-approve")
    created = CreateDirectPurchaseUseCase(auth()).execute(
        proc_conn, actor_user_id="buyer", operation_id="dp-source", supplier_id="supplier",
        branch_id="branch", warehouse_id="warehouse", source_requisition_id=req.entity_id,
        lines=[{"product_id": "p1", "quantity": "1", "unit_cost": "10",
                "purchase_nature": "INVENTORY"}])
    assert created.success
    assert proc_conn.execute(
        "SELECT source_requisition_id FROM direct_purchases WHERE id=?",
        (created.entity_id,)).fetchone()[0] == req.entity_id


def test_rfq_invitations_and_split_award_are_normalized(proc_conn):
    rfq = CreateRfqUseCase(auth()).execute(
        proc_conn, actor_user_id="buyer", operation_id="rfq-op",
        supplier_ids=["supplier-a", "supplier-b"])
    quote_a = CaptureSupplierQuoteUseCase(auth()).execute(
        proc_conn, actor_user_id="buyer", operation_id="quote-a", rfq_id=rfq.entity_id,
        supplier_id="supplier-a", lines=[
            {"product_id": "p1", "quantity": "10", "unit_price": "8"}])
    quote_b = CaptureSupplierQuoteUseCase(auth()).execute(
        proc_conn, actor_user_id="buyer", operation_id="quote-b", rfq_id=rfq.entity_id,
        supplier_id="supplier-b", lines=[
            {"product_id": "p1", "quantity": "10", "unit_price": "9"}])
    line_a = proc_conn.execute(
        "SELECT id FROM supplier_quote_lines WHERE quote_id=?", (quote_a.entity_id,)).fetchone()[0]
    line_b = proc_conn.execute(
        "SELECT id FROM supplier_quote_lines WHERE quote_id=?", (quote_b.entity_id,)).fetchone()[0]
    award = AwardSupplierQuoteUseCase(auth()).execute(
        proc_conn, actor_user_id="approver", operation_id="award-split",
        award_lines=[
            {"quote_line_id": line_a, "supplier_id": "supplier-a",
             "awarded_quantity": "6", "justification": "mejor precio"},
            {"quote_line_id": line_b, "supplier_id": "supplier-b",
             "awarded_quantity": "4", "justification": "capacidad disponible"},
        ])
    assert award.success
    assert proc_conn.execute(
        "SELECT COUNT(*) FROM rfq_supplier_invitations WHERE rfq_id=?",
        (rfq.entity_id,)).fetchone()[0] == 2
    assert proc_conn.execute(
        "SELECT COUNT(*) FROM purchase_award_lines WHERE award_id=?",
        (award.entity_id,)).fetchone()[0] == 2


def test_approved_requisition_can_create_rfq_and_exposes_related_timeline(proc_conn):
    requisition_id = approved_requisition(proc_conn)

    rfq = CreateRfqUseCase(auth()).execute(
        proc_conn, actor_user_id="buyer", operation_id=new_uuid(),
        supplier_ids=["supplier-a", "supplier-b"], requisition_id=requisition_id)
    detail = RequisitionReadService(proc_conn).detail(requisition_id)

    assert rfq.success
    assert [(doc["document_type"], doc["id"]) for doc in detail["related_documents"]] == [
        ("RFQ", rfq.entity_id)]
    assert [event["action"] for event in detail["timeline"]] == [
        "PURCHASE_REQUISITION_CREATED", "PURCHASE_REQUISITION_SUBMITTED",
        "PURCHASE_REQUISITION_APPROVED",
    ]


def test_purchase_order_from_approved_requisition_marks_source_and_keeps_lineage(proc_conn):
    requisition_id = approved_requisition(proc_conn)

    order = CreatePurchaseOrderUseCase(auth()).execute(
        proc_conn, actor_user_id="buyer", operation_id=new_uuid(),
        supplier_id="supplier", branch_id="branch", warehouse_id="warehouse",
        requisition_id=requisition_id,
        lines=[{"product_id": "p1", "quantity": "2", "unit_price": "10"}])
    requisition = RequisitionReadService(proc_conn).detail(requisition_id)
    order_detail = OrderReadService(proc_conn).detail(order.entity_id)

    assert order.success
    assert requisition["status"] == "SOURCED"
    assert requisition["related_documents"][0]["id"] == order.entity_id
    assert order_detail["source_requisition_id"] == requisition_id
    assert order_detail["timeline"][0]["action"] == "PURCHASE_ORDER_CREATED"
