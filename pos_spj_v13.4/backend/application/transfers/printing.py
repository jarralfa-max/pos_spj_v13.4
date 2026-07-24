"""Authorized and audited transfer document printing orchestration."""
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from backend.application.transfers.authorization import TransferAuthorizationPolicy
from backend.application.transfers.permissions import TransferPermissions
from backend.shared.ids import new_uuid


class TransferDocumentType(str, Enum):
    TRANSFER = "TRANSFER"
    PICKING_LIST = "PICKING_LIST"
    SHIPMENT = "SHIPMENT"
    RECEIPT = "RECEIPT"
    PACKAGE_LABEL = "PACKAGE_LABEL"


@dataclass(frozen=True, slots=True)
class TransferPrintDocument:
    document_type: TransferDocumentType
    transfer_id: str
    reference: str
    title: str
    fields: tuple[tuple[str, str], ...]
    lines: tuple[tuple[str, ...], ...] = ()
    barcode_value: str | None = None
    qr_value: str | None = None

    def __post_init__(self) -> None:
        if not self.transfer_id or not self.reference or not self.title:
            raise ValueError("Transfer print document requires identity and title")


@dataclass(frozen=True, slots=True)
class TransferPrintArtifact:
    content: bytes
    media_type: str
    filename: str


@dataclass(frozen=True, slots=True)
class PrintTransferDocumentCommand:
    operation_id: str
    actor_user_id: str
    document: TransferPrintDocument
    printer_id: str
    copies: int = 1
    original_print_id: str | None = None
    reprint_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.operation_id or not self.actor_user_id or not self.printer_id:
            raise ValueError("Print command requires operation, actor, and printer")
        if self.copies < 1 or self.copies > 10:
            raise ValueError("Print copies must be between 1 and 10")
        if self.original_print_id and not (self.reprint_reason or "").strip():
            raise ValueError("A transfer reprint requires a reason")


class TransferDocumentRenderer(Protocol):
    def render(self, document: TransferPrintDocument) -> TransferPrintArtifact: ...


class TransfersPrintGateway(Protocol):
    def print(self, *, printer_id: str, artifact: TransferPrintArtifact,
              copies: int, operation_id: str) -> None: ...


class TransferPrintAuditRepository(Protocol):
    def print_id_for_operation(self, operation_id: str) -> str | None: ...
    def original_exists(self, print_id: str, transfer_id: str) -> bool: ...
    def record(self, *, print_id: str, command: PrintTransferDocumentCommand,
               artifact: TransferPrintArtifact, status: str) -> None: ...


class PrintTransferDocumentUseCase:
    def __init__(self, *, authorization: TransferAuthorizationPolicy,
                 renderers: dict[TransferDocumentType, TransferDocumentRenderer],
                 gateway: TransfersPrintGateway,
                 audit: TransferPrintAuditRepository) -> None:
        self._authorization = authorization
        self._renderers = renderers
        self._gateway = gateway
        self._audit = audit

    def execute(self, command: PrintTransferDocumentCommand) -> str:
        existing_print_id = self._audit.print_id_for_operation(command.operation_id)
        if existing_print_id is not None:
            return existing_print_id
        self._authorization.require(
            user_id=command.actor_user_id,
            permission_code=(TransferPermissions.REPRINT if command.original_print_id
                             else TransferPermissions.PRINT))
        if command.original_print_id and not self._audit.original_exists(
                command.original_print_id, command.document.transfer_id):
            raise ValueError("Original transfer print does not exist")
        renderer = self._renderers.get(command.document.document_type)
        if renderer is None:
            raise ValueError("No renderer configured for transfer document")
        artifact = renderer.render(command.document)
        print_id = new_uuid()
        try:
            self._gateway.print(printer_id=command.printer_id, artifact=artifact,
                                copies=command.copies, operation_id=command.operation_id)
        except Exception:
            self._audit.record(print_id=print_id, command=command, artifact=artifact,
                               status="FAILED")
            raise
        self._audit.record(print_id=print_id, command=command, artifact=artifact,
                           status="PRINTED")
        return print_id
