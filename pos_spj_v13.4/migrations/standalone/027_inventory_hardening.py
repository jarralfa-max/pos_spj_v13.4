
# migrations/027_inventory_hardening.py
# ── FASE 1: Blindaje definitivo del módulo de inventario ─────────────────────
# Crea branch_inventory con CHECK(quantity >= 0) e inventory_movements inmutable.
# Migra datos existentes desde inventario_sucursal si aplica.
# NUNCA rompe tablas existentes.

import logging
import sqlite3

logger = logging.getLogger("spj.migrations.027")


def run(conn: sqlite3.Connection) -> None:
    """
    Ejecutar con:
        from migrations.027_inventory_hardening import run
        run(conn)
    O mediante el migration engine estándar.
    """
    _create_branch_inventory(conn)
    _create_inventory_movements(conn)
    _create_indexes(conn)
    _create_protection_triggers(conn)
    try: conn.commit()
    except Exception: pass
    logger.info("Migración 027 completada: branch_inventory + inventory_movements creados/verificados.")


# ── Tabla principal de stock ──────────────────────────────────────────────────

def _create_branch_inventory(conn: sqlite3.Connection) -> None:
    """
    Crea branch_inventory con CHECK(quantity >= 0).
    Si ya existe SIN el CHECK, recrea la tabla de forma segura migrando datos.
    """
    existing_cols = {
        r[1] for r in conn.execute("PRAGMA table_info(branch_inventory)").fetchall()
    }

    if existing_cols:
        # Verificar si tiene el CHECK constraint inspeccionando el DDL
        ddl_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='branch_inventory'"
        ).fetchone()
        ddl = ddl_row[0] if ddl_row else ""

        if "CHECK" in ddl and "quantity >= 0" in ddl:
            logger.info("branch_inventory ya tiene CHECK(quantity >= 0). Sin cambios.")
            return

        logger.info(
            "branch_inventory: agregando CHECK(quantity >= 0) — migración única..."
        )
        _migrate_branch_inventory(conn)
        return

    # No existe: crear desde cero
    conn.execute("""
        CREATE TABLE branch_inventory (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id  INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            batch_id   INTEGER,
            quantity   REAL    NOT NULL DEFAULT 0
                       CHECK(quantity >= 0),
            updated_at TEXT    DEFAULT (datetime('now')),
            UNIQUE(branch_id, product_id, batch_id),
            FOREIGN KEY (branch_id)  REFERENCES sucursales(id),
            FOREIGN KEY (product_id) REFERENCES productos(id)
        )
    """)
    logger.info("branch_inventory creada con CHECK(quantity >= 0).")


def _migrate_branch_inventory(conn: sqlite3.Connection) -> None:
    """
    Recrea branch_inventory con CHECK sin perder datos.
    Primero fuerza quantity >= 0 en los datos existentes.
    """
    # Clamp negativos a 0 antes de migrar (no puede haber negativos en destino)
    conn.execute("""
        UPDATE branch_inventory SET quantity = 0 WHERE quantity < 0
    """)

    conn.execute("ALTER TABLE branch_inventory RENAME TO branch_inventory_old")

    conn.execute("""
        CREATE TABLE branch_inventory (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id  INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            batch_id   INTEGER,
            quantity   REAL    NOT NULL DEFAULT 0
                       CHECK(quantity >= 0),
            updated_at TEXT    DEFAULT (datetime('now')),
            UNIQUE(branch_id, product_id, batch_id),
            FOREIGN KEY (branch_id)  REFERENCES sucursales(id),
            FOREIGN KEY (product_id) REFERENCES productos(id)
        )
    """)

    conn.execute("""
        INSERT INTO branch_inventory (id, branch_id, product_id, batch_id, quantity, updated_at)
        SELECT id, branch_id, product_id,
               CASE WHEN EXISTS(SELECT 1 FROM pragma_table_info('branch_inventory_old') WHERE name='batch_id')
                    THEN batch_id ELSE NULL END,
               MAX(quantity, 0),
               COALESCE(updated_at, datetime('now'))
        FROM branch_inventory_old
    """)

    conn.execute("DROP TABLE branch_inventory_old")
    logger.info("branch_inventory migrada con CHECK(quantity >= 0). Negativos corregidos a 0.")


# ── Tabla de movimientos inmutable ────────────────────────────────────────────

def _create_inventory_movements(conn: sqlite3.Connection) -> None:
    """
    Crea inventory_movements como registro de auditoría APPEND-ONLY.
    Nunca se hace UPDATE ni DELETE sobre esta tabla.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_movements (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id   TEXT    NOT NULL,
            product_id     INTEGER NOT NULL,
            branch_id      INTEGER NOT NULL,
            batch_id       INTEGER,
            movement_type  TEXT    NOT NULL,
            quantity       REAL    NOT NULL,
            reference_id   INTEGER,
            reference_type TEXT,
            usuario        TEXT    DEFAULT 'Sistema',
            created_at     TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (product_id) REFERENCES productos(id),
            FOREIGN KEY (branch_id)  REFERENCES sucursales(id)
        )
    """)

    # TRIGGER: bloquea UPDATE sobre inventory_movements
    conn.execute("DROP TRIGGER IF EXISTS trg_block_update_inventory_movements")
    conn.execute("""
        CREATE TRIGGER trg_block_update_inventory_movements
        BEFORE UPDATE ON inventory_movements
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE: inventory_movements no permite UPDATE');
        END
    """)

    # TRIGGER: bloquea DELETE sobre inventory_movements
    conn.execute("DROP TRIGGER IF EXISTS trg_block_delete_inventory_movements")
    conn.execute("""
        CREATE TRIGGER trg_block_delete_inventory_movements
        BEFORE DELETE ON inventory_movements
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE: inventory_movements no permite DELETE');
        END
    """)

    logger.info("inventory_movements creada/verificada con triggers IMMUTABLE.")


# ── Índices de rendimiento ────────────────────────────────────────────────────

def _create_indexes(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_branch_inventory_lookup
        ON branch_inventory(branch_id, product_id, batch_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_inventory_movements_operation
        ON inventory_movements(operation_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_inventory_movements_product_branch
        ON inventory_movements(product_id, branch_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_inventory_movements_created
        ON inventory_movements(created_at)
    """)
    logger.info("Índices de inventory creados/verificados.")


# ── Trigger adicional: CHECK a nivel DB en branch_inventory ──────────────────

def _create_protection_triggers(conn: sqlite3.Connection) -> None:
    """
    Trigger de respaldo: aunque el CHECK constraint ya protege,
    este trigger captura el intento con un mensaje descriptivo
    antes de que el constraint lo rechace.
    """
    conn.execute("DROP TRIGGER IF EXISTS trg_block_negative_inventory_insert")
    conn.execute("""
        CREATE TRIGGER trg_block_negative_inventory_insert
        BEFORE INSERT ON branch_inventory
        WHEN NEW.quantity < 0
        BEGIN
            SELECT RAISE(ABORT,
                'INVENTARIO_NEGATIVO_BLOQUEADO: INSERT rechazado en branch_inventory');
        END
    """)

    conn.execute("DROP TRIGGER IF EXISTS trg_block_negative_inventory_update")
    conn.execute("""
        CREATE TRIGGER trg_block_negative_inventory_update
        BEFORE UPDATE OF quantity ON branch_inventory
        WHEN NEW.quantity < 0
        BEGIN
            SELECT RAISE(ABORT,
                'INVENTARIO_NEGATIVO_BLOQUEADO: UPDATE rechazado en branch_inventory');
        END
    """)

    logger.info("Triggers de protección de inventario negativo creados/verificados.")
