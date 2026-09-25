"""Esquema del contexto de Costos (costeo real de transformaciones).

Una asignación por orden de producción: con qué método se repartió, cuánto
costó la entrada, cuánto vale lo producido y cuánto se reconoce como merma. Las
líneas guardan el costo de cada salida. `costing_outbox` lleva los hechos que
Costos publica (costo por salida para Precios, asiento para Finanzas).

Todas las identidades son UUIDv7 en TEXTO; todos los importes, decimales en TEXTO.
"""

from __future__ import annotations

_DEC = "CAST({0} AS NUMERIC) >= 0"
_METHODS = ("'WEIGHT_BASED','RELATIVE_SALES_VALUE','NET_REALIZABLE_VALUE',"
            "'STANDARD_COST','CONFIGURED_FACTOR'")

COSTING_TABLES: tuple[str, ...] = (
    "processing_cost_allocations",
    "processing_cost_allocation_lines",
    "costing_outbox",
)

_DDL = (
    f"""
    CREATE TABLE IF NOT EXISTS processing_cost_allocations (
        id TEXT NOT NULL PRIMARY KEY,
        operation_id TEXT NOT NULL UNIQUE CHECK (operation_id <> id),
        processing_order_id TEXT NOT NULL UNIQUE,
        source_module TEXT NOT NULL,
        branch_id TEXT NOT NULL,
        process_type TEXT NOT NULL,
        method TEXT NOT NULL CHECK (method IN ({_METHODS})),
        currency_code TEXT NOT NULL,
        input_cost_total TEXT NOT NULL CHECK ({_DEC.format('input_cost_total')}),
        output_value_total TEXT NOT NULL CHECK ({_DEC.format('output_value_total')}),
        waste_value_total TEXT NOT NULL CHECK ({_DEC.format('waste_value_total')}),
        created_by_user_id TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS processing_cost_allocation_lines (
        id TEXT NOT NULL PRIMARY KEY,
        allocation_id TEXT NOT NULL REFERENCES processing_cost_allocations(id),
        line_kind TEXT NOT NULL CHECK (line_kind IN ('INPUT','OUTPUT')),
        product_id TEXT NOT NULL,
        output_type TEXT,
        lot_id TEXT,
        quantity TEXT NOT NULL CHECK ({_DEC.format('quantity')}),
        unit_price TEXT,
        basis_value TEXT NOT NULL DEFAULT '0',
        allocated_cost TEXT NOT NULL CHECK ({_DEC.format('allocated_cost')}),
        unit_cost TEXT NOT NULL CHECK ({_DEC.format('unit_cost')})
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS costing_outbox (
        id TEXT NOT NULL PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        event_name TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','DISPATCHED')),
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        created_at TEXT NOT NULL,
        dispatched_at TEXT
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_cost_allocation_lines_allocation"
    " ON processing_cost_allocation_lines(allocation_id)",
    "CREATE INDEX IF NOT EXISTS idx_costing_outbox_status ON costing_outbox(status, created_at)",
)


def create_costing_schema(conn) -> None:
    """Idempotente. La llama la migración 273."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)


def drop_costing_schema(conn) -> list[str]:
    dropped = []
    for table in reversed(COSTING_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
