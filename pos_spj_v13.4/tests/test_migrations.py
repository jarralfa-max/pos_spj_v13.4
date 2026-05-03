
# tests/test_migrations.py — SPJ POS v9
import sqlite3, pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture
def fresh_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn

def test_migration_engine_importa():
    from migrations.engine import MIGRATIONS, aplicar_migraciones
    assert len(MIGRATIONS) >= 36

def test_migrations_tienen_version_unica():
    from migrations.engine import MIGRATIONS
    versions = [m.version for m in MIGRATIONS]
    assert len(versions) == len(set(versions)), "Versiones duplicadas en migraciones"

def test_migrations_ordenadas():
    from migrations.engine import MIGRATIONS
    versions = [m.version for m in MIGRATIONS]
    assert versions == sorted(versions), "Migraciones no estan en orden"

def test_migration_036_crea_tablas(fresh_db):
    try:
        from migrations.m036_v61_enterprise_tables import up
        up(fresh_db)
        tables = [r[0] for r in fresh_db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for expected in ("roles","permisos","audit_logs","feature_flags"):
            assert expected in tables, f"Tabla {expected} no creada por m036"
    except ImportError:
        pytest.skip("m036 no disponible")

def test_migration_idempotente(fresh_db):
    try:
        from migrations.m036_v61_enterprise_tables import up
        up(fresh_db)
        up(fresh_db)  # segunda vez no debe explotar
    except ImportError:
        pytest.skip("m036 no disponible")
    except Exception as e:
        pytest.fail(f"Migracion no es idempotente: {e}")
