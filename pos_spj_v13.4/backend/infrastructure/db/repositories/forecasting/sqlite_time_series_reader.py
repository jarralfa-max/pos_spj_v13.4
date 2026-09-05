"""SQLite implementation of TimeSeriesReaderPort for `daily_sales_by_product`
(BI-8).

Reads the same canonical tables `BiSalesQueryService` already reads
(`detalles_venta`/`ventas`, BI-4) — no new schema, no snapshot table. Any
calendar day in the requested range with no matching sales row comes back as
an explicit imputed-zero `TimeSeriesObservation` (§18) — the reader never
silently drops a gap day, and never claims a gap was genuine zero demand
without saying so via `imputation_reason`.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from backend.domain.forecasting.value_objects.time_series import TimeSeriesObservation

SERIES_KEY = "daily_sales_by_product"


class SqliteDailyProductSalesReader:
    def __init__(self, conn) -> None:
        self._conn = conn

    def read_observations(
        self,
        series_key: str,
        dimension_filter: dict[str, str],
        date_from: date,
        date_to: date,
    ) -> tuple[TimeSeriesObservation, ...]:
        if series_key != SERIES_KEY:
            raise ValueError(
                f"{type(self).__name__} only serves {SERIES_KEY!r}, got {series_key!r}"
            )
        product_id = dimension_filter.get("product")
        if not product_id:
            raise ValueError("dimension_filter['product'] is required for daily_sales_by_product")
        branch_id = dimension_filter.get("branch")

        clauses = ["v.estado = 'completada'", "DATE(v.fecha) BETWEEN ? AND ?", "dv.producto_id = ?"]
        params: list = [date_from.isoformat(), date_to.isoformat(), product_id]
        if branch_id:
            clauses.append("v.sucursal_id = ?")
            params.append(branch_id)
        where = " AND ".join(clauses)

        rows = self._conn.execute(
            "SELECT DATE(v.fecha) AS d, SUM(dv.cantidad) AS qty "
            "FROM detalles_venta dv JOIN ventas v ON v.id = dv.venta_id "
            f"WHERE {where} GROUP BY d",
            params,
        ).fetchall()
        by_date = {r[0]: Decimal(str(r[1] or 0)) for r in rows}

        observations: list[TimeSeriesObservation] = []
        current = date_from
        while current <= date_to:
            key = current.isoformat()
            if key in by_date:
                observations.append(TimeSeriesObservation(timestamp=current, value=by_date[key]))
            else:
                observations.append(TimeSeriesObservation(
                    timestamp=current, value=Decimal("0"), is_imputed=True,
                    imputation_reason="no_sales_recorded",
                ))
            current += timedelta(days=1)
        return tuple(observations)
