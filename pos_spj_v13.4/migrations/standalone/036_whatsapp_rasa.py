
# migrations/standalone/036_whatsapp_rasa.py
# ── WhatsApp Queue + Rasa Sessions ────────────────────────────────────────────
# Tablas requeridas por:
#   core/services/whatsapp_service.py  — cola persistente offline-first
#   rasa/actions/actions.py            — sesiones conversacionales
#
# IDEMPOTENTE: CREATE TABLE IF NOT EXISTS
import logging, sqlite3
logger = logging.getLogger("spj.migrations.036")

def run(conn: sqlite3.Connection) -> None:
    _create_whatsapp_queue(conn)
    _create_rasa_sessions(conn)
    _create_marketing_messages(conn)
    _create_indexes(conn)
    try: conn.commit()
    except Exception: pass
    logger.info("Migración 036: WhatsApp queue + Rasa sessions completada.")

def _create_whatsapp_queue(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_queue (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            to_number  TEXT    NOT NULL,
            message    TEXT    NOT NULL,
            template   TEXT,
            payload    TEXT,
            estado     TEXT    DEFAULT 'pendiente'
                               CHECK(estado IN ('pendiente','enviado','fallido')),
            intentos   INTEGER DEFAULT 0 CHECK(intentos >= 0),
            error      TEXT,
            fecha      TEXT    DEFAULT (datetime('now')),
            enviado_en TEXT
        )""")
    logger.info("whatsapp_queue creada/verificada.")

def _create_rasa_sessions(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rasa_sessions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id       TEXT    NOT NULL UNIQUE,
            slots           TEXT    DEFAULT '{}',
            last_message_at TEXT    DEFAULT (datetime('now')),
            pedido_activo_id INTEGER,
            FOREIGN KEY (pedido_activo_id) REFERENCES pedidos(id) ON DELETE SET NULL
        )""")
    logger.info("rasa_sessions creada/verificada.")

def _create_marketing_messages(conn):
    """Tabla de templates personalizables para WhatsApp / tickets."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS marketing_messages (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre    TEXT    NOT NULL UNIQUE,
            mensaje   TEXT    NOT NULL,
            contexto  TEXT    DEFAULT 'whatsapp',
            prioridad INTEGER DEFAULT 0,
            activo    INTEGER DEFAULT 1,
            creado_en TEXT    DEFAULT (datetime('now'))
        )""")
    logger.info("marketing_messages creada/verificada.")

def _create_indexes(conn):
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wa_queue_estado    ON whatsapp_queue(estado, fecha)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wa_queue_intentos  ON whatsapp_queue(intentos)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rasa_sender        ON rasa_sessions(sender_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_marketing_contexto ON marketing_messages(contexto, activo)")
    logger.info("Índices 036 creados/verificados.")
