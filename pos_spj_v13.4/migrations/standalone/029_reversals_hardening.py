
# migrations/029_reversals_hardening.py
# ── FASE 3: Cancelaciones + Devoluciones + Notas de Crédito ──────────────────
#
# Cambios:
#   1. Tabla sale_refunds   — devoluciones parciales por ítem
#   2. Tabla credit_notes   — notas de crédito sin movimiento físico
#   3. Columna reference_id en movimientos_caja — trazabilidad cruzada
#   4. Actualizar trigger trg_protect_sale_estado para permitir CANCEL_PENDING
#   5. Trigger: bloquea devolver más de lo vendido por ítem
#   6. Trigger: bloquea cancelar venta ya cancelada
#
# PRINCIPIO: nunca borrar, solo compensar.
# Modelo contable real: cada reversión es un movimiento con signo opuesto.

import logging
import sqlite3

logger = logging.getLogger("spj.migrations.029")


def run(conn: sqlite3.Connection) -> None:
    _create_sale_refunds(conn)
    _create_credit_notes(conn)
    _patch_movimientos_caja(conn)
    _update_sale_estado_trigger(conn)
    _create_refund_integrity_triggers(conn)
    _create_indexes(conn)
    try: conn.commit()
    except Exception: pass
    logger.info("Migración 029 completada: sale_refunds + credit_notes + triggers reversión.")


# ── 1. sale_refunds ───────────────────────────────────────────────────────────

def _create_sale_refunds(conn: sqlite3.Connection) -> None:
    """
    Registro de devoluciones parciales.
    Un ítem puede tener múltiples registros parciales, pero
    SUM(sale_refunds.quantity WHERE sale_item_id=X) <= detalles_venta.cantidad
    — verificado por trigger trg_refund_no_excede.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sale_refunds (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id      INTEGER NOT NULL,
            sale_item_id INTEGER NOT NULL,
            product_id   INTEGER NOT NULL,
            quantity     REAL    NOT NULL CHECK(quantity > 0),
            amount       REAL    NOT NULL CHECK(amount > 0),
            method       TEXT    NOT NULL DEFAULT 'Efectivo',
            reason       TEXT,
            operation_id TEXT    NOT NULL,
            created_at   TEXT    DEFAULT (datetime('now')),
            created_by   TEXT    NOT NULL,
            FOREIGN KEY (sale_id)      REFERENCES ventas(id)         ON DELETE RESTRICT,
            FOREIGN KEY (sale_item_id) REFERENCES detalles_venta(id) ON DELETE RESTRICT,
            FOREIGN KEY (product_id)   REFERENCES productos(id)      ON DELETE RESTRICT
        )
    """)

    # IMMUTABLE: triggers bloquean UPDATE y DELETE
    conn.execute("DROP TRIGGER IF EXISTS trg_block_update_sale_refunds")
    conn.execute("""
        CREATE TRIGGER trg_block_update_sale_refunds
        BEFORE UPDATE ON sale_refunds
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE: sale_refunds no permite UPDATE');
        END
    """)
    conn.execute("DROP TRIGGER IF EXISTS trg_block_delete_sale_refunds")
    conn.execute("""
        CREATE TRIGGER trg_block_delete_sale_refunds
        BEFORE DELETE ON sale_refunds
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE: sale_refunds no permite DELETE');
        END
    """)
    logger.info("Tabla sale_refunds creada/verificada.")


# ── 2. credit_notes ───────────────────────────────────────────────────────────

def _create_credit_notes(conn: sqlite3.Connection) -> None:
    """
    Notas de crédito: ajuste financiero sin movimiento de inventario.
    Casos: error de precio, bonificación, garantía.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS credit_notes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id      INTEGER NOT NULL,
            amount       REAL    NOT NULL CHECK(amount > 0),
            reason       TEXT    NOT NULL,
            operation_id TEXT    NOT NULL,
            created_at   TEXT    DEFAULT (datetime('now')),
            created_by   TEXT    NOT NULL,
            FOREIGN KEY (sale_id) REFERENCES ventas(id) ON DELETE RESTRICT
        )
    """)

    conn.execute("DROP TRIGGER IF EXISTS trg_block_update_credit_notes")
    conn.execute("""
        CREATE TRIGGER trg_block_update_credit_notes
        BEFORE UPDATE ON credit_notes
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE: credit_notes no permite UPDATE');
        END
    """)
    conn.execute("DROP TRIGGER IF EXISTS trg_block_delete_credit_notes")
    conn.execute("""
        CREATE TRIGGER trg_block_delete_credit_notes
        BEFORE DELETE ON credit_notes
        BEGIN
            SELECT RAISE(ABORT, 'IMMUTABLE: credit_notes no permite DELETE');
        END
    """)
    logger.info("Tabla credit_notes creada/verificada.")


# ── 3. Columna reference_id en movimientos_caja ───────────────────────────────

def _add_col_safe(conn, tabla, col, defn):
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
    if col not in existing:
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {defn}")
        logger.debug("Columna %s.%s añadida.", tabla, col)


def _patch_movimientos_caja(conn: sqlite3.Connection) -> None:
    """
    Añade reference_id a movimientos_caja para trazabilidad cruzada
    (refund_id, credit_note_id, etc.).
    """
    _add_col_safe(conn, "movimientos_caja", "reference_id",   "INTEGER")
    _add_col_safe(conn, "movimientos_caja", "reference_type", "TEXT")
    _add_col_safe(conn, "movimientos_caja", "operation_id",   "TEXT")
    logger.info("Columnas de trazabilidad añadidas a movimientos_caja.")


# ── 4. Actualizar trigger de estado de ventas ─────────────────────────────────

def _update_sale_estado_trigger(conn: sqlite3.Connection) -> None:
    """
    Actualiza trg_protect_sale_estado para permitir la transición
    completada → CANCEL_PENDING (estado intermedio atómico dentro
    de la misma transacción BEGIN IMMEDIATE).

    Flujo permitido:
        completada → CANCEL_PENDING  (inicio de cancelación)
        completada → cancelada        (cancelación directa)
        CANCEL_PENDING → cancelada    (fin de cancelación)
        CANCEL_PENDING → completada   (rollback de cancelación fallida — nunca visible desde afuera)
    """
    conn.execute("DROP TRIGGER IF EXISTS trg_protect_sale_estado")
    conn.execute("""
        CREATE TRIGGER trg_protect_sale_estado
        BEFORE UPDATE OF estado ON ventas
        WHEN OLD.estado NOT IN ('completada', 'CANCEL_PENDING', 'PENDING')
             AND NEW.estado != OLD.estado
        BEGIN
            SELECT RAISE(ABORT,
                'ESTADO_INVALIDO: transicion de estado no permitida en ventas');
        END
    """)

    # Trigger específico: bloquea reactivar una venta cancelada
    conn.execute("DROP TRIGGER IF EXISTS trg_block_reactivate_cancelled_sale")
    conn.execute("""
        CREATE TRIGGER trg_block_reactivate_cancelled_sale
        BEFORE UPDATE OF estado ON ventas
        WHEN OLD.estado = 'cancelada'
        BEGIN
            SELECT RAISE(ABORT,
                'CANCELACION_IRREVERSIBLE: venta cancelada no puede reactivarse');
        END
    """)
    logger.info("Triggers de transición de estado de ventas actualizados.")


# ── 5. Triggers de integridad de devoluciones ─────────────────────────────────

def _create_refund_integrity_triggers(conn: sqlite3.Connection) -> None:
    """
    Bloquea devolver más cantidad de la vendida para un ítem dado.
    SUM(refunds.quantity) + NEW.quantity <= original.cantidad
    """
    conn.execute("DROP TRIGGER IF EXISTS trg_refund_no_excede")
    conn.execute("""
        CREATE TRIGGER trg_refund_no_excede
        BEFORE INSERT ON sale_refunds
        BEGIN
            SELECT RAISE(ABORT, 'DEVOLUCION_EXCEDE: cantidad devuelta supera la vendida')
            WHERE (
                SELECT COALESCE(SUM(r.quantity), 0) + NEW.quantity
                FROM sale_refunds r
                WHERE r.sale_item_id = NEW.sale_item_id
            ) > (
                SELECT dv.cantidad
                FROM detalles_venta dv
                WHERE dv.id = NEW.sale_item_id
            );
        END
    """)

    # Bloquea cancelar una venta ya cancelada
    conn.execute("DROP TRIGGER IF EXISTS trg_block_double_cancel")
    conn.execute("""
        CREATE TRIGGER trg_block_double_cancel
        BEFORE UPDATE OF estado ON ventas
        WHEN OLD.estado = 'cancelada' AND NEW.estado = 'cancelada'
        BEGIN
            SELECT RAISE(ABORT, 'DOBLE_CANCELACION: la venta ya fue cancelada');
        END
    """)

    logger.info("Triggers de integridad de devoluciones creados/verificados.")


# ── 6. Índices ────────────────────────────────────────────────────────────────

def _create_indexes(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_sale_refunds_sale
        ON sale_refunds(sale_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_sale_refunds_item
        ON sale_refunds(sale_item_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_credit_notes_sale
        ON credit_notes(sale_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_movimientos_caja_op
        ON movimientos_caja(operation_id)
        WHERE operation_id IS NOT NULL
    """)
    logger.info("Índices de reversiones creados/verificados.")
