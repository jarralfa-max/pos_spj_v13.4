# tests/test_rrhh_catalog_service.py
"""Remediación F — Red de seguridad para RRHHCatalogService.

Caracteriza los efectos en BD del SQL extraído de modulos/rrhh.py: catálogos
(roles de turno, puestos), vacaciones, evaluaciones, recibo de nómina, KPIs y
reglas laborales. Incluye el bugfix de identidad born-clean de turno_roles.
"""
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


def _svc(db):
    from core.services.rrhh_catalog_service import RRHHCatalogService
    return RRHHCatalogService(db)


def test_roles_turno_crud_genera_uuid(db):
    """Bugfix: crear_rol_turno asigna un id UUIDv7 (antes el INSERT omitía id →
    filas con id=NULL imposibles de eliminar)."""
    svc = _svc(db)
    rid = svc.crear_rol_turno("Mañana", "08:00", "16:00", "#3498db")
    assert rid and isinstance(rid, str)
    rows = svc.listar_roles_turno()
    assert len(rows) == 1
    assert rows[0][0] == rid          # id no es NULL
    assert rows[0][1] == "Mañana"
    # eliminar por id ahora funciona
    svc.eliminar_rol_turno(rid)
    assert svc.listar_roles_turno() == []


def test_puestos_crud(db):
    svc = _svc(db)
    pid = svc.crear_puesto("Cajero", "Atiende caja")
    assert pid and isinstance(pid, str)
    row = svc.obtener_puesto(pid)
    assert row[0] == "Cajero" and row[1] == "Atiende caja"
    svc.actualizar_puesto(pid, "Cajero Senior", "Turno noche")
    assert svc.obtener_puesto(pid)[0] == "Cajero Senior"
    assert len(svc.listar_puestos()) == 1
    svc.desactivar_puesto(pid)
    assert svc.listar_puestos() == []   # activo=0 ya no aparece


def test_vacaciones_estado(db):
    svc = _svc(db)
    pid = "e1"
    db.execute("INSERT INTO personal (id,nombre,activo) VALUES (?, 'Ana', 1)", (pid,))
    vid = new_uuid()
    db.execute("INSERT INTO vacaciones_personal (id,personal_id,tipo,fecha_inicio,fecha_fin,dias,estado) "
               "VALUES (?,?,?,?,?,?,?)", (vid, pid, "vacaciones", "2026-01-01", "2026-01-05", 5, "pendiente"))
    db.commit()
    svc.actualizar_estado_vacacion(vid, "aprobado")
    assert db.execute("SELECT estado FROM vacaciones_personal WHERE id=?", (vid,)).fetchone()[0] == "aprobado"


def test_evaluaciones(db):
    svc = _svc(db)
    pid = "e1"
    db.execute("INSERT INTO personal (id,nombre,apellidos,activo) VALUES (?, 'Ana','Lopez', 1)", (pid,))
    db.commit()
    eid = svc.crear_evaluacion(pid, "2026-Q1", 9, "jefe")
    assert eid and isinstance(eid, str)
    rows = svc.listar_evaluaciones()
    assert len(rows) == 1
    assert rows[0][0] == "Ana Lopez"
    assert rows[0][2] == 9


def test_recibo_nomina_lookup(db):
    svc = _svc(db)
    pid = "e1"
    db.execute("INSERT INTO personal (id,nombre,apellidos,puesto,rfc,activo) "
               "VALUES (?, 'Ana','Lopez','Cajero','XAXX010101000', 1)", (pid,))
    pago = new_uuid()
    db.execute("INSERT INTO nomina_pagos (id,empleado_id,periodo_inicio,periodo_fin,total,fecha) "
               "VALUES (?,?,?,?,?,?)", (pago, pid, "2026-01-01", "2026-01-15", 5000.0, "2026-01-16"))
    db.commit()
    row = svc.obtener_pago_por_id(pago)
    assert row is not None and row["nombre"] == "Ana" and row["total"] == 5000.0
    row2 = svc.obtener_ultimo_pago_empleado(pid)
    assert row2 is not None and row2["id"] == pago


def test_reglas_laborales_config(db):
    svc = _svc(db)
    assert svc.obtener_config("hr_max_dias_consecutivos") is None
    svc.guardar_config("hr_max_dias_consecutivos", "6", "Regla laboral LFT")
    assert svc.obtener_config("hr_max_dias_consecutivos")[0] == "6"
    # INSERT OR REPLACE actualiza
    svc.guardar_config("hr_max_dias_consecutivos", "7", "Regla laboral LFT")
    assert svc.obtener_config("hr_max_dias_consecutivos")[0] == "7"


def test_kpi_empleados_activos(db):
    svc = _svc(db)
    db.execute("INSERT INTO personal (id,nombre,salario,activo) VALUES ('a','A',1000,1)")
    db.execute("INSERT INTO personal (id,nombre,salario,activo) VALUES ('b','B',2000,0)")
    db.commit()
    assert svc.contar_empleados_activos() == 1
    assert svc.sumar_nomina_activos() == 1000.0
