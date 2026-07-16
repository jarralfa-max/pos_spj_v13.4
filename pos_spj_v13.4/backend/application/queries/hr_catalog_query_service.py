"""Read-only query service for configurable HR catalogs."""

from __future__ import annotations

from sqlite3 import Connection

from backend.application.dto.hr_catalog_dto import HRCatalogItemDTO


class HRCatalogQueryService:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def list_contract_types(self, *, active_only: bool = True) -> list[HRCatalogItemDTO]:
        return self._list_catalog("contract_types", active_only=active_only)

    def list_payment_frequencies(self, *, active_only: bool = True) -> list[HRCatalogItemDTO]:
        return self._list_catalog("payment_frequencies", active_only=active_only)

    def _list_catalog(self, table_name: str, *, active_only: bool) -> list[HRCatalogItemDTO]:
        where = "WHERE active = 1" if active_only else ""
        rows = self._connection.execute(
            f"SELECT id, code, name, active FROM {table_name} {where} ORDER BY name"
        ).fetchall()
        return [HRCatalogItemDTO(id=row[0], code=row[1], name=row[2], active=bool(row[3])) for row in rows]
