"""ProfitCenter repository (§23)."""

from __future__ import annotations

from backend.domain.finance.entities.profit_center import ProfitCenter
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase


def _to_entity(row: dict) -> ProfitCenter:
    return ProfitCenter(id=row["id"], code=row["code"], name=row["name"],
                        branch_id=row["branch_id"], active=bool(row["active"]),
                        created_at=row["created_at"], org_unit_id=row.get("org_unit_id"))


class ProfitCenterRepository(FinanceRepositoryBase):
    def save(self, center: ProfitCenter) -> None:
        self._insert("profit_centers", {
            "id": center.id, "code": center.code, "name": center.name,
            "branch_id": center.branch_id, "active": int(center.active),
            "created_at": center.created_at, "org_unit_id": center.org_unit_id})

    def update(self, center: ProfitCenter) -> None:
        self._update("profit_centers", {"name": center.name, "active": int(center.active),
                                        "branch_id": center.branch_id},
                     where="id=?", params=(center.id,))

    def get(self, center_id: str) -> ProfitCenter | None:
        row = self._query_one("SELECT * FROM profit_centers WHERE id=?", (center_id,))
        return _to_entity(row) if row else None

    def get_by_code(self, code: str) -> ProfitCenter | None:
        row = self._query_one("SELECT * FROM profit_centers WHERE code=?", (code,))
        return _to_entity(row) if row else None

    def list_active(self) -> list[ProfitCenter]:
        return [_to_entity(r) for r in
                self._query("SELECT * FROM profit_centers WHERE active=1 ORDER BY code")]
