"""Compra crea lotes y movimientos_lote con identidad UUIDv7 (sin lotes.uuid).

Regresión del bug: INSERT INTO lotes(uuid, ...) contra un schema sin columna
uuid + randomblob como identidad. La identidad canónica es lotes.id (UUIDv7).
"""
from __future__ import annotations

import uuid as _uuid

from backend.shared.ids import new_uuid
from core.services.lote_service import LoteService
from core.services.purchase_service import PurchaseService
from tests.integration._born_clean_db import make_db


def _producto(conn) -> str:
    pid = new_uuid()
    conn.execute(
        "INSERT INTO productos (id, nombre, activo, existencia) VALUES (?, 'Pollo', 1, 0)",
        (pid,),
    )
    return pid


def test_purchase_creates_lot_with_uuid_identity():
    conn = make_db()
    pid = _producto(conn)
    svc = PurchaseService(conn, purchase_repo=None, inventory_service=None, finance_service=None)

    compra_id, sucursal_id, proveedor_id = new_uuid(), new_uuid(), new_uuid()
    svc._crear_lotes_compra(
        compra_id=compra_id,
        folio="C-777",
        items=[{"product_id": pid, "qty": 12.5, "unit_cost": 80.0}],
        proveedor_id=proveedor_id,
        sucursal_id=sucursal_id,
        usuario="tester",
    )

    lote = conn.execute(
        "SELECT id, producto_id, numero_lote, proveedor_id, sucursal_id, "
        " peso_inicial_kg, costo_kg, estado FROM lotes WHERE producto_id=?",
        (pid,),
    ).fetchone()
    assert lote is not None, "la compra debe crear el lote (bug lotes.uuid)"
    _uuid.UUID(lote[0])                      # id es UUID válido
    assert lote[1] == pid
    assert lote[2] == f"C-777-P{pid}"
    assert lote[3] == proveedor_id and lote[4] == sucursal_id
    assert lote[5] == 12.5 and lote[6] == 80.0 and lote[7] == "activo"

    mov = conn.execute(
        "SELECT id, lote_id, tipo, cantidad_kg FROM movimientos_lote WHERE lote_id=?",
        (lote[0],),
    ).fetchone()
    assert mov is not None
    _uuid.UUID(mov[0])                       # movimiento con id UUID propio
    assert mov[2] == "recepcion" and mov[3] == 12.5


def test_lote_service_registers_lot_and_fifo_with_uuid_ids():
    conn = make_db()
    pid = _producto(conn)
    svc = LoteService(conn, sucursal_id=new_uuid(), usuario="tester")

    lote_id = svc.registrar_lote(pid, peso_kg=10.0, costo_kg=50.0)
    _uuid.UUID(lote_id)

    afectados = svc.descargar_fifo(pid, 4.0, referencia="V-1")
    assert afectados and afectados[0]["lote_id"] == lote_id
    peso = conn.execute(
        "SELECT peso_actual_kg FROM lotes WHERE id=?", (lote_id,)
    ).fetchone()[0]
    assert peso == 6.0

    movs = conn.execute(
        "SELECT id FROM movimientos_lote WHERE lote_id=?", (lote_id,)
    ).fetchall()
    assert len(movs) == 2
    for (mid,) in movs:
        _uuid.UUID(mid)


def test_no_randomblob_or_uuid_column_in_lot_paths():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for rel in ("core/services/purchase_service.py", "core/services/lote_service.py"):
        raw = (root / rel).read_text(encoding="utf-8")
        code = "\n".join(
            l for l in raw.splitlines() if not l.strip().startswith("#")
        )
        assert "randomblob" not in code, f"{rel} usa randomblob como identidad"
        assert "INTO lotes (uuid" not in code.replace("\n", " ")
