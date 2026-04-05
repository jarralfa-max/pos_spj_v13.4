# migrations/standalone/046_comisiones_happy_hour.py
"""Migración 046 — Tablas para comisiones de vendedores y reglas happy hour."""
import logging
logger = logging.getLogger(__name__)
VERSION = "046"
DESCRIPTION = "comisiones_config, comisiones_acumuladas, happy_hour_rules"

def up(conn):
    conn.executescript("""
        -- Config de comisiones por usuario (habilitable/deshabilitable)
        CREATE TABLE IF NOT EXISTS comisiones_config (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario      TEXT NOT NULL UNIQUE,
            pct_comision REAL NOT NULL DEFAULT 0.5
                        CHECK(pct_comision >= 0 AND pct_comision <= 50),
            activo       INTEGER NOT NULL DEFAULT 1,
            sucursal_id  INTEGER DEFAULT 1,
            created_at   DATETIME DEFAULT (datetime('now'))
        );

        -- Comisiones acumuladas por turno
        CREATE TABLE IF NOT EXISTS comisiones_acumuladas (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario      TEXT NOT NULL,
            venta_id     INTEGER REFERENCES ventas(id) ON DELETE CASCADE,
            total_venta  REAL NOT NULL,
            pct          REAL NOT NULL,
            monto        REAL NOT NULL,
            turno_fecha  DATE DEFAULT (date('now')),
            sucursal_id  INTEGER DEFAULT 1,
            pagado       INTEGER DEFAULT 0,
            created_at   DATETIME DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_comis_usuario
            ON comisiones_acumuladas(usuario, turno_fecha, pagado);

        -- Reglas de Happy Hour (descuentos por horario)
        CREATE TABLE IF NOT EXISTS happy_hour_rules (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre       TEXT NOT NULL,
            hora_inicio  TEXT NOT NULL,   -- 'HH:MM'
            hora_fin     TEXT NOT NULL,   -- 'HH:MM'
            dias_semana  TEXT DEFAULT '0,1,2,3,4,5,6',  -- CSV: 0=lun, 6=dom
            tipo_descuento TEXT DEFAULT 'porcentaje',    -- porcentaje | monto_fijo
            valor        REAL NOT NULL DEFAULT 10,
            aplica_a     TEXT DEFAULT 'todos',           -- todos | categoria | producto_id
            aplica_valor TEXT,                           -- nombre de categoria o id de producto
            mensaje_wa   TEXT,           -- Mensaje WhatsApp a enviar al activarse
            activo       INTEGER DEFAULT 1,
            sucursal_id  INTEGER DEFAULT 1,
            created_at   DATETIME DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_hh_activo
            ON happy_hour_rules(activo, sucursal_id);
    """)
    logger.info("046 — comisiones_config, comisiones_acumuladas, happy_hour_rules")
