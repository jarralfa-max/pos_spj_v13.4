"""Resultado por salida de una orden de procesamiento (§13, Fase 10)."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid

_COLUMNS = ("product_id", "output_type", "input_product_id", "input_weight",
            "input_unit_cost", "expected_weight", "actual_weight", "difference_weight",
            "expected_yield_pct", "yield_pct", "variance_pct", "unit_price",
            "allocated_cost", "unit_cost", "input_lot_id", "output_lot_id")


class ProcessingOutputResultsRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def replace_for_order(self, processing_order_id: str, rows: list[dict]) -> None:
        """Idempotente: una orden tiene UN juego de resultados (el último cálculo)."""
        self._conn.execute("DELETE FROM processing_output_results WHERE processing_order_id=?",
                           (processing_order_id,))
        ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for row in rows:
            valores = [None if row.get(c) is None else str(row[c]) for c in _COLUMNS]
            self._conn.execute(
                f"INSERT INTO processing_output_results (id, processing_order_id,"
                f" {', '.join(_COLUMNS)}, created_at) VALUES (?,?,"
                f"{','.join('?' * len(_COLUMNS))},?)",
                (new_uuid(), processing_order_id, *valores, ahora))

    def list_by_order(self, processing_order_id: str) -> list[dict]:
        cur = self._conn.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM processing_output_results"
            " WHERE processing_order_id=? ORDER BY output_type, product_id",
            (processing_order_id,))
        return [dict(zip(_COLUMNS, r)) for r in cur.fetchall()]
