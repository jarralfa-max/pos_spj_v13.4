"""CRM-5 — Opportunities domain unit tests: entity lifecycle,
OpportunityCode, CRMStageDefinition, CRMStageTransitionPolicy,
OpportunityProductInterest. Pure domain — no DB.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.domain.crm.entities.opportunity import Opportunity
from backend.domain.crm.entities.opportunity_product_interest import OpportunityProductInterest
from backend.domain.crm.entities.opportunity_stage_history import OpportunityStageHistory
from backend.domain.crm.entities.stage_definition import CRMStageDefinition
from backend.domain.crm.enums import OpportunityStatus
from backend.domain.crm.exceptions import (
    CRMDomainError,
    InvalidOpportunityCodeError,
    InvalidOpportunityStateError,
    InvalidStageDefinitionError,
    OpportunityStageTransitionNotAllowedError,
)
from backend.domain.crm.policies.stage_transition_policy import CRMStageTransitionPolicy
from backend.domain.crm.value_objects.opportunity_code import OpportunityCode


def _stage(code="PROSPECTING", sequence_order=1, **kwargs) -> CRMStageDefinition:
    return CRMStageDefinition.create(code, code.title(), sequence_order, **kwargs)


def _opportunity(**kwargs) -> Opportunity:
    stage = kwargs.pop("stage", None) or _stage()
    return Opportunity.create(
        OpportunityCode.from_sequence(1), kwargs.pop("customer_id", "cust-1"),
        kwargs.pop("name", "Venta anual"), kwargs.pop("stage_id", stage.id), **kwargs)


class TestOpportunityLifecycle:
    def test_create_defaults_to_open(self):
        opp = _opportunity()
        assert opp.status is OpportunityStatus.OPEN
        assert opp.probability == 0

    def test_create_requires_customer_id(self):
        with pytest.raises(InvalidOpportunityStateError):
            Opportunity.create(OpportunityCode.from_sequence(1), "", "x", "stage-1")

    def test_create_requires_name(self):
        with pytest.raises(InvalidOpportunityStateError):
            Opportunity.create(OpportunityCode.from_sequence(1), "cust-1", "   ", "stage-1")

    def test_create_coerces_amount_to_decimal(self):
        opp = _opportunity(amount="1000.50")
        assert opp.amount == Decimal("1000.50")

    def test_create_rejects_float_amount(self):
        with pytest.raises(InvalidOpportunityStateError):
            _opportunity(amount=1000.5)

    def test_create_rejects_out_of_range_probability(self):
        with pytest.raises(InvalidOpportunityStateError):
            _opportunity(probability=150)

    def test_assign_owner_from_open(self):
        opp = _opportunity()
        opp.assign_owner("u1")
        assert opp.owner_user_id == "u1"

    def test_assign_owner_requires_user_id(self):
        with pytest.raises(InvalidOpportunityStateError):
            _opportunity().assign_owner("")

    def test_move_stage_updates_probability_and_date(self):
        opp = _opportunity()
        opp.move_stage("stage-2", probability=50, expected_close_date=date(2026, 12, 1))
        assert opp.stage_id == "stage-2"
        assert opp.probability == 50
        assert opp.expected_close_date == date(2026, 12, 1)

    def test_move_stage_rejects_out_of_range_probability(self):
        with pytest.raises(InvalidOpportunityStateError):
            _opportunity().move_stage("stage-2", probability=200)

    def test_move_stage_requires_stage_id(self):
        with pytest.raises(InvalidOpportunityStateError):
            _opportunity().move_stage("")

    def test_put_on_hold_and_resume(self):
        opp = _opportunity()
        opp.put_on_hold("esperando presupuesto del cliente")
        assert opp.status is OpportunityStatus.ON_HOLD
        opp.resume()
        assert opp.status is OpportunityStatus.OPEN

    def test_put_on_hold_requires_reason(self):
        with pytest.raises(InvalidOpportunityStateError):
            _opportunity().put_on_hold("")

    def test_resume_only_from_on_hold(self):
        with pytest.raises(InvalidOpportunityStateError):
            _opportunity().resume()

    def test_win_sets_probability_and_closed_at(self):
        opp = _opportunity()
        opp.win(won_stage_id="stage-won")
        assert opp.status is OpportunityStatus.WON
        assert opp.probability == 100
        assert opp.stage_id == "stage-won"
        assert opp.closed_at is not None
        assert opp.is_terminal()

    def test_win_allowed_from_on_hold(self):
        opp = _opportunity()
        opp.put_on_hold("pausa")
        opp.win()
        assert opp.status is OpportunityStatus.WON

    def test_lose_requires_reason_and_sets_zero_probability(self):
        opp = _opportunity()
        with pytest.raises(InvalidOpportunityStateError):
            opp.lose("")
        opp.lose("presupuesto cancelado", lost_stage_id="stage-lost")
        assert opp.status is OpportunityStatus.LOST
        assert opp.probability == 0
        assert opp.stage_id == "stage-lost"
        assert opp.close_reason == "presupuesto cancelado"

    def test_cancel_requires_reason(self):
        opp = _opportunity()
        with pytest.raises(InvalidOpportunityStateError):
            opp.cancel("")
        opp.cancel("cliente se retractó")
        assert opp.status is OpportunityStatus.CANCELLED
        assert opp.is_terminal()

    def test_reopen_from_lost_clears_close_state(self):
        opp = _opportunity()
        opp.lose("no contesta")
        opp.reopen("el cliente volvió a contactar")
        assert opp.status is OpportunityStatus.OPEN
        assert opp.close_reason == ""
        assert opp.closed_at is None

    def test_reopen_requires_reason(self):
        opp = _opportunity()
        opp.cancel("x")
        with pytest.raises(InvalidOpportunityStateError):
            opp.reopen("")

    def test_reopen_rejects_from_won(self):
        opp = _opportunity()
        opp.win()
        with pytest.raises(InvalidOpportunityStateError):
            opp.reopen("motivo")

    def test_terminal_opportunity_rejects_further_stage_moves(self):
        opp = _opportunity()
        opp.cancel("x")
        with pytest.raises(InvalidOpportunityStateError):
            opp.move_stage("stage-2")


class TestOpportunityCode:
    def test_from_sequence_formats_with_prefix_and_padding(self):
        assert str(OpportunityCode.from_sequence(42)) == "OPP-000042"

    def test_rejects_malformed_code(self):
        with pytest.raises(InvalidOpportunityCodeError):
            OpportunityCode("NOT-A-CODE")


class TestCRMStageDefinition:
    def test_create_normalizes_code(self):
        stage = CRMStageDefinition.create("proposal", "Propuesta", 3)
        assert stage.code == "PROPOSAL"

    def test_cannot_be_won_and_lost(self):
        with pytest.raises(InvalidStageDefinitionError):
            CRMStageDefinition.create("X", "X", 1, is_won_stage=True, is_lost_stage=True)

    def test_rejects_out_of_range_probability(self):
        with pytest.raises(InvalidStageDefinitionError):
            CRMStageDefinition.create("X", "X", 1, probability_default=150)

    def test_deactivate(self):
        stage = _stage()
        stage.deactivate()
        assert stage.active is False


class TestCRMStageTransitionPolicy:
    def setup_method(self):
        self.policy = CRMStageTransitionPolicy()
        self.stage1 = _stage("PROSPECTING", 1)
        self.stage2 = _stage("QUALIFICATION", 2, required_fields=("amount",))
        self.stage3_backward = _stage("PROSPECTING", 1)

    def test_forward_move_without_required_fields_fails(self):
        opp = _opportunity(stage_id=self.stage1.id)
        with pytest.raises(OpportunityStageTransitionNotAllowedError):
            self.policy.validate(opp, self.stage1, self.stage2)

    def test_forward_move_with_required_fields_present_passes(self):
        opp = _opportunity(stage_id=self.stage1.id, amount="500")
        self.policy.validate(opp, self.stage1, self.stage2)  # no raise

    def test_required_field_can_be_satisfied_by_proposed_value(self):
        stage_needs_date = _stage("PROPOSAL", 3, required_fields=("expected_close_date",))
        opp = _opportunity(stage_id=self.stage1.id)  # no expected_close_date set yet
        with pytest.raises(OpportunityStageTransitionNotAllowedError):
            self.policy.validate(opp, self.stage1, stage_needs_date)
        # Satisfied by the *proposed* value, not a pre-existing field on the entity.
        self.policy.validate(opp, self.stage1, stage_needs_date,
                             expected_close_date=date(2026, 12, 1))

    def test_backward_move_requires_reason(self):
        opp = _opportunity(stage_id=self.stage2.id, amount="500")
        with pytest.raises(OpportunityStageTransitionNotAllowedError):
            self.policy.validate(opp, self.stage2, self.stage1, reason="")
        self.policy.validate(opp, self.stage2, self.stage1, reason="cliente pidió reevaluar")

    def test_inactive_target_stage_rejected(self):
        inactive = _stage("PROPOSAL", 3)
        inactive.deactivate()
        opp = _opportunity(stage_id=self.stage1.id)
        with pytest.raises(OpportunityStageTransitionNotAllowedError):
            self.policy.validate(opp, self.stage1, inactive)

    def test_closed_opportunity_cannot_move_stage(self):
        opp = _opportunity(stage_id=self.stage1.id)
        opp.win()
        with pytest.raises(OpportunityStageTransitionNotAllowedError):
            self.policy.validate(opp, self.stage1, self.stage2)

    def test_insufficient_activity_rejected(self):
        needs_activity = _stage("NEGOTIATION", 4, min_activities=2)
        opp = _opportunity(stage_id=self.stage1.id)
        with pytest.raises(OpportunityStageTransitionNotAllowedError):
            self.policy.validate(opp, self.stage1, needs_activity, activities_logged_count=1)
        self.policy.validate(opp, self.stage1, needs_activity, activities_logged_count=2)

    def test_out_of_range_probability_rejected(self):
        opp = _opportunity(stage_id=self.stage1.id, amount="500")
        with pytest.raises(OpportunityStageTransitionNotAllowedError):
            self.policy.validate(opp, self.stage1, self.stage2, probability=250)

    def test_override_bypasses_required_fields_but_needs_reason(self):
        opp = _opportunity(stage_id=self.stage1.id)  # amount missing
        with pytest.raises(OpportunityStageTransitionNotAllowedError):
            self.policy.validate(opp, self.stage1, self.stage2, override=True, reason="")
        self.policy.validate(
            opp, self.stage1, self.stage2, override=True, reason="excepción autorizada")

    def test_override_still_rejects_inactive_stage(self):
        inactive = _stage("PROPOSAL", 3)
        inactive.deactivate()
        opp = _opportunity(stage_id=self.stage1.id)
        with pytest.raises(OpportunityStageTransitionNotAllowedError):
            self.policy.validate(opp, self.stage1, inactive, override=True, reason="motivo")

    def test_override_still_rejects_closed_opportunity(self):
        opp = _opportunity(stage_id=self.stage1.id)
        opp.cancel("x")
        with pytest.raises(OpportunityStageTransitionNotAllowedError):
            self.policy.validate(opp, self.stage1, self.stage2, override=True, reason="motivo")


class TestOpportunityStageHistory:
    def test_create_requires_opportunity_id(self):
        with pytest.raises(CRMDomainError):
            OpportunityStageHistory.create("", "stage-1", "u1")

    def test_create_allows_null_from_stage(self):
        history = OpportunityStageHistory.create("opp-1", "stage-1", "u1")
        assert history.from_stage_id is None


class TestOpportunityProductInterest:
    def test_create_requires_positive_quantity(self):
        with pytest.raises(CRMDomainError):
            OpportunityProductInterest.create("opp-1", "Producto X", quantity="0")

    def test_create_rejects_float_quantity(self):
        with pytest.raises(CRMDomainError):
            OpportunityProductInterest.create("opp-1", "Producto X", quantity=2.5)

    def test_create_coerces_price_to_decimal(self):
        interest = OpportunityProductInterest.create(
            "opp-1", "Producto X", quantity="3", estimated_unit_price="19.99")
        assert interest.estimated_unit_price == Decimal("19.99")
