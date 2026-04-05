
# migrations/standalone/041_notification_inbox.py
# ── Inbox de notificaciones POS para empleados ────────────────────────────────
# Los mensajes se muestran al iniciar sesión como bandeja de entrada.
import logging, sqlite3
logger = logging.getLogger("spj.migrations.041")

def run(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notification_inbox (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado_id INTEGER NOT NULL,
            tipo        TEXT    NOT NULL,
            titulo      TEXT    NOT NULL,
            cuerpo      TEXT    DEFAULT '',
            datos       TEXT    DEFAULT '{}',
            leido       INTEGER DEFAULT 0,
            sucursal_id INTEGER DEFAULT 1,
            created_at  TEXT    DEFAULT (datetime('now')),
            leido_at    TEXT
        )""")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ni_empleado "
        "ON notification_inbox(empleado_id, leido)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ni_tipo "
        "ON notification_inbox(tipo, created_at DESC)")
    try: conn.commit()
    except Exception: pass
    logger.info("Migración 041: notification_inbox completada.")
