"""CommercialObligationQueryService — obligaciones por puntos, vales, cupones y tarjetas."""

from __future__ import annotations

from backend.application.queries.finance.base_finance_query_service import (
    FinanceQueryServiceBase,
    decimal_sum,
    money_text,
)

_OPEN = "('OPEN','PARTIALLY_REDEEMED','PENDING_RECOGNITION')"


def outstanding(row: dict):
    return (decimal_sum([row["recognized_amount"]]) - decimal_sum([row["redeemed_amount"]])
            - decimal_sum([row["released_amount"]]))


class CommercialObligationQueryService(FinanceQueryServiceBase):
    def open_obligations(self, *, instrument_type: str | None = None) -> list[dict]:
        conditions, params = [f"status IN {_OPEN}"], []
        if instrument_type:
            conditions.append("instrument_type = ?")
            params.append(instrument_type)
        rows = self._query(
            "SELECT id, instrument_type, source_module, source_instrument_id,"
            " recognition_basis, customer_id, branch_id, original_amount,"
            " recognized_amount, redeemed_amount, released_amount, status,"
            " issued_at, expires_at FROM commercial_obligations"
            f" WHERE {' AND '.join(conditions)} ORDER BY issued_at", tuple(params))
        for row in rows:
            row["outstanding"] = money_text(outstanding(row))
        return rows

    def summary_by_instrument(self) -> list[dict]:
        """Emitido vs canjeado vs expirado vs pendiente por tipo."""
        grouped: dict[str, dict] = {}
        for row in self._query(
                "SELECT instrument_type, recognized_amount, redeemed_amount, released_amount"
                " FROM commercial_obligations ORDER BY instrument_type"):
            bucket = grouped.setdefault(row["instrument_type"], {
                "instrument_type": row["instrument_type"], "instruments": 0,
                "recognized": [], "redeemed": [], "released": [], "outstanding": []})
            bucket["instruments"] += 1
            for key, column in (("recognized", "recognized_amount"),
                                ("redeemed", "redeemed_amount"),
                                ("released", "released_amount")):
                bucket[key].append(row[column])
            bucket["outstanding"].append(outstanding(row))
        return [{**b, **{k: money_text(decimal_sum(b[k]))
                         for k in ("recognized", "redeemed", "released", "outstanding")}}
                for b in grouped.values()]

    def open_total(self) -> str:
        return money_text(decimal_sum(outstanding(r) for r in self._query(
            "SELECT recognized_amount, redeemed_amount, released_amount"
            f" FROM commercial_obligations WHERE status IN {_OPEN}")))

    def expired_without_posting(self, as_of: str) -> list[dict]:
        """Obligaciones vencidas por fecha que siguen abiertas (excepciones)."""
        return self._query(
            "SELECT id, instrument_type, source_instrument_id, expires_at, status"
            " FROM commercial_obligations WHERE expires_at IS NOT NULL AND expires_at < ?"
            f" AND status IN {_OPEN}", (as_of,))

    def events_without_entry(self) -> list[dict]:
        return self._query(
            "SELECT event_id, event_name, operation_id, processed_at FROM finance_processed_events"
            " WHERE operation_id NOT IN (SELECT operation_id FROM journal_entries)"
            " AND event_name NOT LIKE 'FISCAL_PERIOD%'")
