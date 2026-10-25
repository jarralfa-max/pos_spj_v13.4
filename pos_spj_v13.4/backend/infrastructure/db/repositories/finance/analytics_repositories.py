"""Hechos de rentabilidad (§33) y planeación de efectivo (§32).

``profitability_facts`` es un auxiliar analítico de Finanzas: una fila por
línea de venta/devolución/merma con su ingreso neto y costo, ligada al asiento
que la contabilizó (su suma cuadra contra el mayor). ``recurring_expense_plans``
es PLANEACIÓN: nunca produce asientos.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase
from backend.shared.ids import new_uuid

_FACT_FIELDS = ("fact_type", "source_module", "source_document_id", "line_reference",
                "journal_entry_id", "fact_date", "branch_id", "product_id", "category_id",
                "customer_id", "channel", "order_id", "route_id", "quantity", "net_revenue",
                "discount", "cost_of_sales", "direct_cost", "currency_code", "operation_id")


class ProfitabilityFactRepository(FinanceRepositoryBase):
    def record(self, **values) -> bool:
        """Inserta el hecho una sola vez (idempotente por tipo, origen y línea)."""
        unknown = set(values) - set(_FACT_FIELDS)
        if unknown:
            raise ValueError(f"Campos de hecho desconocidos: {sorted(unknown)}")
        existing = self._query_one(
            "SELECT id FROM profitability_facts WHERE fact_type=? AND source_module=?"
            " AND source_document_id=? AND line_reference=?",
            (values["fact_type"], values["source_module"], values["source_document_id"],
             values["line_reference"]))
        if existing is not None:
            return False
        row = {"id": new_uuid(),
               "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        row.update(values)
        self._insert("profitability_facts", row)
        return True


    def facts_of(self, *, fact_type: str, source_module: str,
                 source_document_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM profitability_facts WHERE fact_type=? AND source_module=?"
            " AND source_document_id=? ORDER BY line_reference",
            (fact_type, source_module, source_document_id))


class CashPlanningRepository(FinanceRepositoryBase):
    def save_plan(self, values: dict) -> None:
        self._insert("recurring_expense_plans", values)

    def update_plan(self, plan_id: str, values: dict) -> None:
        self._update("recurring_expense_plans", values, where="id=?", params=(plan_id,))

    def get_plan(self, plan_id: str) -> dict | None:
        return self._query_one("SELECT * FROM recurring_expense_plans WHERE id=?", (plan_id,))
