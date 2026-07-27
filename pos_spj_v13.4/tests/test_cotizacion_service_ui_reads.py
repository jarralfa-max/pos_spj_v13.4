# tests/test_cotizacion_service_ui_reads.py
"""Remediación F — Red de seguridad para las lecturas/estados de cotizaciones.

Caracteriza los métodos extraídos de modulos/cotizaciones.py hacia CotizacionService:
aprobar/rechazar, obtener cabecera+detalle (detalle/PDF) y las lecturas para el
envío por WhatsApp (join cliente, detalle, nombre_empresa).
"""
import sqlite3

import pytest


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from migrations import engine
    engine.up(conn)
    conn.commit()
    return conn


def _svc(db):
    from core.services.cotizacion_service import CotizacionService
    return CotizacionService(db)


def _cotizacion(db, svc):
    db.execute("INSERT INTO clientes (id,nombre,telefono,activo) VALUES ('cl1','Ana','+521999',1)")
    db.execute("INSERT INTO productos (id,nombre,precio,unidad,activo) VALUES ('p1','Pollo',95.0,'kg',1)")
    db.commit()
    res = svc.crear(
        items=[{"product_id": "p1", "nombre": "Pollo", "cantidad": 2,
                "unidad": "kg", "precio_unitario": 95.0, "descuento_pct": 0}],
        cliente_id="cl1", cliente_nombre="Ana", notas="x", vigencia_dias=7)
    return res["cotizacion_id"], res["folio"]


def test_aprobar_rechazar(db):
    svc = _svc(db)
    cid, _ = _cotizacion(db, svc)
    svc.aprobar(cid)
    assert db.execute("SELECT estado FROM cotizaciones WHERE id=?", (cid,)).fetchone()[0] == "aprobada"
    svc.rechazar(cid)
    assert db.execute("SELECT estado FROM cotizaciones WHERE id=?", (cid,)).fetchone()[0] == "rechazada"


def test_obtener_y_detalle(db):
    svc = _svc(db)
    cid, folio = _cotizacion(db, svc)
    row = svc.obtener(cid)
    assert row is not None and dict(row)["folio"] == folio
    det = svc.obtener_detalle(cid)
    assert len(det) == 1 and dict(det[0])["producto_id"] == "p1"


def test_lecturas_whatsapp(db):
    svc = _svc(db)
    cid, folio = _cotizacion(db, svc)
    # por id
    rd = svc.obtener_para_whatsapp(cid)
    assert rd is not None
    f, total, venc, nombre_cli, telefono = rd
    assert f == folio and nombre_cli == "Ana" and telefono == "+521999"
    # por folio también
    assert svc.obtener_para_whatsapp(folio) is not None
    det = svc.obtener_detalle_whatsapp(cid)
    assert len(det) == 1 and det[0][0] == "Pollo"
    # nombre empresa
    assert svc.obtener_nombre_empresa() is None
    db.execute("INSERT OR REPLACE INTO configuraciones(clave,valor) VALUES('nombre_empresa','SPJ Foods')")
    db.commit()
    assert svc.obtener_nombre_empresa()[0] == "SPJ Foods"
