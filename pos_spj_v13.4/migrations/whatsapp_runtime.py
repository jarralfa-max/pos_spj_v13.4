"""Channel-only schema provisioning. Never runs the ERP migration engine.

Existing commercial schemas are owned by the ERP. Incompatible channel schemas
fail without altering or deleting existing data.
"""
from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema

CHANNEL_VERSION = 1


def _validate_version(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS whatsapp_runtime_schema (component TEXT PRIMARY KEY, version INTEGER NOT NULL)")
    row = conn.execute("SELECT version FROM whatsapp_runtime_schema WHERE component='channel'").fetchone()
    if row and row[0] != CHANNEL_VERSION:
        raise RuntimeError("Incompatible WhatsApp channel schema version")


def migrate_channel_schema(conn):
    _validate_version(conn)
    create_whatsapp_schema(conn)
    conn.execute("""CREATE TABLE IF NOT EXISTS wa_event_log (
        id TEXT NOT NULL PRIMARY KEY, event_type TEXT NOT NULL, data_json TEXT,
        sucursal_id TEXT, prioridad INTEGER DEFAULT 5, timestamp TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS wa_horarios_sucursal (
        id TEXT NOT NULL PRIMARY KEY, sucursal_id TEXT NOT NULL, dia TEXT NOT NULL,
        hora_apertura TEXT, hora_cierre TEXT, activo INTEGER DEFAULT 1,
        UNIQUE(sucursal_id,dia))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS ai_intent_log (
        id TEXT NOT NULL PRIMARY KEY, phone_hash TEXT, message_preview TEXT, intent TEXT,
        confidence TEXT, source TEXT, fallback_reason TEXT, needs_clarification INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')), latency_ms INTEGER DEFAULT 0, model TEXT, error TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS wa_business_idempotency (
        id TEXT NOT NULL PRIMARY KEY, action_key TEXT UNIQUE NOT NULL, phone TEXT NOT NULL,
        action_type TEXT NOT NULL, status TEXT NOT NULL, result_json TEXT, error TEXT,
        created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')))""")
    for table in ("wa_event_log", "wa_horarios_sucursal", "ai_intent_log", "wa_business_idempotency"):
        columns = {r[1]: r[2].upper() for r in conn.execute(f"PRAGMA table_info({table})")}
        if columns.get("id") != "TEXT":
            raise RuntimeError(f"Incompatible WhatsApp schema: {table}.id must be UUID text; no data was converted")
    conn.execute("INSERT INTO whatsapp_runtime_schema(component,version) VALUES ('channel',?) ON CONFLICT(component) DO NOTHING", (CHANNEL_VERSION,))
    conn.commit()


def migrate_conversation_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS conversations (
        phone TEXT PRIMARY KEY, state TEXT DEFAULT 'idle', sucursal_id TEXT,
        sucursal_nombre TEXT DEFAULT '', cliente_id TEXT, cliente_nombre TEXT DEFAULT '',
        data_json TEXT DEFAULT '{}', last_activity TEXT DEFAULT (datetime('now')),
        created_at TEXT DEFAULT (datetime('now')))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS message_log (
        id TEXT NOT NULL PRIMARY KEY, message_id TEXT UNIQUE, phone TEXT,
        direction TEXT DEFAULT 'in', content TEXT, timestamp TEXT DEFAULT (datetime('now')))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS pending_intents (
        phone TEXT PRIMARY KEY, payload_json TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')))""")
    columns = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(message_log)")}
    if columns.get("id") != "TEXT":
        raise RuntimeError("Incompatible conversation schema: message_log requires UUID text identity")
    conn.commit()
