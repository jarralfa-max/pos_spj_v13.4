from datetime import date
from decimal import Decimal

import pytest

from backend.application.transfers.authorization import TransferAuthorizationPolicy
from backend.application.transfers.commands.transfer_request_commands import (
    ConfirmTransferReceiptCommand,
    ReceiveTransferLineCommand,
)
from backend.application.transfers.permissions import TransferPermissions
from backend.application.transfers.use_cases.transfer_receipt_use_cases import ConfirmTransferReceiptUseCase
from backend.domain.transfers.entities.stock_transfer import StockTransfer, StockTransferLine
from backend.domain.transfers.entities.transfer_shipment import TransferShipment, TransferShipmentLine
from backend.domain.transfers.enums import TransferNodeType, TransferStatus, TransferType
from backend.domain.transfers.exceptions import (
    DuplicateOperationError,
    SegregationOfDutiesError,
    TransferOverReceiptError,
    TransferReceiptNotAllowedError,
)
from backend.domain.transfers.policies.cold_chain_transfer_policy import (
    ColdChainTransferPolicy,
    ProductTransferProfile,
)
from backend.domain.transfers.value_objects.transfer_node import TransferNode


class TransferRepository:
    def __init__(self, transfer: StockTransfer) -> None:
        self.transfer = transfer

    def get(self, transfer_id: str) -> StockTransfer | None:
        return self.transfer if transfer_id == self.transfer.id else None

    def save(self, transfer: StockTransfer) -> None:
        self.transfer = transfer


class ReceiptRepository:
    def __init__(self) -> None:
        self.receipts = {}
        self.differences = {}
        self.operations = set()
        self.operation_records = []

    def save(self, receipt, differences) -> None:
        self.receipts[receipt.id] = receipt
        self.differences[receipt.id] = differences

    def operation_exists(self, operation_id: str) -> bool:
        return operation_id in self.operations

    def received_totals(self, shipment_id: str):
        totals = {}
        for receipt in self.receipts.values():
            if receipt.shipment_id != shipment_id:
                continue
            for line in receipt.lines:
                quantity, weight = totals.get(line.transfer_line_id, (Decimal("0"), Decimal("0")))
                totals[line.transfer_line_id] = (
                    quantity + line.observed_quantity, weight + line.observed_weight,
                )
        return totals

    def record_operation(self, **record) -> None:
        self.operations.add(record["operation_id"])
        self.operation_records.append(record)


class Permissions:
    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return user_id == "receiver" and permission_code in {
            TransferPermissions.RECEIVE,
            TransferPermissions.PARTIAL_RECEIVE,
        }


class InventoryGateway:
    def __init__(self) -> None:
        self.receipts = []

    def receive(self, **kwargs) -> None:
        self.receipts.append(kwargs)


class QrValidator:
    def __init__(self) -> None:
        self.calls = []

    def validate(self, **values) -> None:
        self.calls.append(values)


class EventSink:
    def __init__(self) -> None:
        self.events = []

    def collect(self, payload) -> None:
        self.events.append(payload)


class ProductProfiles:
    def __init__(self, *, quality_required=False):
        self.profile = ProductTransferProfile(
            "product", catch_weight=True, lot_required=True,
            quality_required=quality_required, temperature_required=True,
            minimum_temperature=Decimal("0"), maximum_temperature=Decimal("4"),
            temperature_warning_margin=Decimal("0.5"),
        )

    def get_transfer_profile(self, product_id):
        return self.profile


class QualityGateway:
    def __init__(self): self.requests = []
    def request_inspection(self, **values): self.requests.append(values)


class ShipmentRepository:
    def __init__(self, transfer_id: str, line_id: str) -> None:
        self.shipment = TransferShipment(
            transfer_id=transfer_id,
            shipment_number="SHP-001",
            dispatched_by_user_id="dispatcher",
            verified_by_user_id="verifier",
            lines=(TransferShipmentLine(line_id, Decimal("4"), Decimal("1180.450")),),
            id="shipment",
        )

    def get(self, shipment_id: str):
        return self.shipment if shipment_id == self.shipment.id else None


def _in_transit_transfer(*, cold_chain=False) -> tuple[StockTransfer, str]:
    line = StockTransferLine(
        product_id="product", unit_id="unit",
        requested_quantity=Decimal("4"), requested_weight=Decimal("1180.450"),
        pieces=Decimal("4"), lot_required=cold_chain,
        temperature_required=cold_chain,
    )
    transfer = StockTransfer(
        transfer_number="TRF-2026-001111",
        transfer_type=TransferType.BRANCH_TO_BRANCH,
        origin_node=TransferNode(TransferNodeType.WAREHOUSE, "branch-a", "warehouse-a"),
        destination_node=TransferNode(TransferNodeType.WAREHOUSE, "branch-b", "warehouse-b"),
        requested_by_user_id="requester", operation_id="create-operation", lines=[line],
        cold_chain_required=cold_chain,
    )
    transfer.submit()
    transfer.approve("approver")
    transfer.reserve()
    transfer.start_picking()
    transfer.record_pick({line.id: (Decimal("4"), Decimal("1180.450"))})
    transfer.ready_to_dispatch()
    transfer.record_dispatch({line.id: Decimal("4")}, {line.id: Decimal("1180.450")})
    return transfer, line.id


def _use_case(transfer, line_id, receipts, inventory, qr=None, events=None):
    return ConfirmTransferReceiptUseCase(
        TransferRepository(transfer), ShipmentRepository(transfer.id, line_id), receipts, inventory,
        TransferAuthorizationPolicy(Permissions()), qr, events,
    )


def test_total_receipt_validates_qr_posts_inventory_and_emits_received():
    transfer, line_id = _in_transit_transfer()
    receipts, inventory, qr, events = ReceiptRepository(), InventoryGateway(), QrValidator(), EventSink()

    result = _use_case(transfer, line_id, receipts, inventory, qr, events).execute(
        ConfirmTransferReceiptCommand(
            transfer.id, "shipment", "receiver", "receive-total",
            (ReceiveTransferLineCommand(line_id, Decimal("4"), Decimal("1180.450")),),
            qr_payload="TRFQR:shipment",
        )
    )

    assert result.transfer_status == TransferStatus.RECEIVED.value
    assert result.sync_status == "CONFIRMED"
    assert qr.calls == [{"payload": "TRFQR:shipment", "transfer_id": transfer.id,
                         "shipment_id": "shipment"}]
    assert inventory.receipts[0]["receipt"].id == result.receipt_id
    assert [event["event_name"] for event in events.events] == ["TRANSFER_RECEIVED"]


def test_partial_receipts_are_cumulative_and_offline_receipt_is_pending_sync():
    transfer, line_id = _in_transit_transfer()
    receipts, inventory = ReceiptRepository(), InventoryGateway()
    use_case = _use_case(transfer, line_id, receipts, inventory)

    first = use_case.execute(ConfirmTransferReceiptCommand(
        transfer.id, "shipment", "receiver", "receive-partial",
        (ReceiveTransferLineCommand(line_id, Decimal("2"), Decimal("590.225")),),
        offline=True, device_id="device", local_sequence=1,
    ))
    second = use_case.execute(ConfirmTransferReceiptCommand(
        transfer.id, "shipment", "receiver", "receive-final",
        (ReceiveTransferLineCommand(line_id, Decimal("2"), Decimal("590.225")),),
    ))

    assert first.transfer_status == TransferStatus.PARTIALLY_RECEIVED.value
    assert first.sync_status == "PENDING"
    assert receipts.operation_records[0]["local_sequence"] == 1
    assert second.transfer_status == TransferStatus.RECEIVED.value
    assert transfer.lines[0].received_quantity == Decimal("4")
    assert len(inventory.receipts) == 2


def test_receipt_rejects_duplicate_operation_invalid_offline_metadata_and_float():
    transfer, line_id = _in_transit_transfer()
    receipts = ReceiptRepository()
    receipts.operations.add("duplicate")
    use_case = _use_case(transfer, line_id, receipts, InventoryGateway())

    with pytest.raises(DuplicateOperationError):
        use_case.execute(ConfirmTransferReceiptCommand(
            transfer.id, "shipment", "receiver", "duplicate",
            (ReceiveTransferLineCommand(line_id, Decimal("4"), Decimal("1180.450")),),
        ))
    with pytest.raises(ValueError, match="Offline receipt"):
        use_case.execute(ConfirmTransferReceiptCommand(
            transfer.id, "shipment", "receiver", "offline-invalid",
            (ReceiveTransferLineCommand(line_id, Decimal("4"), Decimal("1180.450")),),
            offline=True,
        ))
    with pytest.raises(TypeError, match="must use Decimal"):
        use_case.execute(ConfirmTransferReceiptCommand(
            transfer.id, "shipment", "receiver", "float-invalid",
            (ReceiveTransferLineCommand(line_id, 4.0, Decimal("1180.450")),),
        ))


def test_receipt_enforces_shipment_balance_and_dispatcher_receiver_segregation():
    transfer, line_id = _in_transit_transfer()
    use_case = _use_case(transfer, line_id, ReceiptRepository(), InventoryGateway())

    with pytest.raises(TransferOverReceiptError, match="shipment balance"):
        use_case.execute(ConfirmTransferReceiptCommand(
            transfer.id, "shipment", "receiver", "over-shipment",
            (ReceiveTransferLineCommand(line_id, Decimal("5"), Decimal("1180.450")),),
        ))
    with pytest.raises(SegregationOfDutiesError):
        use_case.execute(ConfirmTransferReceiptCommand(
            transfer.id, "shipment", "dispatcher", "same-operator",
            (ReceiveTransferLineCommand(line_id, Decimal("4"), Decimal("1180.450")),),
        ))


def test_catch_weight_receipt_preserves_pieces_weight_lot_temperature_and_expiry():
    transfer, line_id = _in_transit_transfer(cold_chain=True)
    receipts, inventory, quality = ReceiptRepository(), InventoryGateway(), QualityGateway()
    use_case = ConfirmTransferReceiptUseCase(
        TransferRepository(transfer), ShipmentRepository(transfer.id, line_id),
        receipts, inventory, TransferAuthorizationPolicy(Permissions()),
        product_profiles=ProductProfiles(),
        cold_chain_policy=ColdChainTransferPolicy(), quality_gateway=quality,
        today_provider=lambda: date(2026, 7, 24),
    )
    result = use_case.execute(ConfirmTransferReceiptCommand(
        transfer.id, "shipment", "receiver", "receive-meat", (
            ReceiveTransferLineCommand(
                line_id, Decimal("4"), Decimal("1180.450"), lot_id="lot-meat",
                observed_pieces=Decimal("4"), temperature=Decimal("2.1"),
                expires_on="2026-07-30"),)))

    line = result.lines[0]
    assert (line.observed_pieces, line.observed_weight) == (Decimal("4"), Decimal("1180.450"))
    assert line.temperature == Decimal("2.1")
    assert line.cold_chain_status == "COMPLIANT"
    assert line.quality_status == "AVAILABLE"
    assert quality.requests == []
    assert inventory.receipts[0]["receipt"].lines[0].lot_id == "lot-meat"


def test_expired_meat_is_quarantined_and_sent_to_quality():
    transfer, line_id = _in_transit_transfer(cold_chain=True)
    quality = QualityGateway()
    use_case = ConfirmTransferReceiptUseCase(
        TransferRepository(transfer), ShipmentRepository(transfer.id, line_id),
        ReceiptRepository(), InventoryGateway(), TransferAuthorizationPolicy(Permissions()),
        product_profiles=ProductProfiles(), cold_chain_policy=ColdChainTransferPolicy(),
        quality_gateway=quality, today_provider=lambda: date(2026, 7, 24),
    )
    result = use_case.execute(ConfirmTransferReceiptCommand(
        transfer.id, "shipment", "receiver", "receive-expired", (
            ReceiveTransferLineCommand(
                line_id, "4", "1180.450", lot_id="expired-lot", observed_pieces="4",
                temperature="8", expires_on="2026-07-23"),)))

    assert result.lines[0].cold_chain_status == "BLOCKED"
    assert result.lines[0].quality_status == "QUARANTINED"
    assert quality.requests[0]["reason"] == "EXPIRED"
    assert quality.requests[0]["lot_id"] == "expired-lot"


def test_cold_chain_policy_handles_warning_out_of_range_and_mandatory_quality():
    policy = ColdChainTransferPolicy()
    profile = ProductProfiles().profile
    warning = policy.evaluate(profile=profile, temperature="0.4", expires_on="2026-07-30",
                              observed_on=date(2026, 7, 24))
    blocked = policy.evaluate(profile=profile, temperature="8", expires_on="2026-07-30",
                              observed_on=date(2026, 7, 24))
    pending = policy.evaluate(profile=ProductProfiles(quality_required=True).profile,
                              temperature="2", expires_on="2026-07-30",
                              observed_on=date(2026, 7, 24))
    assert (warning.cold_chain_status.value, warning.quality_status.value) == ("WARNING", "AVAILABLE")
    assert (blocked.cold_chain_status.value, blocked.quality_status.value) == (
        "OUT_OF_RANGE", "QUARANTINED")
    assert (pending.cold_chain_status.value, pending.quality_status.value) == (
        "PENDING_QUALITY", "PENDING_INSPECTION")


def test_catch_weight_receipt_requires_integral_pieces_weight_lot_and_decimal_temperature():
    transfer, line_id = _in_transit_transfer(cold_chain=True)
    use_case = ConfirmTransferReceiptUseCase(
        TransferRepository(transfer), ShipmentRepository(transfer.id, line_id),
        ReceiptRepository(), InventoryGateway(), TransferAuthorizationPolicy(Permissions()),
        product_profiles=ProductProfiles(), cold_chain_policy=ColdChainTransferPolicy(),
        quality_gateway=QualityGateway(), today_provider=lambda: date(2026, 7, 24),
    )
    with pytest.raises(TransferReceiptNotAllowedError, match="lot"):
        use_case.execute(ConfirmTransferReceiptCommand(
            transfer.id, "shipment", "receiver", "missing-lot", (
                ReceiveTransferLineCommand(line_id, "4", "1180.450", observed_pieces="4",
                                           temperature="2"),)))
    with pytest.raises(TypeError, match="Decimal"):
        use_case.execute(ConfirmTransferReceiptCommand(
            transfer.id, "shipment", "receiver", "float-temperature", (
                ReceiveTransferLineCommand(line_id, "4", "1180.450", lot_id="lot",
                                           observed_pieces="4", temperature=2.0),)))
