"""ASSET-12 — AssetDisposalRequest and AssetDisposal."""

import pytest

from backend.domain.assets.entities.asset_disposal import AssetDisposal
from backend.domain.assets.entities.asset_disposal_request import AssetDisposalRequest
from backend.domain.assets.enums import AssetDisposalReason, AssetDisposalRequestStatus
from backend.domain.assets.exceptions import (
    AssetDisposalNotAllowedError,
    AssetDomainError,
    SegregationOfDutiesError,
)


def _request(**extra) -> AssetDisposalRequest:
    return AssetDisposalRequest.create("asset-1", AssetDisposalReason.OBSOLESCENCE,
                                       "requester-1", "reemplazado por equipo nuevo",
                                       "op-1", **extra)


class TestAssetDisposalRequestCreate:
    def test_loss_requires_evidence_of_location_or_custodian(self):
        with pytest.raises(AssetDomainError):
            AssetDisposalRequest.create("asset-1", AssetDisposalReason.LOSS, "u1",
                                        "no se encuentra", "op-1")

    def test_loss_with_last_known_location_ok(self):
        req = AssetDisposalRequest.create("asset-1", AssetDisposalReason.LOSS, "u1",
                                          "no se encuentra", "op-1",
                                          last_known_location_id="loc-1")
        assert req.status is AssetDisposalRequestStatus.REQUESTED

    def test_theft_requires_evidence(self):
        with pytest.raises(AssetDomainError):
            AssetDisposalRequest.create("asset-1", AssetDisposalReason.THEFT, "u1",
                                        "robo reportado", "op-1")

    def test_scrap_does_not_require_evidence(self):
        req = _request()
        assert req.reason is AssetDisposalReason.OBSOLESCENCE


class TestAssetDisposalRequestWorkflow:
    def test_full_lifecycle(self):
        req = _request()
        req.begin_review()
        req.approve("approver-1", "aprobado por gerencia")
        req.start_execution()
        req.complete()
        assert req.status is AssetDisposalRequestStatus.COMPLETED

    def test_requester_cannot_self_approve(self):
        req = _request()  # requested_by="requester-1"
        req.begin_review()
        with pytest.raises(SegregationOfDutiesError):
            req.approve("requester-1")

    def test_reject_path(self):
        req = _request()
        req.begin_review()
        req.reject("approver-1", "no se justifica la baja")
        assert req.status is AssetDisposalRequestStatus.REJECTED

    def test_cannot_execute_before_approved(self):
        req = _request()
        req.begin_review()
        with pytest.raises(AssetDisposalNotAllowedError):
            req.start_execution()

    def test_cancel_terminal_fails(self):
        req = _request()
        req.begin_review()
        req.approve("approver-1")
        req.start_execution()
        req.complete()
        with pytest.raises(AssetDisposalNotAllowedError):
            req.cancel()


class TestAssetDisposal:
    def test_create_ok(self):
        disposal = AssetDisposal.create("req-1", "asset-1", AssetDisposalReason.SCRAP,
                                        "executor-1", "op-1", evidence_reference="foto-1")
        assert disposal.reason is AssetDisposalReason.SCRAP

    def test_requires_executed_by(self):
        with pytest.raises(AssetDomainError):
            AssetDisposal.create("req-1", "asset-1", AssetDisposalReason.SCRAP, "", "op-1")
