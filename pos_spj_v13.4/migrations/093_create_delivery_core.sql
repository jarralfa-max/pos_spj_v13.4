-- Delivery core schema extracted from repositories/delivery_repository.py.
-- Idempotent for existing SQLite databases; column backfills are handled by
-- core.delivery.infrastructure.delivery_schema_migrator.DeliverySchemaMigrator.
CREATE TABLE IF NOT EXISTS delivery_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id INTEGER,
    folio TEXT,
    whatsapp_order_id TEXT,
    cliente_id INTEGER,
    cliente_nombre TEXT,
    cliente_tel TEXT,
    direccion TEXT NOT NULL,
    lat REAL,
    lng REAL,
    estado TEXT DEFAULT 'pendiente',
    notas TEXT,
    total REAL DEFAULT 0,
    responsable_entrega TEXT,
    usuario TEXT,
    fecha DATETIME DEFAULT (datetime('now')),
    fecha_actualizacion DATETIME,
    historial_cambios TEXT,
    driver_id INTEGER,
    sucursal_id INTEGER DEFAULT 1,
    workflow_type TEXT,
    delivery_type TEXT,
    scheduled_at DATETIME,
    source_channel TEXT DEFAULT 'whatsapp'
);

CREATE TABLE IF NOT EXISTS delivery_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id INTEGER NOT NULL,
    producto_id INTEGER,
    nombre TEXT NOT NULL,
    cantidad REAL NOT NULL DEFAULT 0,
    precio_unitario REAL NOT NULL DEFAULT 0,
    subtotal REAL NOT NULL DEFAULT 0,
    unidad TEXT DEFAULT 'kg',
    requested_qty REAL,
    prepared_qty REAL,
    final_qty REAL,
    prepared_by TEXT,
    prepared_at DATETIME,
    adjustment_reason TEXT,
    tolerance_exceeded INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS delivery_order_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    estado_anterior TEXT,
    estado_nuevo TEXT,
    usuario TEXT,
    fecha DATETIME DEFAULT (datetime('now')),
    observacion TEXT,
    reason TEXT,
    metadata_json TEXT,
    event_id INTEGER,
    created_at DATETIME DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS drivers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    telefono TEXT,
    vehiculo TEXT,
    activo INTEGER DEFAULT 1,
    en_ruta INTEGER DEFAULT 0,
    sucursal_id INTEGER DEFAULT 1,
    usuario_id INTEGER
);

CREATE INDEX IF NOT EXISTS idx_delivery_estado ON delivery_orders(estado, fecha);
CREATE INDEX IF NOT EXISTS idx_delivery_wa ON delivery_orders(whatsapp_order_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_venta ON delivery_orders(venta_id) WHERE venta_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_wa_order ON delivery_orders(whatsapp_order_id) WHERE whatsapp_order_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_delivery_items_delivery_id ON delivery_items(delivery_id);
CREATE INDEX IF NOT EXISTS idx_delivery_history_order_created ON delivery_order_history(order_id, created_at);
CREATE INDEX IF NOT EXISTS idx_delivery_history_event_id ON delivery_order_history(event_id);
