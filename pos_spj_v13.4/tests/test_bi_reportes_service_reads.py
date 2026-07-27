"""Remediación F — red de seguridad para modulos/reportes_bi_v2.py.

Caracteriza el SQL extraído de la UI del dashboard BI:
  · BIRepository.get_kpis_dia           (barra de KPIs del día)
  · ExportService.export_ventas_hoy_pdf (fallback PDF de ventas del día)
"""
import sqlite3

import pytest

from backend.shared.ids import new_uuid


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from migrations import engine
    engine.up(conn)
    conn.commit()
    return conn


def _venta_hoy(db, total, cliente_id, estado="completada"):
    vid = new_uuid()
    db.execute(
        "INSERT INTO ventas (id, folio, total, cliente_id, estado, fecha) "
        "VALUES (?,?,?,?,?, datetime('now'))",
        (vid, f"F-{total}", total, cliente_id, estado),
    )
    return vid


def test_get_kpis_dia_agrega_ventas_y_clientes(db):
    from repositories.bi_repository import BIRepository
    _venta_hoy(db, 100.0, "cli-1")
    _venta_hoy(db, 300.0, "cli-2")
    _venta_hoy(db, 999.0, "cli-3", estado="cancelada")  # excluida
    db.commit()

    kpi = BIRepository(db).get_kpis_dia()
    assert kpi["ventas"] == 400.0
    assert kpi["tickets"] == 2
    assert kpi["clientes"] == 2


def test_get_kpis_dia_margen(db):
    from repositories.bi_repository import BIRepository
    pid = new_uuid()
    db.execute(
        "INSERT INTO productos (id, nombre, precio, precio_compra, activo) "
        "VALUES (?,?,?,?,1)",
        (pid, "Prod", 50.0, 20.0),
    )
    vid = _venta_hoy(db, 100.0, "cli-1")
    db.execute(
        "INSERT INTO detalles_venta (id, venta_id, producto_id, cantidad, precio_unitario) "
        "VALUES (?,?,?,?,?)",
        (new_uuid(), vid, pid, 2, 50.0),
    )
    db.commit()

    kpi = BIRepository(db).get_kpis_dia()
    assert kpi["ingresos"] == 100.0   # 2 * 50
    assert kpi["costo"] == 40.0       # 2 * 20


def test_get_kpis_dia_vacio_no_falla(db):
    from repositories.bi_repository import BIRepository
    kpi = BIRepository(db).get_kpis_dia()
    assert kpi == {"ventas": 0.0, "tickets": 0, "clientes": 0,
                   "ingresos": 0.0, "costo": 0.0}


def test_export_ventas_hoy_pdf(db, tmp_path):
    from core.services.export_service import ExportService
    _venta_hoy(db, 250.0, "cli-1")
    db.commit()
    destino = str(tmp_path / "ventas_hoy.pdf")
    res = ExportService(db).export_ventas_hoy_pdf(destino)
    # 1 venta del día exportada (PDF o fallback CSV si reportlab no está)
    assert res.rows == 1
