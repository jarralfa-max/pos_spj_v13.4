"""
076_purchase_requests.py
─────────────────────────
Phase 3 — Modelo documental ERP: Purchase Request (PR)

Crea:
  purchase_requests       — cabecera de solicitud de compra
  purchase_request_items  — partidas de la solicitud

Reglas:
  - PR NO afecta inventario
  - PR NO genera CxP
  - PR NO genera asiento contable
  - El inventario se afecta únicamente en recepción
"""


def run(conn):
    conn.executescript("""
        -- ── Solicitudes de Compra (PR) ────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS purchase_requests (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            folio           TEXT UNIQUE,
            proveedor_id    INTEGER,
            proveedor_nombre TEXT,
            sucursal_id     INTEGER NOT NULL DEFAULT 1,
            usuario         TEXT NOT NULL,
            subtotal        REAL NOT NULL DEFAULT 0,
            iva_monto       REAL NOT NULL DEFAULT 0,
            total           REAL NOT NULL DEFAULT 0,
            metodo_pago     TEXT DEFAULT 'CONTADO',
            condicion_pago  TEXT DEFAULT 'liquidado',
            plazo_dias      INTEGER DEFAULT 0,
            moneda          TEXT DEFAULT 'MXN',
            notas           TEXT,
            doc_ref         TEXT,

            -- Estados: BORRADOR | PENDIENTE_APROBACION | APROBADA | RECHAZADA |
            --          CONVERTIDA_A_PO | CANCELADA
            estado          TEXT NOT NULL DEFAULT 'BORRADOR',

            -- Aprobación / rechazo
            aprobado_por    TEXT,
            rechazado_por   TEXT,
            motivo_rechazo  TEXT,
            fecha_aprobacion DATETIME,

            fecha_creacion  DATETIME DEFAULT (datetime('now')),
            fecha_actualizacion DATETIME DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_pr_estado
            ON purchase_requests(estado, fecha_creacion DESC);

        CREATE INDEX IF NOT EXISTS idx_pr_proveedor
            ON purchase_requests(proveedor_id);

        CREATE INDEX IF NOT EXISTS idx_pr_sucursal
            ON purchase_requests(sucursal_id, estado);

        -- ── Partidas de PR ────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS purchase_request_items (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            pr_id           INTEGER NOT NULL REFERENCES purchase_requests(id),
            producto_id     INTEGER NOT NULL,
            nombre          TEXT NOT NULL,
            cantidad        REAL NOT NULL DEFAULT 0,
            unidad          TEXT DEFAULT 'kg',
            precio_unitario REAL NOT NULL DEFAULT 0,
            descuento       REAL DEFAULT 0,
            subtotal        REAL NOT NULL DEFAULT 0,
            lote            TEXT,
            fecha_caducidad DATE,
            notas           TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_pr_items_pr
            ON purchase_request_items(pr_id);
    """)
