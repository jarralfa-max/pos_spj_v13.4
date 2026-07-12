# tests/test_rrhh_turnos_service.py
"""Remediación F — Red de seguridad para RRHHTurnosService.

Caracteriza los efectos en BD del SQL extraído de modulos/rrhh_turnos.py:
roles de turno (CRUD), asignaciones (CRUD), lookups, config de notificaciones y
bitácora de envíos. Incluye los bugfixes de identidad born-clean (turno_roles y
turno_asignaciones ya no insertan id=NULL).
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
    from core.services.rrhh_turnos_service import RRHHTurnosService
    return RRHHTurnosService(db)


def _emp(db, pid="e1", nombre="Ana", tel="+521999"):
    db.execute("INSERT INTO personal (id,nombre,apellidos,telefono,activo) VALUES (?,?,?,?,1)",
               (pid, nombre, "Lopez", tel))
    db.commit()
    return pid


def test_roles_crud_genera_uuid(db):
    svc = _svc(db)
    rid = svc.crear_rol("Mañana", "08:00", "16:00", "turno matutino")
    assert rid and isinstance(rid, str)
    rows = svc.listar_roles_activos()
    assert len(rows) == 1 and rows[0][0] == rid   # id no es NULL
    assert rows[0][1] == "Mañana" and rows[0][2] == "08:00-16:00"
    # editar
    svc.actualizar_rol(rid, "Matutino", "07:00", "15:00", "x")
    row = svc.obtener_rol(rid)
    assert row[0] == "Matutino" and row[1] == "07:00"
    # lookup
    assert [r[0] for r in svc.listar_roles_lookup()] == [rid]
    # baja lógica
    svc.desactivar_rol(rid)
    assert svc.listar_roles_activos() == []


def test_asignaciones_crud_genera_uuid(db):
    svc = _svc(db)
    pid = _emp(db)
    rid = svc.crear_rol("Mañana", "08:00", "16:00", "")
    aid = svc.crear_asignacion(pid, rid, "2026-01-01", "2026-04-01",
                               "Domingo", 7, 1, 1)
    assert aid and isinstance(aid, str)
    rows = svc.listar_asignaciones()
    assert len(rows) == 1
    assert rows[0][0] == aid                      # id no es NULL
    assert rows[0][1] == "Ana Lopez" and rows[0][2] == "Mañana"
    assert rows[0][3] == "Domingo"
    # editar
    svc.actualizar_asignacion(aid, pid, rid, "2026-01-01", "2026-05-01",
                              "Lunes", 5, 0, 1)
    assert svc.listar_asignaciones()[0][3] == "Lunes"
    # baja lógica
    svc.desactivar_asignacion(aid)
    assert svc.listar_asignaciones() == []


def test_lookups(db):
    svc = _svc(db)
    _emp(db, "e1", "Ana")
    _emp(db, "e2", "Beto")
    emps = svc.listar_empleados_lookup()
    assert {r[1].strip() for r in emps} == {"Ana Lopez", "Beto Lopez"}


def test_config_notif(db):
    svc = _svc(db)
    assert svc.obtener_config("turnos_notif_activas") is None
    svc.guardar_config("turnos_notif_activas", "1")
    assert svc.obtener_config("turnos_notif_activas")[0] == "1"
    # ON CONFLICT actualiza
    svc.guardar_config("turnos_notif_activas", "0")
    assert svc.obtener_config("turnos_notif_activas")[0] == "0"


def test_notificar_pendientes_y_bitacora(db):
    svc = _svc(db)
    pid = _emp(db)
    rid = svc.crear_rol("Mañana", "08:00", "16:00", "")
    svc.crear_asignacion(pid, rid, "2026-01-01", None, "Domingo", 7, 1, 1)
    rows = svc.listar_asignaciones_para_notificar("2026-07-08")
    assert len(rows) == 1
    asig_id, nombre, tel, dia, ns, nd = rows[0]
    assert nombre == "Ana" and tel == "+521999" and dia == "Domingo"
    # registrar bitácora (commit por fila)
    svc.registrar_notificacion(asig_id, "semana", "hola")
    log = db.execute("SELECT tipo, mensaje FROM turno_notificaciones_log").fetchall()
    assert len(log) == 1 and log[0][0] == "semana" and log[0][1] == "hola"
