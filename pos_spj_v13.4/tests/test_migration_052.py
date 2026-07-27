"""
test_migration_052.py — v13.4
Verifica que la migración 052 crea la tabla financial_event_log correctamente.
"""
import importlib.util
import sqlite3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_MIGRATION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "migrations", "standalone", "052_financial_event_log.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("m052", _MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fresh_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_run_creates_table():
    mod = _load_migration()
    conn = _fresh_db()
    mod.run(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "financial_event_log" in tables


def test_table_has_required_columns():
    mod = _load_migration()
    conn = _fresh_db()
    mod.run(conn)
    cols = {r[1] for r in conn.execute(
        "PRAGMA table_info(financial_event_log)"
    ).fetchall()}
    required = {"id", "timestamp", "evento", "modulo", "referencia_id",
                "monto", "cuenta_debe", "cuenta_haber", "usuario_id",
                "sucursal_id", "metadata"}
    assert required.issubset(cols), f"Columnas faltantes: {required - cols}"


def test_idempotent():
    """Ejecutar dos veces no debe fallar."""
    mod = _load_migration()
    conn = _fresh_db()
    mod.run(conn)
    mod.run(conn)  # segunda ejecución — no debe lanzar excepción


def test_insert_and_read():
    mod = _load_migration()
    conn = _fresh_db()
    mod.run(conn)
    conn.execute(
        """INSERT INTO financial_event_log
           (evento, modulo, monto, cuenta_debe, cuenta_haber, sucursal_id)
           VALUES ('TEST', 'test', 100.0, 'caja', 'ventas', 1)"""
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM financial_event_log WHERE evento='TEST'"
    ).fetchone()
    assert row is not None
    assert float(row["monto"]) == 100.0
    assert row["cuenta_debe"] == "caja"
    assert row["cuenta_haber"] == "ventas"
