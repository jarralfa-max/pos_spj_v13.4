# tests/test_fase0_recetas_integrity.py
# Fase 0 — Hotfix: piece_product_id en repositories/recetas.py
# Verifica que RecetaRepository.create() no lanza IntegrityError
# cuando piece_product_id tiene NOT NULL en el esquema.
import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture
def recetas_db():
    """BD en memoria con el esquema mínimo para product_recipes."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            precio REAL DEFAULT 0,
            precio_compra REAL DEFAULT 0,
            existencia REAL DEFAULT 100,
            stock_minimo REAL DEFAULT 0,
            unidad TEXT DEFAULT 'pza',
            categoria TEXT DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            activo INTEGER DEFAULT 1
        );
        CREATE TABLE product_recipes (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id        INTEGER NOT NULL,
            piece_product_id  INTEGER NOT NULL,
            base_product_id   INTEGER,
            nombre_receta     TEXT,
            total_rendimiento REAL DEFAULT 0,
            total_merma       REAL DEFAULT 0,
            is_active         INTEGER NOT NULL DEFAULT 1,
            activa            INTEGER DEFAULT 1,
            validates_at      TEXT,
            created_at        TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE product_recipe_components (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id            INTEGER NOT NULL,
            component_product_id INTEGER NOT NULL,
            rendimiento_pct      REAL NOT NULL DEFAULT 0,
            merma_pct            REAL NOT NULL DEFAULT 0,
            tolerancia_pct       REAL DEFAULT 2.0,
            orden                INTEGER NOT NULL DEFAULT 0,
            descripcion          TEXT DEFAULT '',
            created_at           TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE recipe_dependency_graph (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_recipe_id  INTEGER NOT NULL,
            child_product_id  INTEGER NOT NULL,
            depth             INTEGER DEFAULT 1,
            UNIQUE(parent_recipe_id, child_product_id)
        );
        INSERT INTO productos (id, nombre) VALUES (1, 'Pollo entero');
        INSERT INTO productos (id, nombre) VALUES (2, 'Pechuga');
        INSERT INTO productos (id, nombre) VALUES (3, 'Muslo');
    """)
    conn.commit()
    return conn


def test_create_receta_sin_piece_product_id_no_falla(recetas_db):
    """
    RecetaRepository.create() no debe lanzar IntegrityError
    aunque piece_product_id sea NOT NULL en el esquema.
    El repositorio lo rellena automáticamente con base_product_id.
    """
    from repositories.recetas import RecetaRepository

    repo = RecetaRepository(recetas_db)
    rid = repo.create(
        nombre="Despiece pollo",
        base_product_id=1,
        components=[
            {"component_product_id": 2, "rendimiento_pct": 50, "merma_pct": 0},
            {"component_product_id": 3, "rendimiento_pct": 50, "merma_pct": 0},
        ],
        usuario="test",
    )
    assert rid is not None
    assert isinstance(rid, int)
    assert rid > 0


def test_create_receta_piece_product_id_persisted(recetas_db):
    """
    El campo piece_product_id se almacena igual que product_id / base_product_id.
    """
    from repositories.recetas import RecetaRepository

    repo = RecetaRepository(recetas_db)
    rid = repo.create(
        nombre="Receta prueba",
        base_product_id=1,
        components=[
            {"component_product_id": 2, "rendimiento_pct": 100, "merma_pct": 0},
        ],
        usuario="test",
    )
    row = recetas_db.execute(
        "SELECT piece_product_id FROM product_recipes WHERE id=?", (rid,)
    ).fetchone()
    assert row is not None
    assert row["piece_product_id"] == 1


def test_create_dos_recetas_distintos_productos(recetas_db):
    """Dos recetas con distintos base_product_id se crean sin conflicto."""
    from repositories.recetas import RecetaRepository

    repo = RecetaRepository(recetas_db)
    r1 = repo.create(
        nombre="Receta A",
        base_product_id=1,
        components=[{"component_product_id": 2, "rendimiento_pct": 100, "merma_pct": 0}],
        usuario="test",
    )
    r2 = repo.create(
        nombre="Receta B",
        base_product_id=2,
        components=[{"component_product_id": 3, "rendimiento_pct": 100, "merma_pct": 0}],
        usuario="test",
    )
    assert r1 != r2


def test_create_receta_rechaza_total_distinto_a_100(recetas_db):
    from repositories.recetas import RecetaRepository, RecetaPercentageError

    repo = RecetaRepository(recetas_db)
    with pytest.raises(RecetaPercentageError):
        repo.create(
            nombre="Receta inválida",
            base_product_id=1,
            components=[{"component_product_id": 2, "rendimiento_pct": 80, "merma_pct": 0}],
            usuario="test",
        )
