"""INV-26 — etiquetas/impresión de inventario (renderers + print gateway + audit)."""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.labels import (
    InMemoryPrintGateway,
    InventoryLabelPrintService,
)
from backend.application.inventory.labels.renderers import (
    render_count_label,
    render_lot_label,
    render_transfer_label,
    render_weight_label,
)
from backend.application.inventory.permissions import InventoryPermissions
from backend.domain.inventory.enums import LabelType
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


# ── renderers (pure) ─────────────────────────────────────────────────────────
class TestRenderers:
    def test_lot_label(self):
        doc = render_lot_label(product_id="p1", product_name="Arrachera",
                               lot_code="L-01", expiration_date="2026-01-01",
                               origin_type="PURCHASE", lot_id="lot1")
        assert doc.label_type is LabelType.LOT
        assert doc.barcode == "L-01" and doc.entity_ref == "lot1"
        assert any("Caduca: 2026-01-01" in ln for ln in doc.lines)

    def test_weight_label_decimal(self):
        doc = render_weight_label(product_id="p1", product_name="Pollo",
                                  net_weight=Decimal("1.250"), unit="kg",
                                  unit_price=Decimal("90"))
        assert doc.label_type is LabelType.WEIGHT
        # importe = 90 * 1.250 = 112.500 (Decimal, sin float)
        assert any("Importe: 112.500" in ln for ln in doc.lines)

    def test_transfer_and_count_labels(self):
        t = render_transfer_label(transfer_id="t1", folio="TR-9", origin_branch="b1",
                                  dest_branch="b2", items=3)
        assert t.label_type is LabelType.TRANSFER and t.entity_ref == "t1"
        c = render_count_label(count_id="c1", folio="CO-5", warehouse="Central")
        assert c.label_type is LabelType.COUNT and c.qr_payload == "count:c1"


# ── print service ────────────────────────────────────────────────────────────
class TestPrintService:
    def _doc(self):
        return render_lot_label(product_id="p1", product_name="Arrachera",
                                lot_code="L-01", lot_id="lot1", copies=2)

    def test_print_delivers_and_audits(self, conn):
        gw = InMemoryPrintGateway()
        svc = InventoryLabelPrintService(conn, gateway=gw)
        r = svc.print_label(self._doc(), actor_user_id="u1", printer_ref="ZEBRA-1")
        assert r.success
        assert len(gw.printed) == 1 and gw.printed[0]["copies"] == 2
        row = conn.execute("SELECT label_type, is_reprint, copies FROM"
                           " inventory_label_print_log WHERE id=?", (r.entity_id,)).fetchone()
        assert row["label_type"] == "LOT" and row["is_reprint"] == 0 and row["copies"] == 2

    def test_reprint_flagged_and_audited(self, conn):
        svc = InventoryLabelPrintService(conn)
        r = svc.print_label(self._doc(), actor_user_id="u1", is_reprint=True,
                            reason="reimpresión etiqueta dañada")
        assert r.success
        row = conn.execute("SELECT is_reprint, reason FROM inventory_label_print_log"
                           " WHERE id=?", (r.entity_id,)).fetchone()
        assert row["is_reprint"] == 1 and "dañada" in row["reason"]

    def test_events_dispatched(self, conn):
        seen = []
        svc = InventoryLabelPrintService(conn, event_dispatcher=lambda n, p: seen.append((n, p)))
        svc.print_label(self._doc(), actor_user_id="u1")
        svc.print_label(self._doc(), actor_user_id="u1", is_reprint=True)
        names = [n for n, _ in seen]
        assert "INVENTORY_LABEL_PRINTED" in names
        assert "INVENTORY_LABEL_REPRINTED" in names

    def test_permission_denied_blocks(self, conn):
        class _Deny:
            def has_permission(self, user_id, code): return False
        svc = InventoryLabelPrintService(
            conn, authorization=InventoryAuthorizationPolicy(checker=_Deny()))
        r = svc.print_label(self._doc(), actor_user_id="u1")
        assert not r.success and r.error_code == "PERMISSION_DENIED"
        assert conn.execute("SELECT COUNT(*) FROM inventory_label_print_log"
                            ).fetchone()[0] == 0

    def test_gateway_failure_audited_as_failed(self, conn):
        from backend.application.inventory.labels.gateway import PrintDeliveryError

        class _BadGw:
            def print(self, **kw): raise PrintDeliveryError("sin papel")
        svc = InventoryLabelPrintService(conn, gateway=_BadGw())
        r = svc.print_label(self._doc(), actor_user_id="u1")
        assert not r.success and r.error_code == "PRINT_DELIVERY_FAILED"
        # el fallo se audita igualmente (rastro de impresión)
        row = conn.execute("SELECT reason FROM inventory_label_print_log"
                           " ORDER BY created_at DESC LIMIT 1").fetchone()
        assert "sin papel" in row["reason"]
