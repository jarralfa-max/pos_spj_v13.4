"""CARACTERIZACIÓN (SDLC-CORE-012): transformación directa y su disponibilidad, tal
como funcionan HOY. No dicen que sea correcto: `CAMBIA: <ítem>` indica qué ítem
debe actualizarlas al corregir.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.meat_processing.queries.direct_transformation_query_service import (
    DirectTransformationQueryService,
)
from backend.shared.ids import new_uuid
from tests.integration._reversible_cutting import active_yield_profile
from tests.integration.meat_processing._generic_plant import KG, Planta, build_db
from tests.integration.meat_processing.test_production_audit_32cfbf import _direct, _pollo

_P = MeatProcessingPermissions


@pytest.fixture
def conn():
    c = build_db()
    yield c
    c.close()


def _movimientos(conn, orden: str) -> list[tuple[str, str, Decimal]]:
    """(tipo de movimiento, producto, cantidad) que la orden dejó en el libro."""
    return [(str(tipo), str(producto), Decimal(str(cantidad))) for tipo, producto, cantidad in
            conn.execute(
                "SELECT m.movement_type, l.product_id, l.quantity FROM inventory_ledger m"
                " JOIN inventory_ledger_lines l ON l.movement_id = m.id"
                " WHERE m.source_document_id = ? ORDER BY m.rowid, l.rowid", (orden,))]


def test_a_transformation_posts_one_consumption_and_its_outputs(conn):
    """CARACTERIZACIÓN — la conserva SDLC-PROC-002: un consumo de la entrada y una
    salida por producto de existencia; la merma no entra al inventario."""
    p = Planta(conn)
    pollo, pechuga, pierna, merma, lote = _pollo(p)
    r = _direct(conn, {p.operario: (_P.DIRECT_TRANSFORMATION_EXECUTE,)}).execute(
        conn, operation_id=new_uuid(), branch_id=p.branch, lot_id=lote,
        input_weight=Decimal("20"), actor_user_id=p.operario, outputs=[
            {"product_id": pechuga, "weight": Decimal("6.9")},
            {"product_id": pierna, "weight": Decimal("11")},
            {"product_id": merma, "weight": Decimal("2.1")}])
    assert r.success, r.message

    movimientos = _movimientos(conn, r.data["order_id"])

    consumos = [m for m in movimientos if m[1] == pollo]
    assert [m[2] for m in consumos] == [Decimal("20")]
    salidas = {m[1]: m[2] for m in movimientos if m[1] != pollo}
    assert salidas == {pechuga: Decimal("6.9"), pierna: Decimal("11")}
    assert p.saldo(pollo) == Decimal("20")


def _por_piezas(p: Planta, cantidad: str):
    pollo = p.producto("Pollo por pieza")
    p.conn.execute("UPDATE products SET base_unit_id='unit-pza' WHERE id=?", (pollo,))
    active_yield_profile(p.conn, product_id=pollo, outputs=[
        {"product_id": p.producto("Corte"), "output_type": "MAIN_PRODUCT",
         "expected_yield_pct": "100", "unit_id": KG}])
    return pollo, p.existencia(pollo, cantidad, lote="L-PIEZAS")


def test_pieces_are_reported_as_kilograms(conn):
    """CARACTERIZACIÓN — CAMBIA: SDLC-PROC-002 (defecto conocido). El saldo en piezas
    se suma tal cual y se presenta como `available_kg`."""
    p = Planta(conn)
    _pollo_pza, lote = _por_piezas(p, "30")

    (fila,) = DirectTransformationQueryService(conn).lots(p.branch)

    assert fila.lot_id == lote
    assert fila.available_kg == Decimal("30.000")


def test_reserved_quantity_is_subtracted_from_what_can_be_transformed(conn):
    """CARACTERIZACIÓN — CAMBIA: SDLC-PROC-002 sólo en la aritmética (hoy REAL)."""
    p = Planta(conn)
    pollo, _pechuga, _pierna, _merma, lote = _pollo(p, kg="10.5")
    conn.execute("UPDATE inventory_balances SET reserved_quantity='0.25' WHERE product_id=?",
                 (pollo,))

    (fila,) = DirectTransformationQueryService(conn).lots(p.branch)

    assert fila.lot_id == lote
    assert fila.available_kg == Decimal("10.250")
