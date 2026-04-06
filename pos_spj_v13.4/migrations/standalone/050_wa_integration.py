# migrations/standalone/050_wa_integration.py
# ── FASE WA — Integración WhatsApp + ERP ─────────────────────────────────────
#
# Tablas para la orquestación WA ↔ ERP:
#   • wa_event_log          — trazabilidad de eventos WA
#   • wa_reminder_queue     — cola de recordatorios programados
#   • ordenes_compra        — órdenes de compra automáticas (si no existe)
#   • cotizaciones.venta_ref_id  — FK para conversión cotización → venta
#   • ventas.anticipo_pagado     — monto de anticipo registrado
#   • anticipos.referencia       — referencia de pago (MP ID)
#
# IDEMPOTENTE: CREATE TABLE IF NOT EXISTS / ALTER TABLE seguro.

import logging

logger = logging.getLogger("spj.migrations.050")


def _column_exists(conn, table: str, column: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(r[1] == column for r in rows)
    except Exception:
        return False


def _table_exists(conn, table: str) -> bool:
    try:
        r = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        ).fetchone()
        return r is not None
    except Exception:
        return False


def run(conn) -> None:
    """Aplica migración 050 — tablas integración WhatsApp."""

    # ── wa_event_log ──────────────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wa_event_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type  TEXT    NOT NULL,
            data_json   TEXT,
            sucursal_id INTEGER DEFAULT 1,
            prioridad   INTEGER DEFAULT 5,
            timestamp   TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_wa_event_log_type
        ON wa_event_log(event_type, timestamp DESC)
    """)

    # ── wa_reminder_queue ─────────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wa_reminder_queue (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo        TEXT    NOT NULL,
            event_type  TEXT    NOT NULL,
            data_json   TEXT    DEFAULT '{}',
            phone       TEXT    NOT NULL DEFAULT '',
            execute_at  TEXT    NOT NULL,
            prioridad   INTEGER DEFAULT 5,
            sucursal_id INTEGER DEFAULT 1,
            estado      TEXT    DEFAULT 'pendiente',
            created_at  TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_wa_reminder_execute
        ON wa_reminder_queue(estado, execute_at)
    """)

    # ── ordenes_compra (si no existe) ─────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ordenes_compra (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id     INTEGER NOT NULL,
            proveedor_id    INTEGER DEFAULT NULL,
            cantidad        REAL    NOT NULL DEFAULT 0.0,
            estado          TEXT    NOT NULL DEFAULT 'pendiente',
            sucursal_id     INTEGER DEFAULT 1,
            notas           TEXT    DEFAULT '',
            fecha_creacion  TEXT    DEFAULT (datetime('now')),
            fecha_cierre    TEXT    DEFAULT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_ordenes_compra_estado
        ON ordenes_compra(estado, fecha_creacion DESC)
    """)

    # ── cotizaciones: venta_ref_id ────────────────────────────────────────────
    if _table_exists(conn, "cotizaciones"):
        if not _column_exists(conn, "cotizaciones", "venta_ref_id"):
            try:
                conn.execute(
                    "ALTER TABLE cotizaciones ADD COLUMN venta_ref_id INTEGER DEFAULT NULL"
                )
            except Exception as e:
                logger.debug("cotizaciones.venta_ref_id: %s", e)

    # ── ventas: anticipo_pagado ───────────────────────────────────────────────
    if _table_exists(conn, "ventas"):
        if not _column_exists(conn, "ventas", "anticipo_pagado"):
            try:
                conn.execute(
                    "ALTER TABLE ventas ADD COLUMN anticipo_pagado REAL DEFAULT 0.0"
                )
            except Exception as e:
                logger.debug("ventas.anticipo_pagado: %s", e)

    # ── anticipos: referencia ─────────────────────────────────────────────────
    if _table_exists(conn, "anticipos"):
        if not _column_exists(conn, "anticipos", "referencia"):
            try:
                conn.execute(
                    "ALTER TABLE anticipos ADD COLUMN referencia TEXT DEFAULT ''"
                )
            except Exception as e:
                logger.debug("anticipos.referencia: %s", e)
        if not _column_exists(conn, "anticipos", "fecha_pago"):
            try:
                conn.execute(
                    "ALTER TABLE anticipos ADD COLUMN fecha_pago TEXT DEFAULT NULL"
                )
            except Exception as e:
                logger.debug("anticipos.fecha_pago: %s", e)

    # ── Feature flags nuevos en module_toggles ────────────────────────────────
    new_flags = [
        ("whatsapp_advanced_enabled", 0),
        ("reminder_engine_enabled",   0),
    ]
    for clave, activo in new_flags:
        conn.execute(
            "INSERT OR IGNORE INTO module_toggles(clave, activo) VALUES(?, ?)",
            (clave, activo)
        )

    try:
        conn.commit()
    except Exception:
        pass

    logger.info("Migración 050: tablas integración WhatsApp creadas/actualizadas.")
