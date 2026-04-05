
# migrations/standalone/040_qr_reception.py
# ── Recepción de Mercancía con QR ─────────────────────────────────────────────
# Extiende recepciones con:
#   - uuid_qr: vinculación a trazabilidad_qr
#   - condicion_pago: liquidado | credito | parcial
#   - metodo_pago: efectivo | tarjeta | transferencia | cheque
#   - monto_pagado, saldo_pendiente
#   - vencimiento_credito
# Extiende recepcion_items con uuid_qr de contenedor para trazabilidad granular.
import logging, sqlite3
logger = logging.getLogger("spj.migrations.040")

def run(conn: sqlite3.Connection) -> None:
    _patch_recepciones(conn)
    _patch_recepcion_items(conn)
    _patch_trazabilidad_qr(conn)
    _create_contenedores_qr(conn)
    try: conn.commit()
    except Exception: pass
    logger.info("Migración 040: recepción QR completada.")

def _add(conn, tabla, col, defn):
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
    if col not in existing:
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {defn}")
        logger.debug("+ %s.%s", tabla, col)

def _patch_recepciones(conn):
    _add(conn, "recepciones", "uuid_qr",            "TEXT")
    _add(conn, "recepciones", "condicion_pago",      "TEXT DEFAULT 'liquidado'")
    _add(conn, "recepciones", "metodo_pago",         "TEXT DEFAULT 'efectivo'")
    _add(conn, "recepciones", "monto_pagado",        "REAL DEFAULT 0")
    _add(conn, "recepciones", "monto_total",         "REAL DEFAULT 0")
    _add(conn, "recepciones", "saldo_pendiente",     "REAL DEFAULT 0")
    _add(conn, "recepciones", "vencimiento_credito", "TEXT")
    _add(conn, "recepciones", "referencia_pago",     "TEXT")
    logger.info("recepciones extendida con campos de pago + QR.")

def _patch_recepcion_items(conn):
    _add(conn, "recepcion_items", "uuid_qr_contenedor", "TEXT")
    _add(conn, "recepcion_items", "lote_id",             "INTEGER")
    _add(conn, "recepcion_items", "fecha_caducidad",     "TEXT")
    logger.info("recepcion_items extendida con trazabilidad.")

def _patch_trazabilidad_qr(conn):
    _add(conn, "trazabilidad_qr", "recepcion_id",    "INTEGER")
    _add(conn, "trazabilidad_qr", "sucursal_destino","INTEGER")
    logger.info("trazabilidad_qr extendida con recepcion_id.")

def _create_contenedores_qr(conn):
    """
    Tabla de contenedores/cajas con QR reutilizables.
    El QR físico se pega al contenedor y solo se reemplaza si se daña.
    Al reutilizar el contenedor, se actualiza el registro con el nuevo viaje.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contenedores_qr (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid_qr         TEXT    NOT NULL UNIQUE,
            codigo_interno  TEXT,
            descripcion     TEXT,
            estado          TEXT    DEFAULT 'disponible'
                            CHECK(estado IN ('disponible','en_transito','recibido','dañado')),
            sucursal_origen INTEGER,
            sucursal_destino INTEGER,
            viaje_actual    INTEGER DEFAULT 0,
            created_at      TEXT    DEFAULT (datetime('now')),
            updated_at      TEXT    DEFAULT (datetime('now'))
        )""")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cont_uuid   ON contenedores_qr(uuid_qr)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cont_estado ON contenedores_qr(estado)")
    logger.info("contenedores_qr creada.")
