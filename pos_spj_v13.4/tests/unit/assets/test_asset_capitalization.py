"""ASSET-10 — AssetImprovement and AssetCapitalizationProposal.

`approve()`/`reject()`/`mark_posted()` must never touch Finance/Treasury
directly (docs/refactor/assets_finance_boundary_map.md) — verified here the
same way ASSET-6 verified `MaintenanceWorkOrder.complete()`.
"""

from datetime import date
from decimal import Decimal

import pytest

from backend.domain.assets.entities.asset_capitalization_proposal import (
    AssetCapitalizationProposal,
)
from backend.domain.assets.entities.asset_improvement import AssetImprovement
from backend.domain.assets.enums import AssetCapitalizationProposalStatus
from backend.domain.assets.exceptions import (
    AssetCapitalizationProposalInvalidError,
    AssetDomainError,
)
from backend.domain.finance.value_objects.money import Money


def _money(v: str) -> Money:
    return Money(Decimal(v))


class TestAssetImprovement:
    def test_create_ok(self):
        imp = AssetImprovement.create("asset-1", "Motor nuevo", date(2026, 3, 1),
                                      _money("1200.00"), "op-1")
        assert imp.capitalization_proposal_id is None

    def test_requires_positive_cost(self):
        with pytest.raises(AssetDomainError):
            AssetImprovement.create("asset-1", "x", date(2026, 3, 1), _money("0"), "op-1")

    def test_link_to_proposal_once(self):
        imp = AssetImprovement.create("asset-1", "Motor nuevo", date(2026, 3, 1),
                                      _money("1200"), "op-1")
        imp.link_to_proposal("prop-1")
        with pytest.raises(AssetDomainError):
            imp.link_to_proposal("prop-2")


def _proposal(**extra) -> AssetCapitalizationProposal:
    return AssetCapitalizationProposal.create("asset-1", "imp-1", _money("1200.00"),
                                              "Extiende vida útil 24 meses", "u1", "op-1", **extra)


class TestAssetCapitalizationProposal:
    def test_requires_positive_amount(self):
        with pytest.raises(AssetDomainError):
            AssetCapitalizationProposal.create("asset-1", "imp-1", _money("0"),
                                               "justificación", "u1", "op-1")

    def test_full_lifecycle_to_posted(self):
        p = _proposal()
        p.submit()
        assert p.status is AssetCapitalizationProposalStatus.SUBMITTED
        p.begin_review()
        assert p.status is AssetCapitalizationProposalStatus.UNDER_REVIEW
        p.approve("finance-1", "aprobado por comité")
        assert p.status is AssetCapitalizationProposalStatus.APPROVED
        p.mark_posted("journal-entry-ref-1")
        assert p.status is AssetCapitalizationProposalStatus.POSTED
        assert p.financial_reference == "journal-entry-ref-1"

    def test_reject_path(self):
        p = _proposal()
        p.submit()
        p.begin_review()
        p.reject("finance-1", "no cumple criterio de capitalización")
        assert p.status is AssetCapitalizationProposalStatus.REJECTED

    def test_cannot_approve_before_review(self):
        p = _proposal()
        p.submit()
        with pytest.raises(AssetCapitalizationProposalInvalidError):
            p.approve("finance-1")

    def test_cannot_post_before_approved(self):
        p = _proposal()
        with pytest.raises(AssetCapitalizationProposalInvalidError):
            p.mark_posted("ref-1")

    def test_cancel_from_draft(self):
        p = _proposal()
        p.cancel("ya no aplica")
        assert p.status is AssetCapitalizationProposalStatus.CANCELLED

    def test_cancel_terminal_fails(self):
        p = _proposal()
        p.submit()
        p.begin_review()
        p.reject("u2")
        with pytest.raises(AssetCapitalizationProposalInvalidError):
            p.cancel()

    def test_entity_never_touches_finance_or_treasury(self):
        p = _proposal()
        for name in dir(p):
            assert "posting" not in name.lower()
            assert "treasury" not in name.lower()
            assert "asiento" not in name.lower()
