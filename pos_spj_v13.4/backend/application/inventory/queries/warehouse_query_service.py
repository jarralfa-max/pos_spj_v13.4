"""WarehouseQueryService — read side for the storage topology (§12, INV-5).

Lists warehouses/zones/locations and builds the location hierarchy tree from
``parent_location_id``. Read-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.infrastructure.db.repositories.inventory.warehouse_repository import (
    WarehouseRepository,
)


@dataclass
class LocationNode:
    id: str
    code: str
    name: str
    level: int
    status: str
    children: list["LocationNode"] = field(default_factory=list)


class WarehouseQueryService:
    def __init__(self, connection) -> None:
        self._repo = WarehouseRepository(connection)

    def list_warehouses(self, *, branch_id: str) -> list[dict]:
        return self._repo.list_by_branch(branch_id)

    def list_zones(self, *, warehouse_id: str) -> list[dict]:
        return self._repo.list_zones(warehouse_id)

    def list_locations(self, *, warehouse_id: str) -> list[dict]:
        return self._repo.list_locations(warehouse_id)

    def location_hierarchy(self, *, warehouse_id: str) -> list[LocationNode]:
        """Nest storage locations by ``parent_location_id`` into a forest of roots."""
        rows = self._repo.list_locations(warehouse_id)
        nodes: dict[str, LocationNode] = {
            r["id"]: LocationNode(id=r["id"], code=r["code"], name=r["name"],
                                  level=r["level"], status=r["status"]) for r in rows
        }
        roots: list[LocationNode] = []
        for r in rows:
            node = nodes[r["id"]]
            parent_id = r["parent_location_id"]
            if parent_id and parent_id in nodes:
                nodes[parent_id].children.append(node)
            else:
                roots.append(node)
        return roots
