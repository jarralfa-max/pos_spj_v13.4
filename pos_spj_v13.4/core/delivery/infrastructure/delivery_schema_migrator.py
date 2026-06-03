from __future__ import annotations

import logging
from collections.abc import Iterable

logger = logging.getLogger("spj.delivery.schema")


class DeliverySchemaMigrator:
    """Owns SQLite schema compatibility for delivery tables.

    The legacy repository and service may call this as a temporary shim, but all
    create/alter/index SQL is centralized here so repository methods stay focused
    on persistence operations.
    """

    DELIVERY_ORDER_COLUMNS: tuple[str, ...] = (
        "venta_id INTEGER",
        "folio TEXT",
        "whatsapp_order_id TEXT",
        "cliente_id INTEGER",
        "cliente_nombre TEXT",
        "cliente_tel TEXT",
        "direccion TEXT NOT NULL DEFAULT 'Sin dirección'",
        "lat REAL",
        "lng REAL",
        "estado TEXT DEFAULT 'pendiente'",
        "notas TEXT",
        "total REAL DEFAULT 0",
        "responsable_entrega TEXT",
        "usuario TEXT",
        "fecha DATETIME",
        "fecha_actualizacion DATETIME",
        "historial_cambios TEXT",
        "driver_id INTEGER",
        "sucursal_id INTEGER DEFAULT 1",
        "workflow_type TEXT",
        "delivery_type TEXT",
        "scheduled_at DATETIME",
        "source_channel TEXT DEFAULT 'whatsapp'",
        "weight_adjusted INTEGER DEFAULT 0",
        "pago_metodo TEXT DEFAULT ''",
        "pago_monto REAL DEFAULT 0",
        "costo_envio REAL DEFAULT 0",
        "adjustment_pending INTEGER DEFAULT 0",
        "adjustment_blocked_state TEXT DEFAULT ''",
    )
    DELIVERY_ITEM_COLUMNS: tuple[str, ...] = (
        "delivery_id INTEGER NOT NULL DEFAULT 0",
        "producto_id INTEGER",
        "nombre TEXT NOT NULL DEFAULT 'Producto'",
        "cantidad REAL NOT NULL DEFAULT 0",
        "precio_unitario REAL NOT NULL DEFAULT 0",
        "subtotal REAL NOT NULL DEFAULT 0",
        "unidad TEXT DEFAULT 'kg'",
        "requested_qty REAL",
        "prepared_qty REAL",
        "final_qty REAL",
        "prepared_by TEXT",
        "prepared_at DATETIME",
        "adjustment_reason TEXT",
        "tolerance_exceeded INTEGER DEFAULT 0",
        "pending_prepared_qty REAL",
        "pending_subtotal REAL",
        "adjustment_status TEXT DEFAULT 'none'",
        "adjustment_requested_at DATETIME",
        "adjustment_responded_at DATETIME",
        "adjustment_response TEXT",
        "adjustment_token TEXT",
        "tolerance_units REAL DEFAULT 0.2",
    )
    DELIVERY_HISTORY_COLUMNS: tuple[str, ...] = (
        "order_id INTEGER NOT NULL DEFAULT 0",
        "estado_anterior TEXT",
        "estado_nuevo TEXT",
        "usuario TEXT",
        "fecha DATETIME",
        "observacion TEXT",
        "reason TEXT",
        "metadata_json TEXT",
        "event_id INTEGER",
        "created_at DATETIME",
    )
    DRIVER_COLUMNS: tuple[str, ...] = (
        "nombre TEXT NOT NULL DEFAULT ''",
        "telefono TEXT",
        "vehiculo TEXT",
        "activo INTEGER DEFAULT 1",
        "en_ruta INTEGER DEFAULT 0",
        "sucursal_id INTEGER DEFAULT 1",
        "usuario_id INTEGER",
    )

    DELIVERY_OUTBOX_COLUMNS: tuple[str, ...] = (
        "event_type TEXT NOT NULL DEFAULT ''",
        "aggregate_type TEXT DEFAULT 'delivery_order'",
        "aggregate_id INTEGER NOT NULL DEFAULT 0",
        "payload_json TEXT NOT NULL DEFAULT '{}'",
        "status TEXT DEFAULT 'pending'",
        "retries INTEGER DEFAULT 0",
        "last_error TEXT",
        "created_at DATETIME DEFAULT CURRENT_TIMESTAMP",
        "processed_at DATETIME",
        "operation_id TEXT",
    )

    def __init__(self, db) -> None:
        if db is None:
            raise ValueError("DeliverySchemaMigrator requiere una conexión SQLite válida.")
        self.db = db

    def ensure_schema(self) -> None:
        self._create_base_tables()
        self._add_missing_columns("delivery_orders", self.DELIVERY_ORDER_COLUMNS)
        self._add_missing_columns("delivery_items", self.DELIVERY_ITEM_COLUMNS)
        self._add_missing_columns("delivery_order_history", self.DELIVERY_HISTORY_COLUMNS)
        self._add_missing_columns("drivers", self.DRIVER_COLUMNS)
        self._add_missing_columns("delivery_outbox_events", self.DELIVERY_OUTBOX_COLUMNS)
        self._create_indexes()
        self.db.commit()

    def _create_base_tables(self) -> None:
        self.db.execute(
            """
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
            )
            """
        )
        self.db.execute(
            """
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
            )
            """
        )
        self.db.execute(
            """
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
            )
            """
        )
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS drivers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                telefono TEXT,
                vehiculo TEXT,
                activo INTEGER DEFAULT 1,
                en_ruta INTEGER DEFAULT 0,
                sucursal_id INTEGER DEFAULT 1,
                usuario_id INTEGER
            )
            """
        )

        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS delivery_outbox_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                aggregate_type TEXT DEFAULT 'delivery_order',
                aggregate_id INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                retries INTEGER DEFAULT 0,
                last_error TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                processed_at DATETIME,
                operation_id TEXT
            )
            """
        )

    def _add_missing_columns(self, table: str, column_definitions: Iterable[str]) -> None:
        existing = self._column_names(table)
        for definition in column_definitions:
            column_name = definition.strip().split()[0]
            if column_name in existing:
                continue
            self.db.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")
            existing.add(column_name)

    def _column_names(self, table: str) -> set[str]:
        rows = self.db.execute(f"PRAGMA table_info({table})").fetchall()
        return {row[1] for row in rows}

    def _create_indexes(self) -> None:
        for sql in (
            "CREATE INDEX IF NOT EXISTS idx_delivery_estado ON delivery_orders(estado, fecha)",
            "CREATE INDEX IF NOT EXISTS idx_delivery_wa ON delivery_orders(whatsapp_order_id)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_venta ON delivery_orders(venta_id) WHERE venta_id IS NOT NULL",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_wa_order ON delivery_orders(whatsapp_order_id) WHERE whatsapp_order_id IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS idx_delivery_items_delivery_id ON delivery_items(delivery_id)",
            "CREATE INDEX IF NOT EXISTS idx_delivery_items_adjustment_status ON delivery_items(adjustment_status, delivery_id)",
            "CREATE INDEX IF NOT EXISTS idx_delivery_items_adjustment_token ON delivery_items(adjustment_token)",
            "CREATE INDEX IF NOT EXISTS idx_delivery_orders_adjustment_pending ON delivery_orders(adjustment_pending, estado)",
            "CREATE INDEX IF NOT EXISTS idx_delivery_workflow_status ON delivery_orders(workflow_type, estado)",
            "CREATE INDEX IF NOT EXISTS idx_delivery_history_order_created ON delivery_order_history(order_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_delivery_history_event_id ON delivery_order_history(event_id)",
            "CREATE INDEX IF NOT EXISTS idx_delivery_outbox_pending ON delivery_outbox_events(status, id)",
            "CREATE INDEX IF NOT EXISTS idx_delivery_outbox_aggregate ON delivery_outbox_events(aggregate_type, aggregate_id)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_outbox_operation ON delivery_outbox_events(event_type, aggregate_id, operation_id) WHERE operation_id IS NOT NULL",
        ):
            self.db.execute(sql)
