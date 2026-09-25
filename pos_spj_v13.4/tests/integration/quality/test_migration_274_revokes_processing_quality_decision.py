"""Migración 274: ningún rol conserva el permiso de Procesamiento para
registrar decisiones de calidad; el resto de los permisos no se toca."""
from __future__ import annotations

import importlib
import sqlite3

from backend.shared.ids import new_uuid


def _db():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE rol_permisos (id TEXT PRIMARY KEY, rol_id TEXT, modulo TEXT,"
              " accion TEXT, permitido INTEGER, UNIQUE(rol_id, modulo, accion))")
    for rol in ("jefe", "operario"):
        for modulo, accion in (("PRODUCCION", "calidad.registrar_decision"),
                               ("PRODUCCION", "calidad.ver"),
                               ("CALIDAD", "inspeccion.decidir")):
            c.execute("INSERT INTO rol_permisos VALUES (?,?,?,?,1)",
                      (new_uuid(), rol, modulo, accion))
    c.commit()
    return c


def _migrar(c):
    importlib.import_module(
        "migrations.standalone.274_revoke_processing_quality_decision_from_roles").run(c)


def test_the_processing_quality_decision_is_revoked_from_every_role():
    c = _db()
    _migrar(c)
    assert c.execute("SELECT COUNT(*) FROM rol_permisos WHERE modulo='PRODUCCION'"
                     " AND accion='calidad.registrar_decision'").fetchone()[0] == 0


def test_every_other_permission_is_kept_and_it_is_idempotent():
    c = _db()
    _migrar(c)
    _migrar(c)
    assert sorted(c.execute("SELECT DISTINCT modulo || '.' || accion FROM rol_permisos")) == [
        ("CALIDAD.inspeccion.decidir",), ("PRODUCCION.calidad.ver",)]
    assert c.execute("SELECT COUNT(*) FROM rol_permisos").fetchone()[0] == 4


def test_it_is_registered_after_273():
    from migrations.engine import MIGRATIONS

    ids = [m.version if hasattr(m, "version") else m[0] for m in MIGRATIONS]
    assert ids.index("274") == ids.index("273") + 1
