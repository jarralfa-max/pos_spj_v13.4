"""LOY-2 — LoyaltyProgram lifecycle (master prompt §9)."""

from __future__ import annotations

import pytest

from backend.domain.loyalty.entities.loyalty_program import LoyaltyProgram
from backend.domain.loyalty.enums import ProgramStatus
from backend.domain.loyalty.exceptions import InvalidLoyaltyProgramStateError


def _program() -> LoyaltyProgram:
    return LoyaltyProgram.create("PTS", "Puntos SPJ", "Estrellas",
                                  created_by_user_id="user-1")


class TestLoyaltyProgramCreation:
    def test_create_defaults_to_draft(self):
        program = _program()
        assert program.status is ProgramStatus.DRAFT
        assert program.id

    def test_requires_code(self):
        with pytest.raises(InvalidLoyaltyProgramStateError):
            LoyaltyProgram.create("", "Puntos SPJ", "Estrellas")

    def test_requires_currency_name(self):
        with pytest.raises(InvalidLoyaltyProgramStateError):
            LoyaltyProgram.create("PTS", "Puntos SPJ", "")


class TestLoyaltyProgramLifecycle:
    def test_full_approval_and_activation_flow(self):
        program = _program()
        program.submit_for_approval()
        assert program.status is ProgramStatus.PENDING_APPROVAL
        program.approve("supervisor-1")
        assert program.approved_by_user_id == "supervisor-1"
        assert program.status is ProgramStatus.PENDING_APPROVAL
        program.activate()
        assert program.status is ProgramStatus.ACTIVE
        assert program.is_active() is True

    def test_cannot_activate_without_approval(self):
        program = _program()
        program.submit_for_approval()
        with pytest.raises(InvalidLoyaltyProgramStateError):
            program.activate()

    def test_cannot_submit_twice(self):
        program = _program()
        program.submit_for_approval()
        with pytest.raises(InvalidLoyaltyProgramStateError):
            program.submit_for_approval()

    def test_suspend_and_reactivate(self):
        program = _program()
        program.submit_for_approval()
        program.approve("supervisor-1")
        program.activate()
        program.suspend("Revisión de reglas")
        assert program.status is ProgramStatus.SUSPENDED
        program.activate()
        assert program.status is ProgramStatus.ACTIVE

    def test_suspend_requires_reason(self):
        program = _program()
        program.submit_for_approval()
        program.approve("supervisor-1")
        program.activate()
        with pytest.raises(InvalidLoyaltyProgramStateError):
            program.suspend("")

    def test_close_then_archive(self):
        program = _program()
        program.submit_for_approval()
        program.approve("supervisor-1")
        program.activate()
        program.close("Fin de campaña")
        assert program.status is ProgramStatus.CLOSED
        program.archive()
        assert program.status is ProgramStatus.ARCHIVED

    def test_cannot_close_from_draft(self):
        program = _program()
        with pytest.raises(InvalidLoyaltyProgramStateError):
            program.close("motivo")
