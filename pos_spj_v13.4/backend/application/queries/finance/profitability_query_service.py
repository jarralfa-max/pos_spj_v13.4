"""ProfitabilityQueryService — rentabilidad por dimensión (§33).

Fuente: ``profitability_facts`` (una fila por línea de venta, devolución,
merma o costo directo, ligada al asiento que la contabilizó). Margen directo =
ventas netas − costo de venta − costos directos (merma, comisiones de cobro y
de delivery, costo de fidelidad, comisiones). Los costos indirectos NO se
asignan sin una política explícita: ``margin_with_allocations`` queda vacío y
la pantalla lo dice.

Por sucursal además se ofrece el resultado CONTABLE (estado de resultados por
sucursal), que es la cifra oficial.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.queries.finance.base_finance_query_service import (
    FinanceQueryServiceBase,
    decimal_sum,
    money_text,
)
from backend.application.queries.finance.financial_statement_query_service import (
    FinancialStatementQueryService,
)

_DIMENSIONS = {"branch": "branch_id", "product": "product_id", "category": "category_id",
               "customer": "customer_id", "channel": "channel", "order": "order_id",
               "route": "route_id"}


class ProfitabilityQueryService(FinanceQueryServiceBase):
    def __init__(self, connection, *, products=None, customers=None) -> None:
        super().__init__(connection)
        self._products = products
        self._customers = customers
        self._statements = FinancialStatementQueryService(connection)

    def by_dimension(self, dimension: str, *, date_from: str, date_to: str,
                     branch_id: str | None = None, limit: int = 200) -> list[dict]:
        column = _DIMENSIONS.get(dimension)
        if column is None:
            raise ValueError(f"Dimensión de rentabilidad desconocida: {dimension}")
        conditions, params = ["fact_date BETWEEN ? AND ?"], [date_from, date_to]
        if branch_id:
            conditions.append("branch_id = ?")
            params.append(branch_id)
        rows = self._query(
            f"SELECT {column} AS key, product_id, fact_type, quantity, net_revenue, discount,"
            f" cost_of_sales, direct_cost FROM profitability_facts"
            f" WHERE {' AND '.join(conditions)}", tuple(params))
        if dimension == "category" and self._products is not None:
            # La categoría vive en el catálogo de Productos: el hecho guarda el
            # producto y la categoría se resuelve al leer (la vigente).
            categories = self._products.categories_of(
                [r["product_id"] for r in rows if r["product_id"] and not r["key"]])
            for row in rows:
                row["key"] = row["key"] or categories.get(row["product_id"])
        grouped: dict[str | None, dict] = {}
        for row in rows:
            bucket = grouped.setdefault(row["key"], {
                "net_revenue": [], "discount": [], "cost_of_sales": [], "waste": [],
                "direct_cost": [], "quantity": []})
            sign = Decimal("-1") if row["fact_type"] == "RETURN" else Decimal("1")
            bucket["net_revenue"].append(sign * decimal_sum([row["net_revenue"]]))
            bucket["discount"].append(sign * decimal_sum([row["discount"]]))
            bucket["cost_of_sales"].append(sign * decimal_sum([row["cost_of_sales"]]))
            bucket["quantity"].append(sign * decimal_sum([row["quantity"]]))
            if row["fact_type"] == "WASTE":
                bucket["waste"].append(row["direct_cost"])
            elif row["fact_type"] not in ("SALE", "RETURN"):
                bucket["direct_cost"].append(row["direct_cost"])
        names = self._names(dimension, [k for k in grouped if k])
        result = []
        for key, bucket in grouped.items():
            revenue = decimal_sum(bucket["net_revenue"])
            cost = decimal_sum(bucket["cost_of_sales"])
            waste = decimal_sum(bucket["waste"])
            direct = decimal_sum(bucket["direct_cost"])
            margin = revenue - cost - waste - direct
            result.append({
                "key": key, "name": names.get(key, "") if key else "Sin asignar",
                "quantity": format(decimal_sum(bucket["quantity"]), "f"),
                "net_revenue": money_text(revenue),
                "discounts": money_text(decimal_sum(bucket["discount"])),
                "cost_of_sales": money_text(cost), "waste": money_text(waste),
                "direct_costs": money_text(direct),
                "gross_margin": money_text(revenue - cost),
                "contribution_margin": money_text(margin),
                "contribution_percent": (format((margin * 100 / revenue).quantize(
                    Decimal("0.1")), "f") if revenue else ""),
                "margin_with_allocations": "",
            })
        result.sort(key=lambda r: Decimal(r["contribution_margin"]), reverse=True)
        return result[:limit]

    def branch_results(self, *, date_from: str, date_to: str) -> list[dict]:
        """Resultado CONTABLE por sucursal (estado de resultados filtrado)."""
        branches = [r["branch_id"] for r in self._query(
            "SELECT DISTINCT COALESCE(jl.branch_id, je.branch_id) AS branch_id"
            " FROM journal_lines jl JOIN journal_entries je ON je.id = jl.journal_entry_id"
            " WHERE je.status IN ('POSTED','REVERSED') AND je.posting_date BETWEEN ? AND ?",
            (date_from, date_to)) if r["branch_id"]]
        rows = []
        for branch in branches:
            statement = self._statements.income_statement(date_from=date_from, date_to=date_to,
                                                          branch_id=branch)
            rows.append({"branch_id": branch, "net_revenue": statement["net_revenue"],
                         "gross_profit": statement["gross_profit"],
                         "operating_income": statement["operating_income"],
                         "net_income": statement["net_income"]})
        return rows

    def _names(self, dimension: str, keys: list[str]) -> dict[str, str]:
        if dimension == "product" and self._products is not None:
            return self._products.display_names(keys)
        if dimension == "category" and self._products is not None:
            return self._products.category_names(keys)
        if dimension == "customer" and self._customers is not None:
            return self._customers.display_names(keys)
        return {}
