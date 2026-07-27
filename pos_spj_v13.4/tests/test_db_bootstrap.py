"""
test_db_bootstrap.py — verifica que bootstrap crea las tablas críticas.
"""
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
APP_DIR = os.path.join(ROOT, "pos_spj_v13.4")
for _p in (ROOT, SCRIPTS_DIR, APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _existe_tabla(conn, nombre):
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (nombre,)
    )
    return cur.fetchone() is not None


def test_bootstrap_crea_tablas_criticas():
    """Bootstrap debe crear las tablas mínimas requeridas."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        from bootstrap_db import bootstrap_database

        bootstrap_database(db_path)
        conn = sqlite3.connect(db_path)
        for tabla in ("usuarios", "productos", "clientes", "ventas", "configuraciones"):
            assert _existe_tabla(conn, tabla), f"Tabla faltante: {tabla}"
        conn.close()
    finally:
        os.unlink(db_path)


def test_bootstrap_idempotente():
    """Bootstrap puede ejecutarse dos veces sin errores."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        from bootstrap_db import bootstrap_database

        bootstrap_database(db_path)
        bootstrap_database(db_path)  # segunda vez — no debe fallar
    finally:
        os.unlink(db_path)
