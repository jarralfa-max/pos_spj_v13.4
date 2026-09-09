"""Sales/POS bounded context — born-clean UUIDv7 schema (single source of
truth). Mirrors backend/infrastructure/db/schema/inventory_schema.py's
conventions exactly.

Rules (REGLA CERO / §8 / §9):
- Every id is ``TEXT NOT NULL PRIMARY KEY`` holding a lowercase UUIDv7 (PostgreSQL: UUID).
- quantity / price / discount / tax / total columns are ``TEXT`` decimal
  strings (PostgreSQL: NUMERIC); no REAL — floats are forbidden. Conversion
  to/from ``Decimal`` happens in the repository layer (POS-5, not built yet),
  never in SQL.
- Structural idempotency: UNIQUE(operation_id) on ``sales`` (§39 — 'evita
  ventas... duplicadas'), UNIQUE(event_id) on ``sales_outbox``.
- Status/enum values are NOT enforced via SQL CHECK — the domain layer
  (``backend/domain/sales/enums.py`` + policies) is the single source of
  truth for valid transitions, matching this repo's own established
  convention (confirmed: inventory_schema.py has zero enum CHECK
  constraints either, despite also being a "born-clean" schema).

Canonical English names (``sales``, ``sale_lines``) do NOT collide with the
legacy operational tables this bounded context does not touch or replace
yet (``ventas``, ``detalles_venta`` — see ``migrations/m000_base_schema.py``
``_create_ventas``, still REAL-typed money).

CORRECCIÓN (2026-09-08): este docstring decía que ``ventas`` era "the only
live write path per docs/refactor/SALES-0_auditoria.md". Fue cierto en
SALES-4 y dejó de serlo en SALES-19..22, cuando ``modulos/ventas.py`` se
borró y ``sales_pos`` pasó a ser la única pantalla de POS viva: hoy una
venta cobrada en el POS persiste AQUÍ, vía ``CheckoutSaleUseCase`` ->
``SalesUnitOfWork``. La tabla legacy sigue recibiendo el tráfico de la API
REST, cotizaciones, pedidos, anticipos y Delivery, y sigue siendo la que
leen BI, forecasting e historial de cliente — es decir, los dos modelos
están vivos a la vez y sin puente. La brecha está medida y congelada en
``tests/architecture/test_sales_persistence_split_ratchet.py``.

``payments``/``sale_refunds``
are ALREADY legacy table names taken by ``_create_ventas`` — this schema
uses ``sale_payments`` if/when a payments table is needed by a future phase,
never the bare ``payments`` name.

Only a migration in ``migrations/`` may execute this DDL.
"""

from __future__ import annotations

SALES_TABLES: tuple[str, ...] = (
    "sales",
    "sale_lines",
    "sale_payments",
    "sale_returns",
    "sale_invoice_requests",
    "sales_outbox",
)

_DDL = (
    # ── Sale aggregate root (backend/domain/sales/entities.py::Sale) ───────
    """
    CREATE TABLE IF NOT EXISTS sales (
        id TEXT NOT NULL PRIMARY KEY,
        branch_id TEXT NOT NULL,
        cashier_user_id TEXT NOT NULL,
        operation_id TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'DRAFT',   -- DRAFT | ACTIVE | SUSPENDED | CHECKOUT_PENDING | PAYMENT_PENDING | COMPLETED | CANCELLED | RETURNED_PARTIALLY | RETURNED_FULLY | REVERSED
        sale_number TEXT,
        workstation_id TEXT,
        cash_session_id TEXT,
        customer_id TEXT,
        channel TEXT NOT NULL DEFAULT 'POS',
        currency_code TEXT NOT NULL DEFAULT 'MXN',
        gross_subtotal TEXT NOT NULL DEFAULT '0',
        discount_total TEXT NOT NULL DEFAULT '0',
        promotion_total TEXT NOT NULL DEFAULT '0',
        coupon_total TEXT NOT NULL DEFAULT '0',
        loyalty_total TEXT NOT NULL DEFAULT '0',
        tax_total TEXT NOT NULL DEFAULT '0',
        rounding_adjustment TEXT NOT NULL DEFAULT '0',
        total TEXT NOT NULL DEFAULT '0',
        sale_level_discount TEXT NOT NULL DEFAULT '0',
        loyalty_redeemed_amount TEXT NOT NULL DEFAULT '0',
        version INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        suspended_at TEXT,
        completed_at TEXT,
        cancelled_at TEXT,
        reversed_at TEXT,
        suspended_by_user_id TEXT,
        suspended_workstation_id TEXT,
        inventory_reservation_id TEXT
    )
    """,
    # ── SaleLine (backend/domain/sales/entities.py::SaleLine) ──────────────
    """
    CREATE TABLE IF NOT EXISTS sale_lines (
        id TEXT NOT NULL PRIMARY KEY,
        sale_id TEXT NOT NULL REFERENCES sales(id),
        product_id TEXT NOT NULL,
        product_snapshot TEXT NOT NULL DEFAULT '{}',   -- JSON: nombre/sku/unidad al momento de agregar (§11)
        quantity TEXT NOT NULL,
        quantity_unit TEXT NOT NULL DEFAULT 'PZA',
        unit_price TEXT NOT NULL,
        pricing_snapshot_id TEXT,
        discount_total TEXT NOT NULL DEFAULT '0',
        tax_total TEXT NOT NULL DEFAULT '0',
        weight_source TEXT,
        lot_reference TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── SalePayment (backend/domain/sales/value_objects/sale_payment.py,
    #    POS-13). "sale_payments", never bare "payments" — that name is
    #    already taken by the legacy `_create_ventas` table (see module
    #    docstring above). ──────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS sale_payments (
        id TEXT NOT NULL PRIMARY KEY,
        sale_id TEXT NOT NULL REFERENCES sales(id),
        method TEXT NOT NULL,   -- CASH | CARD | TRANSFER | CREDIT | MERCADO_PAGO
        amount TEXT NOT NULL,
        reference TEXT,
        captured_by_user_id TEXT NOT NULL,
        captured_at TEXT NOT NULL
    )
    """,
    # ── SaleReturn (backend/domain/sales/value_objects/sale_return.py,
    #    POS-16) — partial-line returns against a COMPLETED sale ───────────
    """
    CREATE TABLE IF NOT EXISTS sale_returns (
        id TEXT NOT NULL PRIMARY KEY,
        sale_id TEXT NOT NULL REFERENCES sales(id),
        line_id TEXT NOT NULL REFERENCES sale_lines(id),
        quantity TEXT NOT NULL,
        amount TEXT NOT NULL,
        reason TEXT NOT NULL,
        requested_by_user_id TEXT NOT NULL,
        authorized_by_user_id TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    # ── SaleInvoiceRequest (backend/domain/sales/entities.py, POS-18) —
    #    CFDI invoice requests against a completed sale ───────────────────
    """
    CREATE TABLE IF NOT EXISTS sale_invoice_requests (
        id TEXT NOT NULL PRIMARY KEY,
        sale_id TEXT NOT NULL REFERENCES sales(id),
        tax_identifier TEXT NOT NULL,
        legal_name TEXT NOT NULL,
        cfdi_use TEXT NOT NULL,
        requested_by_user_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'REQUESTED',   -- REQUESTED | ISSUED | ERROR | CANCELLED
        uuid_fiscal TEXT,
        error_message TEXT,
        requested_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # ── transactional outbox (§39, master prompt phase POS-4) ──────────────
    """
    CREATE TABLE IF NOT EXISTS sales_outbox (
        id TEXT NOT NULL PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        event_name TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',   -- PENDING | DISPATCHED | DEAD_LETTER
        created_at TEXT NOT NULL,
        dispatched_at TEXT
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_sales_branch_status ON sales(branch_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_sales_cashier ON sales(cashier_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_sales_customer ON sales(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_sales_workstation_status ON sales(workstation_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_sale_lines_sale_id ON sale_lines(sale_id)",
    "CREATE INDEX IF NOT EXISTS idx_sale_lines_product_id ON sale_lines(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_sale_payments_sale_id ON sale_payments(sale_id)",
    "CREATE INDEX IF NOT EXISTS idx_sale_returns_sale_id ON sale_returns(sale_id)",
    "CREATE INDEX IF NOT EXISTS idx_sale_returns_line_id ON sale_returns(line_id)",
    "CREATE INDEX IF NOT EXISTS idx_sale_invoice_requests_sale_id"
    " ON sale_invoice_requests(sale_id)",
    "CREATE INDEX IF NOT EXISTS idx_sales_outbox_status ON sales_outbox(status)",
)


def create_sales_schema(conn) -> None:
    """Create the canonical Sales/POS schema (idempotent). DDL lives only here."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)


def drop_sales_schema(conn) -> list[str]:
    dropped: list[str] = []
    for table in reversed(SALES_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
