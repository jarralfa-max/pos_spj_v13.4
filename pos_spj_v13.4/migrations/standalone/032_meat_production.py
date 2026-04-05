
import logging
import sqlite3

logger = logging.getLogger("spj.migrations.032")

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

def _create_tables(conn: sqlite3.Connection) -> None:
    """Crea las tablas del módulo cárnico asegurando compatibilidad bilingüe (fecha/created_at)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS meat_production_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER NOT NULL,
            source_product_id INTEGER NOT NULL,
            source_weight REAL NOT NULL,
            source_cost REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'DRAFT',
            created_at DATETIME DEFAULT (datetime('now')),
            fecha DATETIME DEFAULT (datetime('now')), 
            completed_at DATETIME,
            user_id INTEGER
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS meat_production_yields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            yield_product_id INTEGER NOT NULL,
            weight REAL NOT NULL,
            allocated_cost REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (run_id) REFERENCES meat_production_runs(id) ON DELETE CASCADE
        )
    """)

def _patch_schema_drift(conn: sqlite3.Connection) -> None:
    """Inyecta las columnas 'fecha' y 'created_at' en tablas problemáticas para evitar colapsos."""
    tablas_potenciales = ["meat_production_runs", "producciones", "kpi_snapshots"]
    for tabla in tablas_potenciales:
        _add_col_safe(conn, tabla, "fecha", "DATETIME DEFAULT (datetime('now'))")
        _add_col_safe(conn, tabla, "created_at", "DATETIME DEFAULT (datetime('now'))")

def run(conn: sqlite3.Connection) -> None:
    """Punto de entrada principal para la migración 032."""
    logger.info("Iniciando migración 032_meat_production...")
    
    _create_tables(conn)
    _patch_schema_drift(conn)
    
    # Creación de índices de forma segura (ignorando errores si ya existen)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_meat_runs_branch_fecha ON meat_production_runs(branch_id, fecha)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_meat_runs_branch_created ON meat_production_runs(branch_id, created_at)")
    except Exception as e:
        logger.warning(f"Advertencia al crear índices en 032: {e}")
        
    logger.info("Migración 032 aplicada correctamente.")