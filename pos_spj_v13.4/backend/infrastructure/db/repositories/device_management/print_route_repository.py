"""SqlitePrintRouteRepository — persists `PrintRoute` (SET-8). Implements
`backend.domain.device_management.repository_ports.PrintRouteRepositoryPort`.
"""

from __future__ import annotations

import json

from backend.domain.device_management.entities.print_route import PrintRoute
from backend.infrastructure.db.repositories.device_management.base import DeviceManagementRepositoryBase

_COLS = (
    "id, document_type, primary_device_id, fallback_device_ids_json, branch_id,"
    " workstation_id, module, channel, active, created_at, updated_at"
)


class SqlitePrintRouteRepository(DeviceManagementRepositoryBase):
    def save(self, route: PrintRoute) -> None:
        self._execute(
            f"INSERT INTO print_routes ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " primary_device_id=excluded.primary_device_id,"
            " fallback_device_ids_json=excluded.fallback_device_ids_json,"
            " branch_id=excluded.branch_id, workstation_id=excluded.workstation_id,"
            " module=excluded.module, channel=excluded.channel, active=excluded.active,"
            " updated_at=excluded.updated_at",
            self._params(route),
        )

    def get(self, route_id: str) -> PrintRoute | None:
        row = self._query_one(f"SELECT {_COLS} FROM print_routes WHERE id=?", (route_id,))
        return self._hydrate(row) if row else None

    def list_candidates(self, document_type: str) -> list[PrintRoute]:
        rows = self._query(
            f"SELECT {_COLS} FROM print_routes WHERE document_type=? AND active=1",
            (document_type.strip().upper(),),
        )
        return [self._hydrate(row) for row in rows]

    def list_active(self) -> list[PrintRoute]:
        rows = self._query(f"SELECT {_COLS} FROM print_routes WHERE active=1 ORDER BY document_type")
        return [self._hydrate(row) for row in rows]

    def list_all(self) -> list[PrintRoute]:
        rows = self._query(f"SELECT {_COLS} FROM print_routes ORDER BY document_type")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(route: PrintRoute) -> tuple:
        return (
            route.id, route.document_type, route.primary_device_id,
            json.dumps(list(route.fallback_device_ids)), route.branch_id, route.workstation_id,
            route.module, route.channel, int(route.active), route.created_at, route.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> PrintRoute:
        return PrintRoute(
            id=row["id"], document_type=row["document_type"], primary_device_id=row["primary_device_id"],
            fallback_device_ids=tuple(json.loads(row["fallback_device_ids_json"] or "[]")),
            branch_id=row["branch_id"], workstation_id=row["workstation_id"], module=row["module"],
            channel=row["channel"], active=bool(row["active"]), created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
