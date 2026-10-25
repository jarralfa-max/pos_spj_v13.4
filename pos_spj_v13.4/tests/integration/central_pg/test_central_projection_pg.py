"""Ventas + Inventario de punta a punta contra PostgreSQL REAL (Slice 5; CI).

Caja SQLite (outbox reales de Ventas e Inventario) → motor de replicación →
HTTPS (TestClient) → API central → libro de hechos → proyecciones. Se verifica
que la venta central tenga los totales de la caja, que la existencia central
cuadre con los saldos de la estación y que reproyectar no duplique nada.
"""

from __future__ import annotations

import importlib
import json
import os
import random
import sqlite3
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

psycopg = pytest.importorskip("psycopg")
DSN = os.environ.get("SPJ_TEST_PG_DSN", "")
pytestmark = pytest.mark.skipif(not DSN, reason="sin PostgreSQL de prueba (SPJ_TEST_PG_DSN)")

import migrations.engine as engine  # noqa: E402
from backend.infrastructure.db.database import (  # noqa: E402
    DatabaseSettings,
    create_connection_factory,
)
from backend.shared.ids import new_uuid  # noqa: E402

T0 = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def conectar():
    nombre = f"t_{uuid.uuid4().hex[:12]}"
    base = create_connection_factory(DatabaseSettings.postgresql(DSN))
    c = base()
    with c.cursor() as cur:
        cur.execute(f"CREATE SCHEMA {nombre}")
        cur.execute(f"SET search_path TO {nombre}")
    c.commit()
    engine.up_postgresql(c)
    c.close()

    def abrir():
        x = base()
        with x.cursor() as cur:
            cur.execute(f"SET search_path TO {nombre}")
        x.commit()
        return x

    yield abrir
    c = base()
    with c.cursor() as cur:
        cur.execute(f"DROP SCHEMA {nombre} CASCADE")
    c.commit()
    c.close()


def test_sales_and_inventory_from_the_till_to_central_projections(conectar):
    from fastapi.testclient import TestClient

    from backend.api.central_app import CentralSyncWorkflow, create_central_app
    from backend.application.inventory.use_cases import PostInventoryMovementUseCase
    from backend.application.sync.central_projection import CentralProjector
    from backend.application.sync.replication_outbox import ReplicationOutboxService
    from backend.application.sync.station_admin import CentralStationAdmin
    from backend.domain.inventory.entities.inventory_movement import (
        InventoryMovement,
        InventoryMovementLine,
    )
    from backend.domain.inventory.enums import MovementType
    from backend.domain.sales.events import SaleEvents, sale_event_payload
    from backend.infrastructure.central.projection_repository import (
        PostgresCentralProjectionRepository,
    )
    from backend.infrastructure.central.sync_inbox_repository import (
        PostgresCentralInboxRepository,
    )
    from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork
    from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
    from backend.infrastructure.db.schema.sales_schema import create_sales_schema
    from backend.infrastructure.sync.http_transport import HttpReplicationTransport

    pg = conectar()
    emitida = CentralStationAdmin(PostgresCentralInboxRepository(pg)).register(
        station_id=new_uuid(), branch_id=new_uuid())
    pg.close()
    app = create_central_app(CentralSyncWorkflow(conectar, PostgresCentralInboxRepository,
                                                 PostgresCentralProjectionRepository))
    cliente = TestClient(app, base_url="http://testserver")

    caja = sqlite3.connect(":memory:")
    caja.row_factory = sqlite3.Row
    create_sales_schema(caja)
    create_inventory_schema(caja)
    importlib.import_module("migrations.standalone.350_replication_engine").run(caja)
    caja.commit()
    ReplicationOutboxService.register_station(caja, station_id=emitida.station_id,
                                              branch_id=emitida.branch_id)
    almacen, producto, ubicacion = new_uuid(), new_uuid(), new_uuid()

    def mover(tipo, cantidad, **linea):
        mov = InventoryMovement.create(
            movement_type=tipo, branch_id=emitida.branch_id, warehouse_id=almacen,
            source_module="sales", source_document_type="SALE", source_document_id=new_uuid(),
            operation_id=new_uuid(), created_by_user_id=new_uuid(),
            lines=[InventoryMovementLine.create(product_id=producto,
                                                quantity=Decimal(cantidad), **linea)])
        assert PostInventoryMovementUseCase().execute(caja, mov, actor_user_id=new_uuid(),
                                                      negative_allowed=True).success

    mover(MovementType.PURCHASE_RECEIPT, "20.000", to_location_id=ubicacion)
    mover(MovementType.SALE_ISSUE, "1.250", from_location_id=ubicacion)
    venta = sale_event_payload(
        SaleEvents.COMPLETED, operation_id=new_uuid(), entity_id=new_uuid(),
        branch_id=emitida.branch_id, user_id=new_uuid(), folio="A-0001",
        currency_code="MXN", gross_subtotal="137.50", discount_total="0",
        promotion_total="0", coupon_total="0", loyalty_total="0", tax_total="0",
        rounding_adjustment="0", total="137.50", change="12.50", channel="POS",
        payments=[{"method": "CASH", "amount": "150.00"}],
        lines=[{"product_id": producto, "quantity": "1.250", "amount": "137.50",
                "unit_cost": "71.2000"}])
    with SalesUnitOfWork(caja) as uow:
        uow.outbox.enqueue(event_id=venta["event_id"], event_name=venta["event_name"],
                           payload_json=json.dumps(venta), operation_id=venta["operation_id"])

    motor = ReplicationOutboxService(HttpReplicationTransport(
        "http://testserver", station_id=emitida.station_id, secret=emitida.secret,
        client=cliente, allow_insecure_localhost=True), rng=random.Random(5))
    resultado = motor.synchronize(caja, station_id=emitida.station_id, now=T0)
    assert resultado.synced == 3, resultado

    pg = conectar()
    with pg.cursor() as cur:
        cur.execute("SELECT total, change_given, folio FROM central_sales WHERE sale_id=%s",
                    (venta["entity_id"],))
        assert cur.fetchone() == (Decimal("137.50"), Decimal("12.50"), "A-0001")
        cur.execute("SELECT quantity, unit_cost FROM central_sale_lines WHERE sale_id=%s",
                    (venta["entity_id"],))
        assert cur.fetchone() == (Decimal("1.250"), Decimal("71.2000"))
        cur.execute("SELECT quantity, movements FROM central_stock_on_hand"
                    " WHERE product_id=%s AND warehouse_id=%s", (producto, almacen))
        central = cur.fetchone()
    local = sum(Decimal(str(r[0])) for r in caja.execute(
        "SELECT quantity FROM inventory_balances WHERE product_id=?", (producto,)))
    assert central == (local, 2) and local == Decimal("18.750")

    # Reproyectar no duplica nada.
    assert CentralProjector(PostgresCentralProjectionRepository(pg)).run_once().projected == 0
    with pg.cursor() as cur:
        cur.execute("SELECT count(*) FROM central_stock_effects")
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(*) FROM central_projection_log WHERE status='OK'")
        assert cur.fetchone()[0] == 3
    pg.close()
    caja.close()
