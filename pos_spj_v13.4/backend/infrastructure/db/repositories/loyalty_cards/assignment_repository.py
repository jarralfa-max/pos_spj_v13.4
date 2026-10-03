"""LoyaltyCardAssignmentRepository — asignaciones de tarjetas preimpresas (§45).
Sólo inserta: una asignación no se edita ni se borra."""

from __future__ import annotations

from backend.domain.loyalty_cards.entities.loyalty_card_assignment import LoyaltyCardAssignment
from backend.infrastructure.db.repositories.loyalty_cards.base import LoyaltyCardsRepositoryBase


class LoyaltyCardAssignmentRepository(LoyaltyCardsRepositoryBase):
    def add(self, assignment: LoyaltyCardAssignment) -> None:
        self._execute(
            "INSERT INTO loyalty_card_assignments (id, card_id, loyalty_account_id,"
            " membership_id, customer_id, assigned_by_user_id, assignment_reason, branch_id,"
            " operation_id, assigned_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (assignment.id, assignment.card_id, assignment.loyalty_account_id,
             assignment.membership_id, assignment.customer_id, assignment.assigned_by_user_id,
             assignment.assignment_reason, assignment.branch_id, assignment.operation_id,
             assignment.assigned_at))

    def get_for_card(self, card_id: str) -> LoyaltyCardAssignment | None:
        row = self._query_one(
            "SELECT * FROM loyalty_card_assignments WHERE card_id=?", (card_id,))
        return None if row is None else LoyaltyCardAssignment(**row)
