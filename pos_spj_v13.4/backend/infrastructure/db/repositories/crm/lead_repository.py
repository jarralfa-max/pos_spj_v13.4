"""LeadRepository — persists the Lead aggregate. Mirrors
backend/infrastructure/db/repositories/customers/customer_repository.py.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.crm.entities.lead import Lead
from backend.domain.crm.enums import LeadPriority, LeadSource, LeadStatus
from backend.domain.crm.value_objects.lead_code import LeadCode
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_LEAD_COLS = (
    "id, lead_number, display_name, company_name, contact_name, phone_e164,"
    " email, source, campaign_reference_id, origin_branch_id, assigned_user_id,"
    " territory_id, status, score, priority, estimated_value,"
    " expected_purchase_date, last_contact_at, next_action_at,"
    " created_by_user_id, operation_id, created_at, updated_at"
)


class LeadRepository(CRMRepositoryBase):
    def next_code(self) -> LeadCode:
        last = self._scalar(
            "SELECT lead_number FROM leads"
            " ORDER BY CAST(SUBSTR(lead_number, 6) AS INTEGER) DESC LIMIT 1")
        seq = (int(last.split("-")[1]) + 1) if last else 1
        return LeadCode.from_sequence(seq)

    def save(self, lead: Lead, *, operation_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO leads ({_LEAD_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(lead, operation_id or lead.operation_id))

    def update(self, lead: Lead) -> None:
        self._execute(
            "UPDATE leads SET display_name=?, company_name=?, contact_name=?,"
            " phone_e164=?, email=?, source=?, campaign_reference_id=?,"
            " origin_branch_id=?, assigned_user_id=?, territory_id=?, status=?,"
            " score=?, priority=?, estimated_value=?, expected_purchase_date=?,"
            " last_contact_at=?, next_action_at=?, updated_at=? WHERE id=?",
            (lead.display_name, lead.company_name, lead.contact_name, lead.phone_e164,
             lead.email, lead.source.value, lead.campaign_reference_id,
             lead.origin_branch_id, lead.assigned_user_id, lead.territory_id,
             lead.status.value, lead.score, lead.priority.value,
             str(lead.estimated_value) if lead.estimated_value is not None else None,
             lead.expected_purchase_date.isoformat() if lead.expected_purchase_date else None,
             lead.last_contact_at, lead.next_action_at, lead.updated_at, lead.id))

    def get(self, lead_id: str) -> Lead | None:
        row = self._query_one(f"SELECT {_LEAD_COLS} FROM leads WHERE id=?", (lead_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> Lead | None:
        row = self._query_one(f"SELECT {_LEAD_COLS} FROM leads WHERE lead_number=?", (code,))
        return self._hydrate(row) if row else None

    def get_by_operation_id(self, operation_id: str) -> Lead | None:
        row = self._query_one(
            f"SELECT {_LEAD_COLS} FROM leads WHERE operation_id=?", (operation_id,))
        return self._hydrate(row) if row else None

    def find_duplicate_rows(self) -> list[dict]:
        """Lightweight rows for a duplicate policy (reuses
        CustomerDuplicatePolicy's shape: display_name/phone_e164/email)."""
        return self._query(
            "SELECT id, display_name, phone_e164, email FROM leads"
            " WHERE status NOT IN ('CONVERTED','ARCHIVED')")

    def list_owned_by(self, owner_user_ids: tuple[str, ...], *,
                       limit: int = 200, offset: int = 0) -> list[Lead]:
        if not owner_user_ids:
            return []
        placeholders = ",".join("?" for _ in owner_user_ids)
        rows = self._query(
            f"SELECT {_LEAD_COLS} FROM leads WHERE assigned_user_id IN ({placeholders})"
            " ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*owner_user_ids, limit, offset))
        return [self._hydrate(r) for r in rows]

    def list_open(self, *, limit: int = 200, offset: int = 0) -> list[Lead]:
        rows = self._query(
            f"SELECT {_LEAD_COLS} FROM leads"
            " WHERE status NOT IN ('CONVERTED','ARCHIVED','LOST')"
            " ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))
        return [self._hydrate(r) for r in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(lead: Lead, operation_id: str | None) -> tuple:
        return (
            lead.id, str(lead.code), lead.display_name, lead.company_name,
            lead.contact_name, lead.phone_e164, lead.email, lead.source.value,
            lead.campaign_reference_id, lead.origin_branch_id, lead.assigned_user_id,
            lead.territory_id, lead.status.value, lead.score, lead.priority.value,
            str(lead.estimated_value) if lead.estimated_value is not None else None,
            lead.expected_purchase_date.isoformat() if lead.expected_purchase_date else None,
            lead.last_contact_at, lead.next_action_at, lead.created_by_user_id,
            operation_id, lead.created_at, lead.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> Lead:
        return Lead(
            id=row["id"], code=LeadCode(row["lead_number"]), display_name=row["display_name"],
            company_name=row["company_name"] or "", contact_name=row["contact_name"] or "",
            phone_e164=row["phone_e164"], email=row["email"],
            source=LeadSource(row["source"]), campaign_reference_id=row["campaign_reference_id"],
            origin_branch_id=row["origin_branch_id"], assigned_user_id=row["assigned_user_id"],
            territory_id=row["territory_id"], status=LeadStatus(row["status"]),
            score=row["score"], priority=LeadPriority(row["priority"]),
            estimated_value=Decimal(row["estimated_value"]) if row["estimated_value"] else None,
            expected_purchase_date=(date.fromisoformat(row["expected_purchase_date"])
                                    if row["expected_purchase_date"] else None),
            last_contact_at=row["last_contact_at"], next_action_at=row["next_action_at"],
            created_by_user_id=row["created_by_user_id"], operation_id=row["operation_id"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
