"""Production query services — consultas de sólo lectura para Producción.

`MeatProductionQueryService` vivía aquí y se eliminó: era una delegación pura a
`core.services.production_query_service`, que desapareció con la carpeta `core/`.
No podía funcionar de ninguna forma y no tenía ni un consumidor en producción —
su único llamador era el test que probaba la propia delegación. Reimplementar sus
cinco consultas habría sido backend sin consumidor (§42) y con el contrato
inventado, porque la implementación está borrada (§18).

El import a nivel de módulo que hacía rompía `backend.application.queries` ENTERO
y, con él, la composición del shell después del login.

Si la vista de cárnicos vuelve a hacer falta, se construye en el contexto acotado
`meat_processing` y con un consumidor real.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.application.queries.base_query_service import BaseQueryService, KpiMetric, QueryFilters, SearchResult, TableRow


class ProductionQueryService(BaseQueryService):
    scope = "production"

    def search_production_runs(self, query: str, filters: QueryFilters | None = None) -> list[SearchResult]:
        return list(self.search(query, filters))

    def list_for_table(self, filters: QueryFilters | None = None) -> list[TableRow]:
        return list(self.list_rows(filters))

    def get_kpis(self, filters: QueryFilters | None = None) -> list[KpiMetric]:
        return list(self.metrics(filters))
