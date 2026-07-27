"""Remediación F — red de seguridad para activos.py antes de extraer su SQL.

Caracteriza las operaciones que la UI de modulos/activos.py ejecutaba con SQL
embebido y que ahora delega en AssetService:

  · listar_activos_para_tabla   (SELECT * ... estado != 'baja')
  · dar_de_baja                 (UPDATE activos SET estado='baja')  ← write
  · listar_depreciacion_acumulada (JOIN depreciacion_acumulada/activos)
  · listar_mantenimientos       (JOIN mantenimientos/activos)
  · eliminar_mantenimiento      (DELETE FROM mantenimientos)        ← write
  · listar_activos_para_pdf / listar_mantenimientos_para_pdf
  · calcular_depreciacion_mensual (accrual legacy sobre activos_depreciacion)

Priority 0: se preserva el comportamiento exacto (mismo SQL, mismos efectos).
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


@pytest.fixture
def svc(db):
    from core.services.asset_service import AssetService
    return AssetService(db, treasury_service=None, finance_service=None)


def _nuevo_activo(db, nombre="Horno", estado="activo", valor=1000.0):
    aid = new_uuid()
    db.execute(
        "INSERT INTO activos (id, nombre, categoria, numero_serie, valor_adquisicion, "
        "valor_actual, vida_util_anios, depreciacion_anual, ubicacion, estado) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (aid, nombre, "Cocina", "SN-1", valor, valor, 5, 120.0, "Planta", estado),
    )
    db.commit()
    return aid


def test_listar_activos_para_tabla_oculta_baja(svc, db):
    activo = _nuevo_activo(db, "Vigente")
    _nuevo_activo(db, "Retirado", estado="baja")
    filas = svc.listar_activos_para_tabla()
    nombres = {f["nombre"] for f in filas}
    assert "Vigente" in nombres and "Retirado" not in nombres
    assert any(f["id"] == activo for f in filas)


def test_dar_de_baja_marca_estado(svc, db):
    aid = _nuevo_activo(db, "Baja")
    svc.dar_de_baja(aid)
    row = db.execute("SELECT estado FROM activos WHERE id=?", (aid,)).fetchone()
    assert row["estado"] == "baja"


def test_listar_mantenimientos_join(svc, db):
    aid = _nuevo_activo(db, "Compresor")
    mid = new_uuid()
    db.execute(
        "INSERT INTO mantenimientos (id, activo_id, tipo, descripcion, fecha_prog, estado) "
        "VALUES (?,?,?,?,?, 'pendiente')",
        (mid, aid, "preventivo", "Cambio de aceite", "2026-08-01"),
    )
    db.commit()
    filas = svc.listar_mantenimientos()
    assert any(f["id"] == mid and f["activo_nombre"] == "Compresor" for f in filas)


def test_eliminar_mantenimiento(svc, db):
    aid = _nuevo_activo(db, "Bomba")
    mid = new_uuid()
    db.execute(
        "INSERT INTO mantenimientos (id, activo_id, tipo, descripcion, fecha_prog, estado) "
        "VALUES (?,?,?,?,?, 'pendiente')",
        (mid, aid, "correctivo", "Sello", "2026-08-02"),
    )
    db.commit()
    svc.eliminar_mantenimiento(mid)
    assert db.execute("SELECT COUNT(*) FROM mantenimientos WHERE id=?", (mid,)).fetchone()[0] == 0


def test_listar_depreciacion_acumulada(svc, db):
    aid = _nuevo_activo(db, "Servidor")
    db.execute(
        "INSERT INTO depreciacion_acumulada (id, activo_id, periodo, monto_mes, acumulado) "
        "VALUES (?,?,?,?,?)",
        (new_uuid(), aid, "2026-07", 50.0, 50.0),
    )
    db.commit()
    filas = svc.listar_depreciacion_acumulada()
    assert any(f[0] == aid and f[1] == "Servidor" for f in filas)


def test_listado_pdf_helpers(svc, db):
    aid = _nuevo_activo(db, "Montacargas")
    mid = new_uuid()
    db.execute(
        "INSERT INTO mantenimientos (id, activo_id, tipo, descripcion, fecha_prog, estado, costo) "
        "VALUES (?,?,?,?,?, 'completado', 300)",
        (mid, aid, "preventivo", "Rev", "2026-07-01"),
    )
    db.commit()
    act_pdf = svc.listar_activos_para_pdf()
    assert any(r["nombre"] == "Montacargas" for r in act_pdf)
    mant_pdf = svc.listar_mantenimientos_para_pdf()
    assert any(r[0] == mid for r in mant_pdf)


def test_calcular_depreciacion_mensual_no_falla_born_clean(svc, db):
    """La tabla activos born-clean no tiene valor_residual: la rutina legacy
    debe degradar sin excepción (contrato: nunca rompe el scheduler)."""
    _nuevo_activo(db, "Legacy")
    res = svc.calcular_depreciacion_mensual("")
    assert isinstance(res, list)


def test_calcular_depreciacion_mensual_escribe_cuando_hay_columna(svc, db):
    """Con valor_residual disponible, aplica y registra la depreciación."""
    db.execute("ALTER TABLE activos ADD COLUMN valor_residual REAL DEFAULT 0")
    aid = new_uuid()
    db.execute(
        "INSERT INTO activos (id, nombre, categoria, numero_serie, valor_adquisicion, "
        "valor_actual, vida_util_anios, depreciacion_anual, estado, valor_residual) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (aid, "Equipo", "Cat", "SN", 1200.0, 1200.0, 5, 240.0, "activo", 0.0),
    )
    db.commit()
    res = svc.calcular_depreciacion_mensual("suc-1")
    assert any(r["id"] == aid for r in res)
    # valor_actual bajó exactamente 240/12 = 20
    nuevo = db.execute("SELECT valor_actual FROM activos WHERE id=?", (aid,)).fetchone()[0]
    assert abs(nuevo - 1180.0) < 0.001
    # asiento en la tabla legacy
    dep = db.execute(
        "SELECT COUNT(*) FROM activos_depreciacion WHERE activo_id=?", (aid,)
    ).fetchone()[0]
    assert dep == 1
