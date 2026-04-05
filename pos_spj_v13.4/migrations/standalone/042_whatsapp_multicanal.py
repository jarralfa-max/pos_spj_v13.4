
# migrations/standalone/042_whatsapp_multicanal.py
# ── WhatsApp Multi-número Configurable ───────────────────────────────────────
# Diseño escalable: un número ahora, múltiples en el futuro sin migración extra.
#
# TABLA whatsapp_numeros:
#   canal:      'clientes' | 'rrhh' | 'alertas' (qué tipo de mensajes sale por este nro)
#   sucursal_id: NULL = global (aplica a todas las sucursales)
#                N    = solo para la sucursal N
#   proveedor:  'meta' | 'twilio' | 'mock'
#   activo:     1/0 — puede desactivarse sin borrar la config
#
# COMPATIBILIDAD: si no existe ningún registro, WhatsAppConfig usa las claves
# legacy de la tabla configuraciones (whatsapp_numero, wa_meta_token, etc.)
import logging, sqlite3
logger = logging.getLogger("spj.migrations.042")

def run(conn: sqlite3.Connection) -> None:
    _create_whatsapp_numeros(conn)
    _create_wa_config_view(conn)
    _seed_from_legacy(conn)
    try: conn.commit()
    except Exception: pass
    logger.info("Migración 042: whatsapp_numeros completada.")

def _create_whatsapp_numeros(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_numeros (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre          TEXT    NOT NULL,
            canal           TEXT    NOT NULL DEFAULT 'clientes'
                            CHECK(canal IN ('clientes','rrhh','alertas','todos')),
            sucursal_id     INTEGER,          -- NULL = global
            proveedor       TEXT    NOT NULL DEFAULT 'meta'
                            CHECK(proveedor IN ('meta','twilio','mock')),
            numero_negocio  TEXT,             -- +521234567890
            meta_token      TEXT,
            meta_phone_id   TEXT,
            twilio_sid      TEXT,
            twilio_token    TEXT,
            verify_token    TEXT    DEFAULT 'spj_verify',
            webhook_puerto  INTEGER DEFAULT 8767,
            activo          INTEGER DEFAULT 1,
            notas           TEXT,
            created_at      TEXT    DEFAULT (datetime('now')),
            updated_at      TEXT    DEFAULT (datetime('now'))
        )""")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_wa_num_canal_suc "
        "ON whatsapp_numeros(canal, COALESCE(sucursal_id, -1)) WHERE activo=1")
    logger.info("whatsapp_numeros creada.")

def _create_wa_config_view(conn):
    """Vista que resuelve el número correcto según canal y sucursal."""
    conn.execute("DROP VIEW IF EXISTS v_whatsapp_config")
    conn.execute("""
        CREATE VIEW v_whatsapp_config AS
        SELECT
            canal,
            sucursal_id,
            proveedor,
            numero_negocio,
            meta_token,
            meta_phone_id,
            twilio_sid,
            twilio_token,
            verify_token,
            webhook_puerto
        FROM whatsapp_numeros
        WHERE activo = 1
        ORDER BY
            CASE WHEN sucursal_id IS NOT NULL THEN 0 ELSE 1 END,
            id
    """)
    logger.info("Vista v_whatsapp_config creada.")

def _seed_from_legacy(conn):
    """Si ya hay configuración legacy, migrarla al nuevo esquema."""
    def _get(clave, default=""):
        try:
            r = conn.execute(
                "SELECT valor FROM configuraciones WHERE clave=?", (clave,)
            ).fetchone()
            return r[0] if r and r[0] else default
        except Exception:
            return default

    numero   = _get("whatsapp_numero")
    meta_tok = _get("wa_meta_token")
    meta_pid = _get("wa_meta_phone_id")
    twi_sid  = _get("wa_account_sid")
    twi_tok  = _get("wa_auth_token")

    # Solo sembrar si hay algo configurado y no existe ya un registro
    if (numero or meta_tok or twi_sid):
        existing = conn.execute(
            "SELECT 1 FROM whatsapp_numeros LIMIT 1"
        ).fetchone()
        if not existing:
            proveedor = "twilio" if twi_sid else "meta" if meta_tok else "mock"
            conn.execute("""
                INSERT INTO whatsapp_numeros
                    (nombre, canal, proveedor, numero_negocio,
                     meta_token, meta_phone_id, twilio_sid, twilio_token)
                VALUES(?,?,?,?,?,?,?,?)
            """, ("Principal", "todos", proveedor, numero,
                  meta_tok, meta_pid, twi_sid, twi_tok))
            logger.info("Configuración legacy migrada a whatsapp_numeros.")
