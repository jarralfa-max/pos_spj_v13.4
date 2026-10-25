"""Proyecciones centrales (Slice 5) sin PostgreSQL.

Los movimientos de inventario salen del caso de uso REAL y pasan por el mismo
lector de fuentes del motor de replicación: lo que el servidor suma es lo que la
estación aplicó a sus saldos. La batería contra PostgreSQL real está en
`tests/integration/central_pg/test_central_projection_pg.py` (CI).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.application.inventory.use_cases import PostInventoryMovementUseCase
from backend.application.inventory.use_cases.reverse_inventory_movement import (
    ReverseInventoryMovementUseCase,
)
from backend.application.sync.central_projection import (
    CentralProjector,
    ProjectionError,
    sale_return_row,
    sale_rows,
    stock_rows,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import MovementType
from backend.domain.sales.events import SaleEvents, sale_event_payload
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.sync.replication_sources import ReplicationSource
from backend.shared.ids import new_uuid

T0 = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
SUCURSAL, ALMACEN, PRODUCTO, ESTACION = new_uuid(), new_uuid(), new_uuid(), new_uuid()
UBICACION = new_uuid()


@pytest.fixture
def inv():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _mover(conn, tipo, cantidad, **linea):
    renglon = InventoryMovementLine.create(product_id=PRODUCTO, quantity=Decimal(cantidad),
                                           **linea)
    mov = InventoryMovement.create(
        movement_type=tipo, branch_id=SUCURSAL, warehouse_id=ALMACEN,
        source_module="sales", source_document_type="SALE", source_document_id=new_uuid(),
        operation_id=new_uuid(), created_by_user_id=new_uuid(), lines=[renglon])
    resultado = PostInventoryMovementUseCase().execute(conn, mov, actor_user_id=new_uuid(),
                                                       negative_allowed=True)
    assert resultado.success, resultado.message
    return mov.id


def _hechos(conn) -> list[dict]:
    """Como llegarían al libro central: el outbox real normalizado por el motor."""
    fuente = ReplicationSource("inventory", "inventory_outbox", "stock")
    hechos = []
    for fila in conn.execute("SELECT * FROM inventory_outbox ORDER BY created_at, rowid"):
        evento, _ = fuente.normalize(dict(fila), station_branch_id=SUCURSAL)
        hechos.append({"event_id": evento["event_id"], "event_type": evento["event_name"],
                       "aggregate_id": evento["entity_id"], "branch_id": evento["branch_id"],
                       "station_id": ESTACION, "occurred_at": T0,
                       "payload": json.loads(json.dumps(evento["payload"]))})
    return hechos


def _existencia(hechos) -> Decimal:
    return sum((e["quantity_delta"] for h in hechos for e in stock_rows(h)["effects"]),
               Decimal("0"))


# ── inventario: la central suma lo mismo que la estación ─────────────────────
def test_central_stock_matches_the_station_after_receipts_and_issues(inv):
    _mover(inv, MovementType.PURCHASE_RECEIPT, "10.500", to_location_id=UBICACION)
    _mover(inv, MovementType.SALE_ISSUE, "3.250", from_location_id=UBICACION)
    hechos = _hechos(inv)
    assert _existencia(hechos) == Decimal("7.250")
    local = sum(Decimal(str(r[0])) for r in inv.execute(
        "SELECT quantity FROM inventory_balances WHERE product_id=?", (PRODUCTO,)))
    assert local == Decimal("7.250")
    movimiento = stock_rows(hechos[0])["movement"]
    assert movimiento["movement_type"] == "PURCHASE_RECEIPT"
    assert movimiento["document_module"] == "sales" and movimiento["warehouse_id"] == ALMACEN


def test_a_reversal_projects_the_exact_inverse(inv):
    _mover(inv, MovementType.PURCHASE_RECEIPT, "10", to_location_id=UBICACION)
    salida = _mover(inv, MovementType.SALE_ISSUE, "4", from_location_id=UBICACION)
    resultado = ReverseInventoryMovementUseCase().execute(
        inv, movement_id=salida, actor_user_id=new_uuid(), reason="error de captura",
        operation_id=new_uuid())
    assert resultado.success, resultado.message
    hechos = _hechos(inv)
    reversa = stock_rows(hechos[-1])["movement"]
    assert reversa["movement_type"] == "REVERSAL" and reversa["reversal_of_id"] == salida
    assert _existencia(hechos) == Decimal("10")


def test_a_movement_from_before_slice_5_is_not_invented():
    viejo = {"event_id": new_uuid(), "event_type": "INVENTORY_MOVEMENT_POSTED",
             "aggregate_id": new_uuid(), "branch_id": SUCURSAL, "station_id": ESTACION,
             "occurred_at": T0, "payload": {"movement_type": "SALE_ISSUE",
                                            "warehouse_id": ALMACEN}}
    with pytest.raises(ProjectionError, match="sin efectos"):
        stock_rows(viejo)


# ── ventas ───────────────────────────────────────────────────────────────────
def _venta_completada(**cambios):
    datos = dict(sale_id=new_uuid(), folio="A-0001", customer_id=None, currency_code="MXN",
                 gross_subtotal="120.00", discount_total="10.00", promotion_total="0",
                 coupon_total="0", loyalty_total="0", tax_total="0",
                 rounding_adjustment="0", total="110.00",
                 payments=[{"method": "CASH", "amount": "100.00"},
                           {"method": "CARD", "amount": "10.00"}],
                 change="0", channel="POS",
                 lines=[{"product_id": PRODUCTO, "quantity": "1.250", "amount": "110.00",
                         "unit_cost": "60.5000"}])
    datos.update(cambios)
    evento = sale_event_payload(SaleEvents.COMPLETED, operation_id=new_uuid(),
                                entity_id=datos["sale_id"], branch_id=SUCURSAL,
                                user_id=new_uuid(), **datos)
    return {"event_id": evento["event_id"], "event_type": evento["event_name"],
            "aggregate_id": evento["entity_id"], "branch_id": SUCURSAL, "station_id": ESTACION,
            "occurred_at": T0, "payload": json.loads(json.dumps(evento["payload"]))}


def test_a_completed_sale_projects_totals_lines_and_payments_exactly():
    filas = sale_rows(_venta_completada())
    assert filas["sale"]["total"] == Decimal("110.00")
    assert filas["sale"]["discount_total"] == Decimal("10.00")
    assert filas["lines"][0]["quantity"] == Decimal("1.250")
    assert filas["lines"][0]["unit_cost"] == Decimal("60.5000")
    assert {p["method"]: p["amount"] for p in filas["payments"]} == {
        "CARD": Decimal("10.00"), "CASH": Decimal("100.00")}


def test_money_as_float_or_garbage_is_refused():
    with pytest.raises(ProjectionError, match="float"):
        sale_rows(_venta_completada(total=110.0))
    with pytest.raises(ProjectionError, match="exacto"):
        sale_rows(_venta_completada(total="ciento diez"))


def test_a_return_needs_its_amount():
    hecho = {"event_id": new_uuid(), "aggregate_id": new_uuid(), "branch_id": SUCURSAL,
             "occurred_at": T0, "payload": {"return_id": new_uuid(), "amount": "40.00"}}
    assert sale_return_row(hecho)["amount"] == Decimal("40.00")
    with pytest.raises(ProjectionError):
        sale_return_row({**hecho, "payload": {}})


# ── ciclo del proyector (libro en MEMORIA: simulación) ───────────────────────
class _Memoria:
    def __init__(self, hechos):
        self.hechos, self.registro, self.ventas, self.movimientos = list(hechos), {}, {}, {}
        self.commits = 0

    def pending_facts(self, *, projector, limit):
        return [h for h in self.hechos if (h["event_id"], projector) not in self.registro][:limit]

    @contextmanager
    def savepoint(self):
        copia = (dict(self.ventas), dict(self.movimientos))
        try:
            yield
        except Exception:
            self.ventas, self.movimientos = copia
            raise

    def log(self, *, event_id, projector, status, error):
        self.registro[(event_id, projector)] = (status, error)

    def upsert_sale(self, rows):
        self.ventas.setdefault(rows["sale"]["sale_id"], rows)

    def set_sale_status(self, *, sale_id, status, event_id):
        if sale_id in self.ventas:
            self.ventas[sale_id]["sale"]["status"] = status

    def add_sale_return(self, row):
        pass

    def add_stock_movement(self, rows):
        self.movimientos.setdefault(rows["movement"]["movement_id"], rows)

    def commit(self):
        self.commits += 1


def test_projector_is_idempotent_and_a_bad_fact_does_not_block_the_rest(inv):
    _mover(inv, MovementType.PURCHASE_RECEIPT, "5", to_location_id=UBICACION)
    venta = _venta_completada()
    mala = _venta_completada(total=1.5)                       # float → ERROR
    otro = {**venta, "event_id": new_uuid(), "event_type": "SALE_RECEIPT_REQUESTED"}
    memoria = _Memoria([*_hechos(inv), mala, venta, otro])
    corrida = CentralProjector(memoria).run_once()
    assert (corrida.projected, corrida.skipped, corrida.errors) == (2, 1, 1)
    assert venta["aggregate_id"] in memoria.ventas and len(memoria.movimientos) == 1
    assert memoria.registro[(mala["event_id"], "central_v1")][0] == "ERROR"
    assert CentralProjector(memoria).run_once().projected == 0    # nada pendiente
    cancelacion = {**venta, "event_id": new_uuid(), "event_type": "SALE_CANCELLED"}
    memoria.hechos.append(cancelacion)
    CentralProjector(memoria).run_once()
    assert memoria.ventas[venta["aggregate_id"]]["sale"]["status"] == "CANCELLED"
