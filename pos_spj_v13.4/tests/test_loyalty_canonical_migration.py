import sqlite3
import importlib.util
from pathlib import Path


def _load_migration(name):
    p = Path(__file__).resolve().parent.parent / 'migrations' / 'standalone' / name
    spec = importlib.util.spec_from_file_location('_migx', p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_092_enforces_unique_and_recalculates_snapshots():
    db = sqlite3.connect(':memory:')
    db.execute("CREATE TABLE loyalty_ledger (id TEXT PRIMARY KEY, cliente_id TEXT, tipo TEXT, puntos INTEGER, monto_equiv REAL, saldo_post INTEGER, referencia TEXT, descripcion TEXT, sucursal_id TEXT, usuario TEXT, created_at TEXT)")
    db.execute("CREATE TABLE growth_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, puntos INTEGER, referencia TEXT, descripcion TEXT, sucursal_id INTEGER, usuario TEXT, created_at TEXT)")
    db.execute("CREATE TABLE clientes (id INTEGER PRIMARY KEY, nombre TEXT, puntos INTEGER DEFAULT 0)")
    db.execute("CREATE TABLE tarjetas_fidelidad (id INTEGER PRIMARY KEY, cliente_id INTEGER, puntos_actuales INTEGER DEFAULT 0)")

    db.execute("INSERT INTO clientes(id,nombre,puntos) VALUES (1,'A',999)")
    db.execute("INSERT INTO tarjetas_fidelidad(id,cliente_id,puntos_actuales) VALUES (10,1,777)")
    db.execute("INSERT INTO loyalty_ledger(cliente_id,tipo,puntos,referencia,created_at) VALUES (1,'acumulacion',100,'V1','2026-01-01')")
    db.execute("INSERT INTO growth_ledger(cliente_id,puntos,referencia,created_at) VALUES (1,-20,'V2','2026-01-02')")

    _load_migration('092_loyalty_ledger_canonicalization.py').run(db)

    bal = db.execute("SELECT COALESCE(SUM(puntos),0) FROM loyalty_ledger WHERE cliente_id=1").fetchone()[0]
    assert bal == 80
    c = db.execute("SELECT puntos FROM clientes WHERE id=1").fetchone()[0]
    t = db.execute("SELECT puntos_actuales FROM tarjetas_fidelidad WHERE id=10").fetchone()[0]
    assert c == 80 and t == 80

    dup_err = None
    try:
        db.execute("INSERT INTO loyalty_ledger(cliente_id,tipo,puntos,referencia) VALUES (1,'acumulacion',5,'V1')")
    except Exception as e:
        dup_err = e
    assert dup_err is not None


def test_migration_092_skips_growth_ledger_without_puntos_column():
    db = sqlite3.connect(':memory:')
    db.execute("CREATE TABLE loyalty_ledger (id TEXT PRIMARY KEY, cliente_id TEXT, tipo TEXT, puntos INTEGER, monto_equiv REAL, saldo_post INTEGER, referencia TEXT, descripcion TEXT, sucursal_id TEXT, usuario TEXT, created_at TEXT)")
    # esquema legacy roto/incompleto: growth_ledger sin columna puntos
    db.execute("CREATE TABLE growth_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, referencia TEXT, descripcion TEXT, sucursal_id INTEGER, usuario TEXT, created_at TEXT)")
    db.execute("CREATE TABLE clientes (id INTEGER PRIMARY KEY, nombre TEXT)")
    db.execute("CREATE TABLE tarjetas_fidelidad (id INTEGER PRIMARY KEY, cliente_id INTEGER, puntos_actuales INTEGER DEFAULT 0)")
    db.execute("INSERT INTO loyalty_ledger(cliente_id,tipo,puntos,referencia,created_at) VALUES (1,'acumulacion',10,'V1','2026-01-01')")

    _load_migration('092_loyalty_ledger_canonicalization.py').run(db)

    bal = db.execute("SELECT COALESCE(SUM(puntos),0) FROM loyalty_ledger WHERE cliente_id=1").fetchone()[0]
    assert bal == 10


def test_migration_092_survives_broken_legacy_view_dependencies():
    db = sqlite3.connect(':memory:')
    db.execute("CREATE TABLE loyalty_ledger (id TEXT PRIMARY KEY, cliente_id TEXT, tipo TEXT, puntos INTEGER, monto_equiv REAL, saldo_post INTEGER, referencia TEXT, descripcion TEXT, sucursal_id TEXT, usuario TEXT, created_at TEXT)")
    db.execute("CREATE TABLE clientes (id INTEGER PRIMARY KEY, nombre TEXT, puntos INTEGER DEFAULT 0)")
    db.execute("INSERT INTO loyalty_ledger(cliente_id,tipo,puntos,referencia,created_at) VALUES (1,'acumulacion',15,'V1','2026-01-01')")
    # Simula metadato roto reportado en producción: vista apuntando a tabla *_old inexistente.
    db.execute("CREATE VIEW v_negative_inventory AS SELECT * FROM branch_inventory_old")

    _load_migration('092_loyalty_ledger_canonicalization.py').run(db)

    bal = db.execute("SELECT COALESCE(SUM(puntos),0) FROM loyalty_ledger WHERE cliente_id=1").fetchone()[0]
    assert bal == 15


def test_migration_092_tarjetas_legacy_id_cliente_supported():
    db = sqlite3.connect(':memory:')
    db.execute("CREATE TABLE loyalty_ledger (id TEXT PRIMARY KEY, cliente_id TEXT, tipo TEXT, puntos INTEGER, monto_equiv REAL, saldo_post INTEGER, referencia TEXT, descripcion TEXT, sucursal_id TEXT, usuario TEXT, created_at TEXT)")
    db.execute("CREATE TABLE clientes (id INTEGER PRIMARY KEY, nombre TEXT, puntos INTEGER DEFAULT 0)")
    # esquema legacy: tarjetas_fidelidad con id_cliente, sin cliente_id
    db.execute("CREATE TABLE tarjetas_fidelidad (id INTEGER PRIMARY KEY, id_cliente INTEGER, puntos_actuales INTEGER DEFAULT 0)")
    db.execute("INSERT INTO tarjetas_fidelidad(id,id_cliente,puntos_actuales) VALUES (10,1,999)")
    db.execute("INSERT INTO loyalty_ledger(cliente_id,tipo,puntos,referencia,created_at) VALUES (1,'acumulacion',25,'V1','2026-01-01')")

    _load_migration('092_loyalty_ledger_canonicalization.py').run(db)

    t = db.execute("SELECT puntos_actuales FROM tarjetas_fidelidad WHERE id=10").fetchone()[0]
    assert t == 25
