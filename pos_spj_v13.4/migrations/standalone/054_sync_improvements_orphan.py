"""
054_sync_improvements_orphan.py — pos_spj v13.4
Resolución del conflicto de migración 048.

El archivo 048_sync_improvements.py agregaba columnas operation_id y uuid a
event_log y sync_outbox, más claves de configuración de sync, pero nunca se
ejecutó vía engine.py porque el canónico 048_v131_hardening.py fue el elegido.

Esta migración aplica esos cambios de forma idempotente.

Ver: migrations/MIGRATION_LOG.md — entrada 054, conflicto 048
"""
import logging

logger = logging.getLogger("spj.migrations.054")


def run(conn) -> None:
    logger.info("Migración 054 — sync improvements huérfanos de 048...")

    def add_col(table, col_def):
        col_name = col_def.split()[0]
        try:
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if col_name not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
                logger.debug("054 add_col %s.%s OK", table, col_name)
        except Exception as e:
            logger.debug("054 add_col %s.%s: %s", table, col_name, e)

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
    except Exception:
        pass

    # Índices de performance para sync
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_event_log_operation ON event_log(operation_id) WHERE operation_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_outbox_not_enviado ON sync_outbox(enviado, lamport_ts) WHERE enviado=0",
    ]:
        try:
            conn.execute(idx)
        except Exception:
            pass

    # Claves de configuración de sync (INSERT OR IGNORE — no sobreescribe)
    for clave, valor in [
        ("sync_url",          ""),
        ("sync_api_key",      ""),
        ("sync_interval_seg", "60"),
        ("sync_batch_size",   "100"),
        ("sync_enabled",      "0"),
    ]:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO configuraciones(clave, valor) VALUES(?,?)",
                (clave, valor)
            )
        except Exception:
            pass

    try:
        conn.commit()
    except Exception:
        pass

    logger.info("Migración 054 completada.")
