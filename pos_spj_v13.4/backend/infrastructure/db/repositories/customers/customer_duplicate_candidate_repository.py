"""CustomerDuplicateCandidateRepository — persists detected duplicate pairs.
Mirrors backend/infrastructure/db/repositories/crm/stage_definition_repository.py
for the CRUD shape, adjusted for this entity's own lifecycle fields.
"""

from __future__ import annotations

import json

from backend.domain.customers.entities.customer_duplicate_candidate import (
    CustomerDuplicateCandidate,
)
from backend.domain.customers.enums import DuplicateCandidateStatus
from backend.infrastructure.db.repositories.customers.base import CustomerRepositoryBase

_COLS = (
    "id, customer_id_a, customer_id_b, match_reasons_json, status,"
    " reviewed_by_user_id, reviewed_at, resolution_reason, operation_id,"
    " created_at, updated_at"
)


class CustomerDuplicateCandidateRepository(CustomerRepositoryBase):
    def save(self, candidate: CustomerDuplicateCandidate, *,
             operation_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO customer_duplicate_candidates ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            self._params(candidate, operation_id or candidate.operation_id))

    def update(self, candidate: CustomerDuplicateCandidate) -> None:
        self._execute(
            "UPDATE customer_duplicate_candidates SET status=?, reviewed_by_user_id=?,"
            " reviewed_at=?, resolution_reason=?, updated_at=? WHERE id=?",
            (candidate.status.value, candidate.reviewed_by_user_id, candidate.reviewed_at,
             candidate.resolution_reason, candidate.updated_at, candidate.id))

    def get(self, candidate_id: str) -> CustomerDuplicateCandidate | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM customer_duplicate_candidates WHERE id=?", (candidate_id,))
        return self._hydrate(row) if row else None

    def get_active_pair(self, customer_id_a: str,
                        customer_id_b: str) -> CustomerDuplicateCandidate | None:
        """A non-terminal (not DISMISSED/MERGED) candidate already covering
        this unordered pair, if any — used to avoid re-detecting the same
        pair every scan."""
        row = self._query_one(
            f"SELECT {_COLS} FROM customer_duplicate_candidates"
            " WHERE ((customer_id_a=? AND customer_id_b=?) OR"
            " (customer_id_a=? AND customer_id_b=?))"
            " AND status NOT IN ('DISMISSED','MERGED') LIMIT 1",
            (customer_id_a, customer_id_b, customer_id_b, customer_id_a))
        return self._hydrate(row) if row else None

    def list_by_status(self, status: str) -> list[CustomerDuplicateCandidate]:
        rows = self._query(
            f"SELECT {_COLS} FROM customer_duplicate_candidates"
            " WHERE status=? ORDER BY created_at DESC", (status,))
        return [self._hydrate(r) for r in rows]

    def list_for_customer(self, customer_id: str) -> list[CustomerDuplicateCandidate]:
        rows = self._query(
            f"SELECT {_COLS} FROM customer_duplicate_candidates"
            " WHERE customer_id_a=? OR customer_id_b=? ORDER BY created_at DESC",
            (customer_id, customer_id))
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _params(candidate: CustomerDuplicateCandidate, operation_id: str | None) -> tuple:
        return (
            candidate.id, candidate.customer_id_a, candidate.customer_id_b,
            json.dumps(list(candidate.match_reasons)), candidate.status.value,
            candidate.reviewed_by_user_id, candidate.reviewed_at, candidate.resolution_reason,
            operation_id, candidate.created_at, candidate.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CustomerDuplicateCandidate:
        return CustomerDuplicateCandidate(
            id=row["id"], customer_id_a=row["customer_id_a"], customer_id_b=row["customer_id_b"],
            match_reasons=tuple(json.loads(row["match_reasons_json"] or "[]")),
            status=DuplicateCandidateStatus(row["status"]),
            reviewed_by_user_id=row["reviewed_by_user_id"], reviewed_at=row["reviewed_at"],
            resolution_reason=row["resolution_reason"] or "", operation_id=row["operation_id"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
