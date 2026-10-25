"""p003 — Proyecciones centrales de Ventas e Inventario (arquitectura híbrida, Slice 5).

Se construyen desde el libro de hechos (`sync_inbox`), nunca desde las bases de
las estaciones:

* `central_sales` (+ renglones, pagos, devoluciones): una venta completada por
  sucursal y estación, con sus totales tal como la cerró la caja.
* `central_stock_movements` + `central_stock_effects`: cada movimiento con los
  efectos EXACTOS que aplicó a los saldos en la estación. La vista
  `central_stock_on_hand` los suma; la existencia central es conciliable por
  movimiento (cada número tiene detrás los movimientos que lo forman).
* `central_projection_log`: qué hecho ya se proyectó (idempotencia y reproceso);
  un hecho que falla queda en ERROR con su motivo sin trabar a los demás.

Dinero y cantidades en `NUMERIC` SIN escala fija: una escala fija (p. ej.
`NUMERIC(14,2)`) redondearía en silencio un valor con más decimales (§5.2:
«sin pérdida silenciosa»). El redondeo lo decide el dominio en la estación; aquí
se guarda exacto. Idempotente.
"""

from __future__ import annotations

DDL = (
    """
    CREATE TABLE IF NOT EXISTS central_projection_log (
        event_id      UUID NOT NULL REFERENCES sync_inbox (event_id),
        projector     TEXT NOT NULL,
        status        TEXT NOT NULL CHECK (status IN ('OK', 'SKIPPED', 'ERROR')),
        error         TEXT,
        projected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (event_id, projector),
        CHECK (status <> 'ERROR' OR error IS NOT NULL)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_central_projection_errors ON central_projection_log (projector)"
    " WHERE status = 'ERROR'",
    """
    CREATE TABLE IF NOT EXISTS central_sales (
        sale_id              UUID PRIMARY KEY,
        event_id             UUID NOT NULL UNIQUE REFERENCES sync_inbox (event_id),
        branch_id            UUID NOT NULL,
        station_id           UUID NOT NULL,
        folio                TEXT NOT NULL,
        customer_id          UUID,
        channel              TEXT NOT NULL,
        currency_code        TEXT NOT NULL,
        occurred_at          TIMESTAMPTZ NOT NULL,
        gross_subtotal       NUMERIC NOT NULL,
        discount_total       NUMERIC NOT NULL,
        promotion_total      NUMERIC NOT NULL,
        coupon_total         NUMERIC NOT NULL,
        loyalty_total        NUMERIC NOT NULL,
        tax_total            NUMERIC NOT NULL,
        rounding_adjustment  NUMERIC NOT NULL,
        total                NUMERIC NOT NULL,
        change_given         NUMERIC NOT NULL,
        status               TEXT NOT NULL DEFAULT 'COMPLETED'
                             CHECK (status IN ('COMPLETED', 'CANCELLED', 'REVERSED')),
        status_event_id      UUID REFERENCES sync_inbox (event_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_central_sales_branch_time ON central_sales (branch_id, occurred_at)",
    """
    CREATE TABLE IF NOT EXISTS central_sale_lines (
        sale_id     UUID NOT NULL REFERENCES central_sales (sale_id),
        line_no     INTEGER NOT NULL CHECK (line_no >= 1),
        product_id  UUID NOT NULL,
        quantity    NUMERIC NOT NULL,
        amount      NUMERIC NOT NULL,
        unit_cost   NUMERIC,
        PRIMARY KEY (sale_id, line_no)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_central_sale_lines_product ON central_sale_lines (product_id)",
    """
    CREATE TABLE IF NOT EXISTS central_sale_payments (
        sale_id  UUID NOT NULL REFERENCES central_sales (sale_id),
        method   TEXT NOT NULL,
        amount   NUMERIC NOT NULL,
        PRIMARY KEY (sale_id, method)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS central_sale_returns (
        event_id     UUID PRIMARY KEY REFERENCES sync_inbox (event_id),
        sale_id      UUID NOT NULL,
        branch_id    UUID NOT NULL,
        amount       NUMERIC NOT NULL,
        occurred_at  TIMESTAMPTZ NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_central_sale_returns_sale ON central_sale_returns (sale_id)",
    """
    CREATE TABLE IF NOT EXISTS central_stock_movements (
        movement_id      UUID PRIMARY KEY,
        event_id         UUID NOT NULL UNIQUE REFERENCES sync_inbox (event_id),
        branch_id        UUID NOT NULL,
        warehouse_id     UUID NOT NULL,
        movement_type    TEXT NOT NULL,
        document_module  TEXT,
        document_type    TEXT,
        document_id      UUID,
        reversal_of_id   UUID,
        occurred_at      TIMESTAMPTZ NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_central_stock_movements_branch"
    " ON central_stock_movements (branch_id, occurred_at)",
    """
    CREATE TABLE IF NOT EXISTS central_stock_effects (
        movement_id       UUID NOT NULL REFERENCES central_stock_movements (movement_id),
        effect_no         INTEGER NOT NULL CHECK (effect_no >= 1),
        product_id        UUID NOT NULL,
        lot_id            UUID,
        warehouse_id      UUID NOT NULL,
        location_id       UUID,
        inventory_status  TEXT NOT NULL,
        quantity_delta    NUMERIC NOT NULL,
        weight_delta      NUMERIC NOT NULL,
        PRIMARY KEY (movement_id, effect_no)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_central_stock_effects_product"
    " ON central_stock_effects (product_id, warehouse_id)",
    """
    CREATE OR REPLACE VIEW central_stock_on_hand AS
    SELECT m.branch_id, e.warehouse_id, e.product_id, e.inventory_status,
           SUM(e.quantity_delta) AS quantity, SUM(e.weight_delta) AS weight,
           COUNT(DISTINCT m.movement_id) AS movements
    FROM central_stock_effects e
    JOIN central_stock_movements m ON m.movement_id = e.movement_id
    GROUP BY m.branch_id, e.warehouse_id, e.product_id, e.inventory_status
    """,
)


def run(conn) -> None:
    with conn.cursor() as cur:
        for sentencia in DDL:
            cur.execute(sentencia)


up = run
