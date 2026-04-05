# migrations/standalone/048_v131_hardening.py — SPJ POS v13.1
"""
Migración 048 — Hardening v13.1

  1. Añade sync_inbox.lamport_ts para ordenamiento de eventos
  2. Garantiza que ventas.sucursal_id exista (refuerzo de 047)
  3. Añade device_id + sequence a event_log para multi-sucursal
  4. Índices de performance para sync y audit
  5. Crea sync_state si no existe con valores iniciales
"""
import logging
logger = logging.getLogger("spj.migrations.048")


def _add_col(conn, table: str, col_def: str) -> None:
    col_name = col_def.split()[0]
    try:
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if col_name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
    except Exception as e:
        logger.debug("048 add_col %s.%s: %s", table, col_name, e)


def _safe_index(conn, sql: str) -> None:
    try:
        conn.execute(sql)
    except Exception as e:
        logger.debug("048 index: %s — %s", sql[:50], e)


def up(conn) -> None:
    # ── 1. ventas.sucursal_id (double-ensure from 047) ────────────────────────
    _add_col(conn, "ventas",              "sucursal_id INTEGER NOT NULL DEFAULT 1")
    _add_col(conn, "compras",             "sucursal_id INTEGER NOT NULL DEFAULT 1")
    _add_col(conn, "lotes",               "sucursal_id INTEGER NOT NULL DEFAULT 1")
    _add_col(conn, "caja_operations",     "sucursal_id INTEGER NOT NULL DEFAULT 1")
    _add_col(conn, "pedidos_whatsapp",    "sucursal_id INTEGER NOT NULL DEFAULT 1")
    _add_col(conn, "delivery_orders",     "sucursal_id INTEGER NOT NULL DEFAULT 1")

    # ── 2. sync_inbox Lamport ordering ────────────────────────────────────────
    _add_col(conn, "sync_inbox",  "lamport_ts INTEGER DEFAULT 0")
    _add_col(conn, "sync_inbox",  "device_id TEXT DEFAULT 'local'")
    _add_col(conn, "sync_outbox", "lamport_ts INTEGER DEFAULT 0")

    # ── 3. event_log device tracking ─────────────────────────────────────────
    _add_col(conn, "event_log", "origin_device_id TEXT DEFAULT 'local'")
    _add_col(conn, "event_log", "device_sequence INTEGER DEFAULT 0")
    _add_col(conn, "event_log", "payload_hash TEXT")

    # ── 4. audit_logs improvements ───────────────────────────────────────────
    _add_col(conn, "audit_logs", "operation_id TEXT")
    _add_col(conn, "audit_logs", "ip TEXT")

    # ── 5. sync_state bootstrap ───────────────────────────────────────────────
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_state (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.execute(
            "INSERT OR IGNORE INTO sync_state(key, value) VALUES('lamport_clock', '0')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO sync_state(key, value) VALUES('device_id', 'local')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO sync_state(key, value) VALUES('last_sync_at', '')"
        )
    except Exception as e:
        logger.debug("048 sync_state: %s", e)

    # ── 6. Performance indexes ────────────────────────────────────────────────
    _safe_index(conn,
        "CREATE INDEX IF NOT EXISTS idx_ventas_suc_fecha "
        "ON ventas(sucursal_id, fecha)")
    _safe_index(conn,
        "CREATE INDEX IF NOT EXISTS idx_sync_outbox_enviado "
        "ON sync_outbox(enviado, intentos)")
    _safe_index(conn,
        "CREATE INDEX IF NOT EXISTS idx_event_log_synced "
        "ON event_log(synced, sucursal_id)")
    _safe_index(conn,
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_fecha "
        "ON audit_logs(fecha, modulo)")
    _safe_index(conn,
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_entidad "
        "ON audit_logs(entidad, entidad_id)")

    try:
        conn.commit()
    except Exception:
        pass

    logger.info("048 — v13.1 hardening aplicado")
