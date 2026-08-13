"""OpportunityRepository — persists the Opportunity aggregate. Mirrors
backend/infrastructure/db/repositories/crm/lead_repository.py.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.crm.entities.opportunity import Opportunity
from backend.domain.crm.enums import OpportunityStatus
from backend.domain.crm.value_objects.opportunity_code import OpportunityCode
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_OPP_COLS = (
    "id, opportunity_number, customer_id, account_id, name, source_lead_id,"
    " owner_user_id, stage_id, status, amount, probability,"
    " expected_close_date, territory_id, origin_branch_id, description,"
    " close_reason, closed_at, created_by_user_id, operation_id, created_at,"
    " updated_at"
)


class OpportunityRepository(CRMRepositoryBase):
    def next_code(self) -> OpportunityCode:
        last = self._scalar(
            "SELECT opportunity_number FROM opportunities"
            " ORDER BY CAST(SUBSTR(opportunity_number, 5) AS INTEGER) DESC LIMIT 1")
        seq = (int(last.split("-")[1]) + 1) if last else 1
        return OpportunityCode.from_sequence(seq)

    def save(self, opportunity: Opportunity, *, operation_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO opportunities ({_OPP_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(opportunity, operation_id or opportunity.operation_id))

    def update(self, opportunity: Opportunity) -> None:
        self._execute(
            "UPDATE opportunities SET account_id=?, name=?, owner_user_id=?, stage_id=?,"
            " status=?, amount=?, probability=?, expected_close_date=?, territory_id=?,"
            " origin_branch_id=?, description=?, close_reason=?, closed_at=?, updated_at=?"
            " WHERE id=?",
            (opportunity.account_id, opportunity.name, opportunity.owner_user_id,
             opportunity.stage_id, opportunity.status.value,
             str(opportunity.amount) if opportunity.amount is not None else None,
             opportunity.probability,
             opportunity.expected_close_date.isoformat()
             if opportunity.expected_close_date else None,
             opportunity.territory_id, opportunity.origin_branch_id, opportunity.description,
             opportunity.close_reason, opportunity.closed_at, opportunity.updated_at,
             opportunity.id))

    def get(self, opportunity_id: str) -> Opportunity | None:
        row = self._query_one(f"SELECT {_OPP_COLS} FROM opportunities WHERE id=?",
                              (opportunity_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> Opportunity | None:
        row = self._query_one(
            f"SELECT {_OPP_COLS} FROM opportunities WHERE opportunity_number=?", (code,))
        return self._hydrate(row) if row else None

    def get_by_operation_id(self, operation_id: str) -> Opportunity | None:
        row = self._query_one(
            f"SELECT {_OPP_COLS} FROM opportunities WHERE operation_id=?", (operation_id,))
        return self._hydrate(row) if row else None

    def list_owned_by(self, owner_user_ids: tuple[str, ...], *,
                       limit: int = 200, offset: int = 0) -> list[Opportunity]:
        if not owner_user_ids:
            return []
        placeholders = ",".join("?" for _ in owner_user_ids)
        rows = self._query(
            f"SELECT {_OPP_COLS} FROM opportunities WHERE owner_user_id IN ({placeholders})"
            " ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*owner_user_ids, limit, offset))
        return [self._hydrate(r) for r in rows]

    def list_open_owned_by(self, owner_user_ids: tuple[str, ...], *,
                            limit: int = 500, offset: int = 0) -> list[Opportunity]:
        if not owner_user_ids:
            return []
        placeholders = ",".join("?" for _ in owner_user_ids)
        rows = self._query(
            f"SELECT {_OPP_COLS} FROM opportunities WHERE owner_user_id IN ({placeholders})"
            " AND status='OPEN' ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*owner_user_ids, limit, offset))
        return [self._hydrate(r) for r in rows]

    def list_by_stage(self, stage_id: str, *, limit: int = 200, offset: int = 0) -> list[Opportunity]:
        rows = self._query(
            f"SELECT {_OPP_COLS} FROM opportunities WHERE stage_id=?"
            " ORDER BY created_at DESC LIMIT ? OFFSET ?", (stage_id, limit, offset))
        return [self._hydrate(r) for r in rows]

    def list_for_customer(self, customer_id: str, *,
                           limit: int = 200, offset: int = 0) -> list[Opportunity]:
        """CRM-12: Customer 360's "pipeline" tab — every opportunity tied to
        this customer, regardless of owner (unlike list_owned_by, which
        filters by scope)."""
        rows = self._query(
            f"SELECT {_OPP_COLS} FROM opportunities WHERE customer_id=?"
            " ORDER BY created_at DESC LIMIT ? OFFSET ?", (customer_id, limit, offset))
        return [self._hydrate(r) for r in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(opportunity: Opportunity, operation_id: str | None) -> tuple:
        return (
            opportunity.id, str(opportunity.code), opportunity.customer_id,
            opportunity.account_id, opportunity.name, opportunity.source_lead_id,
            opportunity.owner_user_id, opportunity.stage_id, opportunity.status.value,
            str(opportunity.amount) if opportunity.amount is not None else None,
            opportunity.probability,
            opportunity.expected_close_date.isoformat()
            if opportunity.expected_close_date else None,
            opportunity.territory_id, opportunity.origin_branch_id, opportunity.description,
            opportunity.close_reason, opportunity.closed_at, opportunity.created_by_user_id,
            operation_id, opportunity.created_at, opportunity.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> Opportunity:
        return Opportunity(
            id=row["id"], code=OpportunityCode(row["opportunity_number"]),
            customer_id=row["customer_id"], name=row["name"], stage_id=row["stage_id"],
            account_id=row["account_id"], source_lead_id=row["source_lead_id"],
            owner_user_id=row["owner_user_id"], status=OpportunityStatus(row["status"]),
            amount=Decimal(row["amount"]) if row["amount"] else None,
            probability=row["probability"],
            expected_close_date=(date.fromisoformat(row["expected_close_date"])
                                 if row["expected_close_date"] else None),
            territory_id=row["territory_id"], origin_branch_id=row["origin_branch_id"],
            description=row["description"] or "", close_reason=row["close_reason"] or "",
            closed_at=row["closed_at"], created_by_user_id=row["created_by_user_id"],
            operation_id=row["operation_id"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
