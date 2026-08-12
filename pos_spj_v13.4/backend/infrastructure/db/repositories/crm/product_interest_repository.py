"""OpportunityProductInterestRepository — persists product interest lines."""

from __future__ import annotations

from decimal import Decimal

from backend.domain.crm.entities.opportunity_product_interest import OpportunityProductInterest
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_INTEREST_COLS = (
    "id, opportunity_id, product_reference_id, product_name, quantity,"
    " estimated_unit_price, notes, created_at"
)


class OpportunityProductInterestRepository(CRMRepositoryBase):
    def save(self, interest: OpportunityProductInterest) -> None:
        self._execute(
            f"INSERT INTO opportunity_product_interests ({_INTEREST_COLS})"
            " VALUES (?,?,?,?,?,?,?,?)",
            (interest.id, interest.opportunity_id, interest.product_reference_id,
             interest.product_name, str(interest.quantity),
             str(interest.estimated_unit_price) if interest.estimated_unit_price is not None
             else None, interest.notes, interest.created_at))

    def list_for_opportunity(self, opportunity_id: str) -> list[OpportunityProductInterest]:
        rows = self._query(
            f"SELECT {_INTEREST_COLS} FROM opportunity_product_interests"
            " WHERE opportunity_id=? ORDER BY created_at ASC", (opportunity_id,))
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _hydrate(row: dict) -> OpportunityProductInterest:
        return OpportunityProductInterest(
            id=row["id"], opportunity_id=row["opportunity_id"],
            product_name=row["product_name"], quantity=Decimal(row["quantity"]),
            product_reference_id=row["product_reference_id"],
            estimated_unit_price=(Decimal(row["estimated_unit_price"])
                                  if row["estimated_unit_price"] else None),
            notes=row["notes"] or "", created_at=row["created_at"],
        )
