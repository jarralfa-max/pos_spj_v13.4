"""CRM-4 — Leads domain unit tests: entity lifecycle, LeadCode,
LeadQualification, LeadQualificationPolicy, LeadDuplicatePolicy. Pure
domain — no DB.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.crm.entities.lead import Lead
from backend.domain.crm.entities.lead_qualification import LeadQualification
from backend.domain.crm.enums import (
    LeadSource,
    LeadStatus,
    QualificationDecision,
    QualificationModel,
)
from backend.domain.crm.exceptions import (
    InvalidLeadCodeError,
    InvalidLeadStateError,
    LeadQualificationFailedError,
)
from backend.domain.crm.policies.duplicate_policy import LeadDuplicatePolicy
from backend.domain.crm.policies.qualification_policy import LeadQualificationPolicy
from backend.domain.crm.value_objects.lead_code import LeadCode


def _lead(**kwargs) -> Lead:
    return Lead.create(LeadCode.from_sequence(1), kwargs.pop("display_name", "Restaurante El Sol"),
                       **kwargs)


class TestLeadLifecycle:
    def test_create_defaults_to_new(self):
        lead = _lead()
        assert lead.status is LeadStatus.NEW

    def test_create_requires_display_name(self):
        with pytest.raises(InvalidLeadStateError):
            Lead.create(LeadCode.from_sequence(1), "   ")

    def test_create_coerces_estimated_value_to_decimal(self):
        lead = _lead(estimated_value="15000.50")
        assert lead.estimated_value == Decimal("15000.50")

    def test_create_rejects_float_estimated_value(self):
        with pytest.raises(InvalidLeadStateError):
            _lead(estimated_value=15000.5)

    def test_assign_from_new_moves_to_assigned(self):
        lead = _lead()
        lead.assign("u-vendedor")
        assert lead.status is LeadStatus.ASSIGNED
        assert lead.assigned_user_id == "u-vendedor"

    def test_reassign_keeps_status_when_not_new(self):
        lead = _lead()
        lead.assign("u1")
        lead.mark_contacted()
        lead.assign("u2")  # reassignment, not a NEW->ASSIGNED transition
        assert lead.status is LeadStatus.CONTACTED
        assert lead.assigned_user_id == "u2"

    def test_assign_requires_user_id(self):
        with pytest.raises(InvalidLeadStateError):
            _lead().assign("")

    def test_full_happy_path_to_conversion(self):
        lead = _lead()
        lead.assign("u1")
        lead.mark_contacted()
        lead.start_nurturing()
        lead.qualify()
        assert lead.status is LeadStatus.QUALIFIED
        lead.convert()
        assert lead.status is LeadStatus.CONVERTED
        assert lead.is_terminal()

    def test_convert_requires_qualified_status(self):
        lead = _lead()
        with pytest.raises(InvalidLeadStateError):
            lead.convert()

    def test_disqualify_requires_reason(self):
        lead = _lead()
        with pytest.raises(InvalidLeadStateError):
            lead.disqualify("")
        lead.disqualify("sin presupuesto")
        assert lead.status is LeadStatus.UNQUALIFIED

    def test_lose_requires_reason(self):
        lead = _lead()
        with pytest.raises(InvalidLeadStateError):
            lead.lose("")
        lead.lose("no contesta")
        assert lead.status is LeadStatus.LOST

    def test_archive_only_from_unqualified_or_lost(self):
        lead = _lead()
        with pytest.raises(InvalidLeadStateError):
            lead.archive()
        lead.disqualify("sin interés")
        lead.archive()
        assert lead.status is LeadStatus.ARCHIVED
        assert lead.is_terminal()

    def test_terminal_lead_rejects_any_further_transition(self):
        lead = _lead()
        lead.disqualify("x")
        lead.archive()
        with pytest.raises(InvalidLeadStateError):
            lead.assign("u1")


class TestLeadCode:
    def test_from_sequence_formats_with_prefix_and_padding(self):
        assert str(LeadCode.from_sequence(42)) == "LEAD-000042"

    def test_rejects_malformed_code(self):
        with pytest.raises(InvalidLeadCodeError):
            LeadCode("NOT-A-CODE")


class TestLeadQualification:
    def test_manual_requires_no_extra_evidence(self):
        q = LeadQualification.create(
            "lead-1", QualificationModel.MANUAL, QualificationDecision.QUALIFIED, "u1")
        assert q.decision is QualificationDecision.QUALIFIED

    def test_score_based_requires_score(self):
        with pytest.raises(LeadQualificationFailedError):
            LeadQualification.create(
                "lead-1", QualificationModel.SCORE_BASED, QualificationDecision.QUALIFIED, "u1")
        q = LeadQualification.create(
            "lead-1", QualificationModel.SCORE_BASED, QualificationDecision.QUALIFIED, "u1",
            score=80)
        assert q.score == 80

    def test_bant_like_requires_criteria(self):
        with pytest.raises(LeadQualificationFailedError):
            LeadQualification.create(
                "lead-1", QualificationModel.BANT_LIKE, QualificationDecision.QUALIFIED, "u1")

    def test_requires_qualified_by_user_id(self):
        with pytest.raises(LeadQualificationFailedError):
            LeadQualification.create(
                "lead-1", QualificationModel.MANUAL, QualificationDecision.QUALIFIED, "")


class TestLeadQualificationPolicy:
    def setup_method(self):
        self.policy = LeadQualificationPolicy()

    def test_manual_returns_supplied_decision(self):
        decision = self.policy.decide(
            QualificationModel.MANUAL, manual_decision=QualificationDecision.UNQUALIFIED)
        assert decision is QualificationDecision.UNQUALIFIED

    def test_manual_without_decision_fails(self):
        with pytest.raises(LeadQualificationFailedError):
            self.policy.decide(QualificationModel.MANUAL)

    def test_score_based_above_threshold_qualifies(self):
        decision = self.policy.decide(
            QualificationModel.SCORE_BASED, score=80, score_threshold=70)
        assert decision is QualificationDecision.QUALIFIED

    def test_score_based_below_threshold_disqualifies(self):
        decision = self.policy.decide(
            QualificationModel.SCORE_BASED, score=50, score_threshold=70)
        assert decision is QualificationDecision.UNQUALIFIED

    def test_bant_like_counts_passing_criteria(self):
        criteria = {"budget": True, "authority": True, "need": False, "timeline": True}
        decision = self.policy.decide(
            QualificationModel.BANT_LIKE, criteria=criteria, min_criteria_passed=3)
        assert decision is QualificationDecision.QUALIFIED

    def test_bant_like_defaults_threshold_to_all_criteria(self):
        criteria = {"budget": True, "authority": False}
        decision = self.policy.decide(QualificationModel.BANT_LIKE, criteria=criteria)
        assert decision is QualificationDecision.UNQUALIFIED

    def test_custom_rule_requires_criteria_and_decision(self):
        with pytest.raises(LeadQualificationFailedError):
            self.policy.decide(QualificationModel.CUSTOM_RULE)
        decision = self.policy.decide(
            QualificationModel.CUSTOM_RULE, criteria={"vip": True},
            custom_decision=QualificationDecision.QUALIFIED)
        assert decision is QualificationDecision.QUALIFIED


class TestLeadDuplicatePolicy:
    def setup_method(self):
        self.policy = LeadDuplicatePolicy()

    def test_matches_on_phone(self):
        existing = [{"id": "l1", "display_name": "Otro", "phone_e164": "+525512345678"}]
        matches = self.policy.find_matches(
            {"display_name": "Distinto", "phone_e164": "+525512345678"}, existing)
        assert len(matches) == 1 and "Mismo teléfono" in matches[0].reasons

    def test_no_false_positive(self):
        existing = [{"id": "l1", "display_name": "Completamente Distinto"}]
        assert self.policy.find_matches({"display_name": "Restaurante El Sol"}, existing) == []
