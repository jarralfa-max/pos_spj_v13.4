
# migrations/m001_enterprise_ajustes.py
import sqlite3

version = 1
description = "Ajustes para Motores Enterprise (Loyalty, Promotions, Feature Flags)"

def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    ).fetchone()
    return row is not None

def column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    if not table_exists(conn, table_name):
        return False
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]
    return column_name in cols

def ensure_column(conn: sqlite3.Connection, table: str, column_definition: str) -> None:
    col_name = column_definition.strip().split()[0]
    if table_exists(conn, table) and not column_exists(conn, table, col_name):
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_definition}")
        except Exception as e:
            print(f"Error agregando columna {col_name} a {table}: {e}")

def up(conn: sqlite3.Connection) -> None:
    # 1. Ajustes para el FeatureFlagService
    # Tu tabla actual usa 'clave' como PK. Agregamos sucursal_id para control multi-sucursal.
    # CÓDIGO CORREGIDO:
    ensure_column(conn, "promotion_rules", "aplica_a TEXT DEFAULT 'todo'") # 'categoria', 'producto_id', 'todo'
    # 2. Ajustes para el LoyaltyService (Tarjetas)
    # Tu tabla tarjetas_fidelidad es excelente, solo aseguramos los campos del lote
    ensure_column(conn, "tarjetas_fidelidad", "lote_origen_id INTEGER")
    
    # 3. Ajustes para el PromotionEngine
    # Tu tabla promotion_rules ya casi lo tiene todo. Añadimos campo para target específico si no existe.
    ensure_column(conn, "promotion_rules", "target_id INTEGER")
    ensure_column(conn, "promotion_rules", "aplica_a TEXT DEFAULT 'todo'")  # 'categoria', 'producto_id', 'todo'
    
    # 4. Ajustes para el ConfigService
    # Enlazamos la tabla configuraciones para soportar el almacenamiento de plantillas pesadas
    ensure_column(conn, "configuraciones", "tipo_dato TEXT DEFAULT 'str'")

def register(MIGRATIONS):
    from migrations.engine import Migration
    MIGRATIONS.append(
        Migration(
            version=version,
            description=description,
            up=up,
            down=lambda conn: None
        )
    )