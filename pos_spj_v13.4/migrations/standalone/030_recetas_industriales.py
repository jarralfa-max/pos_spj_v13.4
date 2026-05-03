
import logging
import sqlite3

logger = logging.getLogger("spj.migrations.030")

def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Verifica si una tabla existe en la base de datos."""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cursor.fetchone() is not None

def _add_col_safe(conn: sqlite3.Connection, tabla: str, col: str, defn: str) -> None:
    """Añade una columna de forma segura si no existe, evitando bloqueos por errores."""
    if not _table_exists(conn, tabla):
        return
        
    try:
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
        if col not in existing:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {defn}")
            logger.debug("Columna %s.%s añadida.", tabla, col)
    except Exception as e:
        logger.warning("No se pudo alterar la tabla %s para añadir %s: %s", tabla, col, e)

def _create_recetas(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            rendimiento REAL DEFAULT 1,
            activa INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT (datetime('now'))
        )
    """)
    
def _create_producciones(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS producciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            receta_id INTEGER NOT NULL,
            cantidad REAL NOT NULL,
            costo_total REAL DEFAULT 0,
            fecha DATETIME DEFAULT (datetime('now')),
            usuario_id INTEGER
        )
    """)

def _create_product_recipe_components(conn: sqlite3.Connection) -> None:
    """
    Componentes de las recetas del sistema pollo/mix (RecetaRepository).
    product_recipes ya existe como tabla de recetas del mix.
    """
    # Primero asegurar que product_recipes tiene las columnas correctas
    if _table_exists(conn, "product_recipes"):
        _add_col_safe(conn, "product_recipes", "base_product_id",   "INTEGER")
        _add_col_safe(conn, "product_recipes", "nombre_receta",     "TEXT")
        _add_col_safe(conn, "product_recipes", "total_rendimiento", "REAL DEFAULT 0")
        _add_col_safe(conn, "product_recipes", "total_merma",       "REAL DEFAULT 0")
        _add_col_safe(conn, "product_recipes", "is_active",         "INTEGER DEFAULT 1")
        _add_col_safe(conn, "product_recipes", "activa",            "INTEGER DEFAULT 1")
        _add_col_safe(conn, "product_recipes", "validates_at",      "TEXT")
        
        try:
            # Sincronizar base_product_id desde product_id
            conn.execute("UPDATE product_recipes SET base_product_id = product_id WHERE base_product_id IS NULL")
        except Exception:
            pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_recipe_components (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id            INTEGER NOT NULL,
            component_product_id INTEGER NOT NULL,
            rendimiento_pct      REAL    NOT NULL DEFAULT 0 CHECK(rendimiento_pct >= 0),
            merma_pct            REAL    NOT NULL DEFAULT 0 CHECK(merma_pct >= 0),
            orden                INTEGER NOT NULL DEFAULT 0,
            descripcion          TEXT    DEFAULT '',
            created_at           TEXT    DEFAULT (datetime('now'))
        )
    """)
    logger.info("product_recipe_components creada/verificada.")

def _patch_recetas_columns(conn: sqlite3.Connection) -> None:
    """Añade columnas adicionales que pudieron faltar en el esquema original."""
    _add_col_safe(conn, "recetas", "operation_id", "TEXT")
    _add_col_safe(conn, "producciones", "operation_id", "TEXT")

def run(conn: sqlite3.Connection) -> None:
    """Punto de entrada principal para el motor de migraciones."""
    logger.info("Iniciando migración 030_recetas_industriales...")
    
    _create_recetas(conn)
    _create_producciones(conn)
    _create_product_recipe_components(conn)
    _patch_recetas_columns(conn)
    
    logger.info("Migración 030 aplicada correctamente.")