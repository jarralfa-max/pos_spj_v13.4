from decimal import Decimal

import pytest

from backend.application.transfers.authorization import TransferAuthorizationPolicy
from backend.application.transfers.commands.transfer_request_commands import (
    DetectTransferDifferenceCommand,
    ResolveTransferDifferenceCommand,
    ReviewTransferDifferenceCommand,
)
from backend.application.transfers.permissions import TransferPermissions
from backend.application.transfers.use_cases.transfer_difference_use_cases import (
    DetectTransferDifferencesUseCase,
    ResolveTransferDifferenceUseCase,
    ReviewTransferDifferenceUseCase,
)
from backend.domain.transfers.entities.stock_transfer import StockTransfer, StockTransferLine
from backend.domain.transfers.enums import (
    DifferenceResolutionType,
    DifferenceStatus,
    DifferenceType,
    TransferNodeType,
    TransferType,
)
from backend.domain.transfers.exceptions import (
    SegregationOfDutiesError,
    TransferDifferenceReviewRequiredError,
)
from backend.domain.transfers.policies.transfer_difference_policy import TransferDifferencePolicy
from backend.domain.transfers.value_objects.transfer_node import TransferNode


class Transfers:
    def __init__(self, transfer): self.transfer = transfer
    def get(self, transfer_id): return self.transfer if transfer_id == self.transfer.id else None
    def save(self, transfer): self.transfer = transfer


class Differences:
    def __init__(self):
        self.items, self.transfer_ids, self.resolutions, self.operations = {}, {}, {}, set()
    def get(self, difference_id): return self.items.get(difference_id)
    def belongs_to_transfer(self, difference_id, transfer_id):
        return self.transfer_ids.get(difference_id) == transfer_id
    def save_all(self, transfer_id, differences):
        for difference in differences:
            self.items[difference.id] = difference
            self.transfer_ids[difference.id] = transfer_id
    def save_resolution(self, difference, resolution):
        self.items[difference.id] = difference
        self.resolutions[resolution.id] = resolution
    def operation_exists(self, operation_id): return operation_id in self.operations
    def record_operation(self, **values): self.operations.add(values["operation_id"])


class Permissions:
    def has_permission(self, user_id, permission_code):
        return (user_id, permission_code) in {
            ("detector", TransferPermissions.DIFFERENCE_REVIEW),
            ("reviewer", TransferPermissions.DIFFERENCE_REVIEW),
            ("resolver", TransferPermissions.DIFFERENCE_RESOLVE),
            ("resolver", TransferPermissions.DIFFERENCE_ACCEPT),
            ("detector", TransferPermissions.DIFFERENCE_RESOLVE),
        }


class Events:
    def __init__(self): self.items = []
    def collect(self, event): self.items.append(event)


def _received_transfer():
    line = StockTransferLine("product", "unit", Decimal("4"), Decimal("100"))
    transfer = StockTransfer(
        "TRF-DIFF", TransferType.BRANCH_TO_BRANCH,
        TransferNode(TransferNodeType.WAREHOUSE, "origin", "origin-wh"),
        TransferNode(TransferNodeType.WAREHOUSE, "destination", "destination-wh"),
        "requester", "create", [line],
    )
    transfer.submit(); transfer.approve("approver"); transfer.reserve(); transfer.start_picking()
    transfer.record_pick({line.id: (Decimal("4"), Decimal("100"))})
    transfer.ready_to_dispatch(); transfer.record_dispatch({line.id: Decimal("4")}, {line.id: Decimal("100")})
    from backend.domain.transfers.entities.stock_transfer import TransferReceipt, TransferReceiptLine
    transfer.receive(TransferReceipt("shipment", "receiver", (
        TransferReceiptLine(line.id, Decimal("4"), Decimal("100")),), "receive"))
    return transfer, line.id


def test_tolerances_classify_quantity_and_weight_only_outside_configured_boundaries():
    policy = TransferDifferencePolicy(quantity_tolerance=Decimal("0.5"),
                                      weight_tolerance=Decimal("1.0"),
                                      temperature_tolerance=Decimal("0.05"))
    assert policy.classify(expected_quantity="4", actual_quantity="3.5",
                           expected_weight="100", actual_weight="99") == ()
    assert policy.classify(expected_quantity="4", actual_quantity="3",
                           expected_weight="100", actual_weight="98") == (
        DifferenceType.SHORT_QUANTITY, DifferenceType.WEIGHT_VARIANCE)
    assert policy.temperature_outside_tolerance(expected="2", actual="2.1") is True
    with pytest.raises(TypeError):
        TransferDifferencePolicy(quantity_tolerance=0.5, weight_tolerance=Decimal("1"),
                                 temperature_tolerance=Decimal("0.5"))


def test_detection_preserves_evidence_and_requires_review_before_resolution():
    transfer, line_id = _received_transfer()
    transfers, differences, events = Transfers(transfer), Differences(), Events()
    auth = TransferAuthorizationPolicy(Permissions())
    detected = DetectTransferDifferencesUseCase(
        transfers, differences, auth,
        TransferDifferencePolicy(quantity_tolerance="0", weight_tolerance="0.5",
                                 temperature_tolerance="0.5"), events,
    ).execute(DetectTransferDifferenceCommand(
        transfer.id, line_id, "detector", "detect", Decimal("4"), Decimal("3"),
        Decimal("100"), Decimal("98"), severity="DANGER",
        responsible_stage="IN_TRANSIT", evidence=("photo://evidence-1", "seal://broken"),
    ))
    assert {item.difference_type for item in detected} == {"SHORT_QUANTITY", "WEIGHT_VARIANCE"}
    assert all(item.evidence == ("photo://evidence-1", "seal://broken") for item in detected)
    assert transfer.status.value == "WITH_DIFFERENCES"
    assert events.items[0]["event_name"] == "TRANSFER_DIFFERENCE_DETECTED"

    with pytest.raises(TransferDifferenceReviewRequiredError):
        ResolveTransferDifferenceUseCase(transfers, differences, auth).execute(
            ResolveTransferDifferenceCommand(
                transfer.id, detected[0].difference_id, "resolver", "resolve-too-soon",
                DifferenceResolutionType.CREATE_CARRIER_CLAIM, "Carrier investigation"))
    reviewed = ReviewTransferDifferenceUseCase(transfers, differences, auth).execute(
        ReviewTransferDifferenceCommand(
            transfer.id, detected[0].difference_id, "reviewer", "review"))
    assert reviewed.status == DifferenceStatus.PENDING_REVIEW.value
    resolved = ResolveTransferDifferenceUseCase(transfers, differences, auth, events).execute(
        ResolveTransferDifferenceCommand(
            transfer.id, detected[0].difference_id, "resolver", "resolve",
            DifferenceResolutionType.CREATE_CARRIER_CLAIM, "Claim with carrier",
            ("claim://001",)))
    assert resolved.difference_status == DifferenceStatus.RESOLVED.value
    assert resolved.evidence == ("claim://001",)
    assert transfer.status.value == "PENDING_RESOLUTION"
    assert events.items[-1]["event_name"] == "TRANSFER_DIFFERENCE_RESOLVED"


def test_explicit_types_and_critical_resolution_segregation_are_enforced():
    transfer, line_id = _received_transfer()
    transfers, differences = Transfers(transfer), Differences()
    auth = TransferAuthorizationPolicy(Permissions())
    result = DetectTransferDifferencesUseCase(
        transfers, differences, auth,
        TransferDifferencePolicy(quantity_tolerance="0", weight_tolerance="0",
                                 temperature_tolerance="0.5"),
    ).execute(DetectTransferDifferenceCommand(
        transfer.id, line_id, "detector", "detect-critical", "4", "4", "100", "100",
        reported_type=DifferenceType.SEAL_BROKEN, severity="CRITICAL",
        evidence=("photo://seal",),
    ))[0]
    ReviewTransferDifferenceUseCase(transfers, differences, auth).execute(
        ReviewTransferDifferenceCommand(transfer.id, result.difference_id, "reviewer", "review-critical"))
    with pytest.raises(SegregationOfDutiesError):
        ResolveTransferDifferenceUseCase(transfers, differences, auth).execute(
            ResolveTransferDifferenceCommand(
                transfer.id, result.difference_id, "detector", "resolve-critical",
                DifferenceResolutionType.CREATE_CARRIER_CLAIM, "Self resolution forbidden"))
