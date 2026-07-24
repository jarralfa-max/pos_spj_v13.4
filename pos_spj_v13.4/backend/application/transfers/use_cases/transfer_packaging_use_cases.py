"""TRF-9 package, seal, tare, and label use cases."""
from __future__ import annotations

from typing import Protocol

from backend.domain.transfers.entities.transfer_package import TransferPackage
from backend.domain.transfers.enums import TransferStatus
from backend.domain.transfers.exceptions import DuplicateOperationError, TransferInvalidStatusError, TransferNotFoundError
from backend.domain.transfers.repository_ports import StockTransferRepository, TransferPackageRepository
from ..authorization import TransferAuthorizationPolicy
from ..commands.transfer_request_commands import CreateTransferPackageCommand
from ..dto.package_dto import TransferPackageDTO
from ..permissions import TransferPermissions


class TransferPackageLabelGateway(Protocol):
    def create_package_label(self, *, package: TransferPackage) -> str: ...


def _dto(package: TransferPackage) -> TransferPackageDTO:
    return TransferPackageDTO(
        package_id=package.id,
        transfer_id=package.transfer_id,
        package_number=package.package_number,
        package_type=package.package_type,
        gross_weight=package.weight,
        tare=package.tare,
        net_weight=package.net_weight,
        seal_number=package.seal_number,
        temperature=package.temperature,
        label_id=package.label_id,
        line_ids=package.line_ids,
        status=package.status,
    )


class CreateTransferPackageUseCase:
    def __init__(
        self,
        transfer_repository: StockTransferRepository,
        package_repository: TransferPackageRepository,
        authorization: TransferAuthorizationPolicy,
        label_gateway: TransferPackageLabelGateway | None = None,
    ) -> None:
        self._transfer_repository = transfer_repository
        self._package_repository = package_repository
        self._authorization = authorization
        self._label_gateway = label_gateway

    def execute(self, command: CreateTransferPackageCommand) -> TransferPackageDTO:
        if self._package_repository.operation_exists(command.operation_id):
            raise DuplicateOperationError("Transfer package operation was already applied")
        transfer = self._transfer_repository.get(command.transfer_id)
        if transfer is None:
            raise TransferNotFoundError("Transfer not found")
        self._authorization.require(
            user_id=command.packed_by_user_id,
            permission_code=TransferPermissions.DISPATCH,
            branch_id=transfer.origin_node.branch_id,
            warehouse_id=transfer.origin_node.warehouse_id,
            location_id=transfer.origin_node.location_id,
        )
        if transfer.status not in (TransferStatus.PICKED, TransferStatus.PARTIALLY_PICKED, TransferStatus.READY_TO_DISPATCH):
            raise TransferInvalidStatusError("Packaging requires picked transfer lines")
        transfer_line_ids = {line.id for line in transfer.lines}
        if not set(command.line_ids).issubset(transfer_line_ids):
            raise ValueError("Package references transfer lines outside this transfer")
        package = TransferPackage(
            transfer_id=transfer.id,
            package_number=command.package_number,
            package_type=command.package_type,
            weight=command.weight,
            tare=command.tare,
            line_ids=command.line_ids,
            seal_number=command.seal_number,
            temperature=command.temperature,
        )
        if command.print_label:
            if self._label_gateway is None:
                raise ValueError("Package label printing requires a label gateway")
            label_id = self._label_gateway.create_package_label(package=package)
            package = TransferPackage(
                transfer_id=package.transfer_id,
                package_number=package.package_number,
                package_type=package.package_type,
                weight=package.weight,
                tare=package.tare,
                line_ids=package.line_ids,
                seal_number=package.seal_number,
                temperature=package.temperature,
                label_id=label_id,
                status=package.status,
                id=package.id,
            )
        self._package_repository.save(package)
        self._package_repository.record_operation(
            package_id=package.id,
            transfer_id=transfer.id,
            operation_id=command.operation_id,
            operation_type="TRANSFER_PACKAGE_CREATE",
        )
        return _dto(package)
