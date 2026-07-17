"""PUR-13 step 2c — QR container lifecycle (generate → assign → reception context)
migrated to the canonical context. Traceability writes only; no inventory/finance."""

import json

import pytest

from backend.application.procurement.queries.qr_traceability_read_service import (
    QrTraceabilityReadService,
)
from backend.application.procurement.use_cases.qr_container_use_cases import (
    AssignQrContainerUseCase,
    RegisterQrContainerUseCase,
)
from backend.application.procurement.use_cases.qr_reception_use_cases import (
    CompleteQrReceptionUseCase,
)
from backend.infrastructure.db.repositories.procurement.qr_container_repository import (
    QrContainerRepository,
)


@pytest.fixture
def qr_conn(proc_conn):
    proc_conn.execute(
        "CREATE TABLE trazabilidad_qr (uuid_qr TEXT PRIMARY KEY, tipo TEXT, proveedor_id TEXT,"
        " sucursal_id TEXT, sucursal_destino TEXT, estado TEXT, datos_extra TEXT,"
        " fecha_generacion TEXT DEFAULT (datetime('now')), fecha_recepcion TEXT, recepcion_id TEXT)")
    proc_conn.execute(
        "CREATE TABLE contenedores_qr (uuid_qr TEXT PRIMARY KEY, codigo_interno TEXT,"
        " descripcion TEXT, sucursal_origen TEXT, estado TEXT, sucursal_destino TEXT,"
        " viaje_actual INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now')),"
        " updated_at TEXT)")
    # catalog tables the read services join against (present in the real app)
    proc_conn.execute("CREATE TABLE proveedores (id TEXT PRIMARY KEY, nombre TEXT,"
                      " rfc TEXT, activo INTEGER DEFAULT 1)")
    proc_conn.execute("CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT)")
    proc_conn.execute("CREATE TABLE recepciones (id TEXT PRIMARY KEY, uuid_qr TEXT,"
                      " estado TEXT, created_at TEXT)")
    proc_conn.execute("INSERT INTO proveedores (id, nombre) VALUES ('s1','Proveedor 1')")
    proc_conn.commit()
    return proc_conn


def test_generate_label_registers_container(qr_conn):
    result = RegisterQrContainerUseCase().execute(
        qr_conn, actor_user_id="alm", operation_id="op1", description="Caja pollo",
        origin_branch_id="br-1")
    assert result.success and result.data["uuid_qr"]
    row = qr_conn.execute("SELECT descripcion FROM contenedores_qr WHERE uuid_qr=?",
                         (result.entity_id,)).fetchone()
    assert row[0] == "Caja pollo"
    # appears as available in the read service
    avail = QrTraceabilityReadService(qr_conn).available_containers()
    assert any(c["uuid_qr"] == result.entity_id for c in avail)


def test_assign_container_records_supplier_and_payment(qr_conn):
    reg = RegisterQrContainerUseCase().execute(
        qr_conn, actor_user_id="alm", operation_id="op1", description="x")
    uuid_qr = reg.entity_id
    result = AssignQrContainerUseCase().execute(
        qr_conn, actor_user_id="alm", operation_id="op2", uuid_qr=uuid_qr,
        supplier_id="s1", payment_condition="liquidado",
        items=[{"product_id": "p1", "cantidad": "10", "costo_unitario": "30"},
               {"product_id": "p2", "cantidad": "5", "costo_unitario": "8"}])
    assert result.success
    assert result.data["total"] == "340"       # 300 + 40
    assert result.data["amount_paid"] == "340"  # liquidado ⇒ pagado = total

    # the reception reads exactly this assignment
    assignment = QrContainerRepository(qr_conn).read_assignment(uuid_qr)
    assert assignment["supplier_id"] == "s1"
    assert str(assignment["amount_total"]) == "340"


def test_credit_assignment_leaves_balance(qr_conn):
    reg = RegisterQrContainerUseCase().execute(
        qr_conn, actor_user_id="alm", operation_id="op1")
    result = AssignQrContainerUseCase().execute(
        qr_conn, actor_user_id="alm", operation_id="op2", uuid_qr=reg.entity_id,
        supplier_id="s1", payment_condition="crédito",
        items=[{"product_id": "p1", "cantidad": "10", "costo_unitario": "30"}])
    assert result.data["total"] == "300" and result.data["amount_paid"] == "0"


def test_assign_requires_supplier_and_items(qr_conn):
    reg = RegisterQrContainerUseCase().execute(qr_conn, actor_user_id="a", operation_id="o1")
    no_sup = AssignQrContainerUseCase().execute(
        qr_conn, actor_user_id="a", operation_id="o2", uuid_qr=reg.entity_id,
        supplier_id="", items=[{"product_id": "p1", "cantidad": "1", "costo_unitario": "1"}])
    assert not no_sup.success and no_sup.error_code == "VALIDATION"
    no_items = AssignQrContainerUseCase().execute(
        qr_conn, actor_user_id="a", operation_id="o3", uuid_qr=reg.entity_id,
        supplier_id="s1", items=[])
    assert not no_items.success and no_items.error_code == "EMPTY"


def test_generate_assign_then_reception_reads_context(qr_conn):
    reg = RegisterQrContainerUseCase().execute(qr_conn, actor_user_id="a", operation_id="o1")
    AssignQrContainerUseCase().execute(
        qr_conn, actor_user_id="a", operation_id="o2", uuid_qr=reg.entity_id,
        supplier_id="s1", payment_condition="liquidado",
        items=[{"product_id": "p1", "cantidad": "10", "costo_unitario": "30"}])
    # pending reception lists the assigned container
    pending = QrTraceabilityReadService(qr_conn).pending_reception()
    assert any(r["uuid_qr"] == reg.entity_id for r in pending)
    # reception consumes it (no inventory tables here → pure event flow)
    rec = CompleteQrReceptionUseCase().execute(
        qr_conn, actor_user_id="a", operation_id="o3", uuid_qr=reg.entity_id,
        items=[{"product_id": "p1", "quantity": "10", "unit_cost": "30"}],
        branch_id="br-1", warehouse_id="wh-1")
    assert rec.success and rec.data["status"] == "RECEIVED"
