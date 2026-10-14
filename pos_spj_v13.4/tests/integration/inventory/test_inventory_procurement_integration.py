"""INV-19 — canonical procurement→inventory handlers (§34).

Procurement never writes stock: its goods-receipt / return / reversal events are
consumed here and posted to the canonical ledger, with cost reference, quality
buckets and lot creation. Handlers are idempotent and (until INV-27) parallel to
the legacy path.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.event_handlers.inventory import (
    GoodsReceiptReversedHandler,
    PurchaseReceiptHandler,
    SupplierReturnHandler,
)
from backend.application.inventory.queries import (
    InventoryAvailabilityQueryService,
    TraceabilityQueryService,
)
from backend.domain.inventory.enums import InventoryStatus
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _avail(conn, product="p1", status=None):
    dto = InventoryAvailabilityQueryService(conn).get_availability(
        product_id=product, branch_id="b1", warehouse_id="w1")
    if status is None:
        return dto.available
    return Decimal(dto.by_status.get(status, "0"))


def _receipt_payload(**over):
    base = dict(operation_id="gr-1", branch_id="b1", warehouse_id="w1",
                goods_receipt_id="GR-1", supplier_id="sup1", user_id="recv",
                lines=[{"product_id": "p1", "quantity": "10", "unit_cost": "25",
                        "to_location_id": "loc1"}])
    base.update(over)
    return base


class TestPurchaseReceipt:
    def test_receipt_increases_available_with_cost_reference(self, conn):
        PurchaseReceiptHandler(conn).handle(_receipt_payload())
        assert _avail(conn) == Decimal("10")
        row = conn.execute(
            "SELECT unit_cost, movement_id FROM inventory_ledger_lines"
            " WHERE product_id='p1'").fetchone()
        assert row["unit_cost"] == "25"  # cost reference carried for Finance
        mv = conn.execute("SELECT movement_type, source_document_type FROM inventory_ledger"
                          " WHERE id=?", (row["movement_id"],)).fetchone()
        assert mv["movement_type"] == "PURCHASE_RECEIPT"
        assert mv["source_document_type"] == "GOODS_RECEIPT"

    def test_quality_hold_lands_in_pending_inspection(self, conn):
        PurchaseReceiptHandler(conn).handle(_receipt_payload(quality_hold=True))
        assert _avail(conn) == Decimal("0")  # not sellable
        assert _avail(conn, status=InventoryStatus.PENDING_INSPECTION.value) == Decimal("10")

    def test_lot_coded_line_creates_and_links_lot(self, conn):
        PurchaseReceiptHandler(conn).handle(_receipt_payload(lines=[{
            "product_id": "p1", "quantity": "8", "unit_cost": "30",
            "to_location_id": "loc1", "lot_code": "L-77",
            "supplier_lot_code": "SUP-L77", "expiration_date": "2026-12-31"}]))
        lot = conn.execute("SELECT id, supplier_lot_code FROM inventory_lots"
                           " WHERE lot_code='L-77'").fetchone()
        assert lot and lot["supplier_lot_code"] == "SUP-L77"
        line = conn.execute("SELECT lot_id FROM inventory_ledger_lines"
                            " WHERE product_id='p1'").fetchone()
        assert line["lot_id"] == lot["id"]
        # downstream trace derives the receipt from the ledger by lot
        up = TraceabilityQueryService(conn).trace_upstream(lot["id"])
        assert {e.movement_type for e in up.events} == {"PURCHASE_RECEIPT"}

    def test_receipt_is_idempotent(self, conn):
        PurchaseReceiptHandler(conn).handle(_receipt_payload())
        PurchaseReceiptHandler(conn).handle(_receipt_payload())  # replay
        assert _avail(conn) == Decimal("10")

    def test_receipt_missing_warehouse_is_not_defaulted_to_branch(self, conn):
        # §5: sin warehouse_id no se procesa con warehouse=branch.
        payload = _receipt_payload()
        payload.pop("warehouse_id")
        PurchaseReceiptHandler(conn).handle(payload)  # fail-closed → no-op
        assert _avail(conn) == Decimal("0")

    def test_receipt_missing_user_is_not_fabricated_as_system(self, conn):
        # §5.4: sin user_id no se procesa con actor "system".
        payload = _receipt_payload()
        payload.pop("user_id")
        PurchaseReceiptHandler(conn).handle(payload)  # fail-closed → no-op
        assert _avail(conn) == Decimal("0")


class TestSupplierReturnAndReversal:
    def test_supplier_return_decrements(self, conn):
        PurchaseReceiptHandler(conn).handle(_receipt_payload())
        SupplierReturnHandler(conn).handle(dict(
            operation_id="ret-1", branch_id="b1", warehouse_id="w1", return_id="RET-1",
            user_id="recv", lines=[{"product_id": "p1", "quantity": "3",
                                    "from_location_id": "loc1"}]))
        assert _avail(conn) == Decimal("7")
        mt = conn.execute("SELECT movement_type FROM inventory_ledger"
                          " WHERE source_document_type='PURCHASE_RETURN'").fetchone()
        assert mt["movement_type"] == "SUPPLIER_RETURN"

    def test_goods_receipt_reversal_backs_out_stock(self, conn):
        PurchaseReceiptHandler(conn).handle(_receipt_payload())
        GoodsReceiptReversedHandler(conn).handle(dict(
            operation_id="gr-1", goods_receipt_id="GR-1", user_id="recv",
            reason="proveedor equivocado"))
        assert _avail(conn) == Decimal("0")
        with InventoryUnitOfWork(conn) as uow:
            orig = uow.ledger.list_for_document("GOODS_RECEIPT", "GR-1")[0]
            assert orig["status"] == "REVERSED"

    def test_reversal_is_idempotent(self, conn):
        PurchaseReceiptHandler(conn).handle(_receipt_payload())
        p = dict(operation_id="gr-1", goods_receipt_id="GR-1", user_id="recv")
        GoodsReceiptReversedHandler(conn).handle(p)
        GoodsReceiptReversedHandler(conn).handle(p)  # replay: no double credit
        assert _avail(conn) == Decimal("0")

    def test_reversal_missing_user_is_not_fabricated_as_system(self, conn):
        # §5.4: sin actor el reverso no se procesa con "system"; recepción intacta.
        PurchaseReceiptHandler(conn).handle(_receipt_payload())
        GoodsReceiptReversedHandler(conn).handle(dict(
            operation_id="gr-1", goods_receipt_id="GR-1"))  # sin user_id → no-op
        assert _avail(conn) == Decimal("10")
        with InventoryUnitOfWork(conn) as uow:
            orig = uow.ledger.list_for_document("GOODS_RECEIPT", "GR-1")[0]
            assert orig["status"] == "POSTED"  # no reversado

    def test_supplier_return_missing_warehouse_is_not_defaulted(self, conn):
        # §5: sin warehouse_id la devolución no se procesa; recepción intacta.
        PurchaseReceiptHandler(conn).handle(_receipt_payload())
        SupplierReturnHandler(conn).handle(dict(
            operation_id="ret-1", branch_id="b1", return_id="RET-1", user_id="recv",
            lines=[{"product_id": "p1", "quantity": "3", "from_location_id": "loc1"}]))
        assert _avail(conn) == Decimal("10")

    def test_real_purchase_return_event_is_consumable_by_supplier_return_handler(self, conn):
        """Producer/consumer payload compatibility: CreatePurchaseReturnUseCase's
        actual PURCHASE_RETURN_CONFIRMED outbox payload — not a hand-written one —
        must be exactly what SupplierReturnHandler expects (resolve_ingress +
        per-line product_id/quantity/unit_cost/lot_id). Two separate connections,
        like the real outbox dispatcher would see: procurement never shares a
        schema with inventory."""
        import json
        import sqlite3 as _sqlite3

        from backend.application.procurement.authorization import (
            PurchaseAuthorizationPolicy,
        )
        from backend.application.procurement.use_cases.purchase_return_use_cases import (
            ConfirmPurchaseReturnUseCase,
            CreatePurchaseReturnUseCase,
        )
        from backend.infrastructure.db.repositories.procurement.unit_of_work import (
            ProcurementUnitOfWork,
        )
        from backend.infrastructure.db.schema.document_output_schema import (
            create_document_numbering_schema,
        )
        from backend.infrastructure.db.schema.procurement_schema import (
            create_procurement_schema,
            create_purchase_returns_schema,
        )

        class _AllowAll:
            def has_permission(self, user_id, permission_code):
                return True

        # Como en producción: la entrada vive en la ubicación de la sucursal y,
        # por ser producto con lote, DENTRO de un lote.
        PurchaseReceiptHandler(conn).handle(_receipt_payload(lines=[
            {"product_id": "p1", "quantity": "10", "unit_cost": "25",
             "to_location_id": "b1", "lot_code": "L-7"}]))
        assert _avail(conn) == Decimal("10")

        proc_conn = _sqlite3.connect(":memory:")
        create_procurement_schema(proc_conn)
        create_purchase_returns_schema(proc_conn)
        create_document_numbering_schema(proc_conn)
        # Auditoría Compras C13: la devolución sale de una recepción COMPLETADA
        # del mismo proveedor; C12: el stock se mueve al CONFIRMAR, no al crear.
        proc_conn.execute(
            "INSERT INTO purchase_orders (id, document_number, supplier_id, branch_id,"
            " warehouse_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            ("PO-1", "OC-1", "sup1", "b1", "w1", "t", "t"))
        proc_conn.execute(
            "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id,"
            " ordered_quantity, unit_price, purchase_nature) VALUES (?,?,?,?,?,?)",
            ("pol-1", "PO-1", "p1", "10", "25", "INVENTORY"))
        proc_conn.execute(
            "INSERT INTO goods_receipts (id, document_number, supplier_id, branch_id,"
            " warehouse_id, purchase_order_id, status, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            ("GR-1", "REC-1", "sup1", "b1", "w1", "PO-1", "COMPLETED", "t"))
        proc_conn.execute(
            "INSERT INTO goods_receipt_lines (id, goods_receipt_id, product_id,"
            " ordered_quantity, received_quantity, accepted_quantity, purchase_order_line_id)"
            " VALUES (?,?,?,?,?,?,?)", ("grl-1", "GR-1", "p1", "10", "10", "10", "pol-1"))
        policy = PurchaseAuthorizationPolicy(_AllowAll())
        result = CreatePurchaseReturnUseCase(policy).execute(
            proc_conn, actor_user_id="recv", operation_id="real-ret-1",
            supplier_id="sup1", branch_id="b1", warehouse_id="w1", reason="DAMAGED",
            goods_receipt_id="GR-1",
            lines=[{"product_id": "p1", "quantity": "3", "unit_cost": "25"}])
        assert result.success
        confirmed = ConfirmPurchaseReturnUseCase(policy).execute(
            proc_conn, actor_user_id="recv", purchase_return_id=result.entity_id,
            operation_id="real-ret-1-confirm")
        assert confirmed.success
        with ProcurementUnitOfWork(proc_conn) as uow:
            outbox_row = next(
                r for r in uow.outbox.list_pending(50)
                if r["event_name"] == "PURCHASE_RETURN_CONFIRMED")
        payload = json.loads(outbox_row["payload_json"])
        proc_conn.close()

        # La devolución no conoce el id del lote de Inventario: el manejador lo
        # resuelve desde la recepción de origen (auditoría Compras C12). Antes
        # la salida caía en el bucket sin lote → «inventario negativo».
        SupplierReturnHandler(conn).handle(payload)
        SupplierReturnHandler(conn).handle(payload)      # reentrega: un efecto
        assert _avail(conn) == Decimal("7")
        with InventoryUnitOfWork(conn) as uow:
            moved = uow.ledger.list_for_document("PURCHASE_RETURN", result.entity_id)
            lines = uow.ledger.get_lines(moved[0]["id"])
            lot = uow.lots.get_by_code("p1", "L-7")
        assert len(moved) == 1 and lines[0]["lot_id"] == lot.id


class TestSupplierReturnLotResolution:
    """Auditoría Compras C12: la salida por devolución sale del lote correcto."""

    def _receive_two_lots(self, conn):
        PurchaseReceiptHandler(conn).handle(_receipt_payload(lines=[
            {"product_id": "p1", "quantity": "4", "unit_cost": "25",
             "to_location_id": "b1", "lot_code": "L-A"},
            {"product_id": "p1", "quantity": "6", "unit_cost": "25",
             "to_location_id": "b1", "lot_code": "L-B"}]))

    def _return(self, conn, **line):
        SupplierReturnHandler(conn).handle(dict(
            operation_id="ret-lot", branch_id="b1", warehouse_id="w1",
            return_id="RET-L", goods_receipt_id="GR-1", user_id="recv",
            lines=[dict({"product_id": "p1", "quantity": "2",
                         "from_location_id": "b1"}, **line)]))

    def test_explicit_lot_code_picks_that_lot(self, conn):
        self._receive_two_lots(conn)
        self._return(conn, lot_code="L-B")
        with InventoryUnitOfWork(conn) as uow:
            moved = uow.ledger.list_for_document("PURCHASE_RETURN", "RET-L")
            line = uow.ledger.get_lines(moved[0]["id"])[0]
            assert line["lot_id"] == uow.lots.get_by_code("p1", "L-B").id
        assert _avail(conn) == Decimal("8")

    def test_ambiguous_lot_is_refused_not_guessed(self, conn):
        self._receive_two_lots(conn)
        with pytest.raises(RuntimeError, match="qué lote"):
            self._return(conn)
        assert _avail(conn) == Decimal("10")
