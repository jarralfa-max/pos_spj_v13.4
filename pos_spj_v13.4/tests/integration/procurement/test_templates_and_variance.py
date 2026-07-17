"""PUR-13 step 1b — purchase templates + cost-variance detection (canonical).

Templates load into the cart via the read service; significant cost variances are
recorded as audit + a canonical PURCHASE_PRICE_VARIANCE_DETECTED event (replacing
the legacy audit_write), never a widget-side float alert.
"""

import json

import pytest

from backend.application.procurement.queries.purchase_template_read_service import (
    ProductPurchaseCostReadService,
    PurchaseTemplateReadService,
)
from backend.application.procurement.use_cases.pricing_use_cases import (
    RecordPurchasePriceVarianceUseCase,
)
from backend.infrastructure.db.repositories.procurement.unit_of_work import (
    ProcurementUnitOfWork,
)


@pytest.fixture
def tpl_conn(proc_conn):
    proc_conn.execute(
        "CREATE TABLE plantillas_compra (id TEXT PRIMARY KEY, nombre TEXT,"
        " descripcion TEXT, proveedor_id TEXT, activo INTEGER DEFAULT 1)")
    proc_conn.execute(
        "CREATE TABLE plantillas_compra_items (id TEXT PRIMARY KEY, plantilla_id TEXT,"
        " producto_id TEXT, cantidad REAL, costo_unitario REAL)")
    proc_conn.execute(
        "CREATE TABLE productos (id TEXT PRIMARY KEY, precio_compra REAL)")
    proc_conn.execute("INSERT INTO plantillas_compra (id, nombre) VALUES ('t1','Semanal')")
    proc_conn.execute("INSERT INTO plantillas_compra_items VALUES ('i1','t1','p1',10,30)")
    proc_conn.execute("INSERT INTO plantillas_compra_items VALUES ('i2','t1','p2',5,8)")
    proc_conn.execute("INSERT INTO productos VALUES ('p1', 30)")
    proc_conn.commit()
    return proc_conn


# ── templates ────────────────────────────────────────────────────────────────
def test_list_and_load_template(tpl_conn):
    svc = PurchaseTemplateReadService(tpl_conn)
    templates = svc.list_templates()
    assert templates and templates[0]["name"] == "Semanal"
    lines = svc.template_lines("t1")
    assert len(lines) == 2
    assert lines[0] == {"product_id": "p1", "quantity": "10.0", "unit_cost": "30.0"}


def test_templates_tolerate_missing_tables(proc_conn):
    svc = PurchaseTemplateReadService(proc_conn)  # no plantillas tables
    assert svc.list_templates() == []
    assert svc.template_lines("x") == []


# ── historical cost ──────────────────────────────────────────────────────────
def test_historical_cost_prefers_precio_compra(tpl_conn):
    # precio_compra is a legacy REAL column → "30.0"; the domain policy parses it
    # via Decimal, so the string form is inconsequential.
    assert ProductPurchaseCostReadService(tpl_conn).historical_cost("p1") == "30.0"
    assert ProductPurchaseCostReadService(tpl_conn).historical_cost("nope") == "0"


# ── variance detection ───────────────────────────────────────────────────────
def test_significant_variance_records_audit_and_event(tpl_conn):
    result = RecordPurchasePriceVarianceUseCase().execute(
        tpl_conn, actor_user_id="u1", operation_id="op-var", document_id="doc-1",
        lines=[{"product_id": "p1", "captured_cost": "45"}], branch_id="br-1")
    assert result.success
    detected = result.data["detected"]
    assert len(detected) == 1 and detected[0]["direction"] == "UP"
    assert "SUBIÓ" in detected[0]["label"]

    audit = tpl_conn.execute(
        "SELECT COUNT(*) FROM procurement_audit_log WHERE action=?",
        ("PURCHASE_PRICE_VARIANCE_DETECTED",)).fetchone()[0]
    assert audit == 1
    with ProcurementUnitOfWork(tpl_conn) as uow:
        events = [json.loads(e["payload_json"]) for e in uow.outbox.list_pending(50)
                  if e["event_name"] == "PURCHASE_PRICE_VARIANCE_DETECTED"]
    assert events and events[0]["product_id"] == "p1"


def test_within_threshold_records_nothing(tpl_conn):
    result = RecordPurchasePriceVarianceUseCase().execute(
        tpl_conn, actor_user_id="u1", operation_id="op-ok", document_id="doc-2",
        lines=[{"product_id": "p1", "captured_cost": "33"}], branch_id="br-1")  # +10%
    assert result.data["detected"] == []
    audit = tpl_conn.execute("SELECT COUNT(*) FROM procurement_audit_log").fetchone()[0]
    assert audit == 0


def test_variance_uses_explicit_historical_when_given(tpl_conn):
    result = RecordPurchasePriceVarianceUseCase().execute(
        tpl_conn, actor_user_id="u1", operation_id="op-h", document_id="doc-3",
        lines=[{"product_id": "pX", "captured_cost": "200", "historical_cost": "100"}])
    assert len(result.data["detected"]) == 1
