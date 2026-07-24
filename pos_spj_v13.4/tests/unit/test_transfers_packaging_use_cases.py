from decimal import Decimal

import pytest

from backend.application.transfers.authorization import TransferAuthorizationPolicy
from backend.application.transfers.commands.transfer_request_commands import (
    ApproveTransferRequestCommand,
    ConfirmTransferPickingCommand,
    CreateTransferPackageCommand,
    CreateTransferRequestCommand,
    ReserveTransferInventoryCommand,
    StartTransferPickingCommand,
    SubmitTransferRequestCommand,
    TransferPickLineCommand,
    TransferRequestLineCommand,
)
from backend.application.transfers.permissions import TransferPermissions
from backend.application.transfers.use_cases.transfer_packaging_use_cases import CreateTransferPackageUseCase
from backend.application.transfers.use_cases.transfer_picking_use_cases import (
    ConfirmTransferPickingUseCase,
    StartTransferPickingUseCase,
)
from backend.application.transfers.use_cases.transfer_request_use_cases import (
    ApproveTransferRequestUseCase,
    CreateTransferRequestUseCase,
    SubmitTransferRequestUseCase,
)
from backend.application.transfers.use_cases.transfer_reservation_use_cases import ReserveTransferInventoryUseCase
from backend.domain.transfers.entities.stock_transfer import StockTransfer
from backend.domain.transfers.entities.transfer_package import TransferPackage
from backend.domain.transfers.enums import TransferNodeType, TransferType
from backend.domain.transfers.exceptions import DuplicateOperationError
from backend.domain.transfers.value_objects.transfer_node import TransferNode


class TransferRepository:
    def __init__(self) -> None:
        self.saved: dict[str, StockTransfer] = {}
        self.operations: set[str] = set()

    def get(self, transfer_id: str) -> StockTransfer | None:
        return self.saved.get(transfer_id)

    def save(self, transfer: StockTransfer) -> None:
        self.saved[transfer.id] = transfer

    def operation_exists(self, operation_id: str) -> bool:
        return operation_id in self.operations

    def record_operation(self, *, transfer_id: str, operation_id: str, operation_type: str) -> None:
        assert transfer_id in self.saved
        self.operations.add(operation_id)


class PackageRepository:
    def __init__(self) -> None:
        self.saved: dict[str, TransferPackage] = {}
        self.operations: set[str] = set()

    def save(self, package: TransferPackage) -> None:
        self.saved[package.id] = package

    def operation_exists(self, operation_id: str) -> bool:
        return operation_id in self.operations

    def record_operation(self, *, package_id: str, transfer_id: str,
                         operation_id: str, operation_type: str) -> None:
        assert package_id in self.saved
        assert operation_type == "TRANSFER_PACKAGE_CREATE"
        self.operations.add(operation_id)


class NumberGenerator:
    def next_transfer_number(self) -> str:
        return "TRF-2026-001000"


class Permissions:
    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return (user_id, permission_code) in {
            ("requester", TransferPermissions.REQUEST_CREATE),
            ("requester", TransferPermissions.REQUEST_SUBMIT),
            ("approver", TransferPermissions.APPROVE),
            ("warehouse", TransferPermissions.RESERVE),
            ("picker", TransferPermissions.PICK),
            ("picker", TransferPermissions.PICK_CONFIRM),
            ("packer", TransferPermissions.DISPATCH),
        }


class InventoryGateway:
    def reserve(self, **kwargs) -> None:
        self.kwargs = kwargs


class LabelGateway:
    def create_package_label(self, *, package: TransferPackage) -> str:
        assert package.seal_number == "seal-1"
        return "label-1"


def _node(branch: str, warehouse: str) -> TransferNode:
    return TransferNode(TransferNodeType.WAREHOUSE, branch, warehouse)


def _auth() -> TransferAuthorizationPolicy:
    return TransferAuthorizationPolicy(Permissions())


def _picked_transfer(repository: TransferRepository) -> tuple[str, str]:
    created = CreateTransferRequestUseCase(repository, _auth(), NumberGenerator()).execute(
        CreateTransferRequestCommand(
            "requester",
            "operation-create",
            TransferType.BRANCH_TO_BRANCH,
            _node("branch-a", "warehouse-a"),
            _node("branch-b", "warehouse-b"),
            (TransferRequestLineCommand("product", "unit", Decimal("4"), Decimal("1180.450")),),
        )
    )
    SubmitTransferRequestUseCase(repository, _auth()).execute(
        SubmitTransferRequestCommand(created.transfer_id, "requester", "operation-submit"))
    ApproveTransferRequestUseCase(repository, _auth()).execute(
        ApproveTransferRequestCommand(created.transfer_id, "approver", "operation-approve"))
    ReserveTransferInventoryUseCase(repository, InventoryGateway(), _auth()).execute(
        ReserveTransferInventoryCommand(created.transfer_id, "warehouse", "operation-reserve"))
    line_id = repository.get(created.transfer_id).lines[0].id
    StartTransferPickingUseCase(repository, _auth()).execute(
        StartTransferPickingCommand(created.transfer_id, "picker", "operation-picking-start"))
    ConfirmTransferPickingUseCase(repository, _auth()).execute(
        ConfirmTransferPickingCommand(
            created.transfer_id,
            "picker",
            "operation-pick-full",
            (TransferPickLineCommand(line_id, Decimal("4"), Decimal("1180.450"), "barcode", None, "loc-1"),),
        ))
    return created.transfer_id, line_id


def test_create_transfer_package_records_seal_tare_net_weight_and_label():
    transfer_repository = TransferRepository()
    package_repository = PackageRepository()
    transfer_id, line_id = _picked_transfer(transfer_repository)

    dto = CreateTransferPackageUseCase(
        transfer_repository,
        package_repository,
        _auth(),
        LabelGateway(),
    ).execute(CreateTransferPackageCommand(
        transfer_id,
        "packer",
        "operation-package",
        "PKG-001",
        "BOX",
        Decimal("1200.000"),
        Decimal("19.550"),
        (line_id,),
        seal_number="seal-1",
        temperature=Decimal("2.5"),
    ))

    assert dto.package_number == "PKG-001"
    assert dto.seal_number == "seal-1"
    assert dto.net_weight == Decimal("1180.450")
    assert dto.label_id == "label-1"
    assert "operation-package" in package_repository.operations


def test_transfer_package_rejects_float_weight_and_duplicate_operation():
    with pytest.raises(TypeError):
        TransferPackage("transfer", "PKG-001", "BOX", 1.2, Decimal("0"), ("line",))

    transfer_repository = TransferRepository()
    package_repository = PackageRepository()
    transfer_id, line_id = _picked_transfer(transfer_repository)
    package_repository.operations.add("operation-package")
    with pytest.raises(DuplicateOperationError):
        CreateTransferPackageUseCase(transfer_repository, package_repository, _auth()).execute(
            CreateTransferPackageCommand(
                transfer_id,
                "packer",
                "operation-package",
                "PKG-001",
                "BOX",
                Decimal("1200.000"),
                Decimal("19.550"),
                (line_id,),
                print_label=False,
            ))


def test_transfer_package_rejects_lines_outside_transfer():
    transfer_repository = TransferRepository()
    package_repository = PackageRepository()
    transfer_id, _line_id = _picked_transfer(transfer_repository)

    with pytest.raises(ValueError):
        CreateTransferPackageUseCase(transfer_repository, package_repository, _auth()).execute(
            CreateTransferPackageCommand(
                transfer_id,
                "packer",
                "operation-package",
                "PKG-001",
                "BOX",
                Decimal("1200.000"),
                Decimal("19.550"),
                ("outside-line",),
                print_label=False,
            ))
