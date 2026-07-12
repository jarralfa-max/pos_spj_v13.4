# tests/test_recepcion_qr_service.py
"""Remediación F — Red de seguridad para la recepción por QR.

Caracteriza los efectos en BD de RecepcionQRService.procesar_recepcion (la
transacción de inventario extraída de RecepcionQRWidget): cabecera de recepción,
detalle, UPSERT de inventario con costo promedio ponderado, sync de
productos.existencia, movimiento de auditoría y cambio de estado de trazabilidad.
"""
import json

import pytest

from backend.shared.ids import new_uuid


@pytest.fixture
def db():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from migrations import engine
    engine.up(conn)
    conn.commit()
    return conn


def _seed(db):
    pid = "p1"
    db.execute("INSERT INTO productos (id,nombre,precio,precio_compra,existencia,unidad,activo) "
               "VALUES (?,?,?,?,?,?,1)", (pid, "Pollo", 95.0, 40.0, 5.0, "kg"))
    # inventario previo: 5 @ costo 40 (para probar el promedio ponderado)
    db.execute("INSERT INTO inventario_actual (id,producto_id,sucursal_id,cantidad,costo_promedio) "
               "VALUES (?,?,?,?,?)", (new_uuid(), pid, "1", 5.0, 40.0))
    # contenedor asignado con datos de pago
    datos = {"proveedor_id": "prov1", "condicion_pago": "liquidado",
             "metodo_pago": "efectivo", "monto_pagado": 500.0, "monto_total": 500.0}
    db.execute("INSERT INTO trazabilidad_qr (uuid_qr,tipo,proveedor_id,sucursal_id,estado,datos_extra) "
               "VALUES (?,?,?,?,'asignado',?)",
               ("QR1", "contenedor", "prov1", "1", json.dumps(datos)))
    db.commit()
    return pid


def test_procesar_recepcion_efectos_en_bd(db):
    from core.services.recepcion_qr_service import RecepcionQRService
    pid = _seed(db)
    svc = RecepcionQRService(db)

    rid = svc.procesar_recepcion(
        uuid_qr="QR1",
        items=[{"product_id": pid, "cantidad": 10.0, "costo_unitario": 50.0}],
        notas="recepcion test", sucursal_id="1", usuario="ana",
    )
    assert rid and isinstance(rid, str)

    # Cabecera de recepción
    rec = dict(db.execute("SELECT * FROM recepciones WHERE id=?", (rid,)).fetchone())
    assert rec["estado"] == "completada"
    assert rec["proveedor_id"] == "prov1"
    assert rec["monto_total"] == 500.0
    assert rec["saldo_pendiente"] == 0.0
    assert rec["uuid_qr"] == "QR1"

    # Detalle
    it = dict(db.execute("SELECT * FROM recepcion_items WHERE recepcion_id=?", (rid,)).fetchone())
    assert it["producto_id"] == pid and it["cantidad"] == 10.0 and it["costo_unitario"] == 50.0

    # Inventario: 5@40 + 10@50 → 15 unidades, costo promedio ponderado 46.666…
    inv = dict(db.execute(
        "SELECT cantidad, costo_promedio FROM inventario_actual WHERE producto_id=? AND sucursal_id='1'",
        (pid,)).fetchone())
    assert inv["cantidad"] == 15.0
    assert round(inv["costo_promedio"], 2) == 46.67

    # productos.existencia = SUM(inventario_actual) = 15; precio_compra = último costo
    prod = dict(db.execute("SELECT existencia, precio_compra FROM productos WHERE id=?", (pid,)).fetchone())
    assert prod["existencia"] == 15.0
    assert prod["precio_compra"] == 50.0

    # Movimiento de inventario (entrada/COMPRA)
    mov = dict(db.execute(
        "SELECT tipo, tipo_movimiento, cantidad FROM movimientos_inventario WHERE producto_id=?",
        (pid,)).fetchone())
    assert mov["tipo"] == "entrada" and mov["tipo_movimiento"] == "COMPRA" and mov["cantidad"] == 10.0

    # Trazabilidad marcada como recibida y ligada a la recepción
    tqr = dict(db.execute("SELECT estado, recepcion_id FROM trazabilidad_qr WHERE uuid_qr='QR1'").fetchone())
    assert tqr["estado"] == "recibido"
    assert tqr["recepcion_id"] == rid


def test_marcar_parcial_e_incidencia(db):
    from core.services.recepcion_qr_service import RecepcionQRService
    _seed(db)
    svc = RecepcionQRService(db)
    svc.marcar_recepcion_parcial("QR1")
    assert db.execute("SELECT estado FROM trazabilidad_qr WHERE uuid_qr='QR1'").fetchone()[0] == "recepcion_parcial"
    svc.marcar_incidencia("QR1", json.dumps({"tipo": "faltante", "descripcion": "x"}))
    assert db.execute("SELECT estado FROM trazabilidad_qr WHERE uuid_qr='QR1'").fetchone()[0] == "incidencia"
