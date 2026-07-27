import logging
import sqlite3

logger = logging.getLogger("spj.migrations.089")


def run(conn: sqlite3.Connection) -> None:
    for col in (
        "dedupe_key TEXT",
        "severity TEXT DEFAULT 'info'",
    ):
        try:
            conn.execute(f"ALTER TABLE notification_inbox ADD COLUMN {col}")
        except Exception:
            pass

    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_inbox_dedupe_key "
        "ON notification_inbox(dedupe_key) WHERE dedupe_key IS NOT NULL"
    )
    try:
        conn.commit()
    except Exception:
        pass
    logger.info("Migración 089: dedupe_key/severity en notification_inbox completada.")
