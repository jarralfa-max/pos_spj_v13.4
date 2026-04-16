import sqlite3


def test_recipe_engine_historial_usa_nombre_receta_compatibilidad_sqlite():
    from core.services.recipe_engine import RecipeEngine

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            unidad TEXT
        );
        CREATE TABLE product_recipes (
            id INTEGER PRIMARY KEY,
            nombre_receta TEXT,
            tipo_receta TEXT,
            producto_base_id INTEGER
        );
        CREATE TABLE producciones (
            id INTEGER PRIMARY KEY,
            fecha TEXT,
            receta_id INTEGER,
            producto_base_id INTEGER,
            cantidad_base REAL,
            unidad_base TEXT,
            usuario TEXT,
            estado TEXT,
            operation_id TEXT,
            sucursal_id INTEGER
        );
        INSERT INTO productos(id, nombre, unidad) VALUES (1, 'Pollo Entero', 'kg');
        INSERT INTO product_recipes(id, nombre_receta, tipo_receta, producto_base_id)
            VALUES (10, 'Receta Prueba', 'subproducto', 1);
        INSERT INTO producciones(id, fecha, receta_id, producto_base_id, cantidad_base, unidad_base, usuario, estado, operation_id, sucursal_id)
            VALUES (100, '2026-04-16T10:00:00', 10, 1, 5.0, 'kg', 'tester', 'ok', 'op-1', 1);
    """)

    svc = RecipeEngine(conn, branch_id=1)
    hist = svc.get_historial(sucursal_id=1, limit=10)

    assert len(hist) == 1
    assert hist[0]["receta_nombre"] == "Receta Prueba"
