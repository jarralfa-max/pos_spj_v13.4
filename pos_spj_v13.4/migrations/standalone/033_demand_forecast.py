
import logging
import sqlite3

logger = logging.getLogger("spj.migrations.033")

def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Verifica si una tabla existe en la base de datos."""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cursor.fetchone() is not None

def _add_col_safe(conn: sqlite3.Connection, tabla: str, col: str, defn: str) -> None:
    """Añade una columna de forma segura si no existe."""
    if not _table_exists(conn, tabla):
        return
    try:
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
        if col not in existing:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {defn}")
            logger.debug("Columna %s.%s añadida.", tabla, col)
    except Exception as e:
        logger.warning("No se pudo alterar la tabla %s para añadir %s: %s", tabla, col, e)

def _create_forecast_tables(conn: sqlite3.Connection) -> None:
    """Crea las tablas base para el motor de pronóstico de demanda."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS demand_forecast (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            branch_id INTEGER NOT NULL,
            forecast_date DATE,
            predicted_quantity REAL NOT NULL DEFAULT 0,
            run_id TEXT,
            created_at DATETIME DEFAULT (datetime('now'))
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS replenishment_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            branch_id INTEGER NOT NULL,
            recommended_quantity REAL NOT NULL DEFAULT 0,
            run_id TEXT,
            created_at DATETIME DEFAULT (datetime('now'))
        )
    """)

def _patch_schema_drift(conn: sqlite3.Connection) -> None:
    """Inyecta la columna 'run_id' si la tabla fue creada previamente sin ella."""
    _add_col_safe(conn, "demand_forecast", "run_id", "TEXT")
    _add_col_safe(conn, "replenishment_recommendations", "run_id", "TEXT")

def run(conn: sqlite3.Connection) -> None:
    """Punto de entrada principal para la migración 033."""
    logger.info("Iniciando migración 033_demand_forecast...")
    
    _create_forecast_tables(conn)
    _patch_schema_drift(conn)
    
    # Creación segura de índices
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_demand_forecast_run ON demand_forecast(run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_replenishment_run ON replenishment_recommendations(run_id)")
    except Exception as e:
        logger.warning(f"Advertencia al crear índices en 033: {e}")

    logger.info("Migración 033 aplicada correctamente.")