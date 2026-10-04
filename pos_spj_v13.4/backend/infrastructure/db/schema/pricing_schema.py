"""Pricing / costing bounded context — born-clean UUIDv7 schema (PRC-3).

Rules (REGLA CERO / Money-only):
- Every id is ``TEXT NOT NULL PRIMARY KEY`` holding a lowercase UUIDv7 (PostgreSQL: UUID).
- Money amounts are ``TEXT`` decimal strings + a 3-letter ``*_currency`` column
  (PostgreSQL: NUMERIC + CHAR(3)); no REAL — floats are forbidden.
- Quantities/percentages are ``TEXT`` decimal too.
- Structural idempotency: UNIQUE(code) on price_list, UNIQUE dimension on
  product_price / product_cost, UNIQUE(event_id) on the change log.

Canonical English names (``price_list``, ``product_price``, ``product_cost`` …) do
NOT collide with the legacy Spanish tables (``listas_precio``, ``precios_lista``,
``precios_volumen``, ``historial_precios``), which keep their live readers until
PRC-6 repoints them and PRC-8 drops them. Only a migration may execute this DDL.
"""

from __future__ import annotations

PRICING_TABLES: tuple[str, ...] = (
    "price_list",
    "product_price",
    "volume_price",
    "customer_price_list",
    "product_cost",
    "price_change_log",
    "pricing_authorization_log",
    "pricing_outbox",
)

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS price_list (
        id TEXT NOT NULL PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        kind TEXT NOT NULL,                 -- BASE | CHANNEL | CUSTOMER | PROMOTIONAL
        status TEXT NOT NULL DEFAULT 'DRAFT',
        channel TEXT,
        discount_pct TEXT NOT NULL DEFAULT '0',
        inherits_from_id TEXT,
        created_by_user_id TEXT,
        approved_by_user_id TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT,
        FOREIGN KEY (inherits_from_id) REFERENCES price_list(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS product_price (
        id TEXT NOT NULL PRIMARY KEY,
        price_list_id TEXT NOT NULL,
        product_id TEXT NOT NULL,
        branch_id TEXT NOT NULL DEFAULT '',    -- '' = todas las sucursales
        sale_price TEXT NOT NULL,              -- Decimal string
        sale_price_currency TEXT NOT NULL DEFAULT 'MXN',
        min_price TEXT,
        min_price_currency TEXT,
        effective_from TEXT,
        effective_to TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(price_list_id, product_id, branch_id),
        FOREIGN KEY (price_list_id) REFERENCES price_list(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS volume_price (
        id TEXT NOT NULL PRIMARY KEY,
        product_price_id TEXT NOT NULL,
        min_quantity TEXT NOT NULL,            -- Decimal string
        price TEXT NOT NULL,
        price_currency TEXT NOT NULL DEFAULT 'MXN',
        FOREIGN KEY (product_price_id) REFERENCES product_price(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_price_list (
        customer_id TEXT NOT NULL,
        price_list_id TEXT NOT NULL,
        assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (customer_id, price_list_id),
        FOREIGN KEY (price_list_id) REFERENCES price_list(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS product_cost (
        id TEXT NOT NULL PRIMARY KEY,
        product_id TEXT NOT NULL,
        branch_id TEXT NOT NULL DEFAULT '',
        average_cost TEXT NOT NULL,            -- Decimal string
        average_cost_currency TEXT NOT NULL DEFAULT 'MXN',
        last_cost TEXT,
        standard_cost TEXT,
        cost_method TEXT NOT NULL DEFAULT 'AVERAGE',
        effective_from TEXT,
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(product_id, branch_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS price_change_log (
        id TEXT NOT NULL PRIMARY KEY,
        product_id TEXT NOT NULL,
        branch_id TEXT,
        field TEXT NOT NULL,                   -- sale_price | min_price | cost
        old_value TEXT,                        -- Decimal string
        new_value TEXT,
        currency TEXT NOT NULL DEFAULT 'MXN',
        user_id TEXT,
        authorized_by TEXT,
        operation_id TEXT NOT NULL,
        reason TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pricing_authorization_log (
        id TEXT NOT NULL PRIMARY KEY,
        permission_code TEXT NOT NULL,
        requested_by TEXT NOT NULL,
        authorized_by TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        reason TEXT NOT NULL,
        entity_id TEXT,
        device_id TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pricing_outbox (
        id TEXT NOT NULL PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        event_name TEXT NOT NULL,
        operation_id TEXT,
        entity_id TEXT,
        payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_price_list_status ON price_list(status, kind)",
    "CREATE INDEX IF NOT EXISTS idx_product_price_product ON product_price(product_id, branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_product_price_list ON product_price(price_list_id)",
    "CREATE INDEX IF NOT EXISTS idx_volume_price_pp ON volume_price(product_price_id)",
    "CREATE INDEX IF NOT EXISTS idx_customer_price_list_cust ON customer_price_list(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_product_cost_product ON product_cost(product_id, branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_price_change_log_product ON price_change_log(product_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_pricing_outbox_status ON pricing_outbox(status)",
)


def _column_exists(conn, table: str, column: str) -> bool:
    return any(str(row[1]) == column
               for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def create_pricing_schema(conn) -> None:
    """Create the canonical pricing schema (idempotent). DDL lives only here."""
    for statement in _DDL:
        conn.execute(statement)
    # `price_list.created_by_user_id` se añadió después. `CREATE TABLE IF NOT
    # EXISTS` no toca una tabla que ya existe, así que las bases creadas por una
    # ejecución anterior de esta misma función se quedarían sin la columna.
    #
    # No es cosmético: `PricingAuthorizationPolicy.ensure_segregation` compara
    # al aprobador contra el CREADOR de la lista, y ese creador no se guardaba
    # en ningún sitio. La protección estaba implementada y probada en
    # aislamiento, pero ninguna ruta real podía suministrarle el dato — es
    # decir, no podía dispararse nunca.
    if not _column_exists(conn, "price_list", "created_by_user_id"):
        conn.execute("ALTER TABLE price_list ADD COLUMN created_by_user_id TEXT")
    for index in _INDEXES:
        conn.execute(index)
    ensure_single_active_base_index(conn)


#: A lo sumo UNA lista base activa, garantizado por la base y no sólo por
#: `ActivatePriceListUseCase` (que desactiva la anterior en la misma operación).
#: Índice PARCIAL: las listas base inactivas —el historial— no cuentan.
SINGLE_ACTIVE_BASE_INDEX = "ux_price_list_single_active_base"


def active_base_list_count(conn) -> int:
    return int(conn.execute(
        "SELECT COUNT(*) FROM price_list WHERE kind='BASE' AND status='ACTIVE'"
    ).fetchone()[0])


def ensure_single_active_base_index(conn) -> bool:
    """Crea el índice único parcial si los datos lo permiten.

    Devuelve False —sin crear nada— si HOY hay más de una lista base activa:
    elegir cuál queda es una decisión de negocio (la toma la migración 284/299
    con la regla que el usuario fijó), no algo que el DDL pueda resolver
    borrando o desactivando en silencio.
    """
    if active_base_list_count(conn) > 1:
        return False
    conn.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {SINGLE_ACTIVE_BASE_INDEX} "
        "ON price_list(kind) WHERE kind='BASE' AND status='ACTIVE'")
    return True


def drop_pricing_schema(conn) -> list[str]:
    dropped: list[str] = []
    for table in reversed(PRICING_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
