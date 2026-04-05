
# migrations/028_sales_transaction_hardening.py
# ── FASE 2: Blindaje transaccional Venta + Inventario + Caja ─────────────────
#
# Cambios:
#   1. Tabla `payments`       — registro de pagos por venta (multi-método)
#   2. Columna `operation_id` en `ventas` — idempotencia y auditoría cruzada
#   3. Columna `credit_approved` en `ventas` — flag de crédito aprobado
#   4. Índice de idempotencia sobre ventas(operation_id)
#   5. Trigger: bloquea UPDATE de `total`/`estado` a COMPLETED si ya está completada
#
# NUNCA destruye datos existentes.

import logging
import sqlite3

logger = logging.getLogger("spj.migrations.028")


def run(conn: sqlite3.Connection) -> None:
    _create_payments(conn)
    _patch_ventas(conn)
    _create_indexes(conn)
    _create_sale_integrity_triggers(conn)
    try: conn.commit()
    except Exception: pass
    logger.info("Migración 028 completada: payments + ventas hardening.")


# ── 1. Tabla payments ─────────────────────────────────────────────────────────

def _create_payments(conn: sqlite3.Connection) -> None:
    """
    Registro detallado de pagos por venta.
    Una venta puede tener múltiples formas de pago (efectivo + tarjeta, etc.).
    SUM(payments.amount) debe = ventas.total.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id      INTEGER NOT NULL,
            method        TEXT    NOT NULL,           -- 'Efectivo','Tarjeta','Crédito','Puntos'
            amount        REAL    NOT NULL
                          CHECK(amount > 0),
            reference     TEXT,                       -- nº autorización tarjeta, etc.
            operation_id  TEXT    NOT NULL,           -- debe coincidir con ventas.operation_id
            created_at    TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (venta_id) REFERENCES ventas(id)
        )
    """)

    # TRIGGER: bloquea UPDATE sobre payments (registro inmutable)
    conn.execute("DROP TRIGGER IF EXISTS trg_block_update_payments")
    conn.execute("""
        CREATE TRIGGER trg_block_update_payments
        BEFORE UPDATE ON payments
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE: payments no permite UPDATE');
        END
    """)

    # TRIGGER: bloquea DELETE sobre payments
    conn.execute("DROP TRIGGER IF EXISTS trg_block_delete_payments")
    conn.execute("""
        CREATE TRIGGER trg_block_delete_payments
        BEFORE DELETE ON payments
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE: payments no permite DELETE');
        END
    """)

    logger.info("Tabla payments creada/verificada con triggers IMMUTABLE.")


# ── 2. Columnas adicionales en ventas ─────────────────────────────────────────

def _add_col_safe(conn: sqlite3.Connection, tabla: str, col: str, defn: str) -> None:
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
    if col not in existing:
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {defn}")
        logger.debug("Columna agregada: %s.%s", tabla, col)


def _patch_ventas(conn: sqlite3.Connection) -> None:
    """
    Añade a ventas:
      - operation_id  TEXT  → trazabilidad cruzada y idempotencia
      - credit_approved INT → 1=pago completado, 0=crédito pendiente
    """
    _add_col_safe(conn, "ventas", "operation_id",   "TEXT")
    _add_col_safe(conn, "ventas", "credit_approved", "INTEGER DEFAULT 1")
    logger.info("Columnas operation_id y credit_approved añadidas a ventas.")


# ── 3. Índices ────────────────────────────────────────────────────────────────

def _create_indexes(conn: sqlite3.Connection) -> None:
    # Idempotencia: buscar venta por operation_id debe ser O(log n)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ventas_operation_id
        ON ventas(operation_id)
        WHERE operation_id IS NOT NULL
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_payments_venta
        ON payments(venta_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_payments_operation
        ON payments(operation_id)
    """)
    logger.info("Índices de ventas/payments creados/verificados.")


# ── 4. Trigger: integridad post-completada ────────────────────────────────────

def _create_sale_integrity_triggers(conn: sqlite3.Connection) -> None:
    """
    Bloquea modificación de total/estado en ventas ya completadas.
    Una venta COMPLETADA no puede cambiar su total ni revertirse a PENDING.
    Solo 'cancelada' es permitido como siguiente estado desde 'completada'.
    """
    conn.execute("DROP TRIGGER IF EXISTS trg_protect_completed_sale")
    conn.execute("""
        CREATE TRIGGER trg_protect_completed_sale
        BEFORE UPDATE OF total, subtotal, iva ON ventas
        WHEN OLD.estado = 'completada'
        BEGIN
            SELECT RAISE(ABORT,
                'VENTA_INMUTABLE: no se puede modificar total de venta completada');
        END
    """)

    conn.execute("DROP TRIGGER IF EXISTS trg_protect_sale_estado")
    conn.execute("""
        CREATE TRIGGER trg_protect_sale_estado
        BEFORE UPDATE OF estado ON ventas
        WHEN OLD.estado = 'completada' AND NEW.estado NOT IN ('cancelada', 'completada')
        BEGIN
            SELECT RAISE(ABORT,
                'ESTADO_INVALIDO: venta completada solo puede cancelarse');
        END
    """)

    logger.info("Triggers de protección de ventas completadas creados/verificados.")
