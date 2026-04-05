# migrations/standalone/048_sync_improvements.py — SPJ POS v13.2
"""
Migración 048 — Mejoras al sistema de sync (v13.2).

Cambios:
  - event_log.operation_id: traza qué UC/operación originó el evento
  - sync_outbox.operation_id: misma trazabilidad en la cola de envío
  - sync_outbox.uuid: asegurar unicidad para idempotencia
  - configuraciones: nuevas claves de sync (sync_url, sync_api_key)
"""
import logging
logger = logging.getLogger("spj.migrations.048")

VERSION     = "048"
DESCRIPTION = "Sync improvements: operation_id, uuid en outbox, claves de config"


def up(conn):
    def add_col(table, col_def):
        col_name = col_def.split()[0]
        try:
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if col_name not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
        except Exception as e:
            logger.debug("048 add_col %s.%s: %s", table, col_name, e)

    # Trazabilidad: operation_id en tablas de sync
    add_col("event_log",   "operation_id TEXT")
    add_col("sync_outbox", "operation_id TEXT")

    # Asegurar uuid en sync_outbox para idempotencia
    add_col("sync_outbox", "uuid TEXT")
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_outbox_uuid "
            "ON sync_outbox(uuid) WHERE uuid IS NOT NULL"
        )
    except Exception: pass

    # Índices de performance para sync
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_event_log_operation ON event_log(operation_id) WHERE operation_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_outbox_not_enviado ON sync_outbox(enviado, lamport_ts) WHERE enviado=0",
    ]:
        try: conn.execute(idx)
        except Exception: pass

    # Claves de configuración de sync (no sobreescribir si ya existen)
    for clave, valor in [
        ("sync_url",           ""),
        ("sync_api_key",       ""),
        ("sync_interval_seg",  "60"),
        ("sync_batch_size",    "100"),
        ("sync_enabled",       "0"),
    ]:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO configuraciones(clave,valor) VALUES(?,?)",
                (clave, valor)
            )
        except Exception: pass

    try: conn.commit()
    except Exception: pass
    logger.info("048 — sync improvements aplicados")
