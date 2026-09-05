"""ASSET-5 — AssetTransfer guarded state machine + segregation of duties."""

import pytest

from backend.domain.assets.entities.asset_transfer import AssetTransfer
from backend.domain.assets.enums import AssetTransferStatus
from backend.domain.assets.exceptions import (
    AssetDomainError,
    AssetTransferNotAllowedError,
    SegregationOfDutiesError,
)


def _transfer(**extra) -> AssetTransfer:
    return AssetTransfer.create("asset-1", "br-1", "br-2", "requester-1", "op-1", **extra)


class TestAssetTransferCreate:
    def test_requires_different_branches(self):
        with pytest.raises(AssetDomainError):
            AssetTransfer.create("asset-1", "br-1", "br-1", "u1", "op-1")

    def test_starts_requested(self):
        t = _transfer()
        assert t.status is AssetTransferStatus.REQUESTED


class TestAssetTransferHappyPath:
    def test_full_lifecycle(self):
        t = _transfer()
        t.approve("approver-1")
        assert t.status is AssetTransferStatus.APPROVED
        t.prepare()
        assert t.status is AssetTransferStatus.PREPARED
        t.ship("shipper-1", condition_out="GOOD")
        assert t.status is AssetTransferStatus.IN_TRANSIT
        t.receive("receiver-1", condition_in="GOOD")
        assert t.status is AssetTransferStatus.RECEIVED
        assert t.received_by == "receiver-1"


class TestAssetTransferGuards:
    def test_cannot_ship_before_prepared(self):
        t = _transfer()
        t.approve("approver-1")
        with pytest.raises(AssetTransferNotAllowedError):
            t.ship("shipper-1")

    def test_requester_cannot_receive_own_transfer(self):
        t = _transfer()  # requested_by="requester-1"
        t.approve("approver-1")
        t.prepare()
        t.ship("shipper-1")
        with pytest.raises(SegregationOfDutiesError):
            t.receive("requester-1")

    def test_reject_only_before_shipping(self):
        t = _transfer()
        t.approve("approver-1")
        t.prepare()
        t.ship("shipper-1")
        with pytest.raises(AssetTransferNotAllowedError):
            t.reject("no longer needed")

    def test_cancel_terminal_state_fails(self):
        t = _transfer()
        t.approve("approver-1")
        t.prepare()
        t.ship("shipper-1")
        t.receive("receiver-1")
        with pytest.raises(AssetTransferNotAllowedError):
            t.cancel()

    def test_cancel_from_requested(self):
        t = _transfer()
        t.cancel("duplicated request")
        assert t.status is AssetTransferStatus.CANCELLED
