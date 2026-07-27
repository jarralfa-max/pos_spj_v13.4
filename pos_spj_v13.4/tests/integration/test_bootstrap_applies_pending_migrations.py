"""Regresión CRÍTICA: el arranque debe aplicar migraciones pendientes a DBs existentes.

Bug raíz del reporte "ningún bug se solucionó realmente": `bootstrap_database`
solo ejecutaba `_run_migrations` cuando la DB estaba VACÍA. Toda instalación
con DB viva quedaba congelada en su schema: las migraciones nuevas
(locked_reason, roles UUIDv7, usuario_permisos, loyalty_snapshots, anticipos…)
jamás llegaban al runtime aunque el código de la rama estuviera actualizado.

Contrato validado aquí:
  1. DB existente con migraciones pendientes → bootstrap las aplica.
  2. DB vacía → nace born-clean completa (comportamiento previo intacto).
  3. verify_only=True → NO migra (solo verifica).
  4. main.py usa bootstrap_database como ruta primaria de arranque.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.shared.ids import SYSTEM_ROLE_UUIDS

ROOT = Path(__file__).resolve().parents[2]


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _make_legacy_db(db_path: str) -> None:
    """Simula la DB del usuario: schema viejo, todo marcado aplicado excepto 115/116."""
    from migrations.engine import MIGRATIONS

    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT);
        CREATE TABLE usuarios (
            id TEXT PRIMARY KEY, username TEXT, nombre TEXT, activo INTEGER DEFAULT 1
        );
        CREATE TABLE roles (id TEXT PRIMARY KEY, nombre TEXT UNIQUE);
        CREATE TABLE rol_permisos (rol_id TEXT, permiso TEXT);
        CREATE TABLE usuarios_roles (usuario_id TEXT, rol_id TEXT);
        CREATE TABLE schema_migrations (
            version TEXT NOT NULL PRIMARY KEY,
            executed_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    # Identidad legacy de roles: enteros sembrados por la 047 vieja.
    conn.execute("INSERT INTO roles (id, nombre) VALUES ('1', 'admin')")
    conn.execute("INSERT INTO roles (id, nombre) VALUES ('3', 'cajero')")
    conn.execute("INSERT INTO rol_permisos (rol_id, permiso) VALUES ('1', 'VENTAS.ver')")
    conn.execute("INSERT INTO usuarios_roles (usuario_id, rol_id) VALUES ('u-1', '3')")
    for mig in MIGRATIONS:
        if mig.version not in ("115", "116"):
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)", (mig.version,)
            )
    conn.commit()
    conn.close()


def test_existing_db_receives_pending_migrations(tmp_path):
    from scripts.bootstrap_db import bootstrap_database

    db_path = str(tmp_path / "legacy.db")
    _make_legacy_db(db_path)

    conn = sqlite3.connect(db_path)
    assert "locked_reason" not in _columns(conn, "usuarios")
    conn.close()

    bootstrap_database(db_path)

    conn = sqlite3.connect(db_path)
    try:
        # 115: columnas de bloqueo/desbloqueo llegaron a la DB existente.
        cols = _columns(conn, "usuarios")
        assert {"locked_reason", "bloqueado_hasta", "intentos_fallidos"} <= cols
        # 115: tablas de overrides RBAC creadas.
        tablas = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {"usuario_permisos", "usuario_sucursal_permisos"} <= tablas
        # 116: roles remapeados de enteros a UUIDv7 canónicos, FKs propagadas.
        roles = dict(conn.execute("SELECT nombre, id FROM roles").fetchall())
        assert roles["admin"] == SYSTEM_ROLE_UUIDS["admin"]
        assert roles["cajero"] == SYSTEM_ROLE_UUIDS["cajero"]
        rol_perm = conn.execute("SELECT rol_id FROM rol_permisos").fetchone()[0]
        assert rol_perm == SYSTEM_ROLE_UUIDS["admin"]
        usr_rol = conn.execute("SELECT rol_id FROM usuarios_roles").fetchone()[0]
        assert usr_rol == SYSTEM_ROLE_UUIDS["cajero"]
        # Quedaron registradas como aplicadas (no se re-ejecutan en el siguiente boot).
        aplicadas = {
            r[0]
            for r in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        assert {"115", "116"} <= aplicadas
    finally:
        conn.close()


def test_empty_db_is_born_clean(tmp_path):
    from scripts.bootstrap_db import bootstrap_database

    db_path = str(tmp_path / "fresh.db")
    bootstrap_database(db_path)

    conn = sqlite3.connect(db_path)
    try:
        assert "locked_reason" in _columns(conn, "usuarios")
        admin_id = conn.execute(
            "SELECT id FROM roles WHERE nombre='admin'"
        ).fetchone()[0]
        assert admin_id == SYSTEM_ROLE_UUIDS["admin"]
    finally:
        conn.close()


def test_verify_only_does_not_migrate(tmp_path):
    from scripts.bootstrap_db import bootstrap_database

    db_path = str(tmp_path / "legacy_ro.db")
    _make_legacy_db(db_path)

    bootstrap_database(db_path, verify_only=True)

    conn = sqlite3.connect(db_path)
    try:
        assert "locked_reason" not in _columns(conn, "usuarios")
        assert conn.execute("SELECT id FROM roles WHERE nombre='admin'").fetchone()[0] == "1"
    finally:
        conn.close()


def test_bootstrap_source_never_gates_migrations_on_empty_db():
    """El gating `is_empty` alrededor de _run_migrations no debe volver."""
    src = (ROOT / "scripts" / "bootstrap_db.py").read_text(encoding="utf-8")
    assert "if not verify_only and is_empty" not in src
    body = src.split("def bootstrap_database", 1)[1].split("def main", 1)[0]
    lines = [ln.strip() for ln in body.splitlines() if "_run_migrations(" in ln]
    assert lines, "bootstrap_database debe ejecutar _run_migrations"
    assert "if not verify_only:" in body


def test_main_boot_path_uses_bootstrap_database():
    """main.py delega el arranque de DB en bootstrap_database (ruta primaria)."""
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    boot = src.split("def _bootstrap_db", 1)[1].split("\ndef ", 1)[0]
    assert "bootstrap_database(" in boot
