
import logging
import sqlite3

logger = logging.getLogger("spj.migrations.035")

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

def _create_suppliers(conn: sqlite3.Connection) -> None:
    """Crea la tabla de proveedores con todas sus columnas financieras."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proveedor_id INTEGER,
            nombre TEXT NOT NULL,
            rfc TEXT,
            telefono TEXT,
            email TEXT,
            direccion TEXT,
            tipo TEXT DEFAULT 'general',
            condiciones_pago INTEGER DEFAULT 30,
            limite_credito REAL DEFAULT 0,
            saldo_pendiente REAL DEFAULT 0,
            banco TEXT,
            cuenta_bancaria TEXT,
            contacto TEXT,
            notas TEXT,
            activo INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT (datetime('now'))
        )
    """)
    # Vacuna contra el Schema Drift para proveedores creados por m000
    _add_col_safe(conn, "suppliers", "contacto", "TEXT")
    _add_col_safe(conn, "suppliers", "notas", "TEXT")

def _create_ap_ar(conn: sqlite3.Connection) -> None:
    """Crea las tablas de Cuentas por Pagar (AP) y Cuentas por Cobrar (AR)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts_payable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            invoice_number TEXT,
            amount REAL NOT NULL,
            balance REAL NOT NULL,
            due_date DATE,
            status TEXT DEFAULT 'PENDING',
            created_at DATETIME DEFAULT (datetime('now'))
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts_receivable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            invoice_number TEXT,
            amount REAL NOT NULL,
            balance REAL NOT NULL,
            due_date DATE,
            status TEXT DEFAULT 'PENDING',
            created_at DATETIME DEFAULT (datetime('now'))
        )
    """)

def _patch_schema_drift(conn: sqlite3.Connection) -> None:
    """Inyecta la columna 'created_at' si las tablas fueron creadas previamente sin ella."""
    _add_col_safe(conn, "accounts_payable", "created_at", "DATETIME DEFAULT (datetime('now'))")
    _add_col_safe(conn, "accounts_receivable", "created_at", "DATETIME DEFAULT (datetime('now'))")

def run(conn: sqlite3.Connection) -> None:
    """Punto de entrada principal para la migración 035."""
    logger.info("Iniciando migración 035_finance_erp...")
    
    _create_suppliers(conn)
    _create_ap_ar(conn)
    _patch_schema_drift(conn)
    
    # Creación segura de índices
    for _idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_ap_supplier ON accounts_payable(supplier_id)",
        "CREATE INDEX IF NOT EXISTS idx_ar_client ON accounts_receivable(client_id)",
        "CREATE INDEX IF NOT EXISTS idx_ar_cliente ON accounts_receivable(cliente_id)",
    ]:
        try:
            conn.execute(_idx_sql)
        except Exception as e:
            logger.debug("035 index skip (column may not exist): %s", e)

    logger.info("Migración 035 aplicada correctamente.")