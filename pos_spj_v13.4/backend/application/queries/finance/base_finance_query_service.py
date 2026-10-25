"""Read-only base for finance query services.

Query services never mutate state: no INSERT/UPDATE/DELETE, no commit.
They feed the desktop UI and BI consumers with stable dict/DTO rows.

Sumas monetarias (auditoría d9f2bca F20): ``decimal_sum`` es la única forma
de agregar importes. Los importes se guardan como texto decimal exacto; SQLite
los suma pasando por real binario (``SUM(CAST(... AS NUMERIC))``) y pierde
centavos en importes grandes. Aquí se suman como ``Decimal``. Un importe
ilegible es un error de datos y se reporta, nunca se salta en silencio.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from backend.domain.finance.exceptions import FinanceDomainError

#: Asientos que forman el mayor: los contabilizados y los originales revertidos
#: (su reverso los compensa). Borradores, validados y cancelados no cuentan.
POSTED = "('POSTED','REVERSED')"

#: Sucursal de una línea: la de la línea o, si no la trae, la del asiento.
LINE_BRANCH = "COALESCE(jl.branch_id, je.branch_id)"


def decimal_sum(values: Iterable) -> Decimal:
    total = Decimal("0")
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        try:
            total += Decimal(text)
        except InvalidOperation as exc:
            raise FinanceDomainError(f"Importe almacenado ilegible: {text!r}") from exc
    return total


def money_text(value: Decimal) -> str:
    return format(Decimal(value).quantize(Decimal("0.01")), "f")


@dataclass(frozen=True, slots=True)
class LedgerFilter:
    """Filtros comunes de lectura del mayor (§31): periodo y dimensiones."""

    date_from: str | None = None
    date_to: str | None = None
    branch_id: str | None = None
    cost_center_id: str | None = None
    profit_center_id: str | None = None
    project_id: str | None = None

    def sql(self) -> tuple[list[str], list]:
        conditions = [f"je.status IN {POSTED}"]
        params: list = []
        if self.date_from:
            conditions.append("je.posting_date >= ?")
            params.append(self.date_from)
        if self.date_to:
            conditions.append("je.posting_date <= ?")
            params.append(self.date_to)
        if self.branch_id:
            conditions.append(f"{LINE_BRANCH} = ?")
            params.append(self.branch_id)
        for column in ("cost_center_id", "profit_center_id", "project_id"):
            value = getattr(self, column)
            if value:
                conditions.append(f"jl.{column} = ?")
                params.append(value)
        return conditions, params


class FinanceQueryServiceBase:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = self._conn.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _query_one(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def _scalar(self, sql: str, params: tuple = (), default: str = "0") -> str:
        row = self._conn.execute(sql, params).fetchone()
        value = row[0] if row and row[0] is not None else default
        return str(value)

    def _money_sum(self, sql: str, params: tuple = ()) -> str:
        """Suma exacta de la primera columna de ``sql`` como texto decimal."""
        rows = self._conn.execute(sql, params).fetchall()
        return money_text(decimal_sum(r[0] for r in rows))
