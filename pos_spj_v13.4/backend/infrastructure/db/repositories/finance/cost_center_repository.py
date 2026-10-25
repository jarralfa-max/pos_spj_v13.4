"""CostCenter repository (§23)."""

from __future__ import annotations

from backend.domain.finance.entities.cost_center import CostCenter
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase


def _to_entity(row: dict) -> CostCenter:
    return CostCenter(id=row["id"], code=row["code"], name=row["name"],
                      parent_id=row["parent_id"], branch_id=row["branch_id"],
                      active=bool(row["active"]), created_at=row["created_at"])


class CostCenterRepository(FinanceRepositoryBase):
    def save(self, center: CostCenter) -> None:
        self._insert("cost_centers", {
            "id": center.id, "code": center.code, "name": center.name,
            "parent_id": center.parent_id, "branch_id": center.branch_id,
            "active": int(center.active), "created_at": center.created_at})

    def update(self, center: CostCenter) -> None:
        self._update("cost_centers", {"name": center.name, "active": int(center.active),
                                      "branch_id": center.branch_id},
                     where="id=?", params=(center.id,))

    def get(self, center_id: str) -> CostCenter | None:
        row = self._query_one("SELECT * FROM cost_centers WHERE id=?", (center_id,))
        return _to_entity(row) if row else None

    def get_by_code(self, code: str) -> CostCenter | None:
        row = self._query_one("SELECT * FROM cost_centers WHERE code=?", (code,))
        return _to_entity(row) if row else None

    def list_active(self) -> list[CostCenter]:
        return [_to_entity(r) for r in
                self._query("SELECT * FROM cost_centers WHERE active=1 ORDER BY code")]
