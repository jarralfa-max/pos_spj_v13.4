"""Lectura paginada de registros del módulo de Fidelidad (LOY-29).

Los repositorios de escritura hidratan agregados uno a uno y no paginan; las
pantallas necesitan listas filtrables. Este lector ejecuta una `RecordSpec`
—columnas, origen, orden, estado y columnas buscables— y devuelve una página.

Ninguna parte de la consulta viene de la pantalla: el texto buscado y el estado
viajan SIEMPRE como parámetros, y los filtros por igualdad sólo aceptan claves
que la propia especificación declara (`filters`). Así no hay forma de inyectar
SQL desde la UI (§13).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class RecordSpec:
    columns: tuple[tuple[str, str], ...]
    source: str
    order: str
    status: str | None = None
    search_in: tuple[str, ...] = ()
    where: str = ""
    #: clave pública → expresión SQL; sólo estas claves se pueden filtrar.
    filters: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RecordPage:
    rows: list[dict]
    total: int


class RecordPageReader:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def page(self, spec: RecordSpec, *, query: str = "", status: str | None = None,
             filters: Mapping[str, str] | None = None, limit: int = 50,
             offset: int = 0) -> RecordPage:
        clauses: list[str] = [spec.where] if spec.where else []
        params: list[Any] = []
        if status and spec.status:
            clauses.append(f"{spec.status} = ?")
            params.append(status)
        texto = (query or "").strip()
        if texto and spec.search_in:
            clauses.append("(" + " OR ".join(
                f"LOWER(COALESCE({col}, '')) LIKE ?" for col in spec.search_in) + ")")
            params.extend([f"%{texto.lower()}%"] * len(spec.search_in))
        for clave, valor in (filters or {}).items():
            expr = spec.filters.get(clave)
            if expr is None:
                raise ValueError(f"Filtro no permitido: {clave}")
            if valor in (None, ""):
                continue
            clauses.append(f"{expr} = ?")
            params.append(valor)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        total = self._conn.execute(
            f"SELECT COUNT(*) FROM {spec.source}{where}", tuple(params)).fetchone()[0]
        select = ", ".join(f"{expr} AS {alias}" for alias, expr in spec.columns)
        cursor = self._conn.execute(
            f"SELECT {select} FROM {spec.source}{where} ORDER BY {spec.order} LIMIT ? OFFSET ?",
            (*params, int(limit), int(offset)))
        names = [col[0] for col in cursor.description]
        return RecordPage(rows=[dict(zip(names, row)) for row in cursor.fetchall()],
                          total=int(total or 0))

    def scalar(self, sql: str, params: tuple = ()) -> Any:
        row = self._conn.execute(sql, params).fetchone()
        return row[0] if row else None


__all__ = ["RecordPage", "RecordPageReader", "RecordSpec"]
