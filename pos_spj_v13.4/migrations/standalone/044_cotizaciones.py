
# migrations/standalone/044_cotizaciones.py — SPJ POS v12
"""
Migración 044 — Tablas de cotizaciones y presupuestos.

CotizacionService._init_tables() creaba estas tablas ad-hoc;
se centraliza aquí para respetar el ciclo formal de migraciones.
"""
import logging
logger = logging.getLogger(__name__)

VERSION = "044"
DESCRIPTION = "Tablas cotizaciones y cotizaciones_detalle"


def up(conn):
    conn.executescript("""
        -- Cotizaciones / presupuestos
        CREATE TABLE IF NOT EXISTS cotizaciones (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid             TEXT UNIQUE DEFAULT (lower(hex(randomblob(16)))),
            folio            TEXT UNIQUE,
            cliente_id       INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
            cliente_nombre   TEXT,
            subtotal         REAL DEFAULT 0,
            descuento        REAL DEFAULT 0,
            total            REAL DEFAULT 0,
            estado           TEXT DEFAULT 'pendiente'
                             CHECK(estado IN ('pendiente','aprobada','rechazada',
                                              'vencida','convertida')),
            notas            TEXT,
            vigencia_dias    INTEGER DEFAULT 7,
            fecha_vencimiento DATE,
            venta_id         INTEGER REFERENCES ventas(id) ON DELETE SET NULL,
            usuario          TEXT,
            sucursal_id      INTEGER DEFAULT 1,
            fecha            DATETIME DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_cot_estado
            ON cotizaciones(estado, sucursal_id);
        CREATE INDEX IF NOT EXISTS idx_cot_cliente
            ON cotizaciones(cliente_id);
        CREATE INDEX IF NOT EXISTS idx_cot_vencimiento
            ON cotizaciones(fecha_vencimiento) WHERE estado = 'pendiente';

        -- Items de cada cotización
        CREATE TABLE IF NOT EXISTS cotizaciones_detalle (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            cotizacion_id    INTEGER NOT NULL
                             REFERENCES cotizaciones(id) ON DELETE CASCADE,
            producto_id      INTEGER REFERENCES productos(id) ON DELETE SET NULL,
            nombre           TEXT NOT NULL,
            cantidad         REAL NOT NULL CHECK(cantidad > 0),
            unidad           TEXT DEFAULT 'kg',
            precio_unitario  REAL NOT NULL CHECK(precio_unitario >= 0),
            descuento_pct    REAL DEFAULT 0 CHECK(descuento_pct BETWEEN 0 AND 100),
            subtotal         REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cot_det_cot
            ON cotizaciones_detalle(cotizacion_id);
    """)
    logger.info("044 — cotizaciones y cotizaciones_detalle creadas")
