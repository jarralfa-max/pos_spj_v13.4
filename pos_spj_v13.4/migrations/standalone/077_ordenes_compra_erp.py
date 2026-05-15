"""
077_ordenes_compra_erp.py
──────────────────────────
Phase 3 — Extiende ordenes_compra (tabla existente) con campos ERP.

Agrega sin romper el schema existente:
  - pr_id             → FK a purchase_requests (nullable)
  - sucursal_id       → sucursal destino de la PO
  - sucursal_destino  → nombre de la sucursal
  - condicion_pago    → crédito/contado/liquidado
  - plazo_dias        → días de crédito
  - moneda            → MXN/USD
  - metodo_pago       → CONTADO/CREDITO/etc.
  - aprobado_por      → usuario que aprobó la PR origen
  - subtotal          → subtotal antes de IVA
  - iva_monto         → IVA de la orden
  - doc_ref           → referencia documental (factura estimada)

Estados ERP para ordenes_compra:
  borrador | pendiente | ABIERTA | PARCIAL | RECIBIDA | CERRADA | CANCELADA
  (se mantiene 'borrador'/'pendiente' para compat con flujo existente de WA)

Extiende ordenes_compra_items:
  - unidad            → unidad de medida
  - lote              → referencia de lote esperado
  - fecha_caducidad   → caducidad estimada
  - notas             → notas de la partida
"""


def run(conn):
    # ── ordenes_compra: agregar columnas faltantes ─────────────────────────────
    _safe_add_column(conn, "ordenes_compra", "pr_id",            "INTEGER")
    _safe_add_column(conn, "ordenes_compra", "sucursal_id",      "INTEGER DEFAULT 1")
    _safe_add_column(conn, "ordenes_compra", "sucursal_destino", "TEXT")
    _safe_add_column(conn, "ordenes_compra", "condicion_pago",   "TEXT DEFAULT 'liquidado'")
    _safe_add_column(conn, "ordenes_compra", "plazo_dias",       "INTEGER DEFAULT 0")
    _safe_add_column(conn, "ordenes_compra", "moneda",           "TEXT DEFAULT 'MXN'")
    _safe_add_column(conn, "ordenes_compra", "metodo_pago",      "TEXT DEFAULT 'CONTADO'")
    _safe_add_column(conn, "ordenes_compra", "aprobado_por",     "TEXT")
    _safe_add_column(conn, "ordenes_compra", "subtotal",         "REAL DEFAULT 0")
    _safe_add_column(conn, "ordenes_compra", "iva_monto",        "REAL DEFAULT 0")
    _safe_add_column(conn, "ordenes_compra", "doc_ref",          "TEXT")
    _safe_add_column(conn, "ordenes_compra", "fecha_actualizacion", "DATETIME")

    # ── ordenes_compra_items: agregar columnas faltantes ───────────────────────
    _safe_add_column(conn, "ordenes_compra_items", "unidad",          "TEXT DEFAULT 'kg'")
    _safe_add_column(conn, "ordenes_compra_items", "lote",            "TEXT")
    _safe_add_column(conn, "ordenes_compra_items", "fecha_caducidad", "DATE")
    _safe_add_column(conn, "ordenes_compra_items", "notas",           "TEXT")

    # ── Índices nuevos ─────────────────────────────────────────────────────────
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_oc_pr_id
            ON ordenes_compra(pr_id);

        CREATE INDEX IF NOT EXISTS idx_oc_sucursal_estado
            ON ordenes_compra(sucursal_id, estado);

        CREATE INDEX IF NOT EXISTS idx_oc_items_orden
            ON ordenes_compra_items(orden_id);
    """)


def _safe_add_column(conn, table: str, column: str, definition: str) -> None:
    """ALTER TABLE ADD COLUMN solo si la columna no existe."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
